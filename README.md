# Agent Orchestrator

A lightweight Python service that exposes multiple named AI agents — each bound to a specific LLM model via [OpenRouter](https://openrouter.ai) — through a simple REST API. Includes music generation via Google Lyria, video generation via Veo/Wan, and agent-chaining pipelines.

```
Client (CLI, web app, IDE)
    → Agent Orchestrator (this service)
        → OpenRouter
            → Claude, GPT, Llama, Gemini, Qwen, Lyria, etc.
```

## Web UI

The service includes a built-in web dashboard at `http://localhost:8000` with a chat interface for all agents and a model availability dashboard.

![Model Availability Dashboard](docs/dashboard.png)

## Why

- **One API, many models** — call different LLMs through a single endpoint
- **Agent-as-config** — add a new agent by editing a YAML file, no code changes
- **Streaming built-in** — SSE streaming for real-time responses
- **Music generation** — generate songs and clips via Google Lyria 3
- **Video generation** — create videos with Veo 3.1, Wan 2.6, and more
- **Agent pipelines** — chain agents together (e.g. video-creator → video generation)
- **MCP server** — built-in Model Context Protocol endpoint at `/mcp`
- **Web UI included** — chat interface, video generation tab, and model availability dashboard
- **Zero cost to start** — ships with 8 free text agents (music + video require credits)

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/nanalin888/agent-orchestrator.git
cd agent-orchestrator
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Add your OpenRouter API key

```bash
cp .env.example .env
```

Edit `.env` and set your key (get one free at [openrouter.ai/keys](https://openrouter.ai/keys)):

```
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

> **Note:** Text agents use free models (no charges). Music generation with Lyria requires OpenRouter credits ($0.04/clip, $0.08/song).

### 3. Start the service

```bash
python3 -m src.main
```

The server starts at `http://localhost:8000` with 12 agents loaded (8 text, 2 music, 2 video).

## API Reference

### List agents

```bash
curl localhost:8000/agents
```

Returns all configured agents with their IDs, names, descriptions, and models.

### Get agent info

```bash
curl localhost:8000/agents/code-reviewer
```

### Run a text agent

```bash
POST /agents/{agent_id}/run
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `messages` | array | yes | — | Conversation messages (`role` + `content`) |
| `stream` | bool | no | `false` | Enable SSE streaming |

**Example:**

```bash
curl -X POST localhost:8000/agents/fast-assistant/run \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ]
  }'
```

**Streaming:**

```bash
curl -N -X POST localhost:8000/agents/creative-writer/run \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Write a haiku about code"}
    ],
    "stream": true
  }'
```

### Generate music

```bash
POST /agents/{agent_id}/generate-music
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | yes | Description of the music to generate |

**Example:**

```bash
curl -X POST localhost:8000/agents/lyria-clip/generate-music \
  -H "Content-Type: application/json" \
  -d '{"prompt": "A chill lo-fi hip hop beat with soft piano and vinyl crackle"}'
```

**Response:**

```json
{
  "agent_id": "lyria-clip",
  "model": "google/lyria-3-clip-preview",
  "caption": "A quintessential Chillhop track...",
  "audio_url": "http://localhost:8000/audio/abc123.mp3",
  "audio_format": "mp3",
  "audio_size_bytes": 744608
}
```

The generated MP3 file is served at the returned `audio_url`.

### Generate video

```bash
POST /agents/{agent_id}/generate-video
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | yes | Description of the video to generate |
| `duration` | int | no | Video length in seconds (3-10, model-dependent) |
| `resolution` | string | no | `480p`, `720p`, `1080p`, or `4K` |
| `aspect_ratio` | string | no | `16:9`, `9:16`, `1:1`, or `4:3` |
| `generate_audio` | bool | no | Generate audio with video (default: false) |

**Example:**

```bash
curl -X POST localhost:8000/agents/veo-3/generate-video \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A cat playing piano in a cozy living room",
    "duration": 4,
    "resolution": "1080p",
    "aspect_ratio": "16:9"
  }'
```

**Response (HTTP 202):**

```json
{
  "job_id": "abc123",
  "status": "pending",
  "agent_id": "veo-3",
  "model": "google/veo-3.1"
}
```

Then poll for status:

```bash
curl localhost:8000/videos/abc123
```

**Response when complete:**

```json
{
  "job_id": "abc123",
  "status": "completed",
  "agent_id": "veo-3",
  "model": "google/veo-3.1",
  "prompt": "A cat playing piano in a cozy living room",
  "video_url": "http://localhost:8000/video/xyz789.mp4",
  "cost": 0.80,
  "created_at": "2026-04-05T14:30:00Z"
}
```

The generated MP4 is available at the returned `video_url`.

### Video pipeline (video-creator → video)

Chain the video-creator agent with a video model to refine your prompt and then generate the video.

```bash
POST /pipelines/video
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prompt` | string | yes | — | Describe the video you want |
| `video_agent` | string | no | `veo-3` | Which video agent to use (`veo-3` or `wan-video`) |
| `skip_refinement` | bool | no | `false` | Skip prompt refinement by video-creator |
| `duration` | int | no | — | Video length in seconds |
| `resolution` | string | no | — | Video resolution |
| `aspect_ratio` | string | no | — | Video aspect ratio |
| `generate_audio` | bool | no | `false` | Generate audio with video |

**Example:**

```bash
curl -X POST localhost:8000/pipelines/video \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A peaceful sunset over mountains",
    "video_agent": "wan-video"
  }'
```

**Response (HTTP 202):**

```json
{
  "job_id": "def456",
  "status": "pending",
  "refined_prompt": "Wide cinematic shot of a golden hour sunset over snow-capped mountain peaks, warm orange and purple gradient sky, slow pan left to right, peaceful atmosphere...",
  "video_agent": "wan-video",
  "model": "alibaba/wan-2.6"
}
```

### Song pipeline (songwriter → music)

Chain the songwriter agent with Lyria to generate lyrics and then turn them into music in a single call.

```bash
POST /pipelines/song
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prompt` | string | yes | — | Describe the song you want |
| `lyria_agent` | string | no | `lyria-pro` | Which Lyria agent to use (`lyria-pro` or `lyria-clip`) |

**Example:**

```bash
curl -X POST localhost:8000/pipelines/song \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A lullaby about a child building with LEGO bricks before bedtime",
    "lyria_agent": "lyria-clip"
  }'
```

**Response:**

```json
{
  "lyrics": "[Verse 1]\nA little brick against the blue...",
  "lyrics_agent": "songwriter",
  "lyrics_model": "qwen/qwen3.6-plus-preview:free",
  "caption": "A gentle lullaby...",
  "audio_url": "http://localhost:8000/audio/def456.mp3",
  "audio_format": "mp3",
  "audio_size_bytes": 744608,
  "music_agent": "lyria-clip",
  "music_model": "google/lyria-3-clip-preview"
}
```

### Multi-turn conversations

Pass the full message history to maintain context:

```bash
curl -X POST localhost:8000/agents/reasoning-analyst/run \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is Python?"},
      {"role": "assistant", "content": "Python is a programming language."},
      {"role": "user", "content": "Compare it to Rust."}
    ]
  }'
```

### Health check

```bash
GET /health
```

## Pre-configured Agents

### Text agents (free)

| Agent ID | Model | Best for |
|----------|-------|----------|
| `code-reviewer` | Qwen3-Coder | Code review, bug detection, security analysis |
| `reasoning-analyst` | Nemotron 3 Super 120B | Step-by-step analysis, comparisons, logic |
| `creative-writer` | Nemotron 3 Super 120B | Creative writing, brainstorming, content |
| `fast-assistant` | Nemotron Nano 9B | Quick answers, low latency tasks |
| `agentic-planner` | GLM-4.5-Air | Task decomposition, planning, workflows |
| `songwriter` | Qwen 3.6 Plus Preview | Song lyrics with structure (verses, chorus, bridge) |
| `research-summarizer` | MiniMax M2.5 | Summarization, long document analysis |
| `video-creator` | Qwen 3.6 Plus Preview | Video scripting, storyboarding, prompt engineering |

### Music agents (requires credits)

| Agent ID | Model | Output | Cost |
|----------|-------|--------|------|
| `lyria-pro` | Google Lyria 3 Pro | Full-length songs with vocals | $0.08/song |
| `lyria-clip` | Google Lyria 3 Clip | 30-second clips and loops | $0.04/clip |

### Video agents (requires credits)

| Agent ID | Model | Output | Cost |
|----------|-------|--------|------|
| `veo-3` | Google Veo 3.1 | High-quality 4K videos with audio | $0.20-$0.60/sec |
| `wan-video` | Alibaba Wan 2.6 | Budget-friendly 720p/1080p videos | $0.04-$0.12/sec |

> **Note:** Video generation is currently in alpha and requires OpenRouter credits. A 4-second video costs approximately $0.32 (Wan) to $0.80 (Veo).

## Adding Your Own Agents

Edit `config/agents.yaml` and add an entry:

```yaml
agents:
  my-custom-agent:
    name: "My Custom Agent"
    description: "What this agent does"
    model: "openai/gpt-4o"          # any OpenRouter model ID
    system_prompt: >
      You are a helpful assistant specialized in...
    temperature: 0.7
    max_tokens: 4096
    audio: false                     # set to true for audio generation models
    video: false                     # set to true for video generation models
    default_duration: 5              # for video agents: default duration in seconds
    default_resolution: "1080p"      # for video agents: default resolution
    default_aspect_ratio: "16:9"     # for video agents: default aspect ratio
```

Restart the service and it's ready. Browse available models at [openrouter.ai/models](https://openrouter.ai/models).

## Configuration

All configuration is via environment variables (or `.env` file):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | yes | — | Your OpenRouter API key |
| `AGENTS_CONFIG_PATH` | no | `config/agents.yaml` | Path to agent definitions |
| `HOST` | no | `0.0.0.0` | Server bind address |
| `PORT` | no | `8000` | Server port |

## Project Structure

```
agent-orchestrator/
├── config/
│   └── agents.yaml              # Agent definitions
├── static/
│   └── index.html               # Web UI (chat + dashboard)
├── docs/
│   └── dashboard.png            # Dashboard screenshot
├── src/
│   ├── main.py                  # FastAPI app + static file serving
│   ├── models.py                # Pydantic request/response schemas
│   ├── routes.py                # API endpoints + pipelines
│   ├── agent_registry.py        # YAML config loader
│   ├── openrouter_client.py     # OpenRouter client (text + audio streaming)
│   ├── video_client.py          # OpenRouter video alpha API client
│   ├── mcp_server.py            # MCP server for Claude Code integration
│   └── settings.py              # Environment configuration
├── generated_audio/             # Generated MP3 files (gitignored)
├── generated_video/             # Generated MP4 files (gitignored)
├── .env.example                 # Environment template
└── pyproject.toml               # Project metadata + dependencies
```

## License

MIT
