from app.services.chunking import split_units
from app.services.parsing import TextUnit


def make_units() -> list[TextUnit]:
    return [
        TextUnit(text="第一章 公司概况\n" + "茅台酒生产工艺说明。" * 20, page=1),
        TextUnit(text="经营数据详表。" * 30, page=2),
        TextUnit(text="第二章 财务报告\n" + "营业收入与利润分析。" * 20, page=3),
    ]


def test_fixed_respects_size_and_overlap():
    chunks = split_units(make_units(), strategy="fixed", chunk_size=200, overlap=50)
    assert all(len(c.content) <= 200 for c in chunks)
    # 相邻块存在重叠：后块开头应出现在前块尾部
    assert chunks[1].content[:30] in chunks[0].content


def test_fixed_page_range_tracks_source():
    chunks = split_units(make_units(), strategy="fixed", chunk_size=200, overlap=50)
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 3
    # 页码范围单调不减
    for prev, cur in zip(chunks, chunks[1:]):
        assert cur.page_start >= prev.page_start


def test_structured_splits_on_headings():
    chunks = split_units(make_units(), strategy="structured", chunk_size=5000, overlap=0)
    # 两个"第X章"标题 => 至少两个 section 块
    assert len(chunks) == 2
    assert chunks[0].content.startswith("第一章")
    assert chunks[1].content.startswith("第二章")


def test_structured_long_section_falls_back_with_title():
    chunks = split_units(make_units(), strategy="structured", chunk_size=200, overlap=20)
    # 超长节回落切分后，子块以节标题开头
    tail_chunks = [c for c in chunks if c.page_start >= 3]
    assert all(c.content.startswith("第二章 财务报告") for c in tail_chunks)


def test_token_count_populated():
    chunks = split_units(make_units(), strategy="fixed", chunk_size=200, overlap=50)
    assert all(c.token_count > 0 for c in chunks)


def test_structured_detects_heading_inside_unit():
    # PDF 的 unit 是整页：标题埋在页中间也必须被识别为节边界
    page = TextUnit(
        text="页眉：贵州茅台年度报告\n" + "前言内容。" * 10 + "\n第三节 管理层讨论与分析\n" + "经营分析内容。" * 10,
        page=5,
    )
    chunks = split_units([page], strategy="structured", chunk_size=5000, overlap=0)
    assert len(chunks) == 2
    assert chunks[1].content.startswith("第三节")


def test_unknown_strategy_raises():
    import pytest

    with pytest.raises(ValueError):
        split_units(make_units(), strategy="magic")
