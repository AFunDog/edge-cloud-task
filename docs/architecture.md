# 端-边-云协同系统架构

## 目标

系统覆盖边缘侧、云端智能体和管理平台三部分。边缘侧负责视频帧采集、预处理、轻量 YOLO 检测和任务调度；云端负责复杂语义分析、知识库检索、联网搜索和报告生成；管理平台负责展示运行状态、检测结果、调度日志和智能体对话。

## 分层

### 边端 Edge

- `edge/camera.py`：封装摄像头采集。安装 OpenCV 后从本地摄像头读取画面，读取失败直接报错。
- `edge/detector.py`：封装 YOLO 检测器。运行时只加载 `.onnx` 并使用 ONNX Runtime；模型缺失或加载失败直接报错，不做模拟降级。
- `domain/scheduler.py`：判断任务复杂度。常规目标检测、有人无人、车辆计数在边端完成；语义理解、跨模态检索、异常解释、报告生成转发云端。该调度规则放在领域层，避免云端 API 依赖边端模块。
- `edge/client.py`：HTTP 客户端，负责把边端检测结果和复杂任务提交给云端。
- `edge/debug.py`：OpenCV 调试窗口，显示采集画面、检测框、显示 FPS、YOLO FPS、推理耗时、目标数量、后端和调度信息。
- `edge/runner.py`：命令行入口，完成摄像头采集、本地推理、调度、调试窗口显示和上报流程。

### 网络层 Network

当前版本采用 HTTP/RESTful API，统一 JSON 数据结构。后续可在 `edge/client.py` 外增加 MQTT 客户端，保持领域模型不变。

### 云端 Cloud

- `cloud/agent.py`：智能体编排入口，整合本地知识库、搜索工具和 LLM 客户端。
- `cloud/knowledge.py`：本地知识库，读取 `data/knowledge` 下的私有文档进行简单关键词检索，后续可替换为向量数据库。
- `cloud/search.py`：搜索工具接口，支持本地摘要和 HTTP JSON 搜索适配器。
- `cloud/llm.py`：大模型客户端抽象，支持 mock 和 OpenAI-compatible Chat Completions。

### 前端 Frontend

`src/frontend/` 使用 Vite + Vue3 + TypeScript 实现组件式控制台，负责系统状态、检测结果、任务日志和智能体对话视图。前端通过 `/api` 访问云端服务，生产环境由 Nginx 反向代理到 FastAPI。

## 数据流

1. 边端采集图像帧并执行 YOLO 检测。
2. 调度器根据任务描述和检测结果决定 `edge` 或 `cloud`。
3. 简单任务在边端生成结果，并通过 API 上报云端。
4. 复杂任务上传云端，由 Agent 结合知识库、搜索工具和 LLM 生成分析。
5. 前端定时读取云端状态，展示连接状态、资源概况、检测框、任务日志和智能体回答。

## 扩展点

- 真实摄像头：`edge/runner.py` 默认连续采集本机摄像头，`--once` 可只处理一帧；实时窗口使用 `EDGE_SKIP_FRAMES` 跳帧推理并复用上一帧检测框，提高显示帧率。
- 真实 YOLO：将模型放入根目录 `public/`，或配置 `YOLO_MODEL_PATH`，并安装 `.[yolo]`。
- 向量数据库：把 `KnowledgeBase.search()` 替换为 FAISS、Chroma 或 Milvus。
- 联网搜索：实现 `SearchTool.search()` 的真实供应商适配。
- 大模型：实现 `LLMClient.generate()` 的具体 API 适配。
