from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount

from src.agent_registry import registry
from src.mcp_server import mcp, register_agent_tools
from src.openrouter_client import AUDIO_DIR, OpenRouterClient
from src.routes import router
from src.settings import settings


# Build MCP sub-app early so session_manager is initialized
mcp_http_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry.load(settings.agents_config_abs)
    client = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        app_title=settings.app_title,
        app_referer=settings.app_referer,
    )
    app.state.openrouter_client = client
    register_agent_tools(app)
    print(f"Loaded {len(registry.list_all())} agents")
    for a in registry.list_all():
        print(f"  [{a.id}] {a.name} → {a.model}")

    # Start MCP session manager inside the app lifespan
    async with mcp.session_manager.run():
        print("MCP endpoint ready at /mcp")
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
app.routes.append(Mount("/mcp", app=mcp_http_app))

AUDIO_DIR.mkdir(exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

STATIC_DIR = Path(__file__).parent.parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


@app.get("/")
async def root():
    return RedirectResponse("/static/index.html")


def main():
    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=True)


if __name__ == "__main__":
    main()
