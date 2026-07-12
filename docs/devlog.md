# 开发日志

> 每天记录：做了什么 / 踩了什么坑 / 做了什么决策。

## 2026-07-12（Day 2 · 阶段 4 完成）★ 全项目最值钱的一天

**做了什么**
- 评测集：4519 chunk 分层抽样（每文档均分名额、表格块占 1/3）→ DeepSeek 反向出题（自包含性约束 + skip 规则）→ 100 条 QA；人工抽查 30 条修正 3 条（数字取错单元格 / 缺"母公司口径"限定 / 负号列示歧义）
- 评测管线：run_eval.py（直调内部链路、可注入配置、并发 6、记 P50/P95）+ run_ragas.py（judge=DeepSeek、embedding=bge-m3）
- 三组对照实验 × 100 题跑完（结果见 docs/eval-report.md），最终默认配置：fixed + rerank top5

**核心数字（简历素材）**
- rerank：context_recall 0.26→0.36（+38%），context_precision 0.19→0.27（+42%），P95 代价 +0.25s
- top_k：top5 召回最优的均衡点；端到端 P50 1.37s / P95 1.91s
- structured 分块反直觉地弱于 fixed（recall 0.29 vs 0.36）——评测集由 fixed chunk 反向生成，存在亲和性偏差；如实写进报告

**踩坑**
- ragas 0.4.3 与 langchain-community 0.4 不兼容（import vertexai 报错）→ 锁 langchain-community<0.4
- DeepSeek 不支持 OpenAI 的 n>1 采样 → AnswerRelevancy(strictness=1)
- structured 分块静默失效（见 fix commit）：PDF 每页一 unit、标题埋页中，节检测只看 unit 首行 → 整书一个大节回落 fixed，产物逐字节相同。靠 chunk 计数对照发现。**教训：对照实验先验证变量真的变了**
- 权限分类服务中断期间用只读工具核对了 ragas API 兼容性——阻塞时先做能做的

**下一步（阶段 5：工程化收尾）**
- docker compose 补 api/worker 服务、部署云服务器、README 快速启动、CI（lint + 单测）

## 2026-07-12（Day 2 · 阶段 3 完成）

**做了什么**
- 两阶段检索链路（services/retrieval.py）：bge-m3 查询向量化 → Milvus HNSW 召回 top20 → bge-reranker-v2-m3 精排 top5 → 阈值过滤（0.35）
- /api/kb_chat SSE：新增 refs 事件（[n] → 文件名+页码+召回分/精排分），RAG prompt 带引用标注规则与数字保真规则；拒答双保险 = 阈值层（不调 LLM 直接拒答）+ prompt 层（检索内容不足时模型自答"未找到"）
- 验收：10 个刁钻问题（表格数字/跨年对比/否定式/库外）全部通过——数字类正确引用到页，跨年对比自动列计算式，库外问题无幻觉拒答；单问延迟 1.3~2.5s

**踩坑 / 发现（阶段 4 实验素材）**
- **定长分块切断表格行的实证**：2024 年报按产品档次营收表被 fixed 分块从数字中间切断（chunk 开头是残缺的 ",955.31 | 15.28"），LLM 面对残行错位表格把"小计"错标为"茅台酒"并产生数字幻觉。原始解析正确、检索正确，错误发生在**分块边界**——表格感知分块（表格原子性）是明确的改进方向
- **rerank 分数跨查询不可比**：问"五粮液营收"，含五粮液对比数据的茅台年报 chunk 精排分高达 0.97，阈值拦不住——拒答不能只靠检索分数阈值，prompt 层约束是必要的第二道防线（本次两个库外问题均由 prompt 层正确拒答）
- 薪酬表、风险章节召回未命中（Q2/Q6），fixed vs structured 对照实验待做

**下一步（阶段 4：评测闭环）**
- 100 条 QA 评测集（LLM 辅助生成 + 人工修正）→ Ragas 四指标 → 三组对照实验（分块策略 / rerank 开关 / top_k）→ P95 延迟

## 2026-07-12（Day 2 下半场 · 阶段 2 完成）

**做了什么**
- 文档入库流水线全链路：上传 API（202 + task_id）→ Celery 任务 → 解析（PDF/docx/md，PDF 表格重排为 Markdown、逐页保留页码）→ 分块（fixed / structured 双策略）→ bge-m3 批量向量化 → Milvus（HNSW/COSINE）+ chunk 元数据入 MySQL
- 任务状态机：pending → parsing → embedding → done/failed/canceled，进度百分比按 embedding 批次推进；取消是协作式（批间检查点）；重试先清旧数据保证幂等
- Milvus standalone 单容器部署（内嵌 etcd，见 infra/embedEtcd.yaml）
- ADR-003：Celery vs BackgroundTasks

**验收结果（手册阶段 2 标准）**
- 批量上传 10 份年报 API 0.8s 返回，不阻塞 ✅
- 杀掉 worker 再重启：在途任务经 acks_late 自动重投并完成，无人工干预 ✅
- 失败任务错误信息明确（UnsupportedFormat: 不支持的格式: .xlsx）；取消/重试接口状态迁移正确 ✅
- 数据一致性：单文档 MySQL 358 chunk = Milvus 358 向量，页码范围与 PDF 实际页数吻合 ✅

**踩坑 / 决策**
- **本阶段最大发现：Celery + Redis 的 acks_late 崩溃重投不是即时的**。杀 worker 后在途消息躺在 Redis unacked 集合，要等 visibility_timeout（默认 1 小时！）超时才被回收重投，且回收检查主要发生在 worker 启动时。实测：一个任务卡"parsing"状态 20 分钟，队列已空——就是这个机制。修复：visibility_timeout 调到 600s（必须 > 单任务最长时长，否则运行中任务被误判超时导致重复投递；幂等设计是最后防线）。RabbitMQ 是断连即重投，没有这个问题——这是 broker 选型的真实差异点
- PowerShell multipart 客户端把中文文件名编码成 RFC 2047（=?utf-8?B?...?=），内含 Windows 非法字符 `?`，落盘 OSError——教训：**服务端永远不能信任客户端文件名**，统一解码（email.header）+ 清洗非法字符 + 去路径分量防目录穿越
- acks_late 崩溃重投的前提是任务幂等：任务开头先删同文档旧 chunk/向量再写入
- Celery 取消没有安全的强杀手段，采用协作式取消：embedding 批间回查状态位；worker 侧读取消标记要 expire_all() 绕过 Session 缓存
- Windows 下 Celery 只能 --pool=solo 单并发，生产部署（Docker/Linux）换 prefork

**下一步（阶段 3：两阶段检索 + 引用溯源）**
- Milvus top20 召回 → bge-reranker 精排 top5 → prompt 组装带 [n] 引用标注 → 低分拒答兜底

## 2026-07-12（Day 2 · 阶段 1 完成）

**做了什么**
- LLM 客户端封装（app/core/llm.py）：AsyncOpenAI 流式调用 + 超时 + 指数退避重试；重试边界设计为"只在首块响应前重试"——流已开始的失败无法安全回滚，通过 SSE error 事件告知客户端
- /api/chat SSE 流式接口：事件协议 meta（回会话 id）→ delta（增量）→ done（落库确认）/ error
- 会话与消息 MySQL 落库（SQLAlchemy 2.0 async + aiomysql），token_count 入库时预计算，裁剪时零编码开销
- 上下文裁剪（services/context.py 纯函数）：从新往旧按 token 预算保留，system 始终保留、最新用户消息无条件保留；6 个单测覆盖边界
- 统一错误响应 {"code", "message"} + 请求日志中间件（request_id + 耗时）——落实 Chatchat 静默失败的反面教训
- ADR-002：SSE vs WebSocket 选型

**验收结果（手册阶段 1 标准）**
- curl 逐 token 流式输出 ✅
- 同一会话连续 20 轮不崩（scripts/chat_smoke.py，累计 11680 token）✅
- 裁剪正确触发：40 条 → 27 条，稳定卡在 8000 预算内 ✅

**踩坑 / 决策**
- 本机 3306 被系统 MySQL 服务占用 → 容器映射 3307
- setuptools flat-layout 发现多个顶层目录（app/data/reference）拒绝构建 → pyproject 显式 packages.find include=["app*"]
- Windows 控制台 GBK：Python 日志/输出里的中文在重定向文件里成乱码，查日志用 ASCII 关键字（logger 名）兜底；后续可设 PYTHONIOENCODING=utf-8
- PowerShell 给 curl.exe 传 JSON 会被引号转义坑，改用 -d @file

**下一步（阶段 2：异步入库流水线）**
- 文档上传接口 → Celery 任务 → task_id；PDF/Word/Markdown 解析；两种分块策略；Milvus 写入；任务状态机

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
