# 官方来源与核验记录

核验日期：2026-11-25（Asia/Shanghai）。仅阅读公开官方文档/源码；未访问用户容器或账户。下面是事实来源索引，不是复制的官方文档包。实现者应重读相关页面，并把目标版本差异记录下来。

## OpenAI

| ID | 来源 | 本包据此确认的事实 |
| --- | --- | --- |
| O01 | [Overview](https://developers.openai.com/siwc/token-sharing-open-source) | 开源/本地应用的订阅授权；client 与 host 分离 |
| O02 | [Registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in) | issued client_id、state/nonce/PKCE、loopback、ID token、scopes |
| O03 | [Accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions) | 刷新、串行、撤销、账户隔离与凭据保护 |
| O04 | [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference) | models/slug、公开 Responses 路由、SSE 完成终态 |
| O05 | [Self-hosted VMs](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms) | 本地授权后转移 session；保留目标 host ID |
| O06 | [Token reference](https://developers.openai.com/siwc/token-sharing-open-source/token-reference) | token 响应字段、expires_in、旋转与有效期 |
| O07 | [Errors and recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery) | 结构化错误、非标准 detail、暂停与重授权条件 |
| O08 | [Preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations) | stream/store、禁用参数、system映射、工具与输入限制 |
| O09 | [Sign in with ChatGPT · Learn](https://learn.chatgpt.com/docs/sign-in-with-chatgpt) | 用户授权与订阅体验说明；不替代开发协议 |
| O10 | [DevKit 仓库](https://github.com/openai/sign-in-with-chatgpt-devkit) | 官方参考实现，非 Python 运行依赖 |
| O11 | [固定版本 LICENSE](https://github.com/openai/sign-in-with-chatgpt-devkit/blob/0a36fefeb913055c8c7a1a29b63d82b96b2e841a/LICENSE) | Noncommercial License Version 1.0；不能假定 MIT |
| O12 | [OIDC discovery](https://auth.openai.com/.well-known/openid-configuration) | 实施时获取已验证 issuer 的 JWKS/revocation 配置；本包未声称已运行实时发现 |

DevKit 研究提交：`0a36fefeb913055c8c7a1a29b63d82b96b2e841a`，`@siwc/local` 0.1.0。源码里的刷新检查点和 earliest_refresh_at 解析是参考实现证据，不能把它们直接说成永久稳定的额外 OAuth 字段语义。pending 状态在本插件中是独立设计要求。

## MaiBot 官方文档

| ID | 来源 | 用途 |
| --- | --- | --- |
| M01 | [插件开发指南](https://docs.maibot.chat/develop/plugin/) | Runner/插件入口、依赖和生命周期 |
| M02 | [LLMProvider](https://docs.maibot.chat/develop/plugin/llmprovider) | 注册、operation、公开接口与局限 |
| M03 | [Manifest](https://docs.maibot.chat/develop/plugin/manifest) | 必填字段、依赖声明、版本范围 |
| M04 | [模型配置](https://docs.maibot.chat/manual/configuration/model-config) | 共享模型目录与任务分配 |
| M05 | [多 Bot Host](https://docs.maibot.chat/manual/multi-bot-host) | workspace、Host 与实例目录 |
| M06 | [部署 FAQ](https://docs.maibot.chat/faq/deployment) | Docker 挂载、持久化核验方向 |

文档中的 message_list/content-only 和 SDK 2.22 示例，与下面当前源码存在差异。这个差异已经进入 T00 和 Host 契约测试，不能由实现者忽略。

## 固定源码证据

MaiBot SHA：`edf42446f123149c57fc79765dd5a8b004b8524c`。

| ID | 永久链接 | 核验重点 |
| --- | --- | --- |
| S01 | [pyproject.toml](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/pyproject.toml) | Host 1.4.8、Python >=3.12、SDK >=2.23.0 |
| S02 | [request_snapshot.py](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/llm_models/request_snapshot.py) | context_items 的实际请求序列化 |
| S03 | [context_item.py](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/llm_models/payload_content/context_item.py) | Item 类型与 schema 常量 |
| S04 | [context_snapshot.py](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/llm_models/payload_content/context_snapshot.py) | Item 的 JSON 形状 |
| S05 | [plugin_client.py](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/llm_models/model_client/plugin_client.py) | RPC 错误包装、output_items、meta、usage |
| S06 | [runner_main.py](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/plugin_runtime/runner/runner_main.py) | InvokeResultPayload 成功/失败协议 |
| S07 | [utils_model.py](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/llm_models/utils_model.py) | 重试总次数、ModelAttemptFailed、指定模型和任务列表 |
| S08 | [plugin_paths.py](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/plugin_runtime/runner/plugin_paths.py) | data_dir/runtime_dir 与当前实例根 |
| S09 | [model_configs.py](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/config/model_configs.py) | auth_type、max_retry、模型配置校验 |

SDK SHA：`f9984673d7e6061832e9306cf0e0daaf375f0f91`。

| ID | 永久链接 | 核验重点 |
| --- | --- | --- |
| K01 | [SDK pyproject](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/f9984673d7e6061832e9306cf0e0daaf375f0f91/pyproject.toml) | SDK 2.23.0、运行要求、许可证 |
| K02 | [llm_provider.py](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/f9984673d7e6061832e9306cf0e0daaf375f0f91/maibot_sdk/llm_provider.py) | 基类及 dispatch 接口 |
| K03 | [context.py](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/f9984673d7e6061832e9306cf0e0daaf375f0f91/maibot_sdk/context.py) | PluginContext 与路径 |
| K04 | [capabilities/llm.py](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/f9984673d7e6061832e9306cf0e0daaf375f0f91/maibot_sdk/capabilities/llm.py) | 公开 LLM 能力；不等同于模型目录写 API |

## 本次没有验证的内容

用户当前镜像 digest、实际 Host/SDK/Python、data_dir 映射、账户资格、可用模型、真实订阅推理、自然续期、真实容器重建、生产环境的 fallback。它们是实施验收项目，不应被 sources 中的研究版本替代。
