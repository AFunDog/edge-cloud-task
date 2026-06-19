# 基于 YOLO-Pose 与云端智能体的边云协同安全监测系统实现方案

## 1. 项目定位

本项目目标是实现一个面向机房或实验室场景的边云协同安全与学习状态监测系统。系统不是单纯展示 YOLO-Pose 检测结果，而是围绕“边端实时感知、云端复杂分析、管理平台可视化”构建一个完整应用闭环。

主线原则：

- 简单任务边缘处理：边端优先完成实时检测、基础规则判断和本地告警，保证低延迟和断网可用。
- 复杂任务云端决策：云端不重复跑 YOLO，而是接收边端摘要、截图、关键点和上下文，由 Agent 结合知识库、搜索和 LLM 生成风险判断与处置建议。
- 管理平台可视化：平台必须清楚展示任务在哪里完成、为什么转云端、云端如何判断，以及最终处置建议是什么。

## 2. 当前代码基础

当前仓库已经具备可复用基础：

- 边端 FastAPI：`src/backend/edge_api/main.py`
- 云端 FastAPI：`src/backend/cloud_api/main.py`
- YOLO 检测：`src/backend/edge_api/runtime/detector.py`
- 姿态规则：`src/backend/edge_api/runtime/pose.py`
- 边云调度：`src/backend/edge_api/runtime/pipeline.py`
- 云端 Agent：`src/backend/cloud_api/cloud/agent.py`
- 本地知识库：`src/backend/cloud_api/cloud/knowledge.py`
- 搜索工具：`src/backend/cloud_api/cloud/search.py`
- 运行状态缓存：`src/backend/shared/core/state.py`
- 共享模型：`src/backend/shared/domain/models.py`
- 边端工作台：`src/frontend/edge_frontend/`
- 云端控制台：`src/frontend/cloud_frontend/`
- Docker 编排：`docker-compose.yml`

因此后续工作应以“扩展事件模型和分析链路”为主，不重写已有 YOLO、WebRTC、Agent 和前端骨架。

## 3. 目标架构

```text
摄像头/视频流
    |
    v
边端采集器 EdgeCollector
    |
    v
YOLO-Pose 检测器 YoloDetector
    |
    v
边端事件规则 EdgeEventAnalyzer
    |
    +--> 简单事件：本地记录、本地展示、本地状态更新
    |
    +--> 复杂/不确定事件：生成 EventReportRequest 上传云端
             |
             v
        云端 Agent 分析
             |
             v
        风险等级 / 判断依据 / 处置建议 / 事件报告
             |
             v
        云端控制台展示与日志归档
```

边端负责实时性，云端负责解释性和综合判断。

## 4. 核心能力拆分

### 4.1 边端实时感知

边端继续复用现有采集和推理链路：

- `EdgeCollector` 读取摄像头帧。
- `YoloDetector` 输出人体框、关键点、置信度、模型耗时。
- `PoseAnalyzer` 输出基础姿态动作。
- `EdgePipeline` 统一生成检测结果、任务日志和云端同步任务。

需要新增或增强：

- `EdgeEventAnalyzer`：基于最近 N 帧状态判断业务事件。
- `EdgeEventState`：维护短时间窗口，例如低头持续时间、人数变化、聚集持续时间。
- `SafetyEvent` 模型：统一描述边端识别出来的安全/学习状态事件。

### 4.2 边端简单事件

边端应优先独立处理以下事件：

| 事件 | 边端判断依据 | 默认处理 |
| --- | --- | --- |
| 是否有人 | person 检测数量 | 本地展示 |
| 人数统计 | 当前帧 person 数量 | 本地展示 |
| 普通姿态 | 头部、上半身、举手等规则 | 本地展示 |
| 举手 | 手腕/肘部高于肩部 | 本地事件 |
| 短时低头 | head_down 单帧或短时间出现 | 本地事件 |
| 边端离线云端 | 云端健康检查失败 | 本地继续运行 |

这些事件不应频繁调用云端 Agent。

### 4.3 边端复杂或不确定事件

以下事件应上传云端分析：

| 事件 | 触发条件 | 上传内容 |
| --- | --- | --- |
| 长时间低头 | 连续超过阈值，例如 10 秒 | 摘要、持续时间、关键点、截图 |
| 疑似摔倒 | 人体框宽高比异常、关键点整体接近水平、低置信度 | 最近帧摘要、关键点、截图 |
| 多人聚集 | 人数超过阈值并持续 | 人数、持续时间、截图 |
| 低置信度姿态 | 关键点缺失或规则冲突 | 置信度、规则证据、截图 |
| 多事件组合 | 例如多人聚集 + 长时间低头 | 事件列表、上下文 |
| 需要解释的行为 | 用户主动询问或策略触发 | 问题、检测上下文 |

上传云端的目标不是重新检测，而是“解释、归因、定级、建议”。

## 5. 建议数据模型

优先在 `src/backend/shared/domain/models.py` 中维护边端、云端和管理平台之间的共享契约。

阶段 1 已落地以下模型：

### 5.1 SafetyEvent

```python
class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class EventStatus(str, Enum):
    EDGE_RESOLVED = "edge_resolved"
    CLOUD_PENDING = "cloud_pending"
    CLOUD_ANALYZED = "cloud_analyzed"

class SafetyEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    event_type: str
    device_id: str
    frame_id: str | None = None
    severity: EventSeverity = EventSeverity.INFO
    status: EventStatus = EventStatus.EDGE_RESOLVED
    summary: str
    evidence: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

`SafetyEvent` 是边端事件的统一描述，不直接绑定具体规则。后续低头、摔倒、聚集、低置信度等规则都会输出这个模型。

### 5.2 CloudAnalysisRequest

```python
class CloudAnalysisRequest(BaseModel):
    event: SafetyEvent
    detection: DetectionResult | None = None
    image_jpeg_base64: str | None = None
    recent_context: list[dict] = Field(default_factory=list)
```

### 5.3 CloudAnalysisResponse

```python
class CloudAnalysisResponse(BaseModel):
    event_id: str
    risk_level: EventSeverity
    conclusion: str
    reasoning: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    report: str
    used_search: bool = False
    used_knowledge: bool = False
    traces: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

这些模型将成为边端、云端和管理平台之间的统一契约。

### 5.4 RuntimeState 状态层

阶段 1 已扩展 `src/backend/shared/core/state.py`：

- `_events: deque[SafetyEvent]`：保存最近 200 条边端安全/学习状态事件。
- `_analysis_results: deque[CloudAnalysisResponse]`：保存最近 200 条云端 Agent 分析结果。
- `add_event(event)`：写入边端事件。
- `add_analysis_result(result)`：写入云端分析结果，并将对应事件状态更新为 `cloud_analyzed`。
- `latest_event(device_id=None)`：获取最新事件，支持按设备过滤。
- `snapshot()`：现在返回 `events` 和 `analysis_results` 字段，云端 `/api/state` 可直接展示事件列表。

边端 WebSocket 初始快照也已同步包含这两个字段，前端 TypeScript 类型已补充 `SafetyEvent` 和 `CloudAnalysisResponse`。

## 6. 边端实现方案

### 6.1 新增事件分析器

建议新增：

```text
src/backend/edge_api/runtime/events.py
```

职责：

- 接收 `DetectionResult` 和 `PoseAnalysis`。
- 维护最近 N 帧状态。
- 输出 `SafetyEvent` 列表。
- 标记事件是否需要云端分析。

初版规则建议：

- `person_count`：每帧人数统计。
- `head_down_duration`：连续低头超过阈值转云端。
- `fall_suspected`：人体框宽高比异常，或关键点整体接近水平。
- `crowding`：人数超过阈值并持续。
- `pose_uncertain`：关键点不足或姿态为 unknown。

阶段 2 已实现 `EdgeEventAnalyzer` 和 `EdgeEventAnalyzerConfig`：

- `person_count`：人数发生变化时生成本地事件，状态为 `edge_resolved`。
- `pose_raising_hand`、`pose_head_down`、`pose_head_left`、`pose_head_right`、`pose_upper_body_left`、`pose_upper_body_right`：由边端姿态规则稳定命中时生成本地事件。
- `long_head_down`：连续低头超过阈值，生成 `warning / cloud_pending` 事件。
- `fall_suspected`：人体框横向比例异常且姿态置信度偏低，生成 `critical / cloud_pending` 事件。
- `crowding`：人数超过阈值并持续，生成 `warning / cloud_pending` 事件。
- `pose_uncertain`：关键点不足、姿态为 unknown 或规则置信度过低，生成 `warning / cloud_pending` 事件。

分析器内部带短期状态和冷却时间，避免同一事件每帧重复刷屏。阶段 2 只负责把复杂事件标记成云端候选；真正上传云端并调用 Agent 的事件分析接口留给阶段 3。

### 6.2 接入 Pipeline

修改：

```text
src/backend/edge_api/runtime/pipeline.py
```

当前流程：

```text
DetectionResult -> PoseAnalyzer -> TaskScheduler -> TaskLog -> CloudClient
```

目标流程：

```text
DetectionResult -> PoseAnalyzer -> EdgeEventAnalyzer -> TaskScheduler -> EdgeCycle -> CloudClient
```

`EdgeCycle` 应增加：

- `events: list[SafetyEvent]`
- `cloud_analysis: CloudAnalysisResponse | None`
- `cloud_analysis_requested: bool`

阶段 2 已接入：

- `EdgePipeline.process()` 在姿态分析之后调用 `EdgeEventAnalyzer.analyze()`。
- `EdgeCycle` 已增加 `events: list[SafetyEvent]`。
- 如果存在 `cloud_pending` 事件，调度决策会切到 `cloud / complex`，并在任务日志中说明边端生成了复杂安全事件。
- `EdgeCollector` 会把事件写入 `RuntimeState`，并通过 WebSocket 广播 `event` 消息。
- 本地边端接口新增 `POST /api/edge/events`，独立 runner 模式也能把事件写入边端 API 状态层。
- 阶段 3 已继续扩展 `EdgeCycle.cloud_analysis_requested` 和 `EdgeCycle.cloud_analysis_results`，用于记录云端结构化分析返回。

### 6.3 边端上报

扩展 `CloudClient`：

```text
src/backend/edge_api/runtime/client.py
```

新增：

- `publish_event(event: SafetyEvent)`
- `request_cloud_analysis(request: CloudAnalysisRequest)`

保留现有：

- `publish_detection`
- `publish_status`
- `publish_task_log`
- `ask_agent`

阶段 2 已补充本地边端上报能力：

- `EdgeClient.publish_event(event)` -> `POST /api/edge/events`

阶段 3 已补充云端上报能力：

- `CloudClient.publish_event(event)` -> `POST /api/events`
- `CloudClient.request_cloud_analysis(request)` -> `POST /api/events/analyze`
- `EdgePipeline.sync_cloud()` 会先同步检测结果和事件，再对 `cloud_pending` 事件请求云端 Agent 结构化分析。
- `EdgeCollector` 会把云端分析结果写回本地 `RuntimeState`，并通过 WebSocket 广播 `analysis_result`。

## 7. 云端实现方案

### 7.1 新增事件路由

建议新增：

```text
src/backend/cloud_api/routes/events.py
```

接口：

- `POST /api/events`：接收边端事件。
- `GET /api/events`：查看事件列表。
- `POST /api/events/analyze`：云端 Agent 分析复杂事件。

阶段 3 已落地：

- `POST /api/events`：接收并幂等写入 `SafetyEvent`。
- `GET /api/events`：返回运行时事件列表。
- `POST /api/events/analyze`：接收 `CloudAnalysisRequest`，调用 `CloudAgent.analyze_event()`，写入 `CloudAnalysisResponse`。
- `GET /api/events/analysis`：返回云端分析结果列表。
- `cloud_api/main.py` 已注册事件路由。

### 7.2 云端事件状态

扩展：

```text
src/backend/shared/core/state.py
```

新增缓存：

- `_events: deque[SafetyEvent]`
- `_analysis_results: deque[CloudAnalysisResponse]`

后续可迁移到 PostgreSQL。

阶段 3 已增强状态写入：

- `RuntimeState.add_event()` 按 `event_id` 幂等更新，避免事件先上报再分析时重复出现。
- `RuntimeState.add_analysis_result()` 写入分析结果后，会把对应事件状态更新为 `cloud_analyzed`。

### 7.3 Agent 分析提示词

扩展：

```text
src/backend/cloud_api/cloud/agent.py
```

新增方法：

- `analyze_event(request: CloudAnalysisRequest) -> CloudAnalysisResponse`

Agent 输出结构：

1. 风险等级
2. 判断依据
3. 可能原因
4. 处置建议
5. 是否需要人工确认
6. 面向报告的完整文字

阶段 3 已落地 `CloudAgent.analyze_event()`：

- 输入：`CloudAnalysisRequest(event, detection, image_jpeg_base64, recent_context)`。
- 输出：`CloudAnalysisResponse(event_id, risk_level, conclusion, reasoning, suggestions, report, used_search, used_knowledge, traces)`。
- 风险等级根据边端事件等级和事件类型归一化，例如 `fall_suspected` 会保持或升级为 `critical`。
- 处置建议按事件类型生成，例如疑似摔倒、长时间低头、多人聚集、低置信度姿态分别给出不同建议。
- 默认测试继续使用 mock LLM、local search、本地知识库，不触发外网或付费模型。

### 7.4 知识库内容

建议扩展：

```text
data/knowledge/
```

新增机房/实验室规则文本，例如：

- 机房安全管理规范
- 实验室人员异常姿态处置建议
- 长时间低头与学习状态监测说明
- 疑似摔倒事件处置流程
- 多人聚集风险说明

云端 Agent 应把这些知识库命中内容写入 `traces`。

## 8. 管理平台实现方案

### 8.1 边端工作台

保留当前实时视频主界面，增强：

- 当前人数
- 当前姿态
- 边端事件列表
- 事件是否已上传云端
- 云端候选标识
- 最近一次云端分析摘要

重点突出“边端实时处理”。

阶段 4 已落地：

- 右侧实时指标增加边端事件数、云端候选数、云端分析数。
- 新增“边云事件”列表，展示事件类型、风险等级、处理状态和摘要。
- 新增“云端分析”摘要，展示最近一次 Agent 结论、建议、是否使用知识库/搜索。
- WebSocket `event` 和 `analysis_result` 消息会实时更新页面状态。

### 8.2 云端控制台

增强当前云端控制台：

- 全局事件总览
- 异常事件列表
- 风险等级颜色标识
- 云端 Agent 分析结果卡片
- 边云调度日志
- 智能体对话

重点突出“云端复杂分析”。

建议标签：

- 监控：边端状态、最新快照、事件概览。
- 事件：异常事件列表、风险等级、分析状态。
- 智能体：对话和事件分析。
- 日志：边云调度和任务日志。

阶段 4 已落地：

- 顶部标签新增“事件”。
- 监控页右侧新增边云调度摘要、最近事件、最近 Agent 分析。
- 事件页新增全局统计：总事件、待云端、高风险、分析报告。
- 事件页展示异常事件列表，包含边端完成、等待云端、云端已分析三种状态。
- 事件页展示云端 Agent 分析卡片，包括风险等级、判断依据、处置建议、知识库/搜索使用情况。

## 9. Docker 与部署方案

保持现有 Docker Compose 结构：

- `postgres`：数据基础设施。
- `cloud`：云端 FastAPI。
- `edge`：边端 FastAPI。
- `cloud-web`：云端控制台。
- `edge-web`：边端工作台。
- `edge-runner`：可选摄像头采集运行器。

后续增强：

- 云端后端维护数据库 schema 和 pgvector 扩展。
- 边端和云端均通过 `.env` 配置服务地址。
- 默认测试和演示使用 mock LLM、local search、本地知识库。
- 真实 LLM/API Key 仅放 `.env`，不提交仓库。

## 10. 分阶段实现计划

### 阶段 1：事件模型与状态层

目标：

- 在 `models.py` 增加 `SafetyEvent`、`CloudAnalysisRequest`、`CloudAnalysisResponse`。
- 在 `RuntimeState` 增加事件和分析结果缓存。
- 增加对应单元测试。

验收：

- 可以创建事件。
- 云端 `/api/state` 能返回事件列表。

实现状态：已完成。

落地文件：

- `src/backend/shared/domain/models.py`
- `src/backend/shared/core/state.py`
- `src/backend/edge_api/routes/stream.py`
- `src/frontend/cloud_frontend/src/types.ts`
- `src/frontend/edge_frontend/src/types.ts`
- `tests/test_events_state.py`

验证命令：

```powershell
python -m pytest tests/test_events_state.py
python -m compileall src/backend/shared src/backend/edge_api/routes/stream.py
```

### 阶段 2：边端事件规则

目标：

- 新增 `events.py`。
- 实现人数、低头、疑似摔倒、多人聚集、低置信度规则。
- 接入 `EdgePipeline`。

验收：

- 边端能在不依赖云端的情况下生成本地事件。
- 复杂事件能标记为云端候选。

实现状态：已完成。

落地文件：

- `src/backend/edge_api/runtime/events.py`
- `src/backend/edge_api/runtime/pipeline.py`
- `src/backend/edge_api/runtime/collector.py`
- `src/backend/edge_api/runtime/client.py`
- `src/backend/edge_api/runtime/runner.py`
- `src/backend/edge_api/routes/edge.py`
- `src/frontend/edge_frontend/src/api.ts`
- `src/frontend/edge_frontend/src/App.vue`
- `tests/test_edge_events.py`
- `tests/test_edge_pipeline.py`

验证命令：

```powershell
python -m pytest tests/test_edge_events.py tests/test_edge_pipeline.py tests/test_events_state.py
python -m compileall src/backend/edge_api/runtime/events.py src/backend/edge_api/runtime/pipeline.py src/backend/edge_api/runtime/collector.py src/backend/edge_api/runtime/client.py src/backend/edge_api/routes/edge.py
```

### 阶段 3：云端事件接收与 Agent 分析

目标：

- 新增 `cloud_api/routes/events.py`。
- 扩展 `CloudAgent.analyze_event()`。
- 生成结构化风险分析结果。

验收：

- 边端可上传事件。
- 云端可返回风险等级、依据、建议和报告。

实现状态：已完成。

落地文件：

- `src/backend/cloud_api/routes/events.py`
- `src/backend/cloud_api/cloud/agent.py`
- `src/backend/cloud_api/main.py`
- `src/backend/edge_api/runtime/client.py`
- `src/backend/edge_api/runtime/pipeline.py`
- `src/backend/edge_api/runtime/collector.py`
- `src/frontend/edge_frontend/src/api.ts`
- `src/frontend/edge_frontend/src/App.vue`
- `src/backend/shared/core/state.py`
- `tests/test_agent.py`
- `tests/test_cloud_events.py`
- `tests/test_edge_pipeline.py`

验证命令：

```powershell
python -m pytest tests/test_agent.py tests/test_cloud_events.py tests/test_edge_pipeline.py tests/test_events_state.py
python -m compileall src/backend/cloud_api src/backend/edge_api/runtime/pipeline.py src/backend/edge_api/runtime/client.py src/backend/edge_api/runtime/collector.py
```

### 阶段 4：前端展示

目标：

- 边端页面展示本地事件和云端候选。
- 云端页面展示事件列表、风险等级和 Agent 分析。
- 日志展示“边端完成/云端分析”的任务来源。

验收：

- 演示时能清楚看到边云分工。
- 管理平台不只是姿态 Demo，而是安全监测系统。

实现状态：已完成。

落地文件：

- `src/frontend/edge_frontend/src/App.vue`
- `src/frontend/edge_frontend/src/styles.css`
- `src/frontend/cloud_frontend/src/App.vue`
- `src/frontend/cloud_frontend/src/styles.css`

验证命令：

```powershell
npm run build # 在 src/frontend/edge_frontend
npm run build # 在 src/frontend/cloud_frontend
python -m pytest
python -m compileall src
```

### 阶段 5：持久化与报告

目标：

- 将事件和分析结果写入 PostgreSQL。
- 使用 pgvector 或知识库扩展事件检索。
- 增加事件报告导出能力。

验收：

- 重启后关键事件不丢失。
- 可以查看历史异常和云端分析报告。

## 11. 演示闭环设计

推荐最终演示流程：

1. 启动 Docker Compose 或本地边云服务。
2. 边端摄像头开始实时检测。
3. 正常姿态、人数统计、举手在边端完成。
4. 人为制造长时间低头或异常姿态。
5. 边端生成异常事件并标记“上传云端”。
6. 云端 Agent 返回风险等级、判断依据和处置建议。
7. 云端控制台显示事件报告。
8. 日志页展示调度链路：边端检测 -> 本地规则 -> 云端分析 -> 管理平台展示。

## 12. 实现约束

- 优先复用现有代码，不重写 YOLO、WebRTC、Agent 基础结构。
- 新增接口时优先补充 `shared/domain/models.py`。
- 默认测试使用 mock LLM、local search、本地知识库。
- 不提交真实 API Key、模型服务地址或私有知识库内容。
- Docker 配置保持云端服务和管理平台可独立启动。
