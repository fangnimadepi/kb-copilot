"""Ragas 打分：读 run_eval.py 的结果文件，输出四指标。

judge LLM = DeepSeek，embedding = 硅基流动 bge-m3（answer_relevancy 用）。

用法：python scripts/run_ragas.py results/baseline.json [results/xxx.json ...]
"""

import json
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import EvaluationDataset, RunConfig, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    AnswerRelevancy,
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
)

from app.core.config import settings

judge = LangchainLLMWrapper(
    ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=0,
        timeout=120,
    )
)
emb = LangchainEmbeddingsWrapper(
    OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        check_embedding_ctx_length=False,
    )
)

METRICS = [
    Faithfulness(llm=judge),
    # strictness=1：DeepSeek 不支持 OpenAI 的 n>1 采样参数（默认 strictness=3 会带 n=3）
    AnswerRelevancy(llm=judge, embeddings=emb, strictness=1),
    LLMContextRecall(llm=judge),
    LLMContextPrecisionWithReference(llm=judge),
]


def score_file(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    samples = [
        {
            "user_input": it["question"],
            "response": it["answer"],
            "retrieved_contexts": it["contexts"] or [""],
            "reference": it["ground_truth"],
        }
        for it in data["items"]
    ]
    ds = EvaluationDataset.from_list(samples)
    result = evaluate(ds, metrics=METRICS, run_config=RunConfig(max_workers=8, timeout=180))
    scores = {k: round(float(v), 4) for k, v in result._repr_dict.items()}
    print(f"{data['config']['name']}: {scores}  latency={data['latency']}")
    return {"config": data["config"], "latency": data["latency"], "scores": scores}


def main() -> None:
    summary = [score_file(p) for p in sys.argv[1:]]
    out = Path("results/summary.json")
    existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    names = {s["config"]["name"] for s in summary}
    merged = [e for e in existing if e["config"]["name"] not in names] + summary
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"summary -> {out}")


if __name__ == "__main__":
    main()
