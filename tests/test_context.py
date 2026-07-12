from app.services.context import trim_messages


def msg(role: str, content: str, tokens: int) -> dict:
    return {"role": role, "content": content, "token_count": tokens}


def test_within_budget_keeps_all():
    messages = [msg("system", "s", 10), msg("user", "q1", 10), msg("assistant", "a1", 10)]
    assert trim_messages(messages, budget=1000) == messages


def test_drops_oldest_first():
    messages = [
        msg("system", "s", 10),
        msg("user", "q1", 100),
        msg("assistant", "a1", 100),
        msg("user", "q2", 100),
    ]
    # 预算只够 system + 最新两条（每条 +4 开销）
    trimmed = trim_messages(messages, budget=230)
    assert [m["content"] for m in trimmed] == ["s", "a1", "q2"]


def test_latest_user_message_always_kept():
    messages = [msg("system", "s", 10), msg("user", "huge", 99999)]
    trimmed = trim_messages(messages, budget=100)
    assert [m["content"] for m in trimmed] == ["s", "huge"]


def test_system_never_trimmed():
    messages = [msg("system", "s", 500), *[msg("user", f"q{i}", 200) for i in range(10)]]
    trimmed = trim_messages(messages, budget=100)
    assert trimmed[0]["role"] == "system"
    assert trimmed[-1]["content"] == "q9"


def test_order_preserved():
    messages = [
        msg("system", "s", 1),
        msg("user", "q1", 1),
        msg("assistant", "a1", 1),
        msg("user", "q2", 1),
    ]
    trimmed = trim_messages(messages, budget=1000)
    assert [m["content"] for m in trimmed] == ["s", "q1", "a1", "q2"]


def test_missing_token_count_computed():
    messages = [{"role": "user", "content": "你好世界"}]
    trimmed = trim_messages(messages, budget=1000)
    assert trimmed == messages
