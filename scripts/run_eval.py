"""评测 runner：对评测集逐题跑 检索 -> 生成，记录答案/上下文/延迟。

直接调项目内部链路（不走 HTTP），以便注入对照配置。

用法：
  python scripts/run_eval.py --name baseline
  python scripts/run_eval.py --name no_rerank --no-rerank
  python scripts/run_eval.py --name top3 --final-top-k 3
输出：results/<name>.json
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from app.api.kb_chat import RAG_PROMPT, REFUSAL, _build_context
from app.core.db import SessionLocal
from app.core.llm import stream_chat
from app.services.retrieval import retrieve

sem = asyncio.Semaphore(6)


async def run_one(row: dict, args: argparse.Namespace) -> dict:
    async with sem:
        t0 = time.perf_counter()
        async with SessionLocal() as db:
            chunks = await retrieve(
                row["question"],
                db,
                recall_top_k=args.recall_top_k,
                final_top_k=args.final_top_k,
                use_rerank=not args.no_rerank,
            )
        t_retrieval = time.perf_counter() - t0

        if not chunks:
            answer = REFUSAL
        else:
            prompt = RAG_PROMPT.format(
                context=_build_context(chunks), question=row["question"]
            )
            parts = [
                d async for d in stream_chat([{"role": "user", "content": prompt}], temperature=0.3)
            ]
            answer = "".join(parts)
        t_total = time.perf_counter() - t0

    return {
        **row,
        "answer": answer,
        "contexts": [c.content for c in chunks],
        "retrieved_pages": [[c.filename, c.page_start] for c in chunks],
        "t_retrieval": round(t_retrieval, 3),
        "t_total": round(t_total, 3),
    }


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--evalset", default="data/evalset.jsonl")
    p.add_argument("--recall-top-k", type=int, default=None)
    p.add_argument("--final-top-k", type=int, default=None)
    p.add_argument("--no-rerank", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    rows = [json.loads(line) for line in Path(args.evalset).read_text(encoding="utf-8").splitlines()]
    if args.limit:
        rows = rows[: args.limit]
    print(f"[{args.name}] {len(rows)} questions ...")

    t0 = time.time()
    results = await asyncio.gather(*[run_one(r, args) for r in rows])
    lat = sorted(r["t_total"] for r in results)
    p50 = lat[len(lat) // 2]
    p95 = lat[int(len(lat) * 0.95) - 1]

    out = Path("results") / f"{args.name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "config": {
                    "name": args.name,
                    "recall_top_k": args.recall_top_k,
                    "final_top_k": args.final_top_k,
                    "use_rerank": not args.no_rerank,
                },
                "latency": {"p50": p50, "p95": p95},
                "items": results,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"[{args.name}] done in {time.time() - t0:.0f}s, P50={p50}s P95={p95}s -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
