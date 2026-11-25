# 凭据存储、双层锁与并发事务

## 1. 目录与文件

Runner 使用 `ctx.paths.data_dir`，CLI 使用显式 `--data-dir`，两者必须指向同一持久化目录。禁止将凭据存入源码目录或 `ctx.paths.runtime_dir`。

| 文件 | 职责与生命周期 |
| --- | --- |
| `host_identity.json` | 持久化的稳定 `ext_agent_host_id`（`urn:uuid:<UUIDv4>`），重启/登出/导入均不变 |
| `credentials.json` | 单活动注册的身份、tokens、scopes、到期时间、状态、代次与额度暂停记录 |
| `credentials.lock` | 所有写入者共用的独立 OS 文件锁；不删除、不原子替换 |

精确字段结构见 [examples/credentials.schema.example.json](../examples/credentials.schema.example.json)。核心字段约定：
- `schema_version`：当前为 `1`；读取未知版本或损坏 JSON 时明确报错，禁止静默覆盖为空文件。
- `revision`：每次状态落盘递增，用于检测其他进程更新。
- `session_generation`：仅在同注册重登、导入或登出等**会话替换**时递增；普通刷新不改变它，避免打断正常在途推理。
- `state`：`active` / `logged_out` / `auth_required` / `refresh_uncertain` / `missing_direct_scope`。
- `registration`：以验证后的 `(issuer, subject, client_id)` 作为唯一身份；`email` 仅作脱敏展示。每个 `data_dir` 固定一个注册，拒绝导入不同账号覆盖。

## 2. 原子落盘与权限

- Unix：目录创建为 `0700`，`host_identity.json` 与 `credentials.json` 创建即 `0600`。Windows 注明遵循当前用户目录默认权限，不伪称 `chmod(0600)` 等同完整 ACL。
- 写入步骤：在目标目录创建唯一临时文件（`0600`）→ 写入完整 JSON → `flush()` → `os.fsync()` → `os.replace()`；失败时清理临时文件。
- 仅支持本地文件系统或标准 Docker bind mount/volume，不承诺多主机 NFS/SMB 并发刷新。

## 3. 双层锁与刷新事务

进程内用 `asyncio.Lock`（或共享 Future/Task）合并同进程并发刷新；跨进程用独立 `credentials.lock` 保护完整事务：

1. 进入进程内协调器，复用已有在途刷新任务或创建新任务。
2. 在**同一个工作线程**中完成 `credentials.lock` 获取（带超时）、重读 `credentials.json`、检查是否已被他进程刷新、执行网络刷新、用缓存 JWKS 验签（若有新 ID token）、原子落盘与释放锁（严禁把 `acquire` 和 `release` 拆到两次 `asyncio.to_thread`）。
3. 浏览器授权等待、SSE 推理和用户输入期间**不持有文件锁**。

**调用者取消保护**：`TokenManager` 持有刷新任务的强引用，调用方通过 `asyncio.shield` 等待。若单个调用协程被取消，已开始的刷新事务继续完成落盘并释放锁，避免丢弃已轮换的新 token；插件 `on_unload` 时有界等待在途刷新收尾。

## 4. 刷新失败与不确定状态（务实策略）

| 情况 | 处理 |
| --- | --- |
| 连接建立前明确失败 | 保留原记录，预算内有限重试 |
| 刷新成功 | 新 access/refresh/expiry/scope 一起原子替换，`revision += 1` |
| 终止错误码（`invalid_grant` 等） | 清除本地 token，置 `state = "auth_required"`，保留注册与 host ID |
| 已发送但读响应超时/断连 | 置 `state = "refresh_uncertain"`，停止盲重试旧 token，提示重新 `login` |
| 验签失败或原子写盘失败 | 不回退旧 refresh token，报错并提示重新 `login`（不做复杂检查点恢复） |

## 5. 登录、导入与登出竞态

- **登录**：开始前记录预期 `session_generation`（浏览器阶段不持锁）；成功后持锁重读，若代次已被并发更新则报 `stale_attempt`，不覆盖更新的会话。
- **导入（`import-credentials`）**：直接接收源端停止所有活动后的 `credentials.json` 副本。Unix 下若源文件权限非 `0600`，报错提示先 `chmod 600` 再导入。校验 schema 与身份一致（不同账号拒绝覆盖）后，持锁写入、递增 `session_generation`、保留目标 `host_identity.json`；**不自动清除同注册的额度暂停**。
- **登出（`logout`）**：先拦截新请求，持锁读最新 `refresh_token` 并尝试远端撤销，随后清空本地 tokens、置 `state = "logged_out"`、递增 `session_generation`（保留注册与 `host_identity`）。远端撤销未确认时明确提示用户前往官方设置手动断开。
- **在途请求保护**：推理开始前记录 `session_generation`；流完成后返回 Host 前再次核对，若期间发生登出或会话替换则丢弃结果并报错，不交给 Host。

## 6. 日志脱敏

只记录错误类别、HTTP 状态、官方 `error.code`、`request_id`、耗时、脱敏标签与状态转换。严禁记录正文、原始 response body、授权 URL、Authorization、Cookie 或原始 SDK 异常 repr；在边界重建安全异常并抑制 `__cause__`/`__context__` 泄密链。
