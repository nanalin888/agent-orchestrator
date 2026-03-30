from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openrouter_api_key: str = ""
    agents_config_path: str = "config/agents.yaml"
    host: str = "0.0.0.0"
    port: int = 8000
    app_title: str = "Agent Orchestrator"
    app_referer: str = "http://localhost:8000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def agents_config_abs(self) -> Path:
        p = Path(self.agents_config_path)
        if p.is_absolute():
            return p
        return Path(__file__).parent.parent / p


settings = Settings()
