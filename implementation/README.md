# MaiBot ChatGPT Subscription Provider · v0.4.1 开发预览

仅供自托管 MaiBot 通过**自己的** ChatGPT 订阅发起文本、函数工具及视觉请求。插件注册 `maibot.chatgpt.subscription`，使用独立 SIWC 会话，不读取 Codex 或浏览器登录缓存，不使用 API key。只认完成的 Responses 终态。不执行工具，不提供音频、Embedding 或结构化输出；跨供应商回退归 Host。

**发布状态：已补齐作者主页与仓库地址，供隔离实例 G2 验证。** 没有在目标容器、真实账号或群聊中运行。不要覆盖生产安装。研究基线与边界见 [兼容报告](docs/compatibility-report.md)。

## 从 v0.1.0 更新

若旧插件报 `openai==2.54.0，当前安装 3.55.1`，请保留宿主现有 openai。v0.1.1 使用 HTTPX 直接请求官方 Responses API，不安装、导入或检查 OpenAI Python SDK。用新 ZIP 替换插件代码；管理器若提示同 ID 已安装，先备份专用数据目录，再按宿主流程移除旧插件代码并安装新版。不要删除插件数据卷，不要在共享 Runner 中安装本项目的精确开发锁。

## 管理页登录：只需插件 ZIP

1. 在测试实例安装并启用本 ZIP，打开插件详情「订阅连接」，点击 **使用 ChatGPT 继续**。
2. 点击 **复制官方授权链接**，在新标签打开并同意。若浏览器限制剪贴板，页面会选中链接供手动复制。
3. 浏览器与 Runner 同机时自动完成。远端 Docker 若跳到打不开的 127.0.0.1，把那个标签页地址栏的**完整网址**粘回插件的「登录返回地址」，点击 **完成登录**。无需终端、额外安装、文件或端口映射。请勿将返回地址发给他人；明文 HTTP 管理页仅在可信网络使用。
4. 看到账号与「已连接」后，可查看或刷新真实可用模型、退出登录。有经过验证的邮箱时显示邮箱，否则显示账号代号。服务端在验证 state、PKCE、nonce 与签名后才保存会话。过期、取消或已消费的返回地址不能复用。

## 分工前测试单个模型

在原生「模型库」找到具体模型，点击模型行右侧的 ⚡，不用先分配任务。插件将该行模型 ID、测试提示、MaiBot 内置测试报告工具，以及启用视觉时的基线测试 PNG 一起交给官方 Responses API。仅模型真实返回已完成、参数符合要求的测试工具调用才回报成功；测试会使用订阅额度。闪电按钮只验证内置报告，不代表 planner 多轮验收。若模型不支持视觉，可关闭该模型的「视觉」后重测不带图的版本。

## Planner 与动态工具

每轮从宿主快照重新构造函数列表并设置 `strict: false`，不缓存工具、不执行或调度。保留 Schema（包括 schedule 的 not）；若上游拒绝，不擅自删约束重试。所有系统消息按原顺序放在 input 开头，保留每个文本段，不发顶层 instructions。纯工具输出和并行调用均按原 call_id 回传。基线 Host 的工具媒体通常出现在结果后的独立用户消息；保留其 media_index 和图文顺序。视觉关闭时用明确的文字占位，不下载任何图片 URL。请求层 reasoning_effort 优先于模型配置，其他扩展只记录忽略数量。建议隔离测试会话中先验证 wait/reply，再验证延迟工具与图片；真实订阅端是否接受完整 schema 需现场确认。

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
- `config` 只输出 TOML，不改 Host 文件。先备份**实际**模型目录与任务配置，再人工合并；保留原 version、任务映射与其他模型，先绑定只需纯文本的私有测试任务。验证 planner 时请使用隔离会话，勿直接在正式群聊做回放。默认 Host timeout 200 秒、max_retry 1（基线含首次），插件总预算 180 秒、并发 1、缓冲 1 MiB。
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
