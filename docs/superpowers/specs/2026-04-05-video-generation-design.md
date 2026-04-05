# Video Generation via OpenRouter Alpha API

**Date:** 2026-04-05
**Status:** Draft
**Source:** https://openrouter.notion.site/video-generation-testing

## Overview

Add video generation capability to the agent orchestrator using OpenRouter's async video alpha API. Two video models (Veo 3.1 and Wan 2.6), fire-and-forget API with client polling, a video-script pipeline, and Web UI support.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Number of models | 2 (Veo 3.1 + Wan 2.6) | Quality + budget. Easy to add more via YAML. |
| Async pattern | Fire-and-forget + client polling | Simple, matches OpenRouter's own pattern. |
| Poll strategy | 30s silence then 15s intervals | ~3-5 requests per generation. Pause on tab hidden. |
| Download timing | On first poll that sees completed | Eager download before URLs expire (1-48h). Cache locally. |
| Pipeline | video-creator text agent → video model | Default flow. Toggle to skip refinement for advanced users. |
| Web UI | Yes, video tab with form + job cards + player | Alongside existing chat and dashboard. |
| Persistence | In-memory job tracker (dict) | Acceptable for alpha. Videos persist on disk. |

## Architecture

```
User (Web UI or curl)
  → POST /agents/{id}/generate-video     (direct)
  → POST /pipelines/video                (scripted)
      → video-creator text agent refines prompt
      → video_client.submit() → OpenRouter POST /api/alpha/videos
      → Returns job_id immediately (HTTP 202)

  → GET /videos/{jobId}                  (poll)
      → video_client.poll() → OpenRouter GET /api/alpha/videos/{jobId}
      → On completed: video_client.download() → saves MP4 locally
      → Returns status + local video URL

  → GET /videos                          (list all jobs)
      → Returns all tracked jobs from memory
```

## Agent Configuration

Two new entries in `config/agents.yaml`:

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

`AgentConfig` gains `video: bool = False` and optional `default_duration`, `default_resolution`, `default_aspect_ratio` fields. `AgentInfo` response includes `video` so the UI knows which agents are video-capable.

## Data Models

### VideoGenRequest

```python
class VideoGenRequest(BaseModel):
    prompt: str                              # Required
    duration: int | None = None              # Seconds, model-dependent
    resolution: str | None = None            # 480p, 720p, 1080p, 4K
    aspect_ratio: str | None = None          # 16:9, 9:16, 1:1, etc.
    generate_audio: bool = False             # Co-generate audio
    input_references: list[dict] | None = None  # Image-to-video references
```

### VideoGenResponse (HTTP 202)

```python
class VideoGenResponse(BaseModel):
    job_id: str
    status: str = "pending"
    agent_id: str
    model: str
```

### VideoStatusResponse

```python
class VideoStatusResponse(BaseModel):
    job_id: str
    status: str                              # pending | in_progress | completed | failed | cancelled | expired
    agent_id: str
    model: str
    prompt: str = ""
    video_url: str | None = None             # Local URL when completed
    error: str | None = None                 # Error message when failed
    cost: float | None = None                # Actual cost from usage
    created_at: datetime
```

### VideoPipelineRequest

```python
class VideoPipelineRequest(BaseModel):
    prompt: str                              # User's idea (will be refined)
    video_agent: str = "veo-3"              # Which video model to use
    skip_refinement: bool = False            # Bypass video-creator text agent
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    generate_audio: bool = False
```

### VideoPipelineResponse (HTTP 202)

```python
class VideoPipelineResponse(BaseModel):
    job_id: str
    status: str = "pending"
    refined_prompt: str | None = None        # The prompt video-creator wrote (None if skipped)
    video_agent: str
    model: str
```

## New Module: video_client.py

Handles all communication with OpenRouter's video alpha API. Separate from `openrouter_client.py` because the video API uses different endpoints (`/api/alpha/videos` vs `/api/v1/chat/completions`) and an async job pattern.

```
BASE_URL = "https://openrouter.ai/api/alpha/videos"
VIDEO_DIR = Path("generated_video")
```

**Methods:**

- `submit(model, prompt, **params) → dict` — POST to /api/alpha/videos, returns {id, polling_url, status}
- `poll(job_id) → dict` — GET /api/alpha/videos/{job_id}, returns full status object
- `download(job_id) → str` — GET /api/alpha/videos/{job_id}/content, saves MP4, returns filename
- `list_models() → dict` — GET /api/alpha/videos/models, returns model capabilities (for future use)

Uses the same OpenRouter API key. Extended timeout for download operations (videos can be tens of MB).

## In-Memory Job Tracker

A dict stored on `app.state.video_jobs`:

```python
video_jobs: dict[str, VideoJob] = {}

@dataclass
class VideoJob:
    job_id: str
    agent_id: str
    model: str
    prompt: str
    status: str          # pending | in_progress | completed | failed | cancelled | expired
    video_url: str | None = None   # Local /video/{file}.mp4 URL after download
    error: str | None = None
    cost: float | None = None
    created_at: datetime
```

Updated on submit (created) and on each poll (status changes). Caches the local video URL after download so subsequent polls don't re-download.

Lost on server restart — acceptable for alpha. Downloaded MP4s persist on disk.

## API Endpoints

### POST /agents/{agent_id}/generate-video

Submit a video generation job directly.

- Validates agent exists and has `video: true`
- Merges agent defaults (duration, resolution, aspect_ratio) with request params
- Calls `video_client.submit()`
- Creates entry in job tracker
- Returns HTTP 202 with VideoGenResponse

### GET /videos/{job_id}

Poll a job's status.

- Looks up job in tracker
- If terminal state with cached video URL → return from tracker (no OpenRouter call)
- Otherwise → calls `video_client.poll()`, updates tracker
- If newly completed → triggers `video_client.download()`, caches local URL in tracker. This single poll response will be slower (download time) but all subsequent polls return instantly from cache.
- Returns VideoStatusResponse

### GET /videos

List all tracked jobs.

- Returns all jobs from the in-memory tracker
- No OpenRouter calls
- Useful for the UI to show all active/completed jobs

### POST /pipelines/video

Video-script pipeline: refine prompt then generate.

- Validates video agent exists and has `video: true`
- If `skip_refinement` is false:
  - Sends user prompt to `video-creator` text agent via existing `openrouter_client.complete()`
  - Gets back a refined, optimized video prompt
- Submits (refined or original) prompt to video model via `video_client.submit()`
- Creates entry in job tracker
- Returns HTTP 202 with VideoPipelineResponse (includes refined_prompt)

## Static File Serving

New directory `generated_video/` (parallel to `generated_audio/`):

- Created on startup, gitignored
- Mounted at `/video/` as static files
- Videos saved as `{uuid}.mp4`

In `main.py`:
```python
VIDEO_DIR = Path("generated_video")
VIDEO_DIR.mkdir(exist_ok=True)
app.mount("/video", StaticFiles(directory=str(VIDEO_DIR)), name="video")
```

## Web UI

Add a **Video** tab to the existing single-file `static/index.html`.

### Video Generation Form

- Agent dropdown: populated from `/agents` filtered by `video: true`
- Prompt textarea
- Optional settings row: duration, resolution, aspect_ratio dropdowns + generate_audio toggle
- "Generate Video" button (default: uses pipeline)
- "Skip prompt refinement" checkbox (when checked, submits directly to video model)

### Job Cards

Each submitted job appears as a card showing:

- Agent name + model
- Prompt text (truncated, expandable)
- Status badge: Queued → Generating → Complete / Failed
- Elapsed time counter
- When pipeline is used: shows the refined prompt after Step 1 completes

### Smart Polling

```javascript
// Per-job polling logic
const INITIAL_DELAY = 30000;  // 30s silence
const POLL_INTERVAL = 15000;  // 15s after that

function startPolling(jobId) {
    setTimeout(() => {
        const interval = setInterval(async () => {
            if (document.hidden) return;  // Page Visibility API
            const status = await fetch(`/videos/${jobId}`).then(r => r.json());
            updateJobCard(jobId, status);
            if (['completed', 'failed', 'cancelled', 'expired'].includes(status.status)) {
                clearInterval(interval);
            }
        }, POLL_INTERVAL);
    }, INITIAL_DELAY);
}
```

### Video Player

On completion, job card expands to show:
- `<video>` element with local `/video/{file}.mp4` URL, controls enabled
- Download button

### UI Integration

- Video agents excluded from the chat agent dropdown (like audio agents)
- Video tab sits alongside existing Chat and Dashboard tabs
- Dark theme, responsive — matches existing UI style

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Generation fails (moderation, model error) | Poll returns `failed` + error message. UI shows error on card. |
| MP4 download fails (network, expired URL) | Poll returns `completed` with download error. User can retry. |
| Rate limit on submit | Return HTTP 429 to client. UI shows rate limit message. |
| Invalid agent / not video-capable | HTTP 404 / 400 with descriptive message. |
| Server restart | In-memory jobs lost. Downloaded MP4s persist on disk. Acceptable for alpha. |
| OpenRouter API spec changes | Only `video_client.py` needs updating — isolated module. |

## Files Changed

| File | Change |
|------|--------|
| `config/agents.yaml` | Add veo-3 and wan-video agents |
| `src/models.py` | Add VideoGenRequest, VideoGenResponse, VideoStatusResponse, VideoPipelineRequest, VideoPipelineResponse. Update AgentConfig and AgentInfo with `video` field + default video params. |
| `src/video_client.py` | **New.** OpenRouter video alpha API client (submit, poll, download, list_models). |
| `src/routes.py` | Add 4 endpoints: POST generate-video, GET /videos/{id}, GET /videos, POST /pipelines/video. Add in-memory job tracker. |
| `src/main.py` | Initialize VideoClient in lifespan. Mount /video static files. Create generated_video dir. |
| `static/index.html` | Add Video tab with generation form, job cards, smart polling, video player. |
| `.gitignore` | Add generated_video/ |

## Out of Scope

- Persistent job storage (SQLite/Redis) — not needed for alpha
- Webhook/push notifications — OpenRouter doesn't support them
- Video-to-video or editing — not in OpenRouter's API
- MCP server tools for video — can add later
- Additional models (Sora 2, Seedance) — easy to add via YAML when ready
