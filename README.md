# Agent Orchestrator

A lightweight Python service that exposes multiple named AI agents — each bound to a specific LLM model via [OpenRouter](https://openrouter.ai) — through a simple REST API.

```
Client (CLI, web app, IDE)
    → Agent Orchestrator (this service)
        → OpenRouter
            → Claude, GPT, Llama, Gemini, Qwen, etc.
```

## Why

- **One API, many models** — call different LLMs through a single endpoint
- **Agent-as-config** — add a new agent by editing a YAML file, no code changes
- **Streaming built-in** — SSE streaming for real-time responses
- **Zero cost to start** — ships with 6 agents using free OpenRouter models

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/nanalin888/agent-orchestrator.git
cd agent-orchestrator
pip install -r <(cat pyproject.toml | python3 -c "
import sys, tomllib
deps = tomllib.loads(sys.stdin.read())['project']['dependencies']
print('\n'.join(deps))
")
```

Or if you use `uv`:

```bash
uv sync
```

### 2. Add your OpenRouter API key

```bash
cp .env.example .env
```

Edit `.env` and set your key (get one free at [openrouter.ai/keys](https://openrouter.ai/keys)):

```
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

### 3. Start the service

```bash
python3 -m src.main
```

The server starts at `http://localhost:8000`. You'll see the loaded agents:

```
Loaded 6 agents
  [code-reviewer] Code Reviewer → qwen/qwen3-coder:free
  [reasoning-analyst] Reasoning Analyst → nvidia/nemotron-3-super-120b-a12b:free
  [creative-writer] Creative Writer → nousresearch/hermes-3-llama-3.1-405b:free
  [fast-assistant] Fast Assistant → nvidia/nemotron-nano-9b-v2:free
  [agentic-planner] Agentic Planner → z-ai/glm-4.5-air:free
  [research-summarizer] Research Summarizer → minimax/minimax-m2.5:free
```

## API Reference

### List agents

```bash
GET /agents
```

```bash
curl localhost:8000/agents
```

Returns all configured agents with their IDs, names, descriptions, and models.

### Get agent info

```bash
GET /agents/{agent_id}
```

```bash
curl localhost:8000/agents/code-reviewer
```

### Run an agent

```bash
POST /agents/{agent_id}/run
```

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `messages` | array | yes | — | Conversation messages (`role` + `content`) |
| `stream` | bool | no | `false` | Enable SSE streaming |

**Non-streaming example:**

```bash
curl -X POST localhost:8000/agents/fast-assistant/run \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ]
  }'
```

**Response:**

```json
{
  "id": "gen-abc123",
  "agent_id": "fast-assistant",
  "model": "nvidia/nemotron-nano-9b-v2:free",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "2 + 2 equals 4."},
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 44, "completion_tokens": 10, "total_tokens": 54}
}
```

**Streaming example:**

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

**Streaming response (SSE):**

```
data: {"content": "Silent"}
data: {"content": " keystrokes"}
data: {"content": " fall"}
data: [DONE]
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

| Agent ID | Model | Best for |
|----------|-------|----------|
| `code-reviewer` | Qwen3-Coder 480B MoE | Code review, bug detection, security analysis |
| `reasoning-analyst` | Nemotron 3 Super 120B | Step-by-step analysis, comparisons, logic |
| `creative-writer` | Hermes 3 Llama 405B | Creative writing, brainstorming, content |
| `fast-assistant` | Nemotron Nano 9B | Quick answers, low latency tasks |
| `agentic-planner` | GLM-4.5-Air | Task decomposition, planning, workflows |
| `research-summarizer` | MiniMax M2.5 (196K ctx) | Summarization, long document analysis |

All models are **free tier** on OpenRouter — no charges.

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
├── src/
│   ├── main.py                  # FastAPI app entry point
│   ├── models.py                # Pydantic request/response schemas
│   ├── routes.py                # API endpoints
│   ├── agent_registry.py        # YAML config loader
│   ├── openrouter_client.py     # OpenRouter API client (streaming + non-streaming)
│   └── settings.py              # Environment configuration
├── .env.example                 # Environment template
└── pyproject.toml               # Project metadata + dependencies
```

## License

MIT
