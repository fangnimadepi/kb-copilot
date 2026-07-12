# ADR-002: 流式输出用 SSE 而非 WebSocket

## 背景

LLM 逐 token 生成，前端需要实时看到增量输出。候选：SSE、WebSocket、短轮询。

## 备选方案

- **A. SSE（Server-Sent Events）**：基于普通 HTTP 的单向服务端推送。
- **B. WebSocket**：全双工长连接。
- **C. 短轮询**：客户端反复拉取。延迟和开销都差，直接排除。

## 决策

选 **A（SSE）**。判断依据是通信方向：聊天流式输出是典型的"请求一次、推送一串"，
**单向**推送就够了——用户发消息走普通 POST，服务端只需往回推 token。

- SSE 就是 HTTP：过网关/反向代理/负载均衡无需额外配置，鉴权复用 HTTP header
- 协议自带断线重连（`Last-Event-ID`）与事件类型（event: meta/delta/done/error）
- 服务端实现是一个 async generator，无连接生命周期管理负担

WebSocket 的双工能力在这里用不上，却要付出代价：连接握手升级、心跳保活、
断线重连要自己写、部分企业代理对 WS 不友好。

## 后果

- ✅ 实现和运维简单，事件协议清晰（meta/delta/done/error 四种事件）
- ❌ 单向通道：将来若要"生成中途打断"，需要客户端另发一个 HTTP 请求来取消（可接受）
- ❌ 若演进到语音实时对话等双向场景，则需另开 WebSocket 通道（当前无此需求）
