"""上下文窗口裁剪。

策略：从最新消息往旧回溯累加 token，超出预算即停——保住最近的对话，
丢弃最早的历史。system 消息不参与裁剪、始终保留（它定义助手行为）。
最新一条用户消息无论多长都必须保留，否则这轮对话就没有意义了。
"""

from app.core.tokens import count_tokens

_MSG_OVERHEAD = 4  # 每条消息的角色/分隔符开销（OpenAI 经验值）


def trim_messages(
    messages: list[dict],
    budget: int,
) -> list[dict]:
    """裁剪消息列表使总 token 不超过 budget。

    messages 按时间正序（最早在前），返回同样正序的裁剪结果。
    每条消息可带 token_count 键（入库时预计算）；缺省时现算。
    """
    system_msgs = [m for m in messages if m["role"] == "system"]
    dialog = [m for m in messages if m["role"] != "system"]

    used = sum(_cost(m) for m in system_msgs)
    kept: list[dict] = []
    for i, msg in enumerate(reversed(dialog)):
        cost = _cost(msg)
        if i == 0:  # 最新一条（本轮用户输入）无条件保留
            kept.append(msg)
            used += cost
            continue
        if used + cost > budget:
            break
        kept.append(msg)
        used += cost

    kept.reverse()
    return system_msgs + kept


def _cost(msg: dict) -> int:
    tokens = msg.get("token_count") or count_tokens(msg["content"])
    return tokens + _MSG_OVERHEAD
