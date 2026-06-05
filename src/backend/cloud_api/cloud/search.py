import httpx


class SearchTool:
    def __init__(self, provider: str = "local", api_url: str = "", api_key: str = "") -> None:
        self.provider = provider
        self.api_url = api_url
        self.api_key = api_key

    def search(self, query: str) -> list[str]:
        if self.provider == "local":
            return [f"离线搜索摘要：当前问题为“{query}”，真实联网搜索可在 SearchTool 中接入。"]
        if self.provider == "http-json":
            return self._search_http_json(query)
        raise RuntimeError(f"未支持的搜索供应商：{self.provider}")

    def _search_http_json(self, query: str) -> list[str]:
        if not self.api_url:
            raise RuntimeError("SEARCH_API_URL 为空，无法调用搜索接口。")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        with httpx.Client(timeout=20) as client:
            response = client.get(self.api_url, params={"q": query}, headers=headers)
            response.raise_for_status()
            data = response.json()
        if isinstance(data, list):
            return [str(item) for item in data[:5]]
        results = data.get("results", [])
        if isinstance(results, list):
            return [str(item) for item in results[:5]]
        return [str(data)[:500]]

