import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from src.agent_registry import registry
from src.models import (
    AgentInfo, Choice, HealthResult, Message, MusicGenRequest, MusicGenResponse,
    RunRequest, RunResponse, SongPipelineRequest, SongPipelineResponse, Usage,
)

router = APIRouter()

# In-memory health cache
_health_cache: list[HealthResult] = []
_health_cache_time: float = 0
_HEALTH_TTL = 120  # seconds

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents():
    return [
        AgentInfo(id=a.id, name=a.name, description=a.description, model=a.model, audio=a.audio)
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
    return AgentInfo(id=agent.id, name=agent.name, description=agent.description, model=agent.model, audio=agent.audio)


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
