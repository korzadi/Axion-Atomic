"""Admisión acotada para llamadas costosas al runtime local Ollama."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager


class CapacityExceeded(RuntimeError):
    def __init__(self, retry_after_seconds: int = 10):
        super().__init__("El servicio de inferencia está ocupado")
        self.retry_after_seconds = max(1, int(retry_after_seconds))


class BoundedInferenceGate:
    """Límite por proceso con cola finita y espera máxima.

    El despliegue inicial usa una instancia API. Este gate no coordina procesos
    distintos; antes de añadir réplicas se debe cambiar por un semáforo Redis.
    """

    def __init__(self, max_concurrent: int, max_waiting: int, wait_timeout: float):
        if max_concurrent < 1 or max_waiting < 0 or wait_timeout <= 0:
            raise ValueError("Configuración de capacidad no válida")
        self.max_concurrent = max_concurrent
        self.max_waiting = max_waiting
        self.wait_timeout = wait_timeout
        self._condition = asyncio.Condition()
        self._active = 0
        self._waiting = 0

    @property
    def active(self):
        return self._active

    @property
    def waiting(self):
        return self._waiting

    @asynccontextmanager
    async def slot(self):
        acquired = False
        async with self._condition:
            if self._active >= self.max_concurrent:
                if self._waiting >= self.max_waiting:
                    raise CapacityExceeded()
                self._waiting += 1
                try:
                    await asyncio.wait_for(
                        self._condition.wait_for(lambda: self._active < self.max_concurrent),
                        timeout=self.wait_timeout,
                    )
                except asyncio.TimeoutError as exc:
                    raise CapacityExceeded() from exc
                finally:
                    self._waiting -= 1
            self._active += 1
            acquired = True
        try:
            yield
        finally:
            if acquired:
                async with self._condition:
                    self._active -= 1
                    self._condition.notify(1)
