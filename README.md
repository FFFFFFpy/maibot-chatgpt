# MaiBot ChatGPT Subscription Provider

以本人 ChatGPT 订阅为 MaiBot 提供文本、视觉和 Planner 函数工具。插件在 MaiBot 中注册厂商类型 `maibot.chatgpt.subscription`，使用独立 OAuth 登录，不读取浏览器或 Codex 凭据，不需要付费 API Key。非 OpenAI 官方插件。

## 安装与连接

插件 ID：`github.ffffffpy.chatgpt_subscription`。市场收录后在 MaiBot WebUI 的「插件市场」搜索插件名；审核期间可从 [GitHub Releases](https://github.com/FFFFFFpy/maibot-chatgpt/releases) 获取对应版本源码，解压后以包含清单和入口的那一层作为插件目录。

1. 启用插件，打开详情页的「订阅连接」，点击「使用 ChatGPT 继续」，打开官方授权链接。
2. 同机登录可自动接收回调；远端部署时，将浏览器最后的完整返回地址粘回插件页。不要向任何人发送该地址。LAN HTTP 管理页仅在可信网络使用。
3. 显示「已连接」后刷新模型，勾选并确认写入模型库，或使用「复制 ID」手动添加。先点模型行的 ⚡ 测试，再手动分配任务。

### 从 0.4.x 或更早的本地预览版迁移

旧 ID 为 `local.maibot.chatgpt_subscription`；宿主会把市场版当成**另一个插件**。先暂停相关任务、私下备份旧插件数据与配置，再禁用并卸载旧插件代码；不要同时启用两版，它们注册相同的厂商类型。安装新版后在新插件页重新登录，检查并发等设置。插件不跨数据目录读取或自动复制旧凭据。已有模型条目和任务分工通常无需重建；确认厂商类型后做单模型测试。不要将备份提交到仓库或工单。

基线：MaiBot 1.4.8 / SDK 2.23.0 / Python 3.12。详见[兼容性说明](docs/compatibility-report.md)。本项目采用 [MIT](LICENSE)，第三方许可另见[来源说明](THIRD_PARTY_NOTICES.md)。

## 分工前测试单个模型

在原生「模型库」找到具体模型，点击模型行右侧的 ⚡，不用先分配任务。插件将该行模型 ID、测试提示、MaiBot 内置测试报告工具，以及启用视觉时的基线测试 PNG 一起交给官方 Responses API。仅模型真实返回已完成、参数符合要求的测试工具调用才回报成功；测试会使用订阅额度。闪电按钮只验证内置报告，不代表 planner 多轮验收。若模型不支持视觉，可关闭该模型的「视觉」后重测不带图的版本。

## Planner 与动态工具

每轮从宿主快照重新构造函数列表并设置 `strict: false`，不缓存工具、不执行或调度。保留 Schema（包括 schedule 的 not）；若上游拒绝，不擅自删约束重试。系统消息逐条原位转换成 developer，保留每个文本段；首条仍在开头，中途和尾部提醒不提前，不发顶层 instructions。纯工具输出和并行调用均按原 call_id 回传。基线 Host 的工具媒体通常出现在结果后的独立用户消息；保留其 media_index 和图文顺序。视觉关闭时用明确的文字占位，不下载任何图片 URL。请求层 reasoning_effort 优先于模型配置，其他扩展只记录忽略数量。建议隔离测试会话中先验证 wait/reply，再验证延迟工具与图片；真实订阅端是否接受完整 schema 需现场确认。

## 观察 Prompt Cache

请求体的 prompt_cache_key 和两个会话亲和头使用同一短摘要；优先使用跨轮 session_id，不用 logical_turn_id。基线 1.4.8 Runner 不传日志外层的 session_id，通常按系统提示首段前 1024 字派生。无系统文本则取第一条用户文本头。相同前缀可能用于多个对话，因此服务端 turn-state 还按当前登录代次、模型及会话（或首条用户消息的宿主 item_id）隔离；无可靠锚点就只发亲和头，不跨聊天猜测重放。状态仅保留在进程内、最多 256 条。明确拒绝旧状态时删除并不带该头重试一次；已有生成流不重试。

当上游报告缓存计数时，INFO 日志会输出 prompt_cache cached_tokens=… input_tokens=… hit_rate=…，不含正文、会话号或状态头。Host 的 prompt_tokens 仍是完整输入，另报命中与未命中；缺失的统计不冒充零。可在同一长上下文对话连续几轮观察，不能从单次请求推断节省金额或承诺命中率。

## 写入模型库（手动触发）

登录并刷新模型后，勾选需要的 ID，点击「写入到 MaiBot 模型库（自动备份原文件）」并确认。仅写入本次选择：创建 ChatGPT 订阅厂商，或复用唯一兼容厂商；跳过已存在的映射。冲突时整批停止，不覆盖、不删除。返回原生模型库重新加载，确认条目后再在「分工」给一项纯文本任务分配模型。登录、刷新、启动、退出都不触发写入。

SDK 2.23.0 没有公开模型库写接口，此功能按管理员此次授权直接更新已有的 `/MaiMBot/host/model_catalog.toml`（仅该路径、目录格式 3.0.0）。不改核心，不动 Bot 分工。使用与基线原生编辑器相同的 model-config.lock；发现遗留事务、格式/版本不支持或权限不足即停止。修改前将原字节以仅属主可读写的独立备份保存到同目录，页面显示备份文件名；验证合并结果、复查源文件后同目录原子替换。请勿同时用不遵守宿主锁的编辑器保存：原子替换不能消除这类写入者的所有竞争窗口。建议关闭旧编辑页再操作。

备份可能含其他厂商私钥，请勿上传或分享。需要撤销时，优先在原生模型库移除本次新增模型及不再使用的厂商；若要整份恢复，先停止所有配置写入并私下备份当前文件，确认期间没有其他需要保留的修改，再用页面所列备份恢复原文件。不要用旧备份覆盖他人的新配置。没有合适的挂载或写权限时，继续使用「复制 ID」和手动添加，不要扩大整个卷的权限。

## 开发者与运维（可选）

开发环境、容器挂载和冷安装见 [Docker 手册](docs/docker.md)。CLI 不属于页面登录步骤。

## CLI：不要把密码、授权码、token 或授权 URL 发给别人

将 `PRIVATE_DIR` 替换为此会话的**绝对私有路径**。插件内仅从 `ctx.paths.data_dir` 取目录；若与 CLI 不同，双方不会看到同一会话。不得选源码目录、临时 runtime、网络共享或多人可读目录。Unix 先设置 `umask 077`；Windows 用当前用户的私有目录并核对 DACL。

~~~text
python scripts/login.py --data-dir PRIVATE_DIR init-host
python scripts/login.py --data-dir PRIVATE_DIR login
python scripts/login.py --data-dir PRIVATE_DIR status --json
python scripts/login.py --data-dir PRIVATE_DIR doctor
python scripts/login.py --data-dir PRIVATE_DIR models --json
python scripts/login.py --data-dir PRIVATE_DIR config --model ACTUAL_MODEL_SLUG
python scripts/login.py --data-dir PRIVATE_DIR smoke --model ACTUAL_MODEL_SLUG --prompt "请回复：测试成功。"
~~~

- `login --no-browser` 仅供本人在同一桌面的浏览器手动打开打印的授权 URL；不是设备码或远程回调。普通登录不打印 URL。只在官方页面同意授权。不同主机按 [转移步骤](docs/docker.md) 办理。
- `doctor` 默认仅本地，`doctor --online` 另核对官方 discovery。`models` 只列当前账号返回的可见名称与 slug，没有内置模型。不要把 synthetic 测试模型当账号模型。
- `config` 只输出 TOML，不改 Host 文件。先备份**实际**模型目录与任务配置，再人工合并；保留原 version、任务映射与其他模型，先绑定只需纯文本的私有测试任务。验证 planner 时请使用隔离会话，勿直接在正式群聊做回放。默认 Host timeout 200 秒、max_retry 1（基线含首次），插件总预算 180 秒、默认同时执行 4 个请求、另最多等待 4 个，每条响应缓冲 1 MiB。已保存的 `request.max_concurrent_requests` 会覆盖新版默认值；旧实例如仍是 1，可手动改为 4。`local_queue_full` 表示请求未发出；`rate_limited` 表示上游 HTTP 429。切换模型时会跳过历史 `ReasoningItem`，不发送其内容，仍严格校验后续工具结果配对。
- `smoke` 会使用本人订阅额度；只用于短人工测试，不要在命令行放真实聊天。CLI 成功不等于 Runner 成功。
- `import-credentials --from-file PRIVATE_TRANSFER_FILE` 只用于本人停止使用的受信本地会话副本，不能用于不可信 JSON。同目录不换账号。`resume` 只解除本地暂停，不保证额度已恢复。`logout` 尝试官方撤销、清空本地 token 并保留注册和 host identity。不要在移交后的源端登出。

## 故障与回滚

| 退出码 | 含义 / 处理 |
|---:|---|
| 0 | 命令完成；status 成功仅表示能读取状态 |
| 2 | 参数、client 或配置错误；核对设置，不自动重注册 |
| 3 | 未连接、资格/权限或会话问题；依安全错误类别操作，勿循环重登 |
| 4 | 输入、路由、能力不匹配；换回纯文本或原模型 |
| 5 | 暂停/限流/冷却；遵守 Retry-After。额度暂停先看 [Usage](https://chatgpt.com/settings/usage)，确认后运行 resume |
| 6 | 网络、上游或不完整流；不交付半段文本、不重放含糊 POST。logout 未确认时去 ChatGPT 设置手动断开 |
| 7 | 本地存储/权限/锁；不要删锁。刷新后写盘失败先停所有进程、修复磁盘、重新 login，勿恢复旧 token 副本 |

关闭：先将测试任务切回原模型，再禁用插件并观察注销，撤回手工新增的模型与供应商条目；不再使用时在最终持有端 logout。详见 [Docker、证书与回滚](docs/docker.md)。第三方依赖不随 ZIP 分发，见 [来源与许可](THIRD_PARTY_NOTICES.md)。
