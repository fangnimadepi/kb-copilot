# 开发日志

> 每天记录：做了什么 / 踩了什么坑 / 做了什么决策。

## 2026-07-08（Day 1）

**做了什么**
- 立项：确定项目定位——企业级知识库问答平台（Python 重写版，参照自己之前的 Java/LangChain4j 版本做"翻译+升级"）
- 建仓库骨架：FastAPI 分层结构（api/services/models/core/tasks）、pyproject、.env 模板、README（架构图 + roadmap）
- 明确相对 Java 版的升级点：LangChain4j 黑盒链路 → 手写 RAG 链路；单阶段向量检索 → 召回+rerank 两阶段；Spring @Async → Celery 任务状态机；新增 Ragas 评测闭环

- 仓库推送 GitHub（fangnimadepi/kb-copilot），配好凭据
- 跑通参照物 Langchain-Chatchat（Docker）：不用官方捆绑 Xinference 的重方案，改为只跑 chatchat 容器 + 在线 API——LLM 用 DeepSeek、Embedding 用硅基流动 bge-m3；改 model_settings.yaml 的 MODEL_PLATFORMS（platform_type: openai 接任意兼容端点）后重启生效
- API 层面完整验证：/chat/chat/completions（LLM 直连）、创建知识库、upload_docs 向量化、search_docs 检索、/chat/kb_chat 端到端 RAG 问答全部通过

**踩坑 / 决策**
- Windows 本地开发：Celery 官方不支持 Windows、Milvus 只有 Docker 发行版 → 决定基础设施全部走 Docker Compose，Python 代码本地跑
- 私人计划文档通过 .gitignore 排除在仓库外；真实 API key 只放 .env（.env.example 一律占位符）
- 阿里云镜像仓库的 chatchat tag 已失效，改用 Docker Hub 的 chatimage/chatchat:0.3.1.3-717e03e-20241109
- chatchat 的 kb_chat 非流式响应是"JSON 字符串再编码一层"，客户端要 json.loads 两次——自己写 API 时要避免这种坑
- Web UI 新建知识库选 milvus 类型时"点击无反应"：镜像里没装 pymilvus，后端 500 且响应非 JSON，前端静默吞错。教训（自己项目要做对）：① 异常要统一转结构化 JSON 错误响应；② 前端必须对失败态给出明确提示。参照物用 faiss 即可
- pptx 入库失败：缺 python-pptx 依赖（容器内 pip install 解决）。看清了 Chatchat 的 OCR 方案：调用开源 RapidOCR（onnxruntime），自己只写 Loader 封装（RapidOCRPDFLoader = PyMuPDF 抽文本 + 图片 OCR；RapidOCRPPTLoader = python-pptx 遍历 + 图片 OCR）。启发：文档解析选型"成熟库 + 自封装"即可，OCR 不必自研
- 英文 PDF"检索有匹配但 LLM 拒答"完整归因：top_k=3 召回的片段都来自实验章节，不含问题答案（定义在摘要）；RAG prompt 限定"仅据已知信息回答"→ 拒答（防幻觉行为正确，是召回质量问题）。**读源码发现 Chatchat 0.3.1.3 的 rerank 代码整段被注释——实际只有单阶段向量召回**。这就是自己项目要做两阶段检索（召回 top20 + reranker 精排 top5）的最直接论据；top_k 调大能缓解但拉长上下文/延迟（trade-off 面试考点）

**语料选型（阶段 0 收尾）**
- 场景定为"贵州茅台投研知识库"：从巨潮资讯抓取 2020~2025 财年年报 6 份 + 半年报 5 份，共 11 份中文完整版 PDF（data/corpus/，不进仓库）
- 选型理由：对标金融 JD；年报表格密度高（三大报表/股东/薪酬），支撑"表格解析 + 页码溯源"卖点；评测题可设计跨年度对比、表格内数字、否定式三类刁钻问题
- 后续可扩展：加五粮液/泸州老窖做跨公司对比；加交易所监管规则做合规问答；转 1~2 份为 docx、加几份 markdown 凑齐三格式解析演示

**明天**
- 精读 Chatchat 三处源码：ChineseRecursiveTextSplitter 分块 / kb_chat 检索链路 / FastAPI 路由组织（已拉到 reference/，读完记笔记）
- 进入阶段 1：FastAPI 骨架 + SSE 流式对话
