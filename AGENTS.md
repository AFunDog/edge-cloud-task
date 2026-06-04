# AGENTS

## 项目约定

- 源代码放在 `src/edge_cloud_system/`，按 `api / edge / cloud / domain / core / management` 分层。
- 新增后端接口时优先补充 `domain/models.py` 中的请求和响应模型。
- 不要把真实 API Key、模型服务地址或私有知识库内容提交到仓库；使用 `.env` 和 `.env.example`。
- 默认测试应使用模拟模型、模拟搜索和本地知识库，不触发付费大模型或外网请求。
- Docker 配置需要保持云端服务和管理平台可独立启动。

## 验证

```powershell
python -m pytest
python -m compileall src
```
