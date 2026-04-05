from datetime import datetime

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    model: str
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    audio: bool = False
    video: bool = False
    default_duration: int | None = None
    default_resolution: str | None = None
    default_aspect_ratio: str | None = None


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str
    model: str
    audio: bool = False
    video: bool = False


class Message(BaseModel):
    role: str = Field(pattern=r"^(user|assistant|system)$")
    content: str


class RunRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    stream: bool = False
    task_id: str | None = None  # Optional task context to inject


class Choice(BaseModel):
    index: int = 0
    message: Message
    finish_reason: str | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class RunResponse(BaseModel):
    id: str = ""
    agent_id: str
    model: str
    choices: list[Choice] = []
    usage: Usage = Usage()


class MusicGenRequest(BaseModel):
    prompt: str = Field(min_length=1)


class MusicGenResponse(BaseModel):
    agent_id: str
    model: str
    caption: str = ""
    audio_url: str = ""
    audio_format: str = "mp3"
    audio_size_bytes: int = 0


class SongPipelineRequest(BaseModel):
    prompt: str = Field(min_length=1)
    lyria_agent: str = "lyria-pro"


class SongPipelineResponse(BaseModel):
    lyrics: str
    lyrics_agent: str
    lyrics_model: str
    caption: str = ""
    audio_url: str = ""
    audio_format: str = "mp3"
    audio_size_bytes: int = 0
    music_agent: str = ""
    music_model: str = ""


class VideoGenRequest(BaseModel):
    prompt: str = Field(min_length=1)
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    generate_audio: bool = False
    input_references: list[dict] | None = None


class VideoGenResponse(BaseModel):
    job_id: str
    status: str = "pending"
    agent_id: str
    model: str


class VideoStatusResponse(BaseModel):
    job_id: str
    status: str
    agent_id: str
    model: str
    prompt: str = ""
    video_url: str | None = None
    error: str | None = None
    cost: float | None = None
    created_at: datetime


class VideoPipelineRequest(BaseModel):
    prompt: str = Field(min_length=1)
    video_agent: str = "veo-3"
    skip_refinement: bool = False
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    generate_audio: bool = False


class VideoPipelineResponse(BaseModel):
    job_id: str
    status: str = "pending"
    refined_prompt: str | None = None
    video_agent: str
    model: str


class TaskContextInit(BaseModel):
    task_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")


class ContextEntry(BaseModel):
    agent_id: str
    entry: str = Field(min_length=1)


class TaskContextResponse(BaseModel):
    task_id: str
    content: str
    created_at: datetime
    updated_at: datetime


class HealthResult(BaseModel):
    agent_id: str
    model: str
    status: str = "unknown"  # ok | error | checking
    latency_ms: int = 0
    error: str | None = None
    checked_at: datetime | None = None
