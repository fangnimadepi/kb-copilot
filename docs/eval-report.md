# 评测报告（阶段 4）

> 评测集：100 条 QA（从 11 份贵州茅台年报/半年报的 4519 个 chunk 分层抽样，
> DeepSeek 反向生成 + 人工修正），85% 为数字/表格类事实题——贴合投研场景的难度分布。
> 评测框架：Ragas（judge = DeepSeek，embedding = bge-m3）。
> 指标：faithfulness（忠实度，防幻觉）/ answer_relevancy（答案相关性）/
> context_recall（上下文召回，检索是否找到了答案所在内容）/ context_precision（上下文精度，检索结果里有多少是有用的）。

## 实验一：纯向量召回 vs 召回 + rerank

| 配置 | faithfulness | answer_relevancy | context_recall | context_precision | P95 延迟 |
|---|---|---|---|---|---|
| 纯向量 top5 | TBD | TBD | TBD | TBD | TBD |
| 召回20 + rerank top5（默认） | TBD | TBD | TBD | TBD | TBD |

**结论**：TBD

## 实验二：final top_k = 3 / 5 / 10

| 配置 | faithfulness | answer_relevancy | context_recall | context_precision | P95 延迟 |
|---|---|---|---|---|---|
| top_k=3 | TBD | TBD | TBD | TBD | TBD |
| top_k=5（默认） | TBD | TBD | TBD | TBD | TBD |
| top_k=10 | TBD | TBD | TBD | TBD | TBD |

**结论**：TBD

## 实验三：分块策略 fixed vs structured

| 配置 | faithfulness | answer_relevancy | context_recall | context_precision | P95 延迟 |
|---|---|---|---|---|---|
| fixed（500 字 / overlap 100） | TBD | TBD | TBD | TBD | TBD |
| structured（标题层级聚合） | TBD | TBD | TBD | TBD | TBD |

**结论**：TBD

## 最终默认配置

TBD

## 复现方式

```bash
python scripts/build_evalset.py 100          # 生成评测集
python scripts/run_eval.py --name baseline   # 跑指定配置（见 --help）
python scripts/run_ragas.py results/baseline.json  # Ragas 打分
```
