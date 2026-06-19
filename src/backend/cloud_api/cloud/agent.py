from backend.cloud_api.cloud.knowledge import KnowledgeBase
from backend.cloud_api.cloud.llm import LLMClient
from backend.cloud_api.cloud.search import SearchTool
from backend.shared.domain.models import (
    AgentRequest,
    AgentResponse,
    CloudAnalysisRequest,
    CloudAnalysisResponse,
    DetectionResult,
    EventSeverity,
)


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

    def analyze_event(self, request: CloudAnalysisRequest) -> CloudAnalysisResponse:
        query = self._event_query(request)
        traces: list[str] = []
        try:
            knowledge_hits = self.knowledge_base.search(query)
        except Exception as exc:
            knowledge_hits = []
            traces.append(f"knowledge_error={exc}")
        try:
            search_hits = self.search_tool.search(query)
        except Exception as exc:
            search_hits = []
            traces.append(f"search_error={exc}")
        prompt = self._build_event_prompt(request, knowledge_hits, search_hits)
        try:
            llm_report = self.llm.generate(prompt)
        except Exception as exc:
            llm_report = "云端大模型暂不可用，已使用规则分析生成降级报告。"
            traces.append(f"llm_error={exc}")
        risk_level = self._risk_level(request)
        reasoning = self._event_reasoning(request, knowledge_hits, search_hits)
        suggestions = self._event_suggestions(request, risk_level)
        conclusion = self._event_conclusion(request, risk_level)
        traces = [
            f"event_type={request.event.event_type}",
            f"risk_level={risk_level.value}",
            f"knowledge_hits={len(knowledge_hits)}",
            f"search_hits={len(search_hits)}",
            f"context_items={len(request.recent_context)}",
            *traces,
        ]
        traces.extend(f"knowledge: {hit}" for hit in knowledge_hits)
        traces.extend(f"search: {hit}" for hit in search_hits)
        return CloudAnalysisResponse(
            event_id=request.event.event_id,
            risk_level=risk_level,
            conclusion=conclusion,
            reasoning=reasoning,
            suggestions=suggestions,
            report=self._compose_report(request, conclusion, reasoning, suggestions, llm_report),
            used_search=bool(search_hits),
            used_knowledge=bool(knowledge_hits),
            traces=traces,
        )

    def _build_prompt(self, request: AgentRequest, knowledge_hits: list[str], search_hits: list[str]) -> str:
        return "\n".join(
            [
                "请结合边端检测上下文、知识库和搜索结果，输出：1. 场景理解；2. 风险判断；3. 边云调度建议；4. 后续操作。",
                f"问题：{request.question}",
                f"设备：{request.device_id or 'web-console'}",
                f"上下文：{request.context}",
                f"知识库：{knowledge_hits}",
                f"搜索：{search_hits}",
            ]
        )

    def _build_event_prompt(
        self,
        request: CloudAnalysisRequest,
        knowledge_hits: list[str],
        search_hits: list[str],
    ) -> str:
        detection_summary = self._detection_summary(request.detection)
        return "\n".join(
            [
                "你是机房/实验室边云协同安全监测系统的云端智能体。",
                "请基于边端事件摘要、YOLO-Pose 关键证据、知识库和搜索摘要，输出风险判断、判断依据、处置建议和报告。",
                f"事件类型：{request.event.event_type}",
                f"事件等级：{request.event.severity.value}",
                f"设备：{request.event.device_id}",
                f"帧：{request.event.frame_id or 'unknown'}",
                f"摘要：{request.event.summary}",
                f"证据：{request.event.evidence}",
                f"指标：{request.event.metrics}",
                f"检测摘要：{detection_summary}",
                f"最近上下文：{request.recent_context}",
                f"知识库：{knowledge_hits}",
                f"搜索：{search_hits}",
            ]
        )

    def _event_query(self, request: CloudAnalysisRequest) -> str:
        return " ".join(
            [
                "机房 实验室 安全 学习状态",
                request.event.event_type,
                request.event.summary,
                " ".join(request.event.evidence[:3]),
            ]
        )

    def _risk_level(self, request: CloudAnalysisRequest) -> EventSeverity:
        if request.event.severity == EventSeverity.CRITICAL:
            return EventSeverity.CRITICAL
        event_type = request.event.event_type
        if event_type in {"fall_suspected"}:
            return EventSeverity.CRITICAL
        if event_type in {"long_head_down", "crowding", "pose_uncertain"}:
            return EventSeverity.WARNING
        return request.event.severity

    def _event_conclusion(self, request: CloudAnalysisRequest, risk_level: EventSeverity) -> str:
        if risk_level == EventSeverity.CRITICAL:
            return f"事件 {request.event.event_type} 风险较高，需要人工立即确认。"
        if risk_level == EventSeverity.WARNING:
            return f"事件 {request.event.event_type} 需要关注，建议结合现场上下文复核。"
        return f"事件 {request.event.event_type} 当前可由边端记录和持续观察。"

    def _event_reasoning(
        self,
        request: CloudAnalysisRequest,
        knowledge_hits: list[str],
        search_hits: list[str],
    ) -> list[str]:
        reasoning = [
            f"边端上报摘要：{request.event.summary}",
            f"边端事件状态：{request.event.status.value}，原始等级：{request.event.severity.value}",
        ]
        if request.event.evidence:
            reasoning.append(f"边端证据：{'；'.join(request.event.evidence[:4])}")
        if request.event.metrics:
            reasoning.append(f"关键指标：{request.event.metrics}")
        if request.detection is not None:
            reasoning.append(self._detection_summary(request.detection))
        if knowledge_hits:
            reasoning.append("已参考本地知识库命中内容。")
        if search_hits:
            reasoning.append("已参考搜索工具返回的外部/离线摘要。")
        return reasoning

    def _event_suggestions(
        self,
        request: CloudAnalysisRequest,
        risk_level: EventSeverity,
    ) -> list[str]:
        event_type = request.event.event_type
        if event_type == "fall_suspected":
            return ["立即通知现场人员确认人员状态。", "保留截图、关键点和事件日志用于后续追溯。", "确认后再关闭该高风险事件。"]
        if event_type == "long_head_down":
            return ["先观察是否为正常阅读或操作设备。", "若持续出现，提醒管理人员关注学习状态或身体不适。", "结合最近多帧事件再决定是否升级。"]
        if event_type == "crowding":
            return ["核对现场是否存在违规聚集或围观。", "结合机房/实验室容量规则判断是否需要疏导。", "持续记录人数变化。"]
        if event_type == "pose_uncertain":
            return ["检查摄像头角度、遮挡和光照。", "等待更多帧确认，不建议单帧直接告警。", "必要时切换更适合上半身/头部姿态的模型。"]
        if risk_level == EventSeverity.CRITICAL:
            return ["立即人工复核。", "保留事件证据。"]
        if risk_level == EventSeverity.WARNING:
            return ["继续观察并记录上下文。", "必要时通知现场管理人员。"]
        return ["本地记录即可。", "保持边端持续检测。"]

    def _compose_report(
        self,
        request: CloudAnalysisRequest,
        conclusion: str,
        reasoning: list[str],
        suggestions: list[str],
        llm_report: str,
    ) -> str:
        return "\n".join(
            [
                f"事件报告：{request.event.event_type}",
                f"设备：{request.event.device_id}",
                f"结论：{conclusion}",
                "判断依据：",
                *[f"- {item}" for item in reasoning],
                "处置建议：",
                *[f"- {item}" for item in suggestions],
                f"智能体补充：{llm_report}",
            ]
        )

    def _detection_summary(self, detection: DetectionResult | None) -> str:
        if detection is None:
            return "无同步检测结果。"
        return (
            f"检测到 {len(detection.detections)} 个目标，"
            f"模型任务 {detection.model_task or '--'}，"
            f"推理耗时 {detection.inference_ms:.1f} ms，"
            f"姿态 {detection.pose.action.value if detection.pose else '--'}。"
        )
