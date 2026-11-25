# MaiBot ChatGPT 订阅 Provider · 开发任务包（v1.1.0 精简务实版）

任务包修订：1.1.0 · 编制日期：2026-11-25（Asia/Shanghai）· 目标插件：v0.1.0 / P0。

**用途：把本目录交给 Codex 或其他编程代理，实施一个使用官方 Sign in with ChatGPT 的 MaiBot 原生模型供应商插件。** 本包是实施规格、任务拆分、测试素材与验收标准，不是已经完成或安装的插件；不包含真实账户凭据或容器运行结果。

## v1.1.0 相对 v1.0.x 的精简与增强

- **砍掉过度防御**：移除 `pending_refresh` 历史回溯验签、`pending_registration` 未激活候选持久化、symlink 攻击检测及四阶段磁盘故障注入；刷新采用“双层锁 + 缓存 JWKS + 原子落盘，异常明确报 `auth_required` 重登”。
- **补齐正向数据结构**：新增 [examples/credentials.schema.example.json](examples/credentials.schema.example.json)，固定 `credentials.json` 与 `host_identity.json` 的精确字段，避免 CLI 与 Provider 漂移。
- **收敛测试矩阵与超时**：G1 离线测试由 46 条合并为 25 条高价值必测用例（总计 37 条）；默认推理超时放宽至 180s（Host 200s）以兼容思考模型。
- **单一事实来源**：去除多文档间重复赘述，核心规则只在对应契约文档定义一次。

## 开始方式

1. 解压到新工作目录，保留相对路径。
2. 让编程代理读取 [START_HERE.md](START_HERE.md)、[AGENTS.md](AGENTS.md)、[MASTER_TASK.md](MASTER_TASK.md)。
3. 复制 `START_HERE.md` 中的启动指令。代理先执行 T00 核验，再在新建 `implementation/` 目录中开发与离线测试。

不要把本任务包直接复制进 MaiBot 插件目录；最终安装的是代理打包后的 `implementation/` 产物。

## 文件导航

| 文件 | 作用（单一事实来源） |
| --- | --- |
| [START_HERE.md](START_HERE.md) | 复制给编程代理的启动指令 |
| [AGENTS.md](AGENTS.md) | 执行纪律、安全边界与许可合规 |
| [MASTER_TASK.md](MASTER_TASK.md) | 交付物、模块结构、CLI 界面与验收门槛 |
| [docs/00-scope.md](docs/00-scope.md) | 四条核心约束、P0 边界与三类证据声明 |
| [docs/10-architecture.md](docs/10-architecture.md) | 数据流、参数处理、SSE 终态与并发超时 |
| [docs/20-maibot-contract.md](docs/20-maibot-contract.md) | MaiBot Host/SDK/RPC/路径与版本契约 |
| [docs/30-openai-contract.md](docs/30-openai-contract.md) | OpenAI SIWC OAuth、模型目录与 Responses 契约 |
| [docs/40-credentials-and-concurrency.md](docs/40-credentials-and-concurrency.md) | 凭据 Schema、双层锁、原子持久化与登出/导入 |
| [docs/45-errors-and-retries.md](docs/45-errors-and-retries.md) | 错误分类、额度暂停、重试预算与脱敏 |
| [docs/50-test-plan.md](docs/50-test-plan.md) | G1/G2/G3 分层测试策略与人工验收步骤 |
| [docs/60-docker-runbook.md](docs/60-docker-runbook.md) | Docker 部署、自托管转移与故障回滚 |
| [docs/70-release-and-handoff.md](docs/70-release-and-handoff.md) | 打包清单、冷安装与交接要求 |
| [docs/80-future-roadmap.md](docs/80-future-roadmap.md) | P1 演进重点（工具调用、图片、顺滑转移） |
| [tasks/BACKLOG.md](tasks/BACKLOG.md) / [tasks/backlog.json](tasks/backlog.json) | 14 个有依赖关系的实施任务 |
| [acceptance/test-matrix.csv](acceptance/test-matrix.csv) | 37 条核心验收测试矩阵 |
| [acceptance/REPORT_TEMPLATE.md](acceptance/REPORT_TEMPLATE.md) | 验收报告模板 |
| [examples/README.md](examples/README.md) | 配置片段与凭据 Schema 示例 |
| [fixtures/README.md](fixtures/README.md) | 合成测试素材说明 |
| [references/SOURCES.md](references/SOURCES.md) / [compatibility-baseline.json](references/compatibility-baseline.json) | 研究基线 SHA 与官方来源 |
| `tools/check_taskpack.py` | 校验本任务包完整性（不测试插件本身） |

## 状态说明

本包内 `todo`、`not_run`、`unverified` 均表示尚未实施或尚未验证；只有 G0–G3 全部有脱敏证据才算正式验收完成。
