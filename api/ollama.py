import httpx
from api.config import settings


async def chat(messages, temperature=0.2, max_tokens=2048):
    payload = {
        "model": settings.chat_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": settings.num_ctx,
        },
    }
    async with httpx.AsyncClient(timeout=240) as client:
        response = await client.post(
            settings.ollama_base_url.rstrip("/") + "/api/chat",
            json=payload,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]


async def embed(value: str):
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            settings.ollama_base_url.rstrip("/") + "/api/embeddings",
            json={"model": settings.embed_model, "prompt": value},
        )
        response.raise_for_status()
        return response.json()["embedding"]
