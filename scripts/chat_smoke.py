"""阶段 1 验收脚本：同一会话连续 20 轮对话。

验证点：
1. 20 轮全部正常收到 meta/delta/done 事件，无中断
2. 历史正确落库（40 条消息）
3. 上下文超预算后服务端触发裁剪（看服务日志"上下文裁剪"）
"""

import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
# 每轮消息附带约 300 token 的填充文本，20 轮后必然超出 8000 预算触发裁剪
FILLER = "贵州茅台是中国白酒行业的龙头企业，主营茅台酒及系列酒的生产与销售。" * 12


def chat_round(client: httpx.Client, conversation_id: str | None, i: int) -> tuple[str, str]:
    payload = {
        "message": f"这是第 {i} 轮测试。请只回复'收到第 {i} 轮'，不要多说。参考背景：{FILLER}",
        "conversation_id": conversation_id,
    }
    conv_id, answer, done = conversation_id, [], False
    with client.stream("POST", f"{BASE}/api/chat", json=payload, timeout=120) as resp:
        resp.raise_for_status()
        event = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = json.loads(line.split(":", 1)[1].strip())
                if event == "meta":
                    conv_id = data["conversation_id"]
                elif event == "delta":
                    answer.append(data["content"])
                elif event == "done":
                    done = True
                elif event == "error":
                    raise RuntimeError(f"第 {i} 轮收到 error 事件: {data}")
    if not done:
        raise RuntimeError(f"第 {i} 轮未收到 done 事件")
    return conv_id, "".join(answer)


def main() -> None:
    conv_id = None
    start = time.time()
    with httpx.Client() as client:
        for i in range(1, 21):
            conv_id, answer = chat_round(client, conv_id, i)
            print(f"round {i:2d} ok ({time.time() - start:5.1f}s): {answer[:30]!r}")

        history = client.get(f"{BASE}/api/conversations/{conv_id}/messages").json()
    n = len(history["messages"])
    total_tokens = sum(m["token_count"] for m in history["messages"])
    print(f"\nconversation={conv_id}")
    print(f"messages in db: {n} (expect 40), total tokens: {total_tokens}")
    if n != 40:
        sys.exit("FAIL: 消息条数不对")
    print("PASS")


if __name__ == "__main__":
    main()
