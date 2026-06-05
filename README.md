# 端-边-云协同智能检测系统

本项目实现一套课程实验用的完整系统骨架，覆盖边缘侧摄像头采集与本地推理、云端智能体服务和独立的 Vue3 前端控制台。

## 结构

```text
src/edge_cloud_system/
  core/           配置与共享状态
  domain/         统一数据模型
src/cloud_api/      云端 FastAPI 程序
src/edge_api/       边端 FastAPI 程序
src/cloud_frontend/ 云端 Vite + Vue3 控制台
src/edge_frontend/  边端 Vite + Vue3 工作台
docs/             架构与实验说明
tests/            核心逻辑测试
```

文档入口：

- `docs/architecture.md`：系统总体架构说明
- `docs/course_design_plan.md`：课程设计要求拆解、实施计划和模块划分

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .[test]
.\.venv\Scripts\uvicorn cloud_api.main:app --reload
```

另开一个终端启动边端服务：

```powershell
.\.venv\Scripts\uvicorn edge_api.main:app --reload --port 8001
```

另开一个终端启动云端前端开发服务器：

```powershell
cd src/cloud_frontend
npm install
npm run dev
```

再开一个终端启动边端前端开发服务器：

```powershell
cd src/edge_frontend
npm install
npm run dev
```

边端在本地电脑运行，默认打开摄像头并执行 YOLO 检测。系统不做模拟降级：摄像头不可用、模型缺失或 YOLO 依赖缺失都会直接报错。

```powershell
.\.venv\Scripts\pip install -e .[yolo]
.\.venv\Scripts\python -m edge_api.runtime.runner --task "姿态识别" --once
```

检测器只加载 `.onnx` 模型并使用 ONNX Runtime，避免额外的导出依赖和运行时分支。

如果要打开一个简单的调试窗口，显示当前采集画面、检测框和运行数据：

```powershell
.\.venv\Scripts\python -m edge_api.runtime.runner --task "姿态识别" --debug-window
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

## Docker

```powershell
docker compose up --build
```

默认暴露：

- 云端 API: `http://localhost:8000`
- 云端前端: `http://localhost:8080`
- 边端 API: `http://localhost:8001`
- 边端前端: `http://localhost:8081`

如需在 Linux 边端容器中运行摄像头采集和 YOLO 检测：

```powershell
docker compose --profile edge up --build
```

Windows 本机摄像头更建议直接运行 `edge.runner`，因为 Docker Desktop 对宿主摄像头透传依赖额外设备映射。

## 当前实现边界

默认云端不会调用付费模型或真实联网搜索。云端智能体通过可替换的 `LLMClient`、`SearchTool` 和 `KnowledgeBase` 接口工作；配置 `LLM_PROVIDER=openai-compatible`、`LLM_BASE_URL`、`LLM_API_KEY` 后可调用兼容 OpenAI Chat Completions 的模型服务。云端前端只通过 `/api` 与云端交互，不包含业务逻辑；边端前端只通过 `/api` 与边端服务器交互。
