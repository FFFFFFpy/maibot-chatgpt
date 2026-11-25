# P0 测试计划与验收规则

状态：**计划，全部尚未执行**。逐项用例见 [acceptance/test-matrix.csv](../acceptance/test-matrix.csv)（共 37 条：G1 25 条、G2 6 条、G3 6 条）。

## 1. 验收分级

| 门禁 | 环境 | 验证重点 |
| --- | --- | --- |
| G1 · offline（25 条） | 无网络、无真实账号；mock HTTP/SSE + 真实多进程 | OAuth 验签、跨进程锁刷新与取消、请求白名单与适配、SSE 终态、错误/暂停、脱敏 |
| G2 · host（6 条） | 目标锁定版本 MaiBot Host + SDK（上游可 mock） | Manifest 加载、真实 `context_items`/`output_items`（含拒答往返）、RPC 错误与 Host 回退、路径对齐、热重载 |
| G3 · live（6 条） | 用户自有账号与目标容器 | 官方 OAuth、真实模型目录、CLI + MaiBot 纯文本回复、自然续期、容器重建持久化 |

测试标记为 `offline`、`host`、`live`，默认 CI 仅跑 `python -m pytest -m offline`；`live` 须显式启用且仅做短文本 smoke test。不得把 `skip` 写成 `pass`。

## 2. 关键测试实现要求

- **真实双进程锁（QA013）**：用 `multiprocessing` 或 `subprocess` 启动至少两个独立进程共享临时 `--data-dir`，配同步屏障和计数 mock 服务，断言仅发生 1 次 refresh、`revision` 递增、`session_generation` 不变且等待进程读到新 token。
- **取消保护（QA015）**：分别在取锁前、refresh HTTP 发出后、写盘后取消等待协程，确认不提前释放工作线程持锁、不丢新 token、不死锁。
- **SSE 异常参数化覆盖（QA024–QA027）**：使用锁定 OpenAI SDK 完整 mock HTTP 响应，覆盖 delta+completed 防重拼、部分输出后 failed/额度超限/EOF/超时/`[DONE]`/status 冲突/空输出/破损 JSON、合法拒答（不含 reasoning）、UTF-8 跨块与取消释放连接。
- **脱敏 canary（QA030）**：向各错误/日志/CLI 路径注入固定假密钥字符串，断言捕获的全部 logger/`stdout`/`stderr` 与异常文本零泄露。

## 3. G3 人工验收顺序

1. 核对目标容器 digest、挂载与 `ctx.paths.data_dir`。
2. 用户本人完成浏览器 OAuth（Docker 场景按自托管流程导入）。
3. `models` 读取真实可用模型并选取纯文本模型 slug。
4. `smoke` 完成一次 CLI 纯文本推理。
5. 手工合并 `config` 片段到测试任务（非工具任务），触发一次 MaiBot 真实回复。
6. 待授权自然临近过期完成一次真实刷新（不篡改 token 强行触发），并经授权验证容器重建持久化。

每项 G3 独立记录；若自然续期或重建尚未发生，先交付已完成项并将余项标为 `not_run`。
