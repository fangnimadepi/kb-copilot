# 开发日志

> 每天记录：做了什么 / 踩了什么坑 / 做了什么决策。

## 2026-07-08（Day 1）

**做了什么**
- 立项：确定项目定位——企业级知识库问答平台（Python 重写版，参照自己之前的 Java/LangChain4j 版本做"翻译+升级"）
- 建仓库骨架：FastAPI 分层结构（api/services/models/core/tasks）、pyproject、.env 模板、README（架构图 + roadmap）
- 明确相对 Java 版的升级点：LangChain4j 黑盒链路 → 手写 RAG 链路；单阶段向量检索 → 召回+rerank 两阶段；Spring @Async → Celery 任务状态机；新增 Ragas 评测闭环

**踩坑 / 决策**
- Windows 本地开发：Celery 官方不支持 Windows、Milvus 只有 Docker 发行版 → 决定基础设施全部走 Docker Compose，Python 代码本地跑
- 私人计划文档通过 .gitignore 排除在仓库外

**明天**
- 跑通 Langchain-Chatchat 参照物，精读其分块 / 检索链路 / 路由组织
- 选定语料（某开源产品官方文档 PDF 30~50 份）
