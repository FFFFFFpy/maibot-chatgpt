# 配置与 Schema 示例说明

- `credentials.schema.example.json`：P0 的 `host_identity.json` 与 `credentials.json` 标准字段结构（CLI 与 Provider 必须对齐）。
- `model_catalog.fragment.toml`：可解析的宿主配置片段模板（`model_identifier` 为占位符，由 `config --model` 生成真实 slug，人工合并，不覆盖 `[inner]`）。
- `plugin-config.target.toml`：建议映射到 SDK `PluginConfigBase` 的插件自身配置项。

Manifest 须在 T01 依据真实目标环境生成并通过 validator，本包不提供虚构的完整 `_manifest.json`。
