from pathlib import Path

import yaml

from src.models import AgentConfig


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentConfig] = {}

    def load(self, config_path: Path) -> None:
        raw = yaml.safe_load(config_path.read_text())
        agents_raw = raw.get("agents", {})
        self._agents = {
            agent_id: AgentConfig(id=agent_id, **cfg)
            for agent_id, cfg in agents_raw.items()
        }

    def get(self, agent_id: str) -> AgentConfig | None:
        return self._agents.get(agent_id)

    def list_all(self) -> list[AgentConfig]:
        return list(self._agents.values())


registry = AgentRegistry()
