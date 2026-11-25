# 错误分类、暂停与重试预算

官方错误码参考 [Errors and recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery)；本地错误类别与暂停策略为本项目设计。

## 1. 内部错误结构与安全摘要

`ProviderError` 包含可选字段：`category`、`safe_message`、`http_status`、`upstream_code`、`upstream_param`、`request_id`、`retry_after_seconds`、`stream_started`。

向 Runner 抛出异常时，`str(error)` 仅含安全摘要（严禁返回伪成功字典或把错误拼入回复正文）：

```text
[chatgpt_subscription:usage_paused] 当前注册的订阅请求已暂停；请查看 ChatGPT 用量设置后执行 resume。request_id=req_example
```

## 2. 错误分类表

| 条件 | `category` | 行为 |
| --- | --- | --- |
| `subscription_sharing_usage_limit_exceeded`（HTTP 429 或 SSE 内） | `usage_paused` | 持久化暂停该注册新推理，引导查看用量页；不猜测重置时间 |
| `subscription_sharing_user_not_eligible` | `ineligible` | 报告资格/区域/工作区限制，不循环登录 |
| `subscription_sharing_usage_unavailable` / `user_unavailable` | `temporarily_unavailable` | 保留凭据，有界冷却 |
| `subscription_sharing_unsupported_capability` | `unsupported_request` | 指出安全 `param`，不重试 |
| `subscription_sharing_route_not_supported` | `route_mismatch` | 检查端点，不切 backend-api |
| `subscription_sharing_invalid_user` | `auth_invalid` | 保留 `request_id`，确认失效时要求重登 |
| `chatpass_v2_scope_not_authorized` / `invalid_authorization_context` | `permission_denied` | 检查授权与 client，不切换计费 |
| HTTP 401/403 仅含 `detail` | `admission_denied` | 保留状态码与受控诊断，不伪造 `error.code` |
| 普通 429 | `rate_limited` | 尊重合法 `Retry-After` 并有限冷却 |
| 网络/5xx | `transport` / `upstream` | 生成前可按预算决策，流开始后绝不重放 |
| 流中断 / `incomplete` / 未知 `failed` | `stream_failed` | 丢弃未提交正文，错误交 Host |
| 协议/schema/工具/多模态/未知 `extra_params` | `unsupported_input` | 发网络前拒绝 |
| 文件锁超时 / 磁盘失败 | `storage_busy` / `storage_failed` | 明确失败，不用旧内存凭据继续 |
| 未登录 / 已登出 / 终止刷新码 / `refresh_uncertain` | `auth_required` | 停止使用旧 token，保留注册与 host ID 提示重登 |

分类优先级：SSE `response.failed` / 顶层 `error` 优先按机器错误码匹配（即使 HTTP 为 200），无法细化才归为 `stream_failed`。非 JSON 或超大错误体截断并脱敏，不原样拼进异常。

## 3. 重试预算与 `Retry-After`

- OpenAI SDK `max_retries=0`；Host 配置片段 `max_retry=1`（研究基线中表示含首次的总尝试次数为 1）。
- Responses 请求默认只发 1 次；仅当 `pre_admission_retry_limit > 0` 且确认在生成前被临时拒绝时，可在剩余总时限内加抖动重试最多 1 次；`stream_started=True` 或模糊 POST 失败绝不自动重放。
- `Retry-After` 支持秒数与 HTTP 日期；若合法等待时长超过剩余预算或本地上限，立即失败并进入冷却，**不得截短等待后提前重试**。
- 模型目录 GET 与 JWKS GET 可做有界短重试。

## 4. 暂停与恢复

- 额度暂停写入 `credentials.json`，重启后仍生效；同注册重登或导入不自动解除，仅管理员执行 `resume` 解除，由下一次真实请求验证恢复。
- 短暂服务错误用进程内有界冷却，冷却结束后只放行单次探测，不阻塞其他供应商。
