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


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str
    model: str


class Message(BaseModel):
    role: str = Field(pattern=r"^(user|assistant|system)$")
    content: str


class RunRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    stream: bool = False


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
