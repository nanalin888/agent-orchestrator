"""MCP server that exposes agent-orchestrator agents as Claude Code tools."""

import json
import sys

import httpx
from mcp.server.fastmcp import FastMCP

ORCHESTRATOR_URL = "http://localhost:8000"

mcp = FastMCP("agent-orchestrator")


def _make_tool(agent_id: str, name: str, description: str, model: str):
    """Dynamically register an MCP tool for an agent."""

    @mcp.tool(name=f"ask_{agent_id.replace('-', '_')}", description=f"{description} (model: {model})")
    async def tool_fn(message: str) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/agents/{agent_id}/run",
                json={"messages": [{"role": "user", "content": message}]},
            )
            if resp.status_code != 200:
                return f"Error {resp.status_code}: {resp.text}"
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return "No response from model"
            content = choices[0].get("message", {}).get("content", "")
            tokens = data.get("usage", {}).get("total_tokens", "?")
            return f"{content}\n\n---\n_Agent: {agent_id} | Model: {data.get('model', '?')} | Tokens: {tokens}_"

    return tool_fn


def _register_agents():
    """Fetch agents from orchestrator and register each as a tool."""
    try:
        resp = httpx.get(f"{ORCHESTRATOR_URL}/agents", timeout=5.0)
        resp.raise_for_status()
        agents = resp.json()
    except Exception as e:
        print(f"Warning: Could not fetch agents from {ORCHESTRATOR_URL}: {e}", file=sys.stderr)
        return

    for agent in agents:
        _make_tool(
            agent_id=agent["id"],
            name=agent["name"],
            description=agent["description"],
            model=agent["model"],
        )
    print(f"Registered {len(agents)} agent tools", file=sys.stderr)


_register_agents()

if __name__ == "__main__":
    mcp.run()
