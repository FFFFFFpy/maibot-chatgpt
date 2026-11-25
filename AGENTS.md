# 本任务包的实施约定

适用于本目录及新建的 `implementation/`。用户后续明确指令优先；外部仓库若有根级指令，冲突时说明而非静默绕过。

## 范围与职责

- 不修改 MaiBot 核心；不导入 Host `src.*` 作为插件运行依赖；插件模块使用唯一顶层包名（如 `maibot_chatgpt_provider`），避免 `auth`/`provider` 顶级包名冲突。
- 不做 WebUI、Node 守护进程、中转服务、多账号轮换或付费 API Key 自动切换。
- Provider 不调用 `ctx.llm.generate` 回退；不自动改写宿主模型配置文件。
- 只接受 P0 支持的纯文本及助手 `refusal` 历史；工具、图片/音频、结构化约束、未知 Item/schema 均在发网络请求前拒绝。

## 安全、凭据与网络

- 不收集聊天中的凭据；token、authorization code、含 `id_token_hint` 的 URL 不得进入命令行参数、异常、日志、测试快照或发布包。
- 不读取 Codex、ChatGPT 浏览器或其他软件的登录缓存，只使用本插件独立 SIWC 会话。
- OAuth 与推理固定官方目的地（校验 scheme/host/port/path），禁止跨域自动携带凭据重定向；保持 TLS 证书验证开启。
- 凭据目录运行时取 `ctx.paths.data_dir`，CLI 取 `--data-dir`；所有写入者共用独立 `credentials.lock`。
- 底层 HTTP/SDK 异常必须在边界提取安全字段并重建脱敏异常，抑制原始异常链泄露秘密。

## 依赖与许可

- 默认目标 Python 3.12（与研究基线一致，以 G0 实测为准）；Manifest 的 `python_package` 依赖须与开发环境及 Runner 共享环境一致，不得随意升级宿主依赖。
- OpenAI DevKit 根许可证为 `SIGN-IN WITH CHATGPT DEVKIT NONCOMMERCIAL LICENSE`（非 MIT）；只作公开协议参考，不得复制或逐行翻译其源码。
- 不伪造 GitHub 仓库 URL、兼容版本范围或测试通过记录。

## 测试与诚实报告

- 默认测试完全离线（`-m offline`）；live 测试必须显式启用，不触碰正式群聊。
- 所有模拟数据明确标为 synthetic；未执行的门禁诚实标记为 `not_run` / `blocked`，不把 mock 通过写成真实账号验收完成。
