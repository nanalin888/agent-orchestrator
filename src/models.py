from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    model: str
    system_prompt: str
    temperature: float = 0.7
    max_tokens: int = 4096


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
