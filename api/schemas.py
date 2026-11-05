from pydantic import BaseModel, Field
from typing import Literal

class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    model: str = "qwen-engineering"
    messages: list[Message]
    temperature: float = Field(0.2, ge=0, le=2)
    max_tokens: int = Field(2048, ge=1, le=8192)
    stream: bool = False

class IngestRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100000)
    source: str = Field("manual", max_length=500)
    project_id: str | None = None

class TaskRequest(BaseModel):
    project_id: str
    goal: str = Field(min_length=5, max_length=10000)

class ApprovalRequest(BaseModel):
    approved: bool
    reviewer: str = Field(min_length=1, max_length=120)
    note: str = Field("", max_length=2000)
