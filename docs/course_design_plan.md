# 课程设计要求拆解与实施计划

本文档根据《计算机系统综合实习》课程设计要求整理，结合当前仓库结构，把需求拆分为可执行的开发计划和模块分工，便于后续实现、联调和写报告。

## 1. 设计目标

本课程设计的核心目标可以归纳为六点：

1. 构建一套包含边端、云端和管理平台的完整边云协同系统。
2. 在边端实现基于 YOLO-Pose 的实时人物检测、姿态识别与安全事件分析。
3. 结合本地知识库规则，对画面中人物进行合理性分析（时段合规、容量合规等）。
4. 在云端实现具备大模型调用、联网搜索和本地知识库能力的智能体。
5. 在管理平台提供可视化监控、事件管理、合理性分析、自然语言日志查询和隐患扫描能力。
6. 所有事件可持久化存储，支持历史检索和报告导出。

结合当前仓库，系统已经按 `src/backend/` 作为后端主目录、`src/backend/shared/` 作为共享层、`src/backend/edge_api/` 和 `src/backend/cloud_api/` 作为两套独立服务、`src/frontend/edge_frontend/` 和 `src/frontend/cloud_frontend/` 作为两套前端的结构拆分，适合直接按模块推进实现。

## 2. 分阶段实施计划

### 阶段一：需求梳理与总体架构确认

- 明确“简单任务边缘处理、复杂任务云端处理”的调度原则。
- 对齐边端、云端、网络层和管理平台的职责边界。
- 固化接口数据结构，优先补齐 `domain/models.py` 中的请求和响应模型。

阶段产物：

- 总体架构说明
- 接口模型草案
- 任务分流规则说明

### 阶段二：边端核心链路开发

- 完成摄像头采集、帧预处理和 YOLO 推理。
- 在边端增加姿态动作的规则化识别层，优先完成本地判断。
- 实现边端任务调度器，区分简单任务和复杂任务。
- 对无法稳定识别的姿态结果生成待云端复核的模拟数据。
- 补充调试窗口，便于查看检测框、FPS 和运行状态。

阶段产物：

- 可独立运行的边端程序
- 本地检测结果
- 边云请求发送能力

### 阶段三：云端智能体能力开发

- 完成云端 Agent 编排入口。
- 接入本地知识库检索、联网搜索和大模型客户端抽象。
- 统一复杂任务的分析输出格式，支持报告式返回结果。

阶段产物：

- 云端智能体服务
- 知识库检索接口
- 搜索与 LLM 适配层

### 阶段四：管理平台开发

- 建立系统状态看板，展示边端与云端运行情况。
- 建立检测结果和任务日志展示区。
- 建立智能体对话界面，便于查看分析结果和执行过程。

阶段产物：

- 可视化管理平台
- 任务日志页面
- 智能体对话页面

### 阶段五：联调、部署与验收

- 通过 Docker Compose 完成云端服务和管理平台的独立启动。
- 校验边端本地运行、云端接口联通和前端页面展示。
- 准备课程设计报告、系统演示素材和复现说明。

阶段产物：

- 可复现部署方案
- 联调记录
- 演示材料和课程报告素材

### 阶段六：知识库规则与合理性分析

- 扩展 `data/knowledge/`，新增机房/实验室场所规则文本（开放时段、容量上限、行为规范）。
- 在 `EdgeEventAnalyzer` 增加基于时间和人数规则的合理性检查，生成 `unauthorized_time`、`excessive_people` 等新事件。
- 云端 Agent 在分析时引用知识库规则命中内容，输出规则依据和处置建议。
- 前端增加合理性检查状态展示。

阶段产物：

- 知识库规则文件（`room_rules.txt`、`safety_regulations.txt`）
- 合理性事件类型和检测逻辑
- 知识库驱动的分析链路

**状态：已完成**

### 阶段七：自然语言日志分析与隐患扫描

- 新增 `LogQueryTool`，支持按时间、类型、等级查询历史事件，进行汇总统计和隐患模式识别。
- 增强 `CloudAgent.answer()`，支持识别日志分析和隐患扫描意图，自动调用日志查询工具。
- 新增 `POST /api/agent/scan` 隐患扫描接口，返回结构化隐患报告。
- 前端 Agent 对话面板增加快捷查询模板和历史分析展示。

阶段产物：

- 日志查询与隐患扫描工具
- 自然语言历史分析能力
- 隐患报告生成与导出

**状态：已完成**

### 阶段八：系统完善与课程报告

- 编写端到端集成测试，验证全链路。
- 设计并录制演示流程。
- 整理课程设计报告（需求分析、架构设计、模块详设、接口文档、测试、总结）。
- UI/UX 打磨和系统细节优化。

**状态：已完成**

## 3. 模块划分

### 3.1 边端模块

边端负责“采集 - 推理 - 调度 - 上报”的实时闭环。

对应仓库位置：

- `src/backend/edge_api/runtime/camera.py`：摄像头采集。
- `src/backend/edge_api/runtime/detector.py`：YOLO 检测。
- `src/backend/edge_api/runtime/pose.py`：基于关键点的姿态动作规则识别。
- `src/backend/shared/domain/scheduler.py`：任务复杂度判断与分流。
- `src/backend/edge_api/runtime/client.py`：边云通信客户端。
- `src/backend/edge_api/runtime/debug.py`：调试窗口和运行信息展示。
- `src/backend/edge_api/runtime/runner.py`：边端命令行入口。
- `src/frontend/edge_frontend/`：边端正式 UI。

职责说明：

- 采集视频帧或图像数据。
- 在本地完成轻量级目标检测。
- 对人体关键点进行规则化判断，优先识别站立、坐下、举手和蹲下等基础动作。
- 根据任务类型决定是否转发云端。
- 在网络波动时保留基础检测能力。

### 3.2 云端模块

云端负责“复杂理解 - 工具调用 - 结果生成”的智能决策闭环。

对应仓库位置：

- `src/backend/cloud_api/cloud/agent.py`：智能体编排入口。
- `src/backend/cloud_api/cloud/llm.py`：大模型客户端抽象。
- `src/backend/cloud_api/cloud/search.py`：联网搜索接口。
- `src/backend/cloud_api/cloud/knowledge.py`：本地知识库检索。
- `src/backend/cloud_api/routes/agent.py`：智能体相关 API。
- `src/backend/cloud_api/routes/tasks.py`：任务处理相关 API。
- `src/frontend/cloud_frontend/`：云端前端控制台。

职责说明：

- 接收边端上传的复杂任务。
- 调用 LLM、搜索和知识库进行综合分析。
- 输出可展示、可记录、可回溯的分析结果。

### 3.3 网络与数据模型模块

这一层负责统一边云之间的数据格式和通信边界。

对应仓库位置：

- `src/backend/shared/domain/models.py`：请求、响应和共享数据模型。
- `src/backend/cloud_api/dependencies.py`：云端服务依赖装配。
- `src/backend/shared/core/config.py`：配置读取。
- `src/backend/shared/core/state.py`：共享运行状态。

职责说明：

- 统一 JSON 请求和响应结构。
- 避免边端、云端和管理平台之间的数据格式漂移。
- 让接口模型先行，减少联调阶段的返工。

### 3.4 管理平台模块

管理平台负责“展示 - 追踪 - 交互”。

对应仓库位置：

- `src/frontend/cloud_frontend/src/components/StatusPanel.vue`：系统状态。
- `src/frontend/cloud_frontend/src/components/DetectionPanel.vue`：检测结果。
- `src/frontend/cloud_frontend/src/components/TaskLogPanel.vue`：任务日志。
- `src/frontend/cloud_frontend/src/components/AgentPanel.vue`：智能体对话。
- `src/frontend/cloud_frontend/src/api.ts`：前端 API 调用。

职责说明：

- 展示边端摄像头画面与检测结果。
- 展示任务分流和日志信息。
- 提供智能体对话界面和状态监控界面。

## 4. 需求和模块对应关系

| 课程设计要求 | 对应模块 | 仓库落点 | 验收关注点 |
| --- | --- | --- | --- |
| 边端实时检测 | 边端模块 | `backend/edge_api/runtime/`、`backend/shared/domain/` | 摄像头采集正常，YOLO-Pose 推理可运行，任务可分流 |
| 姿态动作识别 | 边端姿态模块 | `backend/edge_api/runtime/pose.py` | 能根据关键点识别站立、坐下、低头、举手等姿态，低置信度转云端 |
| 安全事件分析 | 边端事件 + 云端 Agent | `backend/edge_api/runtime/events.py`、`backend/cloud_api/cloud/agent.py` | 边端实时检测低头、摔倒、聚集等事件；云端结合大模型深度分析定级 |
| 知识库合理性分析 | 知识库 + 边端事件 | `data/knowledge/`、`backend/edge_api/runtime/events.py`、`backend/cloud_api/cloud/knowledge.py` | 时段规则和容量规则匹配，生成 unauthorized_time、excessive_people 事件 |
| 云端智能体 | 云端模块 | `backend/cloud_api/cloud/`、`backend/cloud_api/routes/agent.py` | 可调用模型、搜索和知识库，输出完整分析结果 |
| 自然语言日志分析 | 云端 Agent + 日志查询 | `backend/cloud_api/cloud/log_query.py`、`backend/cloud_api/cloud/agent.py` | 可按历史时间查询事件，生成趋势汇总和隐患扫描报告 |
| 事件持久化与报告 | 数据库 + 事件路由 | `backend/cloud_api/cloud/database.py`、`backend/cloud_api/routes/events.py` | PostgreSQL 持久化，支持历史检索和 Markdown 报告导出 |
| 网络通信 | 数据模型与 API | `backend/shared/domain/models.py`、`backend/cloud_api/`、`backend/edge_api/` | JSON 结构统一，边云通信稳定 |
| 边端正式 UI | 边端前端模块 | `frontend/edge_frontend/` | 实时画面、姿态骨架、事件列表、合理性状态可展示 |
| 可视化管理平台 | 云端前端模块 | `frontend/cloud_frontend/` | 事件管理、Agent 分析、日志查询、隐患扫描可展示 |
| Docker 部署 | 部署与运维 | `Dockerfile.cloud`、`docker-compose.yml` | 云端和管理平台可独立启动 |

## 5. 非功能性目标

- 实时性：边端检测尽量保持流畅，目标是满足基础实时展示需求。
- 可扩展性：云端 Agent、搜索工具和知识库都通过抽象层接入，方便替换实现。
- 易用性：前端信息要清晰，优先展示状态、日志和关键结果。
- 稳定性：网络异常时边端仍能完成基础检测，不影响本地运行。

## 6. 交付清单

- 边端程序源代码。
- 云端服务源代码。
- 管理平台源代码。
- 系统架构说明和模块设计说明。
- API 接口文档。
- 部署和复现说明。
- 演示视频或截图材料。

## 7. 后续写作建议

如果后续需要把这份内容整理成课程报告，可以继续扩展为：

1. 需求分析
2. 系统架构设计
3. 模块详细设计
4. 接口设计
5. 部署与测试
6. 总结与展望
