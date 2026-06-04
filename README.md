# 端-边-云协同智能检测系统

本项目实现一套课程实验用的完整系统骨架，覆盖边缘侧摄像头采集与本地推理、云端智能体服务和独立的 Vue3 前端控制台。

## 结构

```text
src/edge_cloud_system/
  api/            FastAPI 云端接口
  cloud/          LLM、搜索、知识库与智能体编排
  core/           配置与共享状态
  domain/         统一数据模型
  edge/           摄像头采集、YOLO 检测、任务调度、边云通信
src/frontend/     Vite + Vue3 + TypeScript 组件式控制台
docs/             架构与实验说明
tests/            核心逻辑测试
```

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .[test]
.\.venv\Scripts\uvicorn edge_cloud_system.api.main:app --reload
```

另开一个终端启动前端开发服务器：

```powershell
cd src/frontend
npm install
npm run dev
```

边端在本地电脑运行，默认打开摄像头并执行 YOLO 检测。系统不做模拟降级：摄像头不可用、模型缺失或 YOLO 依赖缺失都会直接报错。

```powershell
.\.venv\Scripts\pip install -e .[yolo]
.\.venv\Scripts\python -m edge_cloud_system.edge.runner --task "车辆计数" --once
```

检测器只加载 `.onnx` 模型并使用 ONNX Runtime，避免额外的导出依赖和运行时分支。

如果要打开一个简单的调试窗口，显示当前采集画面、检测框和运行数据：

```powershell
.\.venv\Scripts\python -m edge_cloud_system.edge.runner --task "车辆计数" --debug-window
```

实时调试窗口会显示检测框、类别、置信度、显示 FPS、YOLO FPS、推理耗时、目标数、后端和调度信息；按 `q` 或 `Esc` 退出。

YOLO 模型放在根目录 `public/` 下，当前运行时只支持 `.onnx`。要切换到姿态检测模型，直接在 `.env` 里设置 `YOLO_MODEL_PATH=public/yolo-v26/yolo26n-pose.onnx`，边端会自动识别 `task=pose` 并绘制关键点。

如果要快速下载官方姿态模型：

```powershell
.\.venv\Scripts\python scripts\download_pose_model.py --model yolo26n-pose.pt
.\.venv\Scripts\python scripts\download_pose_model.py --model yolo26s-pose.pt
```

当前 Ultralytics 官方姿态模型包括 `yolo26n-pose.pt`、`yolo26s-pose.pt`、`yolo26m-pose.pt`、`yolo26l-pose.pt` 和 `yolo26x-pose.pt`，文档说明这些模型会在首次使用时自动从最新发布版下载。

如果边端和云端分离部署，把 `.env` 里的 `API_BASE_URL` 改成远程云端服务器地址即可。

## Docker

```powershell
docker compose up --build
```

默认暴露：

- API: `http://localhost:8000`
- 前端控制台: `http://localhost:8080`

如需在 Linux 边端容器中运行摄像头采集和 YOLO 检测：

```powershell
docker compose --profile edge up --build
```

Windows 本机摄像头更建议直接运行 `edge.runner`，因为 Docker Desktop 对宿主摄像头透传依赖额外设备映射。

## 当前实现边界

默认云端不会调用付费模型或真实联网搜索。云端智能体通过可替换的 `LLMClient`、`SearchTool` 和 `KnowledgeBase` 接口工作；配置 `LLM_PROVIDER=openai-compatible`、`LLM_BASE_URL`、`LLM_API_KEY` 后可调用兼容 OpenAI Chat Completions 的模型服务。前端只通过 `/api` 与云端交互，不包含业务逻辑。
