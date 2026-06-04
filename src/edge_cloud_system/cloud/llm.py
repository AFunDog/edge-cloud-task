class LLMClient:
    def __init__(self, provider: str = "mock", api_key: str = "") -> None:
        self.provider = provider
        self.api_key = api_key

    def generate(self, prompt: str) -> str:
        if self.provider == "mock" or not self.api_key:
            return (
                "根据边端检测结果、知识库内容和搜索摘要，当前场景可按云端复杂任务处理："
                "先确认目标类别与数量，再结合上下文判断是否存在异常，并给出调度建议。"
            )
        return f"已配置 {self.provider}，但当前示例未绑定具体供应商 SDK。"
