"""Excepciones del Core. Todas heredan de AxionError para manejo uniforme en la API."""


class AxionError(Exception):
    code = "axion_error"


class TransportError(AxionError):
    code = "transport_error"

    def __init__(self, message: str, retryable: bool = True, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class ModelUnavailable(AxionError):
    code = "model_unavailable"

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


class ModelConfigError(AxionError):
    code = "model_config_error"


class NoSuitableModel(AxionError):
    code = "no_suitable_model"


class ContextOverflow(AxionError):
    code = "context_overflow"
