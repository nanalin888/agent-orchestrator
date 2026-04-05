"""OpenRouter video alpha API client."""

import uuid
from pathlib import Path

import httpx


BASE_URL = "https://openrouter.ai/api/alpha/videos"
VIDEO_DIR = Path("generated_video")


class VideoClient:
    """Client for OpenRouter's async video generation API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def submit(
        self,
        model: str,
        prompt: str,
        duration: int | None = None,
        resolution: str | None = None,
        aspect_ratio: str | None = None,
        generate_audio: bool = False,
        input_references: list[dict] | None = None,
    ) -> dict:
        """
        Submit a video generation job.

        Returns:
            dict with keys: id, polling_url, status
        """
        payload = {"model": model, "prompt": prompt}

        if duration is not None:
            payload["duration"] = duration
        if resolution is not None:
            payload["resolution"] = resolution
        if aspect_ratio is not None:
            payload["aspect_ratio"] = aspect_ratio
        if generate_audio:
            payload["generate_audio"] = True
        if input_references:
            payload["input_references"] = input_references

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(BASE_URL, headers=self.headers, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"error": str(e)}

    def poll(self, job_id: str) -> dict:
        """
        Poll the status of a video generation job.

        Returns:
            dict with job status fields: id, status, model, prompt, result, usage, error
        """
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(f"{BASE_URL}/{job_id}", headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"error": str(e)}

    def download(self, job_id: str) -> str:
        """
        Download the generated video content.

        Returns:
            str: filename of the saved video (e.g., "abc123.mp4")
        Raises:
            Exception if download fails
        """
        VIDEO_DIR.mkdir(exist_ok=True)
        filename = f"{uuid.uuid4().hex}.mp4"
        filepath = VIDEO_DIR / filename

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.get(f"{BASE_URL}/{job_id}/content", headers=self.headers)
                response.raise_for_status()

                with open(filepath, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)

                return filename
        except Exception as e:
            # Clean up partial download
            if filepath.exists():
                filepath.unlink()
            raise Exception(f"Download failed: {e}") from e

    def list_models(self) -> dict:
        """
        List available video models and their capabilities.

        Returns:
            dict with model information
        """
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(f"{BASE_URL}/models", headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"error": str(e)}
