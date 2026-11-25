# 兼容性与测试边界

- 插件加载、工具消息协议、WebUI 与模型库以 MaiBot 1.4.8（edf42446）、SDK 2.23.0、Python 3.12 为基线。未声明其他 SDK 已实测。
- 市场的贡献规范允许省略宿主上界，但该基线的 ManifestVersionRange 要求明确的三段式上界。兼容范围见根目录清单。
- 运行时不导入宿主内部模块，不依赖 OpenAI Python SDK。Python 直接依赖用兼容范围；开发复现使用 uv.lock。官方 OAuth 和推理均通过 HTTPS；插件不代持第三方账号，不记录聊天或登录凭据。
- 离线验证：在开发检出中运行 `uv run --frozen python -m pytest -q -m offline`。合成测试覆盖跨模型历史 ReasoningItem 过滤、工具配对、并发上限/本地队满和上游 429 区分；不等同于生产群聊负载测试。
- 发布验证必须检查该提交的 git archive：根目录有清单、入口、MIT 许可、管理页及全部插件模块；无运行配置、测试凭据或历史产物。冷安装用隔离环境及真实基线宿主的严格目录校验器。
