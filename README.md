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

YOLO 模型放在根目录 `public/` 下，支持 `.pt`、`.onnx`、`.engine`。也可以在 `.env` 中配置 `YOLO_MODEL_PATH` 指向具体模型。

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
