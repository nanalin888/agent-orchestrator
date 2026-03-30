"""MCP server mounted inside the FastAPI app at /mcp."""

from mcp.server.fastmcp import FastMCP

from src.agent_registry import registry
from src.models import Message


mcp = FastMCP("agent-orchestrator", stateless_http=True)
mcp.settings.streamable_http_path = "/"


def register_agent_tools(app) -> None:
    """Register one MCP tool per agent. Call after registry.load()."""
    for agent in registry.list_all():
        _make_tool(agent.id, agent.description, agent.model, app)


def _make_tool(agent_id: str, description: str, model: str, app):
    tool_name = f"ask_{agent_id.replace('-', '_')}"
    bound_id = agent_id  # capture in closure

    async def tool_fn(message: str) -> str:
        agent = registry.get(bound_id)
        if not agent:
            return f"Agent '{bound_id}' not found"

        client = app.state.openrouter_client
        messages = [Message(role="user", content=message)]

        try:
            raw = await client.complete(agent, messages)
        except Exception as e:
            return f"Error calling {bound_id}: {e}"

        choices = raw.get("choices", [])
        if not choices:
            return "No response from model"

        content = choices[0].get("message", {}).get("content", "")
        tokens = raw.get("usage", {}).get("total_tokens", "?")
        return f"{content}\n\n---\n_Agent: {bound_id} | Model: {raw.get('model', '?')} | Tokens: {tokens}_"

    mcp.add_tool(tool_fn, name=tool_name, description=f"{description} (model: {model})")
    return tool_fn
