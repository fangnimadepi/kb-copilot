"""评测集构建：从语料 chunk 分层抽样，LLM 反向生成 QA 对。

方法：每个文档按比例抽 chunk（文本块与表格块都覆盖），让 DeepSeek 基于
chunk 内容出一道"自包含"的问题（问题里必须带公司/年份/报告期语境，
否则检索时无从定位）+ 标准答案。生成后需人工抽查修正（手册要求 30%）。

用法：python scripts/build_evalset.py [目标条数=100]
输出：data/evalset.jsonl  {question, ground_truth, source_file, page_start, chunk_id}
"""

import asyncio
import json
import random
import sys
from pathlib import Path

from openai import AsyncOpenAI
from sqlalchemy import select

from app.core.config import settings
from app.core.db_sync import SyncSessionLocal
from app.models.ingest import Chunk, Document

GEN_PROMPT = """你是投研评测集构建专家。基于下面这段来自《{filename}》第{page}页的内容片段，出一道问答题。

要求：
1. 问题必须仅凭该片段就能完整回答
2. 问题必须自包含：明确带上"贵州茅台"、年份和报告期（如"2023年年报"），脱离上下文也能看懂
3. 优先出具体事实题（数字、日期、方案、结论），不出开放式问题
4. 答案要简洁、准确，数字与原文完全一致
5. 如果该片段是目录、页眉、免责声明等无实质信息内容，输出 {{"skip": true}}

只输出 JSON：{{"question": "...", "answer": "..."}} 或 {{"skip": true}}

--- 片段 ---
{content}"""

client = AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,
    timeout=60,
    max_retries=2,
)
sem = asyncio.Semaphore(8)


def sample_chunks(n_target: int) -> list[dict]:
    """分层抽样：每个文档均分名额；表格块保证约 1/3 占比。"""
    with SyncSessionLocal() as db:
        docs = db.execute(select(Document).where(Document.chunk_count > 0)).scalars().all()
        per_doc = max(n_target * 3 // (2 * len(docs)), 1)  # 抽 1.5 倍备选，生成时会有 skip
        picked: list[dict] = []
        for doc in docs:
            rows = (
                db.execute(
                    select(Chunk).where(Chunk.document_id == doc.id, Chunk.token_count >= 120)
                )
                .scalars()
                .all()
            )
            tables = [c for c in rows if "|---|" in c.content]
            texts = [c for c in rows if "|---|" not in c.content]
            n_table = min(per_doc // 3, len(tables))
            take = random.sample(tables, n_table) + random.sample(
                texts, min(per_doc - n_table, len(texts))
            )
            picked += [
                {
                    "chunk_id": c.id,
                    "content": c.content,
                    "filename": doc.filename,
                    "page_start": c.page_start,
                }
                for c in take
            ]
    random.shuffle(picked)
    return picked


async def gen_qa(item: dict) -> dict | None:
    async with sem:
        try:
            resp = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {
                        "role": "user",
                        "content": GEN_PROMPT.format(
                            filename=item["filename"],
                            page=item["page_start"],
                            content=item["content"][:2500],
                        ),
                    }
                ],
                temperature=0.6,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
        except Exception as e:
            print(f"  gen failed chunk={item['chunk_id']}: {e}")
            return None
    if data.get("skip") or not data.get("question") or not data.get("answer"):
        return None
    return {
        "question": data["question"].strip(),
        "ground_truth": data["answer"].strip(),
        "source_file": item["filename"],
        "page_start": item["page_start"],
        "chunk_id": item["chunk_id"],
    }


async def main() -> None:
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    candidates = sample_chunks(target)
    print(f"sampled {len(candidates)} candidate chunks")
    results = await asyncio.gather(*[gen_qa(c) for c in candidates])
    qa = [r for r in results if r][:target]

    out = Path("data/evalset.jsonl")
    out.parent.mkdir(exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in qa:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    n_table = sum(
        1 for r in qa if "表" in r["question"] or any(ch.isdigit() for ch in r["ground_truth"])
    )
    print(f"wrote {len(qa)} QA pairs -> {out}（含数字/表格类约 {n_table} 条）")
    print("注意：按手册要求需人工抽查修正约 30%")


if __name__ == "__main__":
    asyncio.run(main())
