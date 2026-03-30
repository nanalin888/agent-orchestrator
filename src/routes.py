from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from src.agent_registry import registry
from src.models import AgentInfo, Choice, Message, RunRequest, RunResponse, Usage

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents():
    return [
        AgentInfo(id=a.id, name=a.name, description=a.description, model=a.model)
        for a in registry.list_all()
    ]


@router.get("/agents/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str):
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return AgentInfo(id=agent.id, name=agent.name, description=agent.description, model=agent.model)


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
