"""边云任务调度器。

基于关键词匹配判断任务复杂度：简单任务留在边端，
复杂任务（语义分析/报告生成等）转发云端 Agent。
"""

from backend.shared.domain.models import ExecutionTarget, ScheduleDecision, TaskComplexity, TaskRequest


class TaskScheduler:
    complex_keywords = {
        "语义",
        "解释",
        "报告",
        "跨模态",
        "检索",
        "为什么",
        "异常原因",
        "联网",
        "知识库",
        "分析",
        "风险",
        "决策",
    }

    def decide(self, request: TaskRequest) -> ScheduleDecision:
        task_text = request.task.lower()
        if any(keyword.lower() in task_text for keyword in self.complex_keywords):
            return ScheduleDecision(
                target=ExecutionTarget.CLOUD,
                complexity=TaskComplexity.COMPLEX,
                reason="任务包含语义理解、检索、风险判断或报告生成需求，转发云端智能体处理。",
            )
        return ScheduleDecision(
            target=ExecutionTarget.EDGE,
            complexity=TaskComplexity.SIMPLE,
            reason="任务可由边缘侧摄像头采集、YOLO 检测和本地规则完成。",
        )
