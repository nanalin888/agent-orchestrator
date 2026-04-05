import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from src.agent_registry import registry
from src.models import (
    AgentInfo, Choice, HealthResult, Message, MusicGenRequest, MusicGenResponse,
    RunRequest, RunResponse, SongPipelineRequest, SongPipelineResponse, Usage,
    VideoGenRequest, VideoGenResponse, VideoStatusResponse,
    VideoPipelineRequest, VideoPipelineResponse,
)

router = APIRouter()

# In-memory health cache
_health_cache: list[HealthResult] = []
_health_cache_time: float = 0
_HEALTH_TTL = 120  # seconds

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


# In-memory video job tracker
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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


video_jobs: dict[str, VideoJob] = {}


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents():
    return [
        AgentInfo(id=a.id, name=a.name, description=a.description, model=a.model, audio=a.audio, video=a.video)
        for a in registry.list_all()
    ]


@router.get("/agents/health", response_model=list[HealthResult])
async def agents_health(force: bool = False):
    """Check model availability by querying OpenRouter's model catalog (free, no rate limit)."""
    global _health_cache, _health_cache_time

    now = time.time()
    if not force and _health_cache and (now - _health_cache_time) < _HEALTH_TTL:
        return _health_cache

    # Single free API call — no auth needed, doesn't count against rate limit
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(OPENROUTER_MODELS_URL)
            resp.raise_for_status()
            catalog = resp.json()
    except Exception as e:
        return [HealthResult(
            agent_id="__catalog__", model="openrouter", status="error",
            error=f"Failed to fetch model catalog: {e}",
            checked_at=datetime.now(timezone.utc),
        )]

    fetch_ms = int((time.monotonic() - start) * 1000)
    available = {m["id"] for m in catalog.get("data", [])}
    checked_at = datetime.now(timezone.utc)

    results = []
    for agent in registry.list_all():
        if agent.model in available:
            status = "ok"
            error = None
        else:
            status = "error"
            error = f"Model '{agent.model}' not found in OpenRouter catalog"
        results.append(HealthResult(
            agent_id=agent.id, model=agent.model, status=status,
            latency_ms=fetch_ms, error=error, checked_at=checked_at,
        ))

    _health_cache = results
    _health_cache_time = now
    return results


@router.get("/agents/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str):
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return AgentInfo(id=agent.id, name=agent.name, description=agent.description, model=agent.model, audio=agent.audio, video=agent.video)


@router.post("/agents/{agent_id}/run")
async def run_agent(agent_id: str, req: RunRequest, request: Request):
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    client = request.app.state.openrouter_client

    if req.stream:
        return EventSourceResponse(client.stream(agent, req.messages))

    raw = await client.complete(agent, req.messages)

    choices = []
    for c in raw.get("choices", []):
        msg = c.get("message", {})
        choices.append(Choice(
            index=c.get("index", 0),
            message=Message(role=msg.get("role", "assistant"), content=msg.get("content", "")),
            finish_reason=c.get("finish_reason"),
        ))

    usage_raw = raw.get("usage", {})
    return RunResponse(
        id=raw.get("id", ""),
        agent_id=agent_id,
        model=agent.model,
        choices=choices,
        usage=Usage(
            prompt_tokens=usage_raw.get("prompt_tokens", 0),
            completion_tokens=usage_raw.get("completion_tokens", 0),
            total_tokens=usage_raw.get("total_tokens", 0),
        ),
    )


@router.post("/agents/{agent_id}/generate-music", response_model=MusicGenResponse)
async def generate_music(agent_id: str, req: MusicGenRequest, request: Request):
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    if not agent.audio:
        raise HTTPException(400, f"Agent '{agent_id}' does not support audio generation")

    client = request.app.state.openrouter_client
    try:
        result = await client.generate_audio(agent, req.prompt)
    except RuntimeError as e:
        raise HTTPException(502, str(e))

    base_url = str(request.base_url).rstrip("/")
    return MusicGenResponse(
        agent_id=agent_id,
        model=agent.model,
        caption=result["caption"],
        audio_url=f"{base_url}/audio/{result['filename']}",
        audio_format="mp3",
        audio_size_bytes=result["size_bytes"],
    )


@router.post("/pipelines/song", response_model=SongPipelineResponse)
async def song_pipeline(req: SongPipelineRequest, request: Request):
    """Chain songwriter → lyria: generate lyrics then turn them into music."""
    # Step 1: Generate lyrics with songwriter agent
    songwriter = registry.get("songwriter")
    if not songwriter:
        raise HTTPException(500, "Songwriter agent not configured")

    lyria = registry.get(req.lyria_agent)
    if not lyria:
        raise HTTPException(404, f"Lyria agent '{req.lyria_agent}' not found")
    if not lyria.audio:
        raise HTTPException(400, f"Agent '{req.lyria_agent}' does not support audio generation")

    client = request.app.state.openrouter_client

    # Step 1: songwriter generates lyrics
    messages = [Message(role="user", content=req.prompt)]
    try:
        raw = await client.complete(songwriter, messages)
    except RuntimeError as e:
        raise HTTPException(502, f"Songwriter error: {e}")

    lyrics = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not lyrics:
        raise HTTPException(502, "Songwriter returned empty lyrics")

    # Step 2: feed lyrics to Lyria for music generation
    try:
        result = await client.generate_audio(lyria, lyrics)
    except RuntimeError as e:
        raise HTTPException(502, f"Music generation error: {e}")

    base_url = str(request.base_url).rstrip("/")
    return SongPipelineResponse(
        lyrics=lyrics,
        lyrics_agent="songwriter",
        lyrics_model=songwriter.model,
        caption=result["caption"],
        audio_url=f"{base_url}/audio/{result['filename']}",
        audio_format="mp3",
        audio_size_bytes=result["size_bytes"],
        music_agent=req.lyria_agent,
        music_model=lyria.model,
    )


@router.post("/agents/{agent_id}/generate-video", status_code=202, response_model=VideoGenResponse)
async def generate_video(agent_id: str, req: VideoGenRequest, request: Request):
    """Submit a video generation job directly."""
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    if not agent.video:
        raise HTTPException(400, f"Agent '{agent_id}' does not support video generation")

    video_client = request.app.state.video_client

    # Merge agent defaults with request params
    params = {
        "model": agent.model,
        "prompt": req.prompt,
        "duration": req.duration or agent.default_duration,
        "resolution": req.resolution or agent.default_resolution,
        "aspect_ratio": req.aspect_ratio or agent.default_aspect_ratio,
        "generate_audio": req.generate_audio,
    }
    if req.input_references:
        params["input_references"] = req.input_references

    result = video_client.submit(**params)
    if "error" in result:
        raise HTTPException(502, result["error"])

    job_id = result["id"]
    video_jobs[job_id] = VideoJob(
        job_id=job_id,
        agent_id=agent_id,
        model=agent.model,
        prompt=req.prompt,
        status=result.get("status", "pending"),
    )

    return VideoGenResponse(
        job_id=job_id,
        status=result.get("status", "pending"),
        agent_id=agent_id,
        model=agent.model,
    )


@router.get("/videos/{job_id}", response_model=VideoStatusResponse)
async def get_video_status(job_id: str, request: Request):
    """Poll a video job's status."""
    job = video_jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Video job '{job_id}' not found")

    # If terminal state with cached video URL, return immediately
    terminal_states = {"completed", "failed", "cancelled", "expired"}
    if job.status in terminal_states and job.video_url:
        return VideoStatusResponse(
            job_id=job.job_id,
            status=job.status,
            agent_id=job.agent_id,
            model=job.model,
            prompt=job.prompt,
            video_url=job.video_url,
            error=job.error,
            cost=job.cost,
            created_at=job.created_at,
        )

    # Poll OpenRouter
    video_client = request.app.state.video_client
    result = video_client.poll(job_id)

    if "error" in result:
        job.status = "failed"
        job.error = result["error"]
    else:
        job.status = result.get("status", job.status)
        job.prompt = result.get("prompt", job.prompt)
        if "usage" in result and "total_cost" in result["usage"]:
            job.cost = result["usage"]["total_cost"]
        if "error" in result:
            job.error = result["error"]

        # If newly completed, download video
        if job.status == "completed" and not job.video_url:
            try:
                filename = video_client.download(job_id)
                base_url = str(request.base_url).rstrip("/")
                job.video_url = f"{base_url}/video/{filename}"
            except Exception as e:
                job.error = str(e)

    return VideoStatusResponse(
        job_id=job.job_id,
        status=job.status,
        agent_id=job.agent_id,
        model=job.model,
        prompt=job.prompt,
        video_url=job.video_url,
        error=job.error,
        cost=job.cost,
        created_at=job.created_at,
    )


@router.get("/videos", response_model=list[VideoStatusResponse])
async def list_videos():
    """List all tracked video jobs."""
    return [
        VideoStatusResponse(
            job_id=job.job_id,
            status=job.status,
            agent_id=job.agent_id,
            model=job.model,
            prompt=job.prompt,
            video_url=job.video_url,
            error=job.error,
            cost=job.cost,
            created_at=job.created_at,
        )
        for job in video_jobs.values()
    ]


@router.post("/pipelines/video", status_code=202, response_model=VideoPipelineResponse)
async def video_pipeline(req: VideoPipelineRequest, request: Request):
    """Chain video-creator → video model: refine prompt then generate video."""
    video_agent = registry.get(req.video_agent)
    if not video_agent:
        raise HTTPException(404, f"Video agent '{req.video_agent}' not found")
    if not video_agent.video:
        raise HTTPException(400, f"Agent '{req.video_agent}' does not support video generation")

    client = request.app.state.openrouter_client
    video_client = request.app.state.video_client

    refined_prompt = req.prompt

    # Step 1: Optionally refine prompt with video-creator
    if not req.skip_refinement:
        video_creator = registry.get("video-creator")
        if not video_creator:
            raise HTTPException(500, "video-creator agent not configured")

        messages = [Message(role="user", content=req.prompt)]
        try:
            raw = await client.complete(video_creator, messages)
        except RuntimeError as e:
            raise HTTPException(502, f"Video creator error: {e}")

        refined_prompt = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not refined_prompt:
            raise HTTPException(502, "Video creator returned empty prompt")

    # Step 2: Submit video generation with refined prompt
    params = {
        "model": video_agent.model,
        "prompt": refined_prompt,
        "duration": req.duration or video_agent.default_duration,
        "resolution": req.resolution or video_agent.default_resolution,
        "aspect_ratio": req.aspect_ratio or video_agent.default_aspect_ratio,
        "generate_audio": req.generate_audio,
    }

    result = video_client.submit(**params)
    if "error" in result:
        raise HTTPException(502, result["error"])

    job_id = result["id"]
    video_jobs[job_id] = VideoJob(
        job_id=job_id,
        agent_id=req.video_agent,
        model=video_agent.model,
        prompt=refined_prompt,
        status=result.get("status", "pending"),
    )

    return VideoPipelineResponse(
        job_id=job_id,
        status=result.get("status", "pending"),
        refined_prompt=refined_prompt if not req.skip_refinement else None,
        video_agent=req.video_agent,
        model=video_agent.model,
    )
