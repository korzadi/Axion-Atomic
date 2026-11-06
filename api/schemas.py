from pydantic import BaseModel, Field
from typing import Literal


class Message(BaseModel):
    # El system prompt es propiedad del servidor; nunca aceptar mensajes system del cliente.
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    model: str = "atomic-code:16k-8k"
    project_id: str = Field(min_length=1, max_length=200)
    messages: list[Message] = Field(min_length=1, max_length=100)
    temperature: float = Field(0.2, ge=0, le=2)
    max_tokens: int = Field(2048, ge=1, le=8192)
    stream: bool = False


class IngestRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100000)
    source: str = Field("manual", max_length=500)
    project_id: str = Field(min_length=1, max_length=200)


class TaskRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=5, max_length=10000)


class ApprovalRequest(BaseModel):
    approved: bool
    note: str = Field("", max_length=2000)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    display_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
