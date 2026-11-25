# OpenAI 订阅授权与推理契约

核验日期：**2026-11-25**（基于官方文档与固定 DevKit 提交，未做真实账号测试；实施时若官方接口变更以最新文档为准并记录差异）。

## 1. 官方 DevKit 参考边界与许可

- 仓库：[openai/sign-in-with-chatgpt-devkit](https://github.com/openai/sign-in-with-chatgpt-devkit)（Commit `0a36fefeb913055c8c7a1a29b63d82b96b2e841a`，`@siwc/local` 0.1.0）
- 许可证：`SIGN-IN WITH CHATGPT DEVKIT NONCOMMERCIAL LICENSE` Version 1.0（[LICENSE](https://github.com/openai/sign-in-with-chatgpt-devkit/blob/0a36fefeb913055c8c7a1a29b63d82b96b2e841a/LICENSE)）
- **合规要求**：严禁将其视为 MIT 复制或逐行翻译；本项目依据公开协议独立编写 Python 实现。

## 2. OAuth 端点与授权流程

| 字段 | 官方约定 |
| --- | --- |
| `issuer` | `https://auth.openai.com` |
| `discovery` | `https://auth.openai.com/.well-known/openid-configuration` |
| `authorization_endpoint` | `https://auth.openai.com/api/accounts/authorize` |
| `token_endpoint` | `https://auth.openai.com/api/accounts/oauth/token` |
| `jwks_uri` | 运行时从合法 discovery 获取（文档示例 `https://auth.openai.com/.well-known/jwks.json`） |
| `resource` | `https://api.openai.com/v1` |
| `response_type` / `code_challenge_method` | `code` / `S256` |
| `scope` | `openid profile email offline_access resource.invoke chatgpt.tokens.use.direct` |
| `redirect_uri` | `http://127.0.0.1:<已绑定端口>/auth/callback`（不可改为 `localhost` 或 `/callback`） |

核心规则：
1. **首次注册与重登**：首次用 `client_id=dynamic_agent_client`、稳定 `ext_agent_host_id`（`urn:uuid:<UUIDv4>`）与固定 `agent_name_hint`；回调签发的 `issued client_id` 才用于换码和持久化保存。后续重登复用已保存的 `issued client_id` 并省略 `agent_name_hint`；回调若带不同 `client_id` 则拒绝。
2. **回调安全**：每次生成随机 `state`、`nonce` 与 PKCE `code_verifier`；先绑定 `127.0.0.1` 端口再打开浏览器；先校验 `state` 再处理 `error`/`code`；禁止重复消费同一回调；设定超时并关闭临时监听器。
3. **换码与验签**：form POST `grant_type=authorization_code`、`client_id`、`code`、`code_verifier`、`redirect_uri`、`resource`（无 client secret）。对 ID token 用缓存/拉取的 JWKS 验证 `RS256` 签名、`iss`、`aud`（含多 aud/`azp`）、`exp`（允许 5 秒时钟容差）、`iat`、`sub` 与 `nonce`；**不得仅解码 payload**。
4. **权限判断**：以 token 响应的 granted `scope` 确认包含 `chatgpt.tokens.use.direct`；缺失时标记订阅推理不可用，不发起推理。重授权请求同意沿用 `prompt=consent`，普通登录不反复强制同意。

## 3. 刷新与撤销

- **刷新请求**：form POST `grant_type=refresh_token`、已保存 `issued client_id`、最新 `refresh_token`、`resource`，**省略 `scope`**。
- **时机与缓存**：按实际 `expires_in` 计算到期（默认提前 60 秒触发刷新），保留并尊重 `earliest_refresh_at`（支持 Unix 秒或 ISO 时间字符串；无法解析时不触发高频刷新）。登录时即缓存 JWKS；刷新若返回新 ID token，优先用缓存 JWKS 验签，遇未知 `kid` 再联网刷新一次 JWKS。
- **失败策略（务实简化）**：
  - 连接前失败可在预算内重试；
  - 收到终止错误码（`invalid_grant`、`invalid_refresh_token`、`token_expired`、`refresh_token_expired`、`refresh_token_invalidated`、`refresh_token_reused`）直接清除失效 token、标记 `auth_required`；`invalid_client` 报配置错误不重注册；
  - 已发送但读响应中断/超时标为 `refresh_uncertain`（停止盲重试旧 token，提示重新 `login`）；验签或写盘失败同样不回退旧 token，明确报错并提示重新 `login`。
- **退出撤销**：从 discovery 获取 `revocation_endpoint`，form POST `token=<refresh_token>`、`token_type_hint=refresh_token`、`client_id`；无论远端是否确认（网络/5xx 有限重试后若仍未确认须明确提示用户前往 ChatGPT 设置断开），均清除本地 token 并保留注册与 `host_identity`。自托管转移后的源端只清理副本，**禁止在源端执行远端 revoke**。

## 4. 模型目录与 Responses 请求白名单

- **模型目录**：`GET https://api.openai.com/v1/models`（OAuth Bearer），解析顶层 `models` 数组，过滤 `visibility="list"` 并保持服务端顺序，展示 `display_name`，配置与请求使用 `slug`（**不是标准 API 的 `data[].id`**）。
- **推理端点**：唯一目标 `POST https://api.openai.com/v1/responses`。
- **P0 请求体白名单**：

| 字段 | 规则 |
| --- | --- |
| `model` | 账号目录真实 `slug` |
| `input` | 数组；纯文本及助手 `refusal` 历史，系统消息统一为 `developer` |
| `store` | 强制 `false` |
| `stream` | 强制 `true` |

构造多轮 `input` 时，须在 T05 对照当前官方 Responses schema 与锁定 SDK 确认 `user`/`developer`/`assistant`（含 `refusal`）的 `content` item 类型，避免 `assistant` 历史误用 `input_text` 触发 400。

**明确禁止发送的字段**：`background`、`conversation`、`instructions`（P0 统一用 `developer`）、`max_output_tokens`、`max_tool_calls`、`metadata`、`moderation`、`multi_agent`、`previous_response_id`、`prompt`、`prompt_cache_retention`、`safety_identifier`、`temperature`、`top_logprobs`、`top_p`、`truncation`、`user`。

## 5. 官方错误码与客户端隔离

SDK 必须显式固定官方 `base_url`、禁用内置重试（`max_retries=0`）、不继承环境变量里的 API Key / organization / project、关闭自动重定向。

| 官方 `error.code` | 常见 HTTP | 协议处理 |
| --- | ---: | --- |
| `subscription_sharing_usage_limit_exceeded` | 429 / SSE | 持久暂停新推理，引导至 [ChatGPT Usage](https://chatgpt.com/settings/usage)，不猜测重置时间 |
| `subscription_sharing_user_not_eligible` | 403 | 报告资格/区域/工作区限制，不循环登录 |
| `subscription_sharing_usage_unavailable` / `user_unavailable` | 503 | 保留凭据，有限冷却 |
| `subscription_sharing_unsupported_capability` | 400 | 指出安全 `param`，不重试同请求 |
| `subscription_sharing_route_not_supported` | 403 | 检查端点与方法，不切 backend-api |
| `subscription_sharing_invalid_user` | 401 | 保留脱敏 `request_id`，仅在确认失效后要求重登 |
| `chatpass_v2_scope_not_authorized` / `invalid_authorization_context` | 403 | 检查授权范围与 client，不切换计费路径 |

Direct admission 还可能返回 401/403/503 且响应体仅为 `{"detail": "..."}`；保留状态码与受控诊断，不伪造 `error.code`。

## 官方来源

- [总览](https://developers.openai.com/siwc/token-sharing-open-source) · [注册登录](https://developers.openai.com/siwc/token-sharing-open-source/sign-in) · [账号会话](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions) · [模型推理](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference) · [Token 参考](https://developers.openai.com/siwc/token-sharing-open-source/token-reference)
- [自托管 VM](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms) · [错误恢复](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery) · [预览限制](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations) · [OIDC/JWT](https://developers.openai.com/siwc/website) · [用户说明](https://learn.chatgpt.com/docs/sign-in-with-chatgpt)
