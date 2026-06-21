"""大模型客户端抽象层。

支持 mock(测试)、openai 和 openai-compatible 三种模式。
视觉模型通过 content 数组传递 base64 编码图像。
"""

import json

import httpx


_IMAGE_MIME = "image/jpeg"


class LLMClient:
    def __init__(self, provider: str = "mock", api_key: str = "", base_url: str = "", model: str = "") -> None:
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model or "gpt-4o-mini"

    def generate(self, prompt: str, images: list[str] | None = None) -> str:
        if self.provider == "mock" or not self.api_key:
            return (
                "根据边端检测结果、知识库内容和搜索摘要，当前场景可按云端复杂任务处理："
                "先确认目标类别与数量，再结合上下文判断是否存在异常，并给出调度建议。"
            )
        if self.provider in {"openai", "openai-compatible"}:
            return self._generate_openai_compatible(prompt, images)
        raise RuntimeError(f"未支持的大模型供应商：{self.provider}")

    def _generate_openai_compatible(self, prompt: str, images: list[str] | None = None) -> str:
        if not self.base_url:
            raise RuntimeError("LLM_BASE_URL 为空，无法调用 OpenAI-compatible 接口。")
        messages = [
            {"role": "system", "content": "你是端-边-云协同系统的云端智能体，负责复杂场景分析和决策建议。"},
            {"role": "user", "content": self._build_user_content(prompt, images)},
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            data = response.json()
        return str(data["choices"][0]["message"]["content"])

    @staticmethod
    def _build_user_content(prompt: str, images: list[str] | None) -> str | list[dict]:
        if not images:
            return prompt
        content: list[dict] = []
        for img in images:
            data_uri = img if img.startswith("data:") else f"data:{_IMAGE_MIME};base64,{img}"
            content.append({"type": "image_url", "image_url": {"url": data_uri}})
        content.append({"type": "text", "text": prompt})
        return content
