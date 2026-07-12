"""阶段 3 验收：10 个刁钻问题过 /api/kb_chat，人工核对引用与拒答。

问题设计（按手册）：表格内数字、跨文档（跨年度）对比、否定式、知识库外拒答。
"""

import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"

QUESTIONS = [
    # 表格内数字
    "贵州茅台2024年度的营业收入是多少？",
    "2023年年报里，董事长的税前报酬总额是多少？",
    "2022年年度报告中经营活动产生的现金流量净额是多少？",
    # 跨文档（跨年度）对比
    "对比2023年和2024年的营业收入，同比增长了多少？",
    "茅台酒和系列酒在2024年的营收分别是多少？",
    # 细节/否定式
    "2024年年报中是否披露了公司面临的主要风险？都有哪些？",
    "公司2023年有没有进行现金分红？方案是什么？",
    "2025年半年度报告的审计意见是什么类型？是否经过审计？",
    # 知识库外（应拒答）
    "五粮液2024年的营业收入是多少？",
    "贵州茅台2026年三季度的业绩预告是什么？",
]


def ask(client: httpx.Client, question: str) -> dict:
    refs, answer, refused = [], [], None
    start = time.time()
    with client.stream(
        "POST", f"{BASE}/api/kb_chat", json={"message": question}, timeout=180
    ) as resp:
        resp.raise_for_status()
        event = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = json.loads(line.split(":", 1)[1].strip())
                if event == "refs":
                    refs = data
                elif event == "delta":
                    answer.append(data["content"])
                elif event == "done":
                    refused = data.get("refused")
    return {
        "answer": "".join(answer),
        "refs": refs,
        "refused": refused,
        "elapsed": time.time() - start,
    }


def main() -> None:
    out = []
    with httpx.Client() as client:
        for i, q in enumerate(QUESTIONS, 1):
            r = ask(client, q)
            print(f"\n{'=' * 70}\nQ{i}: {q}   ({r['elapsed']:.1f}s, refused={r['refused']})")
            print(f"A: {r['answer']}")
            for ref in r["refs"]:
                pages = (
                    f"p{ref['page_start']}"
                    if ref["page_start"] == ref["page_end"]
                    else f"p{ref['page_start']}-{ref['page_end']}"
                )
                print(f"   [{ref['ref']}] {ref['filename']} {pages} rerank={ref['rerank_score']}")
            out.append({"question": q, **r})
    with open(
        sys.argv[1] if len(sys.argv) > 1 else "kb_eval_result.json", "w", encoding="utf-8"
    ) as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
