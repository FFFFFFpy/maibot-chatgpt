# P0 之后的演进路线（当前不实施）

P0 跑通纯文本最小闭环后，P1 优先把工程预算投向 MaiBot 真实核心场景，而非过度复杂的本地凭据状态机：

| 优先级 | 方向 | 前置条件 | 核心验收重点 |
| --- | --- | --- | --- |
| P1-高 | 工具调用（Planner/Action） | P0 全链路通过，复核官方 `namespace`/`additional_tools` 协议与 Host Tool Item 契约 | `call_id`/参数流式拼接、工具结果往返、异常与循环边界 |
| P1-高 | 图片理解（多模态） | 确认目标模型支持视觉且任务需要 | Host 图片 Item 适配、大小/格式校验、拒绝未知媒体 |
| P1-中 | 顺滑的自托管转移 CLI | P0 `import-credentials` 稳定 | 提供引导式 `export-bundle` / `import-bundle`（自动剥离源 `host_id`、校验权限与状态） |
| P2 | 多账户管理 | 单会话刷新与登出稳定 | `issuer/subject/client_id` 严格隔离与显式切换（仍不做额度轮换） |
| P2 | WebUI 集成 | 核验目标镜像 WebUI 扩展规范 | 状态展示、脱敏配置与真实模型选择 |
| P2 | 模型配置写回 | Host 提供官方公开写入 API | 原子配置事务、版本冲突检查与可审阅回滚 |
