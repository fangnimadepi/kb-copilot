# ADR-003: 入库用 Celery 任务队列而非 FastAPI BackgroundTasks

## 背景

文档入库（解析 → 分块 → 向量化）是分钟级长任务，不能同步阻塞上传接口。
FastAPI 自带 BackgroundTasks，为什么还要引入 Celery + Redis？

## 备选方案

- **A. FastAPI BackgroundTasks**：任务在 API 进程的事件循环里执行。
  - 零依赖，但任务与 API 同生共死：进程重启/崩溃任务直接丢失，无持久化、无重试、无状态查询
  - CPU 密集的解析会挤占事件循环，拖慢所有在线请求
- **B. Celery + Redis**：独立 worker 进程 + 持久化消息队列。
  - 任务与 API 解耦：API 挂了任务照跑，worker 挂了任务重投（acks_late）
  - 天然支持状态查询、重试、水平扩容（多 worker 分担）
- **C. ARQ / Dramatiq**：更轻的异步队列，能力类似 Celery 但生态与岗位认知度低。

## 决策

选 **B（Celery）**。判断标准是**任务的生命周期是否允许和请求进程绑定**：
入库任务动辄几分钟、失败要可追溯可重试，答案显然是否。

关键配置：`task_acks_late + task_reject_on_worker_lost`——消息在任务完成后才确认，
worker 被杀时消息自动回队列重投。代价是任务必须**幂等**：本项目在任务开头
先清理该文档的旧 chunk（MySQL）与旧向量（Milvus），重复执行结果一致。

## 后果

- ✅ 上传接口毫秒级返回 task_id；worker 崩溃后任务自愈
- ✅ 状态机（pending/parsing/embedding/done/failed/canceled）+ 进度百分比可查询
- ❌ 引入 Redis 依赖与 worker 进程运维成本
- ❌ Windows 开发环境 Celery 只能 solo pool（单并发）；生产 Linux 下用 prefork 即可
