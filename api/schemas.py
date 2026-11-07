from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal


class Message(BaseModel):
    # El system prompt es propiedad del servidor; nunca aceptar mensajes system del cliente.
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El contenido del mensaje no puede estar vacío")
        return value


class ChatRequest(BaseModel):
    # ID público estable del catálogo; nunca es una etiqueta arbitraria de Ollama.
    model: Literal["atomic-code"] = "atomic-code"
    project_id: str = Field(min_length=1, max_length=200)
    messages: list[Message] = Field(min_length=1, max_length=100)
    temperature: float = Field(0.2, ge=0, le=2)
    max_tokens: int = Field(2048, ge=1, le=8192)
    stream: bool = False

    @model_validator(mode="after")
    def total_message_content_is_bounded(self):
        total_chars = sum(len(message.content) for message in self.messages)
        if total_chars > 40000:
            raise ValueError("La conversación supera el límite de 40000 caracteres")
        return self

    @field_validator("project_id")
    @classmethod
    def project_id_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("project_id no puede estar vacío")
        return value


class IngestRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100000)
    source: str = Field("manual", max_length=500)
    project_id: str = Field(min_length=1, max_length=200)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El texto que se va a indexar no puede estar vacío")
        return value

    @field_validator("source", "project_id")
    @classmethod
    def identifiers_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacío")
        return value


class TaskRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=5, max_length=10000)

    @field_validator("project_id")
    @classmethod
    def project_id_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("project_id no puede estar vacío")
        return value

    @field_validator("goal")
    @classmethod
    def goal_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("El objetivo debe contener al menos 5 caracteres útiles")
        return value


class ApprovalRequest(BaseModel):
    approved: bool
    note: str = Field("", max_length=2000)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    display_name: str = Field(min_length=1, max_length=120)
    terms_accepted: bool = False


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class EmailTokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class PasswordResetRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=12, max_length=1024)


class EmailAddressRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)



class MfaChallengeVerifyRequest(BaseModel):
    challenge_token: str | None = Field(default=None, min_length=20, max_length=256)
    code: str = Field(min_length=6, max_length=32)

    @field_validator("code")
    @classmethod
    def validate_mfa_code(cls, value: str) -> str:
        import re
        if not re.fullmatch(r"(?:[0-9]{6}|[A-Fa-f0-9]{32})", value):
            raise ValueError("Código MFA no válido")
        return value.upper()


class MfaConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)

    @field_validator("code")
    @classmethod
    def validate_totp_code(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("Código TOTP no válido")
        return value
