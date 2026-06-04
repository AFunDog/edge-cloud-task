# 端-边-云协同智能检测系统

本项目实现一套课程实验用的完整系统骨架，覆盖边缘侧实时检测、云端智能体、网络通信接口和 Python 可视化管理平台。

## 结构

```text
src/edge_cloud_system/
  api/            FastAPI 云端接口
  cloud/          LLM、搜索、知识库与智能体编排
  core/           配置与共享状态
  domain/         统一数据模型
  edge/           YOLO 检测、任务调度、边云通信
  management/     Streamlit 管理平台
docs/             架构与实验说明
tests/            核心逻辑测试
```

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e .[test]
.\.venv\Scripts\uvicorn edge_cloud_system.api.main:app --reload
```

另开一个终端启动管理平台：

```powershell
.\.venv\Scripts\streamlit run src/edge_cloud_system/management/app.py
```

边端模拟采集与调度：

```powershell
.\.venv\Scripts\python -m edge_cloud_system.edge.runner --task "车辆计数"
```

如需启用真实 YOLO 摄像头检测，可安装可选依赖：

```powershell
.\.venv\Scripts\pip install -e .[yolo]
```

然后在 `.env` 中配置 `YOLO_MODEL_PATH`，可使用本地 `.pt` 模型或 Ultralytics 支持的模型名称。

## Docker

```powershell
docker compose up --build
```

默认暴露：

- API: `http://localhost:8000`
- 管理平台: `http://localhost:8501`

## 当前实现边界

默认运行路径不会调用付费模型或真实联网搜索。云端智能体通过可替换的 `LLMClient`、`SearchTool` 和 `KnowledgeBase` 接口工作；配置 API Key 后可继续扩展真实供应商。
