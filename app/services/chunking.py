"""分块策略。输出 ChunkDraft（文本 + 页码范围），供向量化与落库。

两种策略（阶段 4 做对照实验）：
- fixed：固定长度 + overlap。overlap 的作用是让被切断的语义在相邻块中
  各保留一份，代价是索引膨胀（overlap/size 的比例）。
- structured：按标题层级聚合成节，节内超长再回落到 fixed 切分。
  对年报这类层级分明的文档，块边界与语义边界对齐，理论召回更准。
"""

import re
from dataclasses import dataclass

from app.core.tokens import count_tokens
from app.services.parsing import TextUnit

_HEADING = re.compile(r"^(#{1,6} |第[一二三四五六七八九十百]+[章节] |\d{1,2}(\.\d{1,2}){0,3}\s+\S)")


@dataclass
class ChunkDraft:
    content: str
    page_start: int
    page_end: int
    token_count: int = 0


def split_units(
    units: list[TextUnit],
    strategy: str = "fixed",
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[ChunkDraft]:
    if strategy == "fixed":
        return _fixed(units, chunk_size, overlap)
    if strategy == "structured":
        return _structured(units, chunk_size, overlap)
    raise ValueError(f"未知分块策略: {strategy}（可选 fixed / structured）")


def _fixed(units: list[TextUnit], chunk_size: int, overlap: int) -> list[ChunkDraft]:
    """把所有 unit 拼成带页码标记的字符流，按 chunk_size 字符切，相邻块重叠 overlap。"""
    # (char_offset, page) 记录页码边界，切块后据此回查页码范围
    buf: list[str] = []
    boundaries: list[tuple[int, int]] = []
    offset = 0
    for u in units:
        boundaries.append((offset, u.page))
        buf.append(u.text)
        offset += len(u.text) + 1
    text = "\n".join(buf)

    chunks: list[ChunkDraft] = []
    step = max(chunk_size - overlap, 1)
    for start in range(0, len(text), step):
        piece = text[start : start + chunk_size]
        if not piece.strip():
            continue
        chunks.append(
            ChunkDraft(
                content=piece,
                page_start=_page_at(boundaries, start),
                page_end=_page_at(boundaries, start + len(piece) - 1),
            )
        )
        if start + chunk_size >= len(text):
            break
    return _with_tokens(chunks)


def _structured(units: list[TextUnit], chunk_size: int, overlap: int) -> list[ChunkDraft]:
    """按标题聚合：遇到标题行开新节；节内容超过 chunk_size 时回落 fixed 切分，
    并把节标题冠到每个子块开头（保住上下文语义）。"""
    sections: list[tuple[str, list[TextUnit]]] = []
    title, current = "", []
    for u in units:
        first_line = u.text.strip().splitlines()[0] if u.text.strip() else ""
        if _HEADING.match(first_line):
            if current:
                sections.append((title, current))
            title, current = first_line[:80], [u]
        else:
            current.append(u)
    if current:
        sections.append((title, current))

    chunks: list[ChunkDraft] = []
    for title, sec_units in sections:
        total = sum(len(u.text) for u in sec_units)
        if total <= chunk_size:
            chunks.append(
                ChunkDraft(
                    content="\n".join(u.text for u in sec_units),
                    page_start=min(u.page for u in sec_units),
                    page_end=max(u.page for u in sec_units),
                )
            )
        else:
            for sub in _fixed(sec_units, chunk_size, overlap):
                if title and not sub.content.startswith(title):
                    sub.content = f"{title}\n{sub.content}"
                chunks.append(sub)
    return _with_tokens([c for c in chunks if c.content.strip()])


def _page_at(boundaries: list[tuple[int, int]], offset: int) -> int:
    page = boundaries[0][1] if boundaries else 0
    for boundary_offset, boundary_page in boundaries:
        if boundary_offset > offset:
            break
        page = boundary_page
    return page


def _with_tokens(chunks: list[ChunkDraft]) -> list[ChunkDraft]:
    for c in chunks:
        c.token_count = count_tokens(c.content)
    return chunks
