# Video Generation Implementation Plan

**Date:** 2026-04-05  
**Spec:** `docs/superpowers/specs/2026-04-05-video-generation-design.md`  
**Status:** Ready to implement

## Overview

Add video generation to the agent orchestrator using OpenRouter's async video alpha API. Two video models (Veo 3.1 + Wan 2.6), fire-and-forget submission with client polling, video-script pipeline, and Web UI.

## Implementation Steps

### Step 1: Update Data Models

**File:** `src/models.py`

1. Add `video: bool = False` to `AgentConfig`
2. Add optional fields to `AgentConfig`: `default_duration: int | None = None`, `default_resolution: str | None = None`, `default_aspect_ratio: str | None = None`
3. Add `video: bool` to `AgentInfo` (copy from AgentConfig during serialization)
4. Add new request/response models:
   - `VideoGenRequest` (prompt, duration, resolution, aspect_ratio, generate_audio, input_references)
   - `VideoGenResponse` (job_id, status, agent_id, model)
   - `VideoStatusResponse` (job_id, status, agent_id, model, prompt, video_url, error, cost, created_at)
   - `VideoPipelineRequest` (prompt, video_agent, skip_refinement, duration, resolution, aspect_ratio, generate_audio)
   - `VideoPipelineResponse` (job_id, status, refined_prompt, video_agent, model)

### Step 2: Add Video Agents to YAML

**File:** `config/agents.yaml`

Add two new agents at the end:

```yaml
veo-3:
  name: "Veo 3.1"
  description: "Generate high-quality videos up to 4K with audio (Google Veo 3.1)"
  model: "google/veo-3.1"
  system_prompt: ""
  video: true
  default_duration: 4
  default_resolution: "1080p"
  default_aspect_ratio: "16:9"

wan-video:
  name: "Wan 2.6"
  description: "Generate budget-friendly videos with flexible aspect ratios (Alibaba Wan 2.6)"
  model: "alibaba/wan-2.6"
  system_prompt: ""
  video: true
  default_duration: 5
  default_resolution: "720p"
  default_aspect_ratio: "16:9"
```

### Step 3: Create Video Client Module

**File:** `src/video_client.py` (new)

Create a new module parallel to `openrouter_client.py` for OpenRouter's video alpha API:

1. **Constants:**
   - `BASE_URL = "https://openrouter.ai/api/alpha/videos"`
   - `VIDEO_DIR = Path("generated_video")`

2. **VideoClient class:**
   - `__init__(api_key: str)`
   - `submit(model: str, prompt: str, **params) -> dict` — POST to /api/alpha/videos, returns {id, polling_url, status}
   - `poll(job_id: str) -> dict` — GET /api/alpha/videos/{job_id}, returns full status object
   - `download(job_id: str) -> str` — GET /api/alpha/videos/{job_id}/content, saves MP4 to `generated_video/{uuid}.mp4`, returns filename
   - `list_models() -> dict` — GET /api/alpha/videos/models (for future use)

3. **Error handling:**
   - Wrap all HTTP calls in try/except
   - Use extended timeout (60s) for download operations
   - Return error messages in dict format compatible with VideoStatusResponse

### Step 4: Update Routes with Video Endpoints

**File:** `src/routes.py`

1. **Add in-memory job tracker:**
   ```python
   from dataclasses import dataclass, field
   from datetime import datetime
   
   @dataclass
   class VideoJob:
       job_id: str
       agent_id: str
       model: str
       prompt: str
       status: str
       video_url: str | None = None
       error: str | None = None
       cost: float | None = None
       created_at: datetime = field(default_factory=datetime.now)
   
   video_jobs: dict[str, VideoJob] = {}
   ```

2. **Add 4 new endpoints:**

   **POST /agents/{agent_id}/generate-video**
   - Validate agent exists and has `video: true`
   - Merge agent defaults with request params
   - Call `video_client.submit()`
   - Create VideoJob in tracker
   - Return HTTP 202 with VideoGenResponse

   **GET /videos/{job_id}**
   - Look up job in tracker
   - If terminal state with cached video_url → return from tracker (no API call)
   - Otherwise → call `video_client.poll()`, update tracker
   - If newly completed → call `video_client.download()`, update tracker.video_url
   - Return VideoStatusResponse

   **GET /videos**
   - Return all jobs from tracker as list[VideoStatusResponse]
   - No API calls

   **POST /pipelines/video**
   - Validate video_agent exists and has `video: true`
   - If `skip_refinement` is False:
     - Call `openrouter_client.complete()` with video-creator agent and user prompt
     - Extract refined prompt from response
   - Call `video_client.submit()` with refined or original prompt
   - Create VideoJob in tracker
   - Return HTTP 202 with VideoPipelineResponse (include refined_prompt)

### Step 5: Initialize Video Client in Main

**File:** `src/main.py`

1. **Import VideoClient:**
   ```python
   from .video_client import VideoClient, VIDEO_DIR
   ```

2. **In lifespan context:**
   - Create `VideoClient(settings.openrouter_api_key)` and store on `app.state.video_client`

3. **After app creation:**
   ```python
   VIDEO_DIR.mkdir(exist_ok=True)
   app.mount("/video", StaticFiles(directory=str(VIDEO_DIR)), name="video")
   ```

### Step 6: Update .gitignore

**File:** `.gitignore`

Add:
```
generated_video/
```

### Step 7: Add Video Tab to Web UI

**File:** `static/index.html`

1. **Add tab navigation:**
   - New "Video" tab alongside Chat and Dashboard

2. **Video tab content:**
   
   **Generation Form:**
   - Agent dropdown (populate from `/agents`, filter by `video: true`)
   - Prompt textarea
   - Optional settings row:
     - Duration dropdown (3-10s, model-dependent)
     - Resolution dropdown (480p, 720p, 1080p, 4K)
     - Aspect ratio dropdown (16:9, 9:16, 1:1)
     - Generate audio checkbox
   - "Skip prompt refinement" checkbox
   - "Generate Video" button → calls `/pipelines/video` (or `/agents/{id}/generate-video` if skip_refinement checked)

   **Job Cards Section:**
   - Container for video job cards
   - Each card shows: agent name, model, prompt (expandable), status badge, elapsed time
   - When pipeline is used: show refined prompt once available
   - On completion: expand to show `<video>` player with `/video/{file}.mp4` URL + download button

3. **Smart Polling Logic:**
   ```javascript
   const INITIAL_DELAY = 30000;  // 30s
   const POLL_INTERVAL = 15000;  // 15s
   
   function startPolling(jobId) {
       setTimeout(() => {
           const interval = setInterval(async () => {
               if (document.hidden) return;  // Pause when tab hidden
               const status = await fetch(`/videos/${jobId}`).then(r => r.json());
               updateJobCard(jobId, status);
               if (['completed', 'failed', 'cancelled', 'expired'].includes(status.status)) {
                   clearInterval(interval);
               }
           }, POLL_INTERVAL);
       }, INITIAL_DELAY);
   }
   ```

4. **Style:**
   - Match existing dark theme
   - Responsive layout
   - Status badges: yellow (pending), blue (in_progress), green (completed), red (failed)

### Step 8: Update Agent Registry Logic

**File:** `src/agent_registry.py`

In `load_agents()`, when building `AgentConfig` from YAML:
- Copy `video` field (default False)
- Copy `default_duration`, `default_resolution`, `default_aspect_ratio` if present

In the `/agents` endpoint (routes.py), when building `AgentInfo`:
- Include `video` field from `AgentConfig`

## Testing Checklist

Manual testing via curl and browser (no test suite in project):

1. **Agent registration:**
   - [ ] GET `/agents` returns veo-3 and wan-video with `video: true`
   - [ ] Video agents excluded from chat dropdown in UI

2. **Direct video generation:**
   - [ ] POST `/agents/veo-3/generate-video` with minimal prompt returns job_id
   - [ ] GET `/videos/{job_id}` polls and shows status progression
   - [ ] First poll after completion triggers download and returns local video URL
   - [ ] Subsequent polls return instantly from cache
   - [ ] MP4 file exists in `generated_video/`
   - [ ] Video plays at `/video/{file}.mp4`

3. **Pipeline:**
   - [ ] POST `/pipelines/video` with prompt triggers video-creator refinement
   - [ ] Response includes refined_prompt
   - [ ] Video generates with refined prompt
   - [ ] `skip_refinement: true` bypasses video-creator step

4. **UI:**
   - [ ] Video tab shows agent dropdown populated with video agents
   - [ ] Submit button creates job card
   - [ ] Job card shows status progression (30s silence, then 15s polls)
   - [ ] Polling pauses when tab is hidden
   - [ ] On completion, video player appears in card
   - [ ] Video plays inline
   - [ ] Download button works

5. **Error cases:**
   - [ ] Invalid agent_id returns 404
   - [ ] Non-video agent returns 400
   - [ ] Failed generation shows error in job card
   - [ ] Download failure shows error but job remains accessible

## Rollback Plan

If OpenRouter API issues arise:
1. Comment out video endpoints in routes.py
2. Hide Video tab in UI
3. Keep code in place for when API stabilizes

Video generation is isolated — no impact on existing chat/audio features.

## Post-Implementation

1. Update SESSION-STATE.md to mark implementation complete
2. Test with both veo-3 and wan-video agents
3. Verify costs are tracked correctly via OpenRouter usage API
4. Consider adding more video models to agents.yaml (Sora 2, Seedance) when available
