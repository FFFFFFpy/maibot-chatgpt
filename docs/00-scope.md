# 范围、四条约束与证据层级

## 用户确认的四条核心约束

| 约束 | 可验证结果 |
| --- | --- |
| Fallback 属于 Host | Provider 无跨供应商调用、不调 `ctx.llm.generate`；错误经 RPC 传播 |
| 双层锁保护刷新 | 进程内锁 + 跨进程独立锁覆盖读—刷—写完整事务；异常时明确暂停或报错重登 |
| 不直接写宿主模型目录 | 安装、登录、models/config/smoke 后，宿主模型配置文件字节不变 |
| 先跑最薄链路 | 无 WebUI/Node 服务；P0 聚焦纯文本 Responses 主链路 |

## P0 接受与拒绝

- **接受**：每 `data_dir` 单活动注册、同注册重登、纯文本上下文、合法模型拒答（含下一轮历史往返）、真实模型目录、官方 HTTP/SSE、CLI 与原生 Provider。
- **拒绝**：工具声明或工具历史、图像/音频/视频、Embedding/ASR、非文本结构化输出约束、未知 schema/Item、第三方 API 目的地址、多账号轮换、自动改宿主配置。
- **显式不做（防过度工程化）**：`pending_refresh` 历史时间回溯验签、`pending_registration` 未激活候选持久化、多租户 symlink 对抗检测、四阶段磁盘故障注入。

## 三类陈述分离

1. **已核验事实**：2026-11-25 官方文档与固定 commit SHA（见 `references/SOURCES.md`）。
2. **本项目设计**：双层锁、CLI 界面、额度暂停、退出码、纯文本白名单等。
3. **待目标环境验证**：用户容器 digest、真实路径映射、账号资格、模型权限、首次推理、自然续期与重建持久化。

实施者须维护 `docs/compatibility-report.md`，不把研究基线（MaiBot 1.4.8 / SDK 2.23.0 / Python >=3.12）冒充为用户当前镜像版本；若目标版无 Provider API 则明确报错并给出最小升级要求，不做核心 monkeypatch。
