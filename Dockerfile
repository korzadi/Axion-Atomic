FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser
# Docker CLI oficial (solo cliente; sin daemon) para el sandbox AGT-04.
# Se instala desde el repositorio firmado de Docker Inc.; la API lo usa solo
# contra el daemon dedicado con TLS (SANDBOX_DOCKER_HOST=tcp://...).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli \
 && apt-get purge -y gnupg curl \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api ./api
COPY agent ./agent
COPY .agents/skills ./.agents/skills
COPY core ./core
COPY rag ./rag
COPY sandbox ./sandbox
COPY audit ./audit
COPY migrations ./migrations
USER appuser
EXPOSE 8000
# Las migraciones son una operación administrativa explícita; nunca se ejecutan
# automáticamente al iniciar o reiniciar el contenedor.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "64", "--backlog", "128", "--timeout-keep-alive", "5"]
