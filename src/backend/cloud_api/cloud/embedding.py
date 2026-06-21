"""文本 Embedding 客户端 —— 调用 OpenAI 兼容的 Embedding API。"""

import httpx


class EmbeddingClient:
    def __init__(self, provider: str = "", api_key: str = "", base_url: str = "", model: str = "text-embedding-v3") -> None:
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    @property
    def enabled(self) -> bool:
        return bool(self.provider and self.api_key and self.base_url)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.enabled:
            return [[0.0] * 1024 for _ in texts]
        results: list[list[float]] = []
        for text in texts:
            payload = {"model": self.model, "input": text}
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"{self.base_url}/embeddings",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                results.append(list(data["data"][0]["embedding"]))
        return results
