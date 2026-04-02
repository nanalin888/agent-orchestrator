import base64
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
from httpx_sse import aconnect_sse

from src.models import AgentConfig, Message

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
AUDIO_DIR = Path(__file__).parent.parent / "generated_audio"


class OpenRouterClient:
    def __init__(self, api_key: str, app_title: str, app_referer: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": app_referer,
            "X-Title": app_title,
            "Content-Type": "application/json",
        }
        self._http = httpx.AsyncClient(headers=self._headers, timeout=120.0)

    def _build_payload(
        self, agent: AgentConfig, messages: list[Message], stream: bool
    ) -> dict:
        all_messages = [{"role": "system", "content": agent.system_prompt.strip()}]
        all_messages.extend(m.model_dump() for m in messages)
        return {
            "model": agent.model,
            "messages": all_messages,
            "temperature": agent.temperature,
            "max_tokens": agent.max_tokens,
            "stream": stream,
        }

    async def complete(
        self, agent: AgentConfig, messages: list[Message]
    ) -> dict:
        payload = self._build_payload(agent, messages, stream=False)
        resp = await self._http.post(OPENROUTER_URL, json=payload)
        data = resp.json()
        if "error" in data:
            code = data["error"].get("code", resp.status_code)
            msg = data["error"].get("message", "Unknown error")
            raise RuntimeError(f"OpenRouter {code}: {msg}")
        resp.raise_for_status()
        return data

    async def stream(
        self, agent: AgentConfig, messages: list[Message]
    ) -> AsyncIterator[str]:
        payload = self._build_payload(agent, messages, stream=True)
        req = self._http.build_request("POST", OPENROUTER_URL, json=payload)
        resp = await self._http.send(req, stream=True)

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" not in content_type:
            # OpenRouter returned JSON (error or non-streaming fallback)
            body = await resp.aread()
            data = json.loads(body)
            if "error" in data:
                yield json.dumps({"error": data["error"]})
            else:
                # Extract content from non-streamed response
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    yield json.dumps({"content": content})
            yield "[DONE]"
            return

        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                yield "[DONE]"
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield json.dumps({"content": content})
            except (json.JSONDecodeError, IndexError, KeyError):
                continue
        await resp.aclose()

    async def generate_audio(self, agent: AgentConfig, prompt: str) -> dict:
        """Stream a Lyria audio generation request. Returns caption, file path, and size."""
        AUDIO_DIR.mkdir(exist_ok=True)
        payload = {
            "model": agent.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        req = self._http.build_request("POST", OPENROUTER_URL, json=payload)
        resp = await self._http.send(req, stream=True)

        caption = ""
        audio_b64 = ""

        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                if "error" in chunk:
                    raise RuntimeError(
                        f"OpenRouter: {chunk['error'].get('message', 'Unknown error')}"
                    )
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if "audio" in delta:
                    audio_b64 += delta["audio"].get("data", "")
                elif "content" in delta:
                    caption += delta["content"]
            except json.JSONDecodeError:
                continue

        await resp.aclose()

        if not audio_b64:
            raise RuntimeError("No audio data received from model")

        audio_bytes = base64.b64decode(audio_b64)
        filename = f"{uuid.uuid4().hex}.mp3"
        filepath = AUDIO_DIR / filename
        filepath.write_bytes(audio_bytes)

        return {
            "caption": caption,
            "filename": filename,
            "size_bytes": len(audio_bytes),
        }

    async def close(self) -> None:
        await self._http.aclose()
