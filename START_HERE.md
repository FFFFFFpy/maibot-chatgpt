# 给 Codex 的启动指令

将下面整段复制给编程代理。相对路径均以任务包根目录为基准。

```text
请直接实施这个任务包，目标是完成 MaiBot ChatGPT 订阅供应商插件 v0.1.0（P0）。

先读取 AGENTS.md、MASTER_TASK.md、docs/10-architecture.md、docs/20-maibot-contract.md、
docs/30-openai-contract.md、docs/40-credentials-and-concurrency.md、examples/credentials.schema.example.json
和 tasks/backlog.json，按依赖顺序在新建 implementation/ 目录中开发（若另有指定仓库则在隔离分支开发）。

第一步执行 T00：核实目标 MaiBot 镜像、Host/SDK/Python 版本、真实 Provider 请求/返回、ctx.paths、依赖与重试语义。
任务包记录的是研究基线，不能冒充用户运行版本。优先适配已核实的 context_items 协议，未知 schema 明确拒绝。

P0 核心链路：官方 OAuth+PKCE、ID token 验签、缓存 JWKS、凭据原子持久化与跨进程锁刷新、统一 CLI、
动态模型目录、纯文本 Responses API（api.openai.com/v1/responses，store=false，stream=true，仅 response.completed 才成功），
以及原生 LLMProvider 集成。所有系统指令统一映射为 developer 消息（P0 不发顶层 instructions）。

严格遵守四条边界：
1. 跨供应商回退归 Host；Provider 只做错误分类与暂停/冷却，绝不调用 ctx.llm.generate。
2. 进程内锁 + 跨进程独立 credentials.lock 覆盖“读—刷新—原子写”完整事务；CLI 导入与登出共用同一锁协议。
3. 不直接修改宿主 host/model_catalog.toml 或 Bot 模型配置；config 子命令只向 stdout 输出可审阅 TOML。
4. 本版不做 WebUI、Node 服务、工具调用、图片/音频、Embedding 或多账号轮换。

务实开发，不做过度防御：采用标准同目录临时文件+fsync+os.replace+0600，不需要实现 pending_refresh 历史回溯、
pending_registration 持久化或 symlink 对抗检查；遇到刷新响应中断或持久化失败直接明确报错并引导重新登录。

参考 OpenAI DevKit 时注意其非商业许可证（非 MIT），须独立实现公开协议，不得复制或逐行翻译其源码。

持续完成所有可离线开发与 G1 测试，不每一步都询问我；无目标容器或账号时把缺失项标为 blocked/not_run。
不要向我索要密码、验证码或任何 token；未经授权不推送远程仓库、不重建正式容器、不发真实群消息。

最后按 acceptance/REPORT_TEMPLATE.md 填写 docs/acceptance-report.md，如实列出 G0/G1/G2/G3 结果、
交付产物、安装步骤、实际执行命令与剩余人工步骤。
```

## 缺少环境时的处理

无法访问目标容器不阻塞 Python 核心、CLI、模拟 HTTP/SSE、多进程锁和 `plugin.py` 接线开发；完成“源码基线兼容”与 G1 后，将 G0 部署部分和 G2/G3 标为 `blocked`，并只向用户索要缺失的非敏感信息（容器名、镜像 digest、脱敏挂载路径）。
