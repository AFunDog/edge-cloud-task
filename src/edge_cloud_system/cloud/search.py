class SearchTool:
    def __init__(self, provider: str = "local") -> None:
        self.provider = provider

    def search(self, query: str) -> list[str]:
        if self.provider == "local":
            return [f"离线搜索摘要：当前问题为“{query}”，真实联网搜索可在 SearchTool 中接入。"]
        return [f"搜索供应商 {self.provider} 尚未配置适配器。"]
