# 端-边-云协同智能检测系统

本项目实现一套课程实验用的完整系统骨架，覆盖边缘侧摄像头采集与本地推理、云端智能体服务和独立的 Vue3 前端控制台。
当前同时提供一个独立的 PostgreSQL 服务作为系统数据底座，默认不写入展示数据，后续可平滑扩展为向量数据库。

## 结构

```text
src/backend/
  cloud_api/      云端 FastAPI 程序
  edge_api/       边端 FastAPI 程序
  shared/         共享层
src/frontend/
  cloud_frontend/ 云端 Vite + Vue3 控制台
  edge_frontend/  边端 Vite + Vue3 工作台
docs/             架构与实验说明
tests/            核心逻辑测试
data/postgres/    PostgreSQL 初始化脚本
```

文档入口：

- `docs/architecture.md`：系统总体架构说明
- `docs/course_design_plan.md`：课程设计要求拆解、实施计划和模块划分

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .[test]
.\.venv\Scripts\uvicorn backend.cloud_api.main:app --reload
```

另开一个终端启动边端服务：

```powershell
.\.venv\Scripts\uvicorn backend.edge_api.main:app --reload --port 8001
```

边端 API 启动时会自动打开摄像头并启动采集、YOLO 检测和 WebRTC 视频发布，关闭 API 时会一并停止采集器。通过 `http://localhost:8001/health` 可以查看内置采集器的运行状态和错误信息。

另开一个终端启动云端前端开发服务器：

```powershell
cd src/frontend/cloud_frontend
npm install
npm run dev
```

再开一个终端启动边端前端开发服务器：

```powershell
cd src/frontend/edge_frontend
npm install
npm run dev
```

也可以用一个 PowerShell 调试脚本同时启动边端前端和包含采集器的边端后端；按 `Ctrl+C` 会一起停止：

```powershell
.\scripts\start_edge_dev.ps1
```

实时视频默认由采集器在后台压缩并通过 WebRTC 推送，繁忙时只保留最新帧，避免旧帧堆积造成越来越高的延迟。可在 `.env` 中通过 `EDGE_STREAM_WIDTH`、`EDGE_STREAM_JPEG_QUALITY` 和 `EDGE_STREAM_MAX_FPS` 调整清晰度与流畅度。

边端在本地电脑运行，默认打开摄像头并执行 YOLO 检测。摄像头不可用、模型缺失或 YOLO 依赖缺失时，内置采集器会在 `/health` 中报告错误，API 仍保持可用。

独立 runner 仅用于单帧检查或本地调试窗口。运行它之前应在 `.env` 中设置 `EDGE_COLLECTOR_ENABLED=false`，避免与 API 内置采集器争抢摄像头：

```powershell
.\.venv\Scripts\pip install -e .[yolo]
.\.venv\Scripts\python -m backend.edge_api.runtime.runner --task "姿态识别" --once
```

检测器只加载 `.onnx` 模型并使用 ONNX Runtime，避免额外的导出依赖和运行时分支。

如果要打开一个简单的调试窗口，显示当前采集画面、检测框和运行数据：

```powershell
.\.venv\Scripts\python -m backend.edge_api.runtime.runner --task "姿态识别" --debug-window
```

边端正式 UI 会显示检测框、类别、置信度、显示 FPS、YOLO FPS、推理耗时、目标数、后端、姿态动作和调度信息；按 `q` 或 `Esc` 退出调试窗口时不会影响后台采集。

姿态识别默认走边端规则分类和模拟云端复核。如果后续云端接口接入完成，可以加上 `--real-cloud` 切换到真实云端调用。

YOLO 模型放在根目录 `public/` 下，当前运行时只支持 `.onnx`。要切换到姿态检测模型，直接在 `.env` 里设置 `YOLO_MODEL_PATH=public/yolo-v26/yolo26n-pose.onnx`，边端会自动识别 `task=pose` 并绘制关键点。

如果要快速下载官方姿态模型：

```powershell
.\.venv\Scripts\python scripts\download_pose_model.py --model yolo26n-pose.pt
.\.venv\Scripts\python scripts\download_pose_model.py --model yolo26s-pose.pt
```

当前 Ultralytics 官方姿态模型包括 `yolo26n-pose.pt`、`yolo26s-pose.pt`、`yolo26m-pose.pt`、`yolo26l-pose.pt` 和 `yolo26x-pose.pt`，文档说明这些模型会在首次使用时自动从最新发布版下载。

边端服务器默认监听 `8001`，云端服务器默认监听 `8000`。如果边端和云端分离部署，把 `.env` 里的 `EDGE_API_BASE_URL` 和 `CLOUD_API_BASE_URL` 改成对应地址即可。
PostgreSQL 默认监听 `5432`，当前只创建空库并启用 `pgvector` 扩展，不预置业务表和演示数据。

## Docker

```powershell
docker compose up --build
```

默认暴露：

- 云端 API: `http://localhost:8000`
- 云端前端: `http://localhost:8080`
- 边端 API: `http://localhost:8001`
- 边端前端: `http://localhost:8081`
- PostgreSQL: `localhost:5432`

数据库默认账号：

- Database: `edge_cloud`
- User: `edge_cloud`
- Password: `edge_cloud_dev`

如果只想单独启动数据库：

```powershell
docker compose up -d postgres
```

进入数据库：

```powershell
docker compose exec postgres psql -U edge_cloud -d edge_cloud
```

验证 `pgvector` 扩展是否已就绪：

```sql
\dx
```

如需在 Linux 边端容器中运行摄像头采集和 YOLO 检测：

```powershell
docker compose --profile edge up --build
```

Windows 本机摄像头更建议直接运行边端 API，因为 Docker Desktop 对宿主摄像头透传依赖额外设备映射。

## 当前实现边界

默认云端不会调用付费模型或真实联网搜索。云端智能体通过可替换的 `LLMClient`、`SearchTool` 和 `KnowledgeBase` 接口工作；配置 `LLM_PROVIDER=openai-compatible`、`LLM_BASE_URL`、`LLM_API_KEY` 后可调用兼容 OpenAI Chat Completions 的模型服务。云端前端只通过 `/api` 与云端交互，不包含业务逻辑；边端前端只通过 `/api` 与边端服务器交互。

当前数据库只承担基础设施角色，尚未接入 FastAPI 的业务读写链路。后续若要改为向量数据库，优先建议直接基于现有 `pgvector` 扩展增加向量表和检索接口，而不是再切换到另一套数据库产品。
