# 端-边-云协同系统架构

## 目标

系统覆盖边端服务器、云端服务器、边端前端和云端前端四部分。边端服务器负责视频帧采集、预处理、轻量 YOLO 检测、基于关键点的姿态动作识别和任务调度；云端服务器负责复杂语义分析、知识库检索、联网搜索和报告生成；边端前端负责正式化展示采集画面、姿态动作和本地调度结果；云端前端负责智能体对话、任务日志和系统概览。

## 分层

### 边端 Edge

- `backend/edge_api/runtime/camera.py`：封装摄像头采集。安装 OpenCV 后从本地摄像头读取画面，读取失败直接报错。
- `backend/edge_api/runtime/detector.py`：封装 YOLO 检测器。运行时支持 `.onnx`/ONNX Runtime 和 OpenVINO `.xml + .bin`；模型缺失或加载失败直接报错，不做模拟降级。
- `backend/edge_api/runtime/pose.py`：边端姿态动作判定器。基于人体关键点的几条规则识别站立、坐下、举手和蹲下等基础动作，无法稳定识别时标记为待云端复核。
- `backend/shared/domain/scheduler.py`：判断任务复杂度。常规目标检测、有人无人、姿态识别在边端完成；语义理解、跨模态检索、异常解释、报告生成转发云端。该调度规则放在领域层，避免云端 API 依赖边端模块。
- `backend/edge_api/runtime/pipeline.py`：统一组织检测结果、姿态分析、任务调度、任务日志和云端同步，供内置采集器与独立 runner 复用。
- `backend/edge_api/runtime/monitoring.py`：采集真实 CPU、内存和 FPS 状态，无法读取时安全降级。
- `backend/edge_api/runtime/client.py`：HTTP 客户端，负责把边端检测结果和复杂任务提交给云端。
- `backend/edge_api/runtime/collector.py`：随边端 API 生命周期运行的默认入口。本地检测与云端同步使用独立线程，云端不可用时不阻塞采集和推理。
- `backend/edge_api/runtime/debug.py`：OpenCV 调试窗口，显示采集画面、检测框、显示 FPS、YOLO FPS、推理耗时、目标数量、后端和调度信息。
- `backend/edge_api/runtime/runner.py`：可选诊断入口，用于单帧检查和本地调试窗口，不参与边端后端的正式启动流程。

### 网络层 Network

当前版本采用 HTTP/RESTful API，统一 JSON 数据结构。后续可在 `backend/edge_api/runtime/client.py` 外增加 MQTT 客户端，保持领域模型不变。

### 云端 Cloud

- `backend/cloud_api/cloud/agent.py`：智能体编排入口，整合本地知识库、搜索工具和 LLM 客户端。
- `backend/cloud_api/cloud/knowledge.py`：本地知识库，读取 `data/knowledge` 下的私有文档进行简单关键词检索，后续可替换为向量数据库。
- `backend/cloud_api/cloud/search.py`：搜索工具接口，支持本地摘要和 HTTP JSON 搜索适配器。
- `backend/cloud_api/cloud/llm.py`：大模型客户端抽象，支持 mock 和 OpenAI-compatible Chat Completions。

### 数据层 Data

- `docker-compose.yml`：提供独立的 PostgreSQL 服务，当前使用 `pgvector/pgvector:pg16` 镜像；数据库容器不再挂载初始化 SQL。
- `backend/cloud_api/cloud/database.py`：云端后端启动时按配置维护 PostgreSQL schema 和 `vector` 扩展，不创建业务表、不插入演示数据。
- `backend/shared/core/config.py`：统一暴露 PostgreSQL 主机、端口、库名、账号和向量能力开关，供后续云端知识库和任务存储接入。

### 前端 Frontend

`src/frontend/cloud_frontend/` 使用 Vite + Vue3 + TypeScript + Vue Router 实现云端控制台，页面按 `views/MonitorView.vue`、`EventsView.vue`、`AgentView.vue`、`LogsView.vue`、`KnowledgeView.vue` 拆分。`src/frontend/edge_frontend/` 使用同样技术栈实现边端工作台，页面按 `views/MonitorView.vue`、`PoseView.vue`、`LogsView.vue` 拆分。两套前端的 `App.vue` 仅保留顶栏、状态指示和 `RouterView`，监控页通过 `KeepAlive` 保持 WebRTC `<video>` 节点和检测叠加层状态；切回监控页时优先恢复已有 `srcObject` 播放，只有连接断开或媒体对象丢失时才重新建联，避免切页返回出现黑屏重连等待。两套前端分别通过 `/api` 访问云端服务与边端服务，生产环境可由 Nginx 分别反向代理到对应 FastAPI。

## 数据流

1. 边端采集图像帧并执行 YOLO 检测和姿态关键点解析。
2. 调度器根据任务描述和检测结果决定 `edge` 或 `cloud`。
3. 对姿态任务，边端优先用规则算法输出基础动作结果；若匹配不到合理姿态，则自动调度到云端复核。
4. 本地检测结果和任务日志立即写入边端状态并通过 WebSocket 展示；后台同步线程再上传云端，网络延迟不阻塞本地实时链路。
5. 复杂任务由云端 Agent 结合知识库、搜索工具和 LLM 生成分析；Agent 调用带冷却时间，避免视频帧触发高频调用。
6. 边端前端读取边端实时状态，展示资源概况、检测框、姿态动作和任务日志；云端前端展示汇总后的边端状态、任务日志和智能体回答。监控页是独立路由组件，切换到其他页面不会主动关闭 WebRTC 流，返回时恢复播放并复用现有检测数据。
7. PostgreSQL 当前作为独立基础设施运行，暂不承载展示数据；后续可用于任务日志持久化、知识片段存储和向量检索。

## 扩展点

- 真实摄像头：`backend/edge_api/runtime/runner.py` 默认连续采集本机摄像头，`--once` 可只处理一帧；实时窗口使用 `EDGE_SKIP_FRAMES` 跳帧推理并复用上一帧检测框，提高显示帧率。
- 真实 YOLO：将 `.onnx` 或 OpenVINO 导出目录放入根目录 `public/`，或配置 `YOLO_MODEL_PATH`，并安装 `.[yolo]`。
- 向量数据库：优先复用当前 PostgreSQL + `pgvector`，把 `KnowledgeBase.search()` 从关键词匹配扩展为 embedding 存储与近邻检索。
- 联网搜索：实现 `SearchTool.search()` 的真实供应商适配。
- 大模型：实现 `LLMClient.generate()` 的具体 API 适配。
