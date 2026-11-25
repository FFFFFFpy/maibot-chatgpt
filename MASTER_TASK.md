# 主任务：MaiBot ChatGPT Subscription Provider v0.1.0（P0）

## 1. 交付目标

实现一个独立安装和卸载的 MaiBot `LLMProvider` 插件：用户在自有设备上通过官方 Sign in with ChatGPT 授权，个人自托管 MaiBot 经原生 Provider 接口完成纯文本模型推理，并在日常请求中安全续期。

核心验收：**目标 MaiBot 经原生 Provider 接口收到真实订阅模型的完整回复**（CLI 推理仅作为中间里程碑）。

- 名称：`MaiBot ChatGPT Subscription Provider`
- 插件 ID：`local.maibot.chatgpt_subscription`
- `client_type`：`maibot.chatgpt.subscription`（首次成功授权后保持应用名与 `ext_agent_host_id` 稳定）

## 2. 推荐模块结构（置于 `implementation/`）

| 位置 | 职责 |
| --- | --- |
| `_manifest.json`、`plugin.py` | 插件注册、生命周期、Provider 分发、配置接入 |
| `maibot_chatgpt_provider/auth/oauth.py` | PKCE、loopback callback、OIDC 验签（含 JWKS 缓存） |
| `maibot_chatgpt_provider/auth/credentials.py` | host identity、Schema 读写、原子落盘与权限校验 |
| `maibot_chatgpt_provider/auth/token_manager.py` | 进程内串行、跨进程文件锁、刷新、取消收尾、导入与登出 |
| `maibot_chatgpt_provider/provider/chatgpt_provider.py` | 请求校验、Token 获取、官方调用与并发/暂停控制 |
| `maibot_chatgpt_provider/provider/maibot_adapter.py` | 经版本验证的 Host `context_items`（或实测旧协议）适配 |
| `maibot_chatgpt_provider/provider/responses_adapter.py` | 白名单构造、SSE 终态状态机、正文/拒答与 usage 映射 |
| `maibot_chatgpt_provider/provider/errors.py` | 稳定脱敏错误码、暂停与冷却策略 |
| `scripts/login.py`（或 `python -m maibot_chatgpt_provider.cli`） | 统一 CLI 入口，共用核心包 |
| `tests/` | `offline`、`host`、`live` 分组测试 |
| `README.md`、`docs/`、`pyproject.toml` | 中文文档、兼容/验收报告、可复现依赖 |

## 3. P0 功能摘要（细则见对应契约文档）

- **授权与会话**：见 [docs/30-openai-contract.md](docs/30-openai-contract.md) 与 [docs/40-credentials-and-concurrency.md](docs/40-credentials-and-concurrency.md)。每个 `data_dir` 固定一个注册，按 `issuer/sub/client_id` 识别身份；失败登录不覆盖有效旧会话。
- **推理与协议**：见 [docs/10-architecture.md](docs/10-architecture.md) 与 [docs/20-maibot-contract.md](docs/20-maibot-contract.md)。固定 `POST https://api.openai.com/v1/responses`，`store=false`、`stream=true`；仅 `response.completed` 才返回成功；`usage` 取真实值不造数。
- **错误与暂停**：见 [docs/45-errors-and-retries.md](docs/45-errors-and-retries.md)。通过抛脱敏异常向 Runner 报错；额度超限持久暂停至管理员 `resume`；跨供应商回退交 Host。

## 4. 必须实现的 CLI

全局 `--data-dir` 置于子命令之前；帮助文本含 Windows/macOS/Linux 示例。

| 命令 | 行为约定 |
| --- | --- |
| `python scripts/login.py --data-dir PATH init-host` | 原子创建或读取稳定 `host_identity.json` |
| `... login [--no-browser]` | 官方浏览器 OAuth；`--no-browser` 仍须与浏览器同机访问 loopback |
| `... status [--json]` | 本地状态、脱敏标签、到期时间、暂停状态；不输出 token |
| `... doctor [--online]` | 默认检查本地路径/版本/权限；`--online` 才访问官方服务 |
| `... models [--json]` | 拉取账号真实模型目录，失败不输出伪造模型 |
| `... config --model SLUG` | `stdout` 输出可解析 TOML 片段，说明走 `stderr`；不改宿主配置 |
| `... smoke --model SLUG --prompt TEXT` | 短文本验证；未达 `response.completed` 则非零退出 |
| `... import-credentials --from-file PATH` | 导入源端停止活动后的 `credentials.json` 副本；保留目标 host ID；拒绝覆盖不同注册 |
| `... resume` | 管理员明确解除本地额度暂停 |
| `... logout` | 阻止新请求、尝试远端撤销 refresh token、清本地 token，保留注册与 host identity |

建议退出码：`0` 成功，`2` 参数/配置错误，`3` 未连接或须重授权，`4` 不支持/协议不匹配，`5` 暂停/限流，`6` 网络或上游失败，`7` 文件锁/持久化失败（需测试并文档化）。

## 5. 验收门槛

| 门槛 | 必交证据 |
| --- | --- |
| G0 契约 | 目标版本/digest、SDK API、脱敏请求/输出反序列化、路径映射（无环境则部署部分标 `blocked`） |
| G1 离线 | 25 条离线用例全通过（OAuth、HTTP/SSE、真实多进程锁、取消、脱敏、配置生成），零网络依赖 |
| G2 Host | 真实 SDK/Runner 加载、Provider 分发、拒答往返、RPC 错误与任务/显式路由行为（可 mock 上游） |
| G3 Live | 用户本人 OAuth、真实模型目录、CLI + MaiBot 纯文本回复、自然续期、容器重建持久化（逐项独立记录） |

## 6. 最终交付物

可安装插件 ZIP（不含任何运行凭据、锁文件、私钥、日志或虚拟环境）、完整源码、依赖清单、中文 README、Docker 手册、`docs/compatibility-report.md`、`docs/acceptance-report.md`、`THIRD_PARTY_NOTICES.md`，并完成一次干净临时目录冷安装校验。
