# 评测报告（阶段 4）

> **评测集**：100 条 QA，从 11 份贵州茅台年报/半年报（4519 chunk）分层抽样、DeepSeek 反向出题、
> 人工抽查 30 条修正 3 条（v1.1）。85% 为数字/表格类事实题，难度贴合投研场景。
> **框架**：Ragas 0.4（judge = DeepSeek，embedding = bge-m3，AnswerRelevancy strictness=1）。
> **指标**：faithfulness（忠实度，防幻觉）/ answer_relevancy（答案相关性）/
> context_recall（答案所需内容是否被检索到）/ context_precision（检索结果中有用内容占比）。
> **延迟**：端到端（含 LLM 生成），并发 6 下测得。

## 总表（100 题 × 5 配置）

| 配置 | faithfulness | answer_relevancy | context_recall | context_precision | P50 | P95 |
|---|---|---|---|---|---|---|
| 纯向量 top5 | 0.30 | 0.29 | 0.26 | 0.19 | 1.11s | 1.66s |
| **fixed + rerank top5（默认）** | 0.35 | 0.34 | **0.36** | 0.27 | 1.37s | 1.91s |
| fixed + rerank top3 | **0.38** | 0.33 | 0.31 | **0.28** | 1.63s | 2.23s |
| fixed + rerank top10 | **0.39** | **0.42** | 0.33 | 0.24 | 1.45s | 2.00s |
| structured + rerank top5 | 0.31 | 0.32 | 0.29 | 0.23 | 1.48s | 2.08s |

## 实验一：纯向量召回 vs 召回 + rerank（其余变量固定：fixed / top5）

**结论：rerank 四项指标全面提升，是性价比最高的一处优化。**
- context_recall **0.26 → 0.36（相对 +38%）**，context_precision **0.19 → 0.27（相对 +42%）**
- faithfulness 0.30 → 0.35，answer_relevancy 0.29 → 0.34
- 代价：P95 +0.25s（bge-reranker API 一次调用）

机制：embedding 双塔模型把长文本压成单向量存在信息瓶颈，召回列表排序粗糙；
交叉编码器对 query+doc 做全量注意力交叉，在 20 条小候选集上精排，精度换回来了。

## 实验二：final top_k = 3 / 5 / 10（其余变量固定：fixed / rerank）

**结论：典型三方 trade-off，top5 为均衡点，设为默认。**
- top3：上下文最干净（precision 0.28 最高）但召回受损（recall 0.31）——答案不在前 3 条就没救
- top10：上下文最全（relevancy 0.42 最高）但噪声最多（precision 0.24 最低）、token 成本最大
- top5：**recall 0.36 最高**——"答案在不在上下文里"是 RAG 的第一瓶颈，故选 top5
- 注意：三档间部分差异在 ±0.03~0.05 噪声带内（n=100），结论以 recall 主导

## 实验三：分块策略 fixed vs structured（其余变量固定：rerank / top5）

**结论（反直觉）：structured 在本评测集上全面弱于 fixed，默认保留 fixed。**

| | fixed | structured |
|---|---|---|
| chunk 总数 | 4519 | 5177（+15%） |
| context_recall | **0.36** | 0.29 |
| context_precision | **0.27** | 0.23 |

原因分析（按可信度排序）：
1. **评测集亲和性偏差**：评测题由 fixed 分块的 chunk 反向生成，问题的信息边界天然与 fixed 块对齐，
   对 structured 不公平。要做无偏对比，需要按页面/章节独立采样出题——记为后续工作。
2. 年报附注中"一、/（一）"编号密集，structured 的标题检测导致过度切分，块变碎。
3. 节标题前缀稀释了表格数字在向量空间中的特征。

> 工程教训：structured 第一版曾因"PDF 每页一个 unit、标题埋在页中间"而静默退化成 fixed
> （产物逐字节相同），靠 chunk 计数对照才发现。**对照实验先验证变量真的变了。**

## 最终默认配置

`fixed(500/overlap 100) + Milvus HNSW 召回 top20 + bge-reranker-v2-m3 精排 top5 + 阈值 0.35`
——即 `app/core/config.py` 当前默认值。端到端 P50 1.37s / P95 1.91s。

## 方法论说明（防质疑）

- 绝对分数偏低（0.3 档）的两个客观原因：① 评测集 85% 是财报附注深处的硬题；
  ② 拒答回答（"知识库中未找到"）在 faithfulness/answer_relevancy 中天然得低分，
  这是"宁可拒答不瞎编"的设计代价。对照结论不受影响（所有配置同等承受）。
- 五个配置使用同一评测集快照（v1.0）打分，横向可比；v1.1 的 3 处人工修正
  （<1% 影响）自下一轮起生效。
- rerank 分数跨查询不可比（库外问题也可能出现 0.97 高分 chunk），拒答需要
  "阈值层 + prompt 层"双层设计——阈值只是第一道粗滤。

## 复现

```bash
python scripts/build_evalset.py 100                # 生成评测集
python scripts/run_eval.py --name baseline          # 生成回答（--no-rerank / --final-top-k 3 等见 --help）
python scripts/run_ragas.py results/baseline.json   # Ragas 打分，汇总至 results/summary.json
```
