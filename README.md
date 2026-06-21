# 边云协同安全监测系统

基于 YOLO-Pose 与云端智能体（阿里百炼 qwen3-vl-plus）的端-边-云协同安全监测系统，面向机房/实验室场景，实现实时人物检测、姿态识别、安全事件分析、场所合理性检查、自然语言日志查询和隐患扫描。

## 结构

```text
src/backend/
  cloud_api/      云端 FastAPI (Agent/事件/分析/日报/持久化)
  edge_api/       边端 FastAPI (采集/检测/姿态/事件/WebRTC)
  shared/         共享层 (模型/配置/状态/调度)
src/frontend/
  cloud_frontend/ 云端控制台 (监控/事件/智能体/日报)
  edge_frontend/  边端工作台 (视频/检测框/姿态骨架/事件/合理性)
docs/             设计文档与课程报告
tests/            54 个单元测试
scripts/          模型下载 / 集成测试
data/knowledge/   本地知识库 (场所规则/安全规范)
```

文档入口：

- `docs/architecture.md` — 系统总体架构
- `docs/course_design_plan.md` — 课程设计实施计划
- `docs/safety_monitoring_implementation_plan.md` — 详细技术方案 (8 阶段全完成)
- `docs/course_report.md` — 课程设计报告

## 快速启动

```powershell
# 1. 安装依赖 (首次)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[yolo,test]"

# 2. 启动云端 API (终端1)
cloud-api

# 3. 启动边端 API (终端2，自动打开摄像头)
edge-api

# 4. 启动前端 (终端3/4)
cd src\frontend\cloud_frontend && npm install && npm run dev   # :5173
cd src\frontend\edge_frontend && npm install && npm run dev    # :5174
```

访问 `http://localhost:5174` 查看边端工作台，`http://localhost:5173` 查看云端控制台。

## 核心功能

| 功能 | 说明 |
|------|------|
| 实时检测 | YOLO-Pose ONNX/OpenVINO 双后端，17 点人体关键点 |
| 姿态识别 | 9 种姿态：站/坐/举手/蹲/头部3向/上身2向 |
| 安全事件 | 10 类事件自动检测 (低头/摔倒/聚集/非授权时段/容量超限等) |
| 合理性分析 | 基于知识库的时段合规 + 容量合规实时判断 |
| 云端分析 | 大模型 (qwen3-vl-plus) 多模态分析，含图像输入 |
| 日志查询 | 自然语言查历史事件，支持"最近24h异常"等 |
| 隐患扫描 | 5 类隐患自动检测 (未处理高风险/重复非授权/频繁聚集/摔倒/超容量) |
| 日报报告 | 每日检测报告 JSON + Markdown，支持下载 |
| 持久化 | PostgreSQL 持久化 + 启动恢复 + 全文检索 |
| 视频流 | WebRTC 实时推送 + WebSocket 状态广播 |
| Docker | 6 服务一键部署 (`docker compose up -d`) |

## 配置

关键环境变量 (完整列表见 `.env.example`)：

```env
# 大模型
LLM_PROVIDER=openai-compatible          # 或 mock (测试用)
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3-vl-plus

# 场所规则
ROOM_ALLOWED_HOURS_START=08:00
ROOM_ALLOWED_HOURS_END=22:00
ROOM_CAPACITY=15
ROOM_REASONABILITY_COOLDOWN_SECONDS=30

# 边端控制
EDGE_SKIP_FRAMES=2                      # 每 N 帧推理一次
EDGE_CLOUD_AGENT_COOLDOWN_SECONDS=10    # Agent 调用冷却
EDGE_CLOUD_ANALYSIS_COOLDOWN_SECONDS=3  # 分析请求冷却
EDGE_CLOUD_SYNC_ENABLED=true            # 云端同步开关
EDGE_CLOUD_INCLUDE_IMAGE=true           # 上传分析图像

# 持久化
POSTGRES_PERSISTENCE_ENABLED=true
EVENT_HISTORY_LIMIT=200
```

## Docker

```powershell
docker compose up -d                      # 云端 + 前端 + 数据库
docker compose --profile edge up -d       # 含边端采集

# 服务端口
# 云端 API      → http://localhost:8000
# 边端 API      → http://localhost:8001
# 云端前端      → http://localhost:8080
# 边端前端      → http://localhost:8081
# PostgreSQL    → localhost:5433
```

## API 概览

| 端 | 主要接口 |
|------|---------|
| 云端 | `/api/events` (CRUD+分析+搜索+报告) `/api/agent` (对话+扫描) `/api/reports/daily` (日报) `/api/state` |
| 边端 | `/api/stream` (WebSocket) `/api/webrtc` (视频流) `/api/edge` (检测+事件) `/api/state` |

完整列表见 `docs/course_report.md` 第 4 节。

## 测试

```powershell
# 单元测试 (默认 mock LLM，不触发付费 API)
python -m pytest                          # 54 tests

# 集成测试 (需先启动云端)
python scripts/demo_test.py
python scripts/demo_test.py --quick       # 仅单元+编译
```

## 项目状态

8 个开发阶段全部完成，54 测试 100% 通过，编译 0 错误。详见 `docs/safety_monitoring_implementation_plan.md` 阶段总览表。
