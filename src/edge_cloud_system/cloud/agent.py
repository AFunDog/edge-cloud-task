from edge_cloud_system.cloud.knowledge import KnowledgeBase
from edge_cloud_system.cloud.llm import LLMClient
from edge_cloud_system.cloud.search import SearchTool
from edge_cloud_system.domain.models import AgentRequest, AgentResponse


class CloudAgent:
    def __init__(self, llm: LLMClient, search_tool: SearchTool, knowledge_base: KnowledgeBase) -> None:
        self.llm = llm
        self.search_tool = search_tool
        self.knowledge_base = knowledge_base

    def answer(self, request: AgentRequest) -> AgentResponse:
        knowledge_hits = self.knowledge_base.search(request.question)
        search_hits = self.search_tool.search(request.question)
        prompt = self._build_prompt(request, knowledge_hits, search_hits)
        answer = self.llm.generate(prompt)
        traces = [
            f"knowledge_hits={len(knowledge_hits)}",
            f"search_hits={len(search_hits)}",
            f"context_keys={','.join(request.context.keys()) or 'none'}",
        ]
        if knowledge_hits:
            traces.extend(f"knowledge: {hit}" for hit in knowledge_hits)
        traces.extend(f"search: {hit}" for hit in search_hits)
        return AgentResponse(
            answer=answer,
            used_search=bool(search_hits),
            used_knowledge=bool(knowledge_hits),
            traces=traces,
        )

    def _build_prompt(self, request: AgentRequest, knowledge_hits: list[str], search_hits: list[str]) -> str:
        return "\n".join(
            [
                f"问题：{request.question}",
                f"设备：{request.device_id or 'management-console'}",
                f"上下文：{request.context}",
                f"知识库：{knowledge_hits}",
                f"搜索：{search_hits}",
            ]
        )
