from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.agent_registry import registry
from src.openrouter_client import OpenRouterClient
from src.routes import router
from src.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry.load(settings.agents_config_abs)
    client = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        app_title=settings.app_title,
        app_referer=settings.app_referer,
    )
    app.state.openrouter_client = client
    print(f"Loaded {len(registry.list_all())} agents")
    for a in registry.list_all():
        print(f"  [{a.id}] {a.name} → {a.model}")
    yield
    await client.close()


app = FastAPI(title="Agent Orchestrator", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def main():
    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=True)


if __name__ == "__main__":
    main()
