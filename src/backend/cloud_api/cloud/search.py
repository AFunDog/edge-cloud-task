"""联网搜索工具。

支持三种模式：
- local: 离线占位
- tavily: Tavily Search API (联网搜索)
- http-json: 通用 JSON 搜索 API
"""

import httpx


class SearchTool:
    def __init__(self, provider: str = "local", api_url: str = "", api_key: str = "") -> None:
        self.provider = provider
        self.api_url = api_url
        self.api_key = api_key

    def search(self, query: str) -> list[str]:
        if self.provider == "local":
            return [f'离线搜索摘要：当前问题为"{query}"，真实联网搜索可在 SearchTool 中接入。']
        if self.provider == "tavily":
            return self._search_tavily(query)
        if self.provider == "http-json":
            return self._search_http_json(query)
        raise RuntimeError(f"未支持的搜索供应商：{self.provider}")

    def _search_tavily(self, query: str) -> list[str]:
        if not self.api_key:
            return [f"Tavily API Key 未配置。"]
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://api.tavily.com/search",
                json={
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": 5,
                    "include_raw_content": "markdown",
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results", [])
        if not results:
            return ["Tavily 未返回搜索结果。"]
        snippets = []
        for r in results[:5]:
            title = r.get("title", "")
            content = r.get("content", "") or r.get("raw_content", "")
            url = r.get("url", "")
            snippets.append(f"{title}\n{content[:300]}\n来源: {url}")
        if data.get("answer"):
            snippets.insert(0, f"[AI 回答] {data['answer']}")
        return snippets

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

