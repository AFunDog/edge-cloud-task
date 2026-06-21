# 边云协同安全监测系统 — 课程设计报告

> **项目名称**: 基于 YOLO-Pose 与云端智能体的边云协同安全监测系统
>
> **课程**: 计算机系统综合实践
>
> **技术栈**: Python 3.12 / FastAPI / Vue3 / TypeScript / PostgreSQL / Docker / OpenVINO

---

## 1. 需求分析

### 1.1 系统目标

构建一套面向机房/实验室场景的端-边-云协同安全监测系统，实现以下核心能力：

1. **实时人物与姿态识别**: 摄像头采集视频流，YOLO-Pose 实时检测人员数量、人体关键点和姿态动作。
2. **安全事件分析预警**: 边端规则引擎自动识别低头、摔倒、聚集等安全事件；云端 Agent 结合大模型和知识库进行深度分析定级。
3. **合理性分析**: 基于知识库中的场所规则（开放时段、容量上限），判断画面中人员是否合规，异常自动记录。
4. **事件持久化与追溯**: PostgreSQL 持久化存储所有事件和分析结果，支持历史检索和 Markdown 报告导出。
5. **自然语言日志分析**: 管理员通过对话界面自然语言查询历史事件、隐患扫描、生成趋势报告。

### 1.2 功能需求

| 编号 | 功能 | 描述 | 实现位置 |
|------|------|------|---------|
| F1 | 摄像头采集 | 实时视频流采集，支持分辨率配置 | `edge_api/runtime/camera.py` |
| F2 | YOLO-Pose 检测 | 人体框+17 点关键点检测，ONNX/OpenVINO | `edge_api/runtime/detector.py` |
| F3 | 姿态识别 | 基于关键点的规则化姿态分类(站/坐/低头/举手等) | `edge_api/runtime/pose.py` |
| F4 | 实时视频推送 | WebRTC 视频流 + WebSocket 状态推送 | `edge_api/routes/webrtc.py` |
| F5 | 安全事件检测 | 低头/摔倒/聚集/姿态不确定等 6 类事件 | `edge_api/runtime/events.py` |
| F6 | 合理性检查 | 时段合规/容量合规事件(unauthorized_time/excessive_people) | `edge_api/runtime/events.py` |
| F7 | 云端事件分析 | Agent 调用 LLM+知识库+搜索生成结构化分析 | `cloud_api/cloud/agent.py` |
| F8 | 大模型集成 | 阿里百炼 qwen3-vl-plus，支持视觉输入 | `cloud_api/cloud/llm.py` |
| F9 | 知识库检索 | 本地文本知识库关键词匹配 | `cloud_api/cloud/knowledge.py` |
| F10 | 事件持久化 | PostgreSQL 持久化 + 启动恢复 | `cloud_api/cloud/database.py` |
| F11 | 报告导出 | Markdown 格式事件报告 | `cloud_api/routes/events.py` |
| F12 | 日志查询 | 按时间/类型/等级过滤历史事件 | `cloud_api/cloud/log_query.py` |
| F13 | 隐患扫描 | 自动扫描未处理高风险、重复异常等 5 类隐患 | `cloud_api/cloud/log_query.py` |
| F14 | 边端工作台 | 实时视频+姿态骨架+事件列表+合理性状态 | `frontend/edge_frontend/` |
| F15 | 云端控制台 | 事件管理+Agent 分析+快捷查询+隐患扫描 | `frontend/cloud_frontend/` |

### 1.3 非功能需求

| 需求 | 实现方式 |
|------|---------|
| 实时性 | 边端 `edge_skip_frames=2` 跳帧策略，WebRTC 低延迟推送 |
| 断网可用 | 边端离线时本地检测/事件/告警正常，恢复后队列同步 |
| 可扩展性 | LLM/Search/Knowledge 通过抽象层接入，支持 mock/real 切换 |
| 安全性 | API Key 通过 `.env` 注入，不提交仓库 |
| 可部署性 | Docker Compose 6 服务一键启动 |

---

## 2. 系统架构设计

### 2.1 总体架构

```text
┌─────────────────────────────────────────────────────────────┐
│                      管理平台 (前端)                          │
│  ┌──────────────────────┐  ┌──────────────────────────────┐ │
│  │  边端工作台 (Vue3)    │  │  云端控制台 (Vue3)            │ │
│  │  :5174               │  │  :5173                       │ │
│  │  WebRTC + WebSocket   │  │  HTTP Polling                │ │
│  └──────────┬───────────┘  └──────────────┬───────────────┘ │
└─────────────┼──────────────────────────────┼────────────────┘
              │                              │
  ┌───────────▼──────────┐    ┌──────────────▼───────────────┐
  │   边端 API :8001      │    │     云端 API :8000           │
  │  ┌────────────────┐  │    │  ┌─────────────────────────┐ │
  │  │ EdgeCollector   │  │    │  │ CloudAgent              │ │
  │  │ CameraSource    │  │    │  │  ├─ LLMClient (百炼)    │ │
  │  │ YoloDetector    │  │    │  │  ├─ SearchTool          │ │
  │  │ PoseAnalyzer    │  │    │  │  ├─ KnowledgeBase       │ │
  │  │ EdgeEventAnalyzer│ │    │  │  └─ LogQueryTool        │ │
  │  │ EdgePipeline    │──┼────┼──│                         │ │
  │  │ CloudClient     │  │    │  │ CloudEventRepository    │ │
  │  └────────────────┘  │    │  └─────────────────────────┘ │
  └──────────────────────┘    └──────────────┬───────────────┘
                                             │
                                  ┌──────────▼───────────┐
                                  │   PostgreSQL :5433    │
                                  │   cloud_events        │
                                  │   cloud_analysis_results│
                                  └──────────────────────┘
```

### 2.2 数据流

```text
摄像头 → CameraSource.read() → 原始帧(BGR)
  │
  ├─→ 视频流: resize → JPEG → WebRTC push → 前端播放
  │
  └─→ 检测流: YoloDetector.detect() → DetectionResult
         │
         ├─→ PoseAnalyzer.analyze() → PoseAnalysis
         │
         ├─→ EdgeEventAnalyzer.analyze() → [SafetyEvent]
         │     ├─ person_count (INFO)
         │     ├─ pose_* (INFO/WARNING)
         │     ├─ long_head_down (WARNING, CLOUD_PENDING)
         │     ├─ fall_suspected (CRITICAL, CLOUD_PENDING)
         │     ├─ crowding (WARNING, CLOUD_PENDING)
         │     ├─ pose_uncertain (WARNING, CLOUD_PENDING)
         │     ├─ unauthorized_time (WARNING, CLOUD_PENDING)   ← 阶段6
         │     └─ excessive_people (WARNING, CLOUD_PENDING)    ← 阶段6
         │
         └─→ EdgePipeline.sync_cloud()
               ├─→ CloudClient.publish_detection() → POST /api/edge/detections
               ├─→ CloudClient.publish_event() → POST /api/events
               ├─→ CloudClient.request_cloud_analysis() → POST /api/events/analyze
               │     └─→ CloudAgent.analyze_event()
               │           ├─→ KnowledgeBase.search(query)
               │           ├─→ SearchTool.search(query)
               │           └─→ LLMClient.generate(prompt, images)
               │                 → CloudAnalysisResponse
               └─→ RuntimeState.add_analysis_result()
```

### 2.3 技术选型

| 层次 | 技术 | 理由 |
|------|------|------|
| 边端推理 | OpenVINO / ONNX Runtime | 本地高效推理，无需 GPU |
| 边端 API | FastAPI + Uvicorn | 异步高性能 Web 框架 |
| 云端 API | FastAPI + Uvicorn | 同上，统一技术栈 |
| 实时通信 | WebRTC (aiortc) | 低延迟视频流 |
| 状态推送 | WebSocket | 全双工实时更新 |
| 大模型 | 阿里百炼 DashScope | OpenAI 兼容接口，qwen3-vl-plus 视觉理解 |
| 数据库 | PostgreSQL + pgvector | 成熟的关系型 + 向量检索 |
| 前端 | Vue3 + TypeScript + Vite | 现代响应式框架，类型安全 |
| 容器化 | Docker Compose | 一键部署，服务隔离 |
| 测试 | pytest | Python 标准测试框架 |

---

## 3. 模块详细设计

### 3.1 共享层 (`backend/shared/`)

#### 数据模型 (`domain/models.py`)

定义了边端、云端和管理平台之间的统一数据契约，共 14 个 Pydantic 模型：

| 模型 | 用途 |
|------|------|
| `Detection` | 单目标检测结果（框、标签、置信度、关键点） |
| `DetectionResult` | 帧级检测结果（含 JPEG base64 图像、姿态） |
| `PoseAnalysis` | 姿态分析输出（动作、置信度、是否需要云端） |
| `SafetyEvent` | 安全事件统一描述（类型、等级、状态、证据、指标） |
| `CloudAnalysisRequest` | 云端分析请求（事件 + 检测 + 图像 + 上下文） |
| `CloudAnalysisResponse` | 云端分析响应（风险等级、结论、依据、建议、报告） |
| `AgentRequest/Response` | 智能体对话请求/响应 |
| `TaskRequest/ScheduleDecision/TaskLog` | 任务调度 |
| `EdgeStatus` | 边端设备状态 |
| `EventReport` | 事件报告（含 Markdown） |

#### 运行时状态 (`core/state.py`)

线程安全的内存存储，使用 `deque(maxlen=200)` 和 `threading.Lock`。存储边端状态、检测结果、任务日志、事件列表、分析结果。`add_event()` 和 `add_analysis_result()` 均为幂等操作。

#### 配置管理 (`core/config.py`)

基于 `pydantic-settings` 的 `Settings` 类，从 `.env` 读取全部配置。涵盖：
- 服务地址（edge/cloud API URL）
- 数据库连接
- 摄像头参数
- YOLO 参数
- LLM 提供商配置
- 知识库/搜索配置
- 场所规则（时段、容量）
- 分析冷却策略

### 3.2 边端模块 (`backend/edge_api/`)

#### 摄像头采集 (`runtime/camera.py`)

`CameraSource` 上下文管理器封装 `cv2.VideoCapture`，支持可配置的索引/分辨率，提供 `read()` 和 `read_latest()` 方法。`encode_frame_to_jpeg_base64()` 将 BGR 帧编码为 JPEG base64。

#### YOLO 检测 (`runtime/detector.py`)

`YoloDetector` 支持 ONNX Runtime 和 OpenVINO 双后端。自动解析模型路径（支持 ONNX 文件和 OpenVINO IR 目录），从 ONNX 自定义元数据或 `metadata.yaml` 读取模型任务类型和关键点名称。`process_frame()` 进行预处理、推理、NMS 和坐标映射。

#### 姿态分析 (`runtime/pose.py`)

`PoseAnalyzer` 基于 COCO 17 关键点进行规则化姿态分类。支持的姿态动作：站立、坐下、举手、蹲下、头部偏转（左/右/下）、上半身偏转（左/右）、未知。当关键点稀疏或置信度 < 0.58 时标记 `needs_cloud=True`。

#### 事件分析 (`runtime/events.py`)

`EdgeEventAnalyzer` 基于帧级检测进行安全事件识别，维护短期状态（低头持续时间、聚集持续时间、人数变化）。支持 10 类事件：

| 事件类型 | 严重程度 | 云端状态 | 冷却时间 |
|---------|---------|---------|---------|
| `person_count` | INFO | EDGE_RESOLVED | 无（变化触发） |
| `pose_*`（6种） | INFO/WARNING | EDGE_RESOLVED | 8s |
| `long_head_down` | WARNING | CLOUD_PENDING | 8s |
| `fall_suspected` | CRITICAL | CLOUD_PENDING | 8s |
| `crowding` | WARNING | CLOUD_PENDING | 8s |
| `pose_uncertain` | WARNING | CLOUD_PENDING | 8s |
| `unauthorized_time` | WARNING | CLOUD_PENDING | 30s（独立冷却） |
| `excessive_people` | WARNING | CLOUD_PENDING | 30s（独立冷却） |

合理性检查使用独立冷却机制，避免频繁触发。

#### 流水线 (`runtime/pipeline.py`)

`EdgePipeline` 是边端处理的核心编排器：
1. `process()`: 姿态分析 → 事件分析 → 调度决策 → 生成 EdgeCycle
2. `sync_cloud()`: 云端可用性检查 → 上报检测/事件 → 云端分析请求（带 3s 冷却）→ Agent 对话

#### 通信客户端 (`runtime/client.py`)

- `EdgeClient`: 边端 API HTTP 客户端
- `CloudClient`: 云端 API HTTP 客户端（`publish_status/detection/event/task_log`, `request_cloud_analysis`, `ask_agent`）
- `LatestFramePublisher`: 后台线程按 FPS 发布 JPEG 帧

### 3.3 云端模块 (`backend/cloud_api/`)

#### 智能体 (`cloud/agent.py`)

`CloudAgent` 是云端分析的核心：

| 方法 | 功能 |
|------|------|
| `answer()` | 通用对话：知识库搜索 → 搜索工具 → 日志查询（意图识别）→ LLM 生成 |
| `analyze_event()` | 事件分析：知识库 → 搜索 → LLM（含视觉）→ 规则降级 → 结构化输出 |
| `scan()` | 隐患扫描：调用 LogQueryTool 汇总统计 + 危险模式扫描 |

日志意图识别关键词：`历史/日志/过去/异常/统计/趋势/隐患/扫描`

#### 日志查询 (`cloud/log_query.py`)

`LogQueryTool` 提供历史数据查询能力：

- `query_events(hours_back, event_type, severity, status)`: 按条件过滤
- `summarize(hours_back)`: 汇总统计（总数/类型分布/等级分布/状态分布/趋势判断）
- `scan_hazards(hours_back)`: 5 类隐患检测
  - 未处理高风险事件
  - 重复非授权进入
  - 频繁聚集
  - 疑似摔倒
  - 反复超容量

#### 大模型客户端 (`cloud/llm.py`)

`LLMClient` 支持 mock、openai、openai-compatible 三种模式。vision 模式使用阿里百炼 `data:image/jpeg;base64,` 格式的 `image_url` content。

#### 知识库 (`cloud/knowledge.py`)

`KnowledgeBase` 扫描指定目录的 `*.txt` 和 `*.md` 文件，基于关键词匹配返回相关片段。

知识库内容：
- `edge.txt`: 边端基本能力说明
- `room_rules.txt`: 场所规则（时段/容量/行为/处置）
- `safety_regulations.txt`: 安全管理规范

#### 数据库 (`cloud/database.py`, `cloud/schema.py`, `cloud/event_repository.py`)

`CloudEventRepository` 封装 PostgreSQL CRUD 操作。`initialize_database()` 自动建表（`cloud_events`、`cloud_analysis_results`，含索引和检索文本）。`hydrate_runtime_state()` 在启动时从数据库恢复历史数据。

### 3.4 前端模块

#### 边端工作台 (`frontend/edge_frontend/`)

| 面板 | 功能 |
|------|------|
| 实时视频 | WebRTC 视频流 + YOLO 检测框/关键点/骨架叠加 |
| 实时指标 | 检测目标数、推理耗时、当前姿态、云端候选数、边端事件数、云端分析数 |
| 合理性检查 | 时段合规 ✓/✗、容量合规 ✓/✗、当前人数和时间 |
| 边云事件 | 事件列表（类型/等级/状态/摘要），最近 5 条 |
| 云端分析 | 最新 Agent 分析结论和建议 |
| 边端日志 | 任务调度日志列表 |

#### 云端控制台 (`frontend/cloud_frontend/`)

| 面板 | 功能 |
|------|------|
| 监控 | 实时指标（检测/推理/事件/待分析）、边云调度统计、最近事件、最近 Agent 分析 |
| 事件 | 统计磁贴（总数/待云端/高风险/分析报告）、完整事件列表、分析卡片 |
| 智能体 | 快捷查询按钮、自由对话、隐患扫描、调度预测 |
| 日志 | 任务日志列表 |

---

## 4. 接口设计

### 4.1 REST API

#### 云端 API (`:8000`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/state` | 运行时状态快照 |
| POST | `/api/edge/status` | 接收边端状态 |
| POST | `/api/edge/detections` | 接收检测结果 |
| POST | `/api/events` | 接收事件 |
| GET | `/api/events` | 事件列表 |
| GET | `/api/events/search?q=&limit=` | 事件搜索 |
| POST | `/api/events/analyze` | 事件分析 |
| GET | `/api/events/analysis` | 分析结果列表 |
| GET | `/api/events/{event_id}/report` | 事件报告 |
| POST | `/api/tasks/schedule` | 任务调度 |
| POST | `/api/tasks/logs` | 任务日志 |
| POST | `/api/agent/chat` | 智能体对话 |
| GET | `/api/agent/scan?hours=` | 隐患扫描 |
| GET | `/api/agent/tools` | 可用工具列表 |

#### 边端 API (`:8001`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（含采集器状态） |
| GET | `/api/state` | 运行时状态快照 |
| POST | `/api/edge/status` | 更新边端状态 |
| POST | `/api/edge/frames/raw` | 原始 BGR 帧 |
| POST | `/api/edge/frames/jpeg` | JPEG 帧 |
| POST | `/api/edge/detections` | 检测结果 |
| POST | `/api/edge/events` | 事件 |
| GET | `/api/stream` | WebSocket 状态流 |
| POST | `/api/webrtc/offer` | WebRTC SDP 协商 |
| POST | `/api/webrtc/candidate/{pc_id}` | WebRTC ICE 候选 |
| POST | `/api/tasks/schedule` | 任务调度 |
| POST | `/api/tasks/logs` | 任务日志 |

### 4.2 WebSocket 消息格式

```json
{"type": "detection",    "data": DetectionResult}
{"type": "task_log",     "data": TaskLog}
{"type": "event",        "data": SafetyEvent}
{"type": "analysis_result", "data": CloudAnalysisResponse}
{"type": "status",       "data": EdgeStatus}
```

### 4.3 核心数据模型

```python
# DetectionResult
class DetectionResult(BaseModel):
    device_id: str
    frame_id: str
    backend: str  # onnxruntime / openvino
    model_task: str  # pose
    inference_ms: float
    fps: float
    frame_width: int
    frame_height: int
    image_jpeg_base64: str | None  # JPEG base64
    detections: list[Detection]
    pose: PoseAnalysis | None

# SafetyEvent
class SafetyEvent(BaseModel):
    event_id: str = uuid4().hex
    event_type: str  # person_count / long_head_down / fall_suspected / ...
    device_id: str
    frame_id: str | None
    severity: EventSeverity  # info / warning / critical
    status: EventStatus  # edge_resolved / cloud_pending / cloud_analyzed
    summary: str
    evidence: list[str]
    metrics: dict
    created_at: datetime

# CloudAnalysisResponse
class CloudAnalysisResponse(BaseModel):
    event_id: str
    risk_level: EventSeverity
    conclusion: str
    reasoning: list[str]
    suggestions: list[str]
    report: str
    used_search: bool
    used_knowledge: bool
    traces: list[str]
    created_at: datetime
```

---

## 5. 数据库设计

### 5.1 表结构

```sql
-- cloud_events
CREATE TABLE cloud_events (
    event_id    TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,
    device_id   TEXT NOT NULL,
    severity    TEXT NOT NULL,
    status      TEXT NOT NULL,
    summary     TEXT,
    evidence    JSONB DEFAULT '[]',
    metrics     JSONB DEFAULT '{}',
    payload     JSONB NOT NULL,
    search_text TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_cloud_events_type ON cloud_events(event_type);
CREATE INDEX idx_cloud_events_device ON cloud_events(device_id);
CREATE INDEX idx_cloud_events_created ON cloud_events(created_at DESC);

-- cloud_analysis_results
CREATE TABLE cloud_analysis_results (
    event_id      TEXT PRIMARY KEY REFERENCES cloud_events(event_id),
    risk_level    TEXT NOT NULL,
    conclusion    TEXT,
    reasoning     JSONB DEFAULT '[]',
    suggestions   JSONB DEFAULT '[]',
    report        TEXT,
    used_search   BOOLEAN DEFAULT FALSE,
    used_knowledge BOOLEAN DEFAULT FALSE,
    traces        JSONB DEFAULT '[]',
    search_text   TEXT,
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_cloud_analysis_risk ON cloud_analysis_results(risk_level);
```

### 5.2 ER 图

```text
cloud_events 1 ──── 1 cloud_analysis_results
  (event_id)          (event_id FK)
```

---

## 6. 部署方案

### 6.1 Docker Compose

```yaml
services:
  postgres:    # PostgreSQL 16 + pgvector, port 5433
  cloud:       # 云端 FastAPI, port 8000, 持久化开启
  edge:        # 边端 FastAPI, port 8001, 摄像头采集
  cloud-web:   # 云端控制台 Nginx, port 8080
  edge-web:    # 边端工作台 Nginx, port 8081
  edge-runner: # 可选独立摄像头运行器 (profile: edge)
```

启动命令：
```bash
docker compose up -d              # 全部服务
docker compose --profile edge up -d  # 含摄像头采集
```

### 6.2 本地开发

```powershell
pip install -e ".[yolo,test]"
cloud-api        # 云端 :8000
edge-api         # 边端 :8001
cd src\frontend\cloud_frontend && npm install && npm run dev  # :5173
cd src\frontend\edge_frontend && npm install && npm run dev   # :5174
```

### 6.3 环境变量

关键配置（完整列表见 `.env.example`）:

```env
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3-vl-plus
POSTGRES_PERSISTENCE_ENABLED=true
ROOM_ALLOWED_HOURS_START=08:00
ROOM_ALLOWED_HOURS_END=22:00
ROOM_CAPACITY=15
ROOM_REASONABILITY_COOLDOWN_SECONDS=30
EDGE_CLOUD_ANALYSIS_COOLDOWN_SECONDS=3
```

---

## 7. 测试

### 7.1 单元测试覆盖

**50 个测试用例**，覆盖以下模块：

| 测试文件 | 用例数 | 覆盖内容 |
|---------|--------|---------|
| `test_agent.py` | 11 | Agent 对话、事件分析、日志查询、隐患扫描、降级处理 |
| `test_cloud_events.py` | 4 | 事件 CRUD、持久化、容错、报告导出 |
| `test_detector.py` | 4 | ONNX 输出解析、OpenVINO 模型加载、元数据解析 |
| `test_edge_collector_sync.py` | 1 | 云端同步队列背压 |
| `test_edge_events.py` | 11 | 6 类安全事件 + 3 类合理性事件 + 冷却机制 |
| `test_edge_lifespan.py` | 1 | 采集器生命周期 |
| `test_edge_pipeline.py` | 4 | 流水线处理、云端同步、离线处理、失败处理 |
| `test_events_state.py` | 6 | RuntimeState 读写、幂等、合并 |
| `test_pose.py` | 4 | 举手/头部方向/上身方向/稀疏关键点 |
| `test_scheduler.py` | 2 | 简单/复杂任务分流 |
| `test_webrtc_stream.py` | 2 | 视频帧广播、丢帧 |

### 7.2 集成测试

`scripts/demo_test.py` 支持以下验证：

```powershell
python scripts/demo_test.py                # 全量
python scripts/demo_test.py --quick        # 快速冒烟
python scripts/demo_test.py --skip-docker  # 跳过 Docker 检查
```

测试覆盖：单元测试、编译检查、环境配置、知识库检索、日志查询、云端 API、Agent API、前端构建、Docker 配置。

### 7.3 测试策略

- 默认使用 `LLM_PROVIDER=mock` 避免触发付费 API
- 数据库测试使用 `FakeEventRepository` 和 `FailingEventRepository`
- 时间敏感测试使用固定 `datetime` 避免依赖系统时间

---

## 8. 总结与展望

### 8.1 项目成果

1. **完整的端-边-云协同架构**: 边端实时感知 + 云端智能分析 + 管理平台可视化，三层分工清晰。
2. **12 类安全事件检测**: 覆盖姿态、安全、合理性、容量四大维度，支持本地告警和云端深度分析。
3. **多模态智能分析**: 集成阿里百炼 qwen3-vl-plus，支持图像理解、知识库检索、自然语言日志分析。
4. **完善的数据管理**: PostgreSQL 持久化 + 历史恢复 + 全文检索 + Markdown 报告导出。
5. **双前端管理平台**: 边端工作台（实时视频+检测+事件）和云端控制台（事件管理+Agent 分析+隐患扫描）。
6. **50 个自动化测试**: 单元测试全覆盖，集成测试脚本支持一键验证。

### 8.2 创新点

- **知识库驱动的合理性分析**: 将场所规则编码为结构化知识，边端实时判断时段和容量合规性。
- **智能体日志分析**: 管理员可通过自然语言查询历史事件、自动扫描隐患、生成趋势报告。
- **视觉+文本多模态分析**: 将摄像头画面以 base64 格式直接传给大模型，实现端到端视觉理解。

### 8.3 改进方向

| 方向 | 说明 |
|------|------|
| 人脸识别 | 接入人脸识别模型，实现人员身份确认 |
| 行为分析 | 基于连续帧的行为链分析（如"进入→坐下→操作设备"） |
| 告警通知 | 集成邮件/短信/钉钉等通知渠道 |
| 数据看板 | 引入 ECharts 图表，展示事件趋势和热力图 |
| 模型升级 | 支持更多 YOLO 模型版本，提升检测精度 |
| 分布式部署 | 支持多边端设备统一接入和管理 |

---

## 附录

### A. 项目结构

```
src/
├── data/knowledge/          # 知识库文件
│   ├── edge.txt
│   ├── room_rules.txt
│   └── safety_regulations.txt
├── docs/                    # 设计文档
│   ├── architecture.md
│   ├── course_design_plan.md
│   └── safety_monitoring_implementation_plan.md
├── scripts/
│   ├── demo_test.py         # 集成测试脚本
│   └── download_pose_model.py
├── src/
│   ├── backend/
│   │   ├── shared/          # 共享层
│   │   ├── cloud_api/       # 云端服务
│   │   └── edge_api/        # 边端服务
│   └── frontend/
│       ├── cloud_frontend/  # 云端控制台
│       └── edge_frontend/   # 边端工作台
├── tests/                   # 单元测试
├── docker-compose.yml
├── Dockerfile.cloud
├── Dockerfile.edge
├── pyproject.toml
├── .env.example
└── README.md
```

### B. 阶段开发历程

| 阶段 | 内容 | 测试数 |
|------|------|--------|
| 1 | 事件模型与状态层 | +6 |
| 2 | 边端事件规则 | +5 |
| 3 | 云端 Agent 分析 | +5 |
| 4 | 前端展示 | +0 |
| 5 | 持久化与报告 | +4 |
| 6 | 知识库规则与合理性分析 | +8 |
| 7 | 日志分析与隐患扫描 | +6 |
| 8 | 系统完善与课程报告 | +0 |
| **合计** | | **50** |

### C. 验证命令

```powershell
# 单元测试
python -m pytest

# 编译检查
python -m compileall src

# 集成测试
python scripts/demo_test.py

# 前端构建
cd src\frontend\cloud_frontend && npm run build
cd src\frontend\edge_frontend && npm run build
```
