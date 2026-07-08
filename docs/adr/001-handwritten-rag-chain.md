# ADR-001: 手写 RAG 链路，LangChain 只用组件层

## 背景

上一版（Java/LangChain4j）的 RAG 链路完全依赖框架的 `ContentRetriever` + AiService 黑盒：检索、Prompt 组装、上下文注入都在框架内部完成。带来两个问题：
1. 无法插入自定义环节（rerank、引用标注、无答案兜底都难做）；
2. 链路细节说不清，调优只能改 `maxResults`/`minScore` 两个参数。

## 备选方案

- **A. 全用 LangChain（LCEL / Chain）**：开发最快，但链路黑盒化，自定义环节要和框架抽象搏斗，出问题难排查。
- **B. 完全不用框架**：一切自己写，包括文档 Loader、Splitter——重复造轮子，这部分并无技术含量。
- **C. 手写链路 + LangChain 只当工具库**：召回 → 重排 → Prompt 组装 → LLM 调用 → 流式输出全部自己写；只复用 LangChain 的 Document Loader / Text Splitter 这类纯组件。

## 决策

选 **C**。核心链路每一步可控、可观测、可做对照实验（分块策略、rerank 开关、top_k 都要进评测），同时不在文档解析这类通用组件上浪费时间。

## 后果

- ✅ rerank、引用溯源、拒答兜底可以自由插入链路任意位置
- ✅ 每一步可以打点计时，评测报告能拆到环节级
- ❌ 代码量比全用 LangChain 多，需要自己维护 Prompt 模板与上下文组装逻辑
