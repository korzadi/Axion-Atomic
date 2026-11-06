FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api ./api
COPY agent ./agent
COPY core ./core
COPY rag ./rag
COPY sandbox ./sandbox
COPY audit ./audit
COPY migrations ./migrations
USER appuser
EXPOSE 8000
# Las migraciones son una operación administrativa explícita; nunca se ejecutan
# automáticamente al iniciar o reiniciar el contenedor.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
