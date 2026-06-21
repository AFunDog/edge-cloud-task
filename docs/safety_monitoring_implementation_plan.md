# 基于 YOLO-Pose 与云端智能体的边云协同安全监测系统实现方案

## 1. 项目定位

本项目目标是实现一个面向机房或实验室场景的边云协同安全与学习状态监测系统。系统不是单纯展示 YOLO-Pose 检测结果，而是围绕"边端实时感知、云端复杂分析、管理平台可视化"构建一个完整应用闭环。

核心能力：

- **人物与姿态识别**：基于 YOLO-Pose 实时检测画面中的人员数量、关键点、姿态动作。
- **安全事件分析预警**：边端规则引擎识别低头、摔倒、聚集、异常姿态等安全事件，云端 Agent 结合大模型和知识库进行深度分析定级。
- **合理性分析**：结合本地知识库中的机房/实验室规则，分析画面中人物的时间合理性（是否在允许时段）、人数合理性（是否超容量），发现异常自动记录。
- **事件持久化与追溯**：所有事件和分析结果写入 PostgreSQL，支持历史检索和报告导出。
- **自然语言日志分析**：管理员可通过对话界面让智能体查询历史事件、分析隐患趋势、生成检查报告。

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

实现状态：已完成。

已落地能力：

- 云端启动时由后端自主维护 PostgreSQL 表结构，不依赖 `data/postgres/init/001-enable-pgvector.sql`：
  - `cloud_events`：保存边端事件完整 payload、状态、证据、指标和检索文本。
  - `cloud_analysis_results`：保存 Agent 分析完整 payload、报告、判断依据、处置建议和检索文本。
- `POSTGRES_PERSISTENCE_ENABLED=true` 时，`/api/events` 与 `/api/events/analyze` 会同步写入 PostgreSQL；Docker Compose 云端服务默认开启。
- 云端启动后会按 `EVENT_HISTORY_LIMIT` 从 PostgreSQL 恢复事件和分析结果到运行态，控制台重启后仍能看到历史异常。
- 新增事件检索接口 `GET /api/events/search?q=...`，可按事件类型、摘要、证据、指标和 Agent 报告内容检索。
- 新增事件报告接口 `GET /api/events/{event_id}/report`，返回可导出的 Markdown 报告，包含边端摘要、证据、指标、云端结论、判断依据和处置建议。
- 云端控制台事件页支持查看报告并导出 Markdown。

落地文件：

- `src/backend/shared/domain/models.py`
- `src/backend/shared/core/config.py`
- `src/backend/shared/core/state.py`
- `src/backend/cloud_api/cloud/database.py`
- `src/backend/cloud_api/dependencies.py`
- `src/backend/cloud_api/main.py`
- `src/backend/cloud_api/routes/events.py`
- `src/frontend/cloud_frontend/src/api.ts`
- `src/frontend/cloud_frontend/src/types.ts`
- `src/frontend/cloud_frontend/src/App.vue`
- `src/frontend/cloud_frontend/src/styles.css`
- `docker-compose.yml`
- `.env.example`
- `tests/test_cloud_events.py`
- `tests/test_events_state.py`

配置说明：

```env
POSTGRES_PERSISTENCE_ENABLED=true
POSTGRES_VECTOR_ENABLED=true
EVENT_HISTORY_LIMIT=200
```

本地不想连接数据库时保持 `POSTGRES_PERSISTENCE_ENABLED=false`，系统仍使用内存态运行，测试默认不会触发真实 PostgreSQL。

验证命令：

```powershell
python -m pytest tests/test_cloud_events.py tests/test_events_state.py
npm run build # 在 src/frontend/cloud_frontend
python -m pytest
python -m compileall src
```

### 阶段 6：知识库规则增强与合理性分析

目标：

- 扩展本地知识库，补充机房/实验室的场所规则（开放时间、容量上限、行为规范、授权策略等）。
- 新增合理性事件类型，边端根据时间和人数规则对画面进行实时合规判断。
- 云端 Agent 能够结合知识库规则对"不合理"场景生成解释性分析。

验收：

- 知识库可检索到机房/实验室规则内容。
- 边端能在非允许时段检测到人员时生成 `unauthorized_time` 事件。
- 边端能在人数超出容量上限时生成 `excessive_people` 事件。
- 云端 Agent 分析时引用知识库命中内容作为判断依据。
- 管理员可通过前端查看合理性分析结果。

实现状态：已完成。

**6.1 知识库内容扩展**

在 `data/knowledge/` 下新增规则文件：

```
data/knowledge/
  edge.txt              # 保留：边端基本能力说明
  room_rules.txt        # 新增：机房/实验室场所规则
  safety_regulations.txt # 新增：安全管理规范
```

`room_rules.txt` 应包含：

- 场所开放时段（例如 08:00-22:00）。
- 场所容量上限（例如最多 15 人）。
- 允许的行为和禁止的行为。
- 异常情况处置流程。

`safety_regulations.txt` 应包含：

- 人员异常姿态与安全隐患的对应关系。
- 长时间低头的健康风险说明。
- 多人聚集的管理规定。
- 摔倒事件的应急处置流程。
- 非开放时段进入的报警策略。

**6.2 合理性事件模型**

在 `domain/models.py` 中新增 `inference_context` 字段或扩展 `SafetyEvent.metrics`：

- `current_time`：当前时间（ISO 格式），供知识库匹配时段规则。
- `person_count`：当前人数，供知识库匹配容量规则。
- `room_capacity`：场所容量上限（从知识库或配置读取）。
- `allowed_hours`：允许时段描述（从知识库提取）。

新增事件类型：

| 事件类型 | 触发条件 | 严重程度 | 状态 |
| --- | --- | --- | --- |
| `unauthorized_time` | 当前时间不在场所开放时段内，且检测到人员 | WARNING | CLOUD_PENDING |
| `excessive_people` | 人数超过场所容量上限 | WARNING | CLOUD_PENDING |
| `unusual_duration` | 同一人员连续在画面中超过异常时长阈值 | INFO → WARNING | EDGE_RESOLVED / CLOUD_PENDING |

**6.3 边端合理性检查**

扩展 `EdgeEventAnalyzer`：

- 新增 `_time_validity_event()` 方法：检查当前时间是否在允许时段内。
- 新增 `_capacity_event()` 方法：检查人数是否超过容量上限。
- 规则阈值从 `EdgeEventAnalyzerConfig` 可配置。
- 合理性事件标注 `CLOUD_PENDING`，携带时间、人数等上下文指标。

**6.4 云端合理性分析**

扩展 `CloudAgent.analyze_event()`：

- 对 `unauthorized_time` 和 `excessive_people` 事件生成专项分析。
- 提示词中加入知识库规则匹配结果作为判断依据。
- 处置建议中引用知识库规则原文。

新增事件类型的处置建议：

- `unauthorized_time`：核实是否为授权加班或设备维护；记录人员信息和逗留时段；通知场所管理员。
- `excessive_people`：检查是否临时活动或违规聚集；建议分流或限流；核对现场容量标识。

**6.5 前端展示增强**

- 边端工作台：增加"合理性检查"指标（当前时段状态、人数/容量比）。
- 云端控制台事件列表：显示 `unauthorized_time`、`excessive_people` 事件类型及状态。
- 云端分析卡片：展示知识库命中内容和规则依据。

落地文件规划：

- `data/knowledge/room_rules.txt`
- `data/knowledge/safety_regulations.txt`
- `src/backend/shared/domain/models.py`
- `src/backend/edge_api/runtime/events.py`
- `src/backend/cloud_api/cloud/agent.py`
- `src/backend/cloud_api/cloud/knowledge.py`
- `src/frontend/edge_frontend/src/App.vue`
- `src/frontend/cloud_frontend/src/App.vue`
- `tests/test_edge_events.py`
- `tests/test_agent.py`

验证命令：

```powershell
python -m pytest tests/test_edge_events.py tests/test_agent.py tests/test_events_state.py
python -m compileall src
```

---

### 阶段 7：管理员自然语言日志分析与隐患检查

目标：

- 增强云端 Agent，使其能够理解并执行面向历史数据的自然语言查询。
- 实现"分析日志 → 发现模式 → 检查隐患"的分析链路。
- 管理员可通过对话界面完成：查询特定时段事件、统计异常趋势、扫描潜在隐患。

验收：

- 可通过自然语言查询"过去 24 小时有哪些异常事件"并得到结构化回复。
- 可通过自然语言查询"本周隐患趋势分析"并得到汇总报告。
- Agent 可遍历历史事件，结合知识库规则识别潜在隐患模式。
- 分析结果可导出为报告。

实现状态：已完成。

已落地能力：

- `LogQueryTool` 支持按时间范围、事件类型、等级和状态查询历史事件，支持汇总统计和隐患模式扫描。
- `CloudAgent.answer()` 增加日志意图识别，当问题包含"历史、日志、趋势、隐患、统计"等关键词时自动查询运行时状态中的事件记录并拼入 LLM 上下文。
- `GET /api/agent/scan?hours=168` 返回结构化隐患报告，包含汇总统计、隐患列表（未处理高风险、重复非授权进入、频繁聚集、疑似摔倒、反复超容量）和最近事件摘要。
- 前端智能体面板新增快捷查询按钮（"24h 异常"、"隐患分析"、"事件统计"、"隐患扫描"），扫描结果以风险卡片展示。
- `CloudAgent` 构造函数和依赖注入已适配，`LogQueryTool` 作为独立组件注入。

落地文件：

- `src/backend/cloud_api/cloud/log_query.py`
- `src/backend/cloud_api/cloud/agent.py`
- `src/backend/cloud_api/routes/agent.py`
- `src/backend/cloud_api/dependencies.py`
- `src/frontend/cloud_frontend/src/App.vue`
- `src/frontend/cloud_frontend/src/api.ts`
- `src/frontend/cloud_frontend/src/styles.css`
- `tests/test_agent.py`

验证命令：

```powershell
python -m pytest tests/test_agent.py
npm run build  # 在 src/frontend/cloud_frontend
python -m pytest
python -m compileall src
```

---

### 阶段 8：系统完善、演示准备与课程报告

目标：

- 完成端到端集成测试，确保边端 → 云端 → 前端全链路通畅。
- 准备课程设计演示流程和录屏素材。
- 撰写课程设计报告。
- 系统细节打磨（UI 优化、错误处理、性能调优）。

验收：

- Docker Compose 一键启动全部服务无报错。
- 演示流程完整可复现：摄像头采集 → 姿态识别 → 事件生成 → 云端分析 → 合理性检查 → 日志查询 → 隐患扫描。
- 课程报告内容完整（需求分析、架构设计、模块详设、接口文档、测试、总结）。

实现状态：已完成。

已落地能力：

- `scripts/demo_test.py` 覆盖 8 项检查：单元测试、编译、环境配置、知识库、日志查询、云端 API、Agent API、Docker 配置。支持 `--quick` / `--skip-docker` / `--skip-frontend` 选项。
- `docs/course_report.md` 完整的课程设计报告，包含需求分析、系统架构、模块详细设计、接口文档、数据库设计、部署方案、测试总结、创新点与改进方向。
- 前端 UI 已包含合理性检查面板（边端）和快捷查询按钮（云端），色彩标识统一。
- 所有文档同步更新，阶段状态表和演示流程已刷新。

落地文件：

- `scripts/demo_test.py`
- `docs/course_report.md`

验证命令：

```powershell
python -m pytest
python -m compileall src
python scripts/demo_test.py
```

---

## 11. 阶段总览表

| 阶段 | 名称 | 状态 | 核心交付 |
| --- | --- | --- | --- |
| 1 | 事件模型与状态层 | 已完成 | SafetyEvent、CloudAnalysisRequest/Response、RuntimeState |
| 2 | 边端事件规则 | 已完成 | EdgeEventAnalyzer、6 类安全事件、Pipeline 接入 |
| 3 | 云端事件接收与 Agent 分析 | 已完成 | 事件路由、CloudAgent.analyze_event()、结构化分析 |
| 4 | 前端展示 | 已完成 | 边端工作台事件面板、云端控制台事件/分析页 |
| 5 | 持久化与报告 | 已完成 | PostgreSQL 持久化、事件检索、Markdown 报告导出 |
| 6 | 知识库规则与合理性分析 | 已完成 | 场所规则知识库、时间/人数合理性事件、前端合理性指标 |
| 7 | 自然语言日志分析与隐患检查 | 已完成 | LogQueryTool、历史分析对话、隐患扫描报告 |
| 8 | 系统完善、日报与课程报告 | 已完成 | 集成测试、日报接口、演示流程、课程报告 |

## 12. 演示闭环设计

推荐最终演示流程：

1. 启动 Docker Compose 或本地边云服务。
2. 边端摄像头开始实时检测。
3. 正常姿态、人数统计在边端完成。
4. 人为制造异常场景：
   - 长时间低头 → 触发 `long_head_down` 事件，云端 Agent 给出健康提醒。
   - 多人聚集 → 触发 `crowding` 事件，结合知识库容量上限给出处置建议。
   - 非开放时段检测 → 触发 `unauthorized_time` 事件，Agent 引用知识库时段规则。
   - 摔倒模拟 → 触发 `fall_suspected` CRITICAL 事件，Agent 给出紧急处置建议。
5. 云端控制台实时显示事件列表、风险等级、Agent 分析卡片。
6. 管理员通过自然语言交互：
   - 输入"分析今天的异常事件" → Agent 查询历史事件，输出类型分布和趋势汇总。
   - 输入"扫描本周隐患" → Agent 遍历日志，输出隐患列表和优先级建议。
7. 导出事件报告（Markdown），展示完整追溯链路。
8. 打开日报页面，查看当日检测报告（事件统计/风险分布/隐患摘要/下载 Markdown）。
9. 日志页展示全链路调度：边端检测 → 事件规则 → 合理性检查 → 云端分析 → 管理平台展示。

## 13. 实现约束

- 优先复用现有代码，不重写 YOLO、WebRTC、Agent 基础结构。
- 新增接口时优先补充 `shared/domain/models.py`。
- 默认测试使用 mock LLM、local search、本地知识库。
- 不提交真实 API Key、模型服务地址或私有知识库内容。
- Docker 配置保持云端服务和管理平台可独立启动。
