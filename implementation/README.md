# MaiBot ChatGPT Subscription Provider · v0.1.1 开发预览

仅供自托管 MaiBot 通过**自己的** ChatGPT 订阅发起纯文本请求。插件注册 `maibot.chatgpt.subscription`，使用独立 SIWC 会话，不读取 Codex 或浏览器登录缓存，不使用 API key。只认完成的 Responses 终态。工具、图像、音频、Embedding、结构化输出不在 P0；跨供应商回退归 Host。

**发布状态：已补齐作者主页与仓库地址，供隔离实例 G2 验证。** 没有在目标容器、真实账号或群聊中运行。不要覆盖生产安装。研究基线与边界见 [兼容报告](docs/compatibility-report.md)。

## 从 v0.1.0 更新

若旧插件报 `openai==2.54.0，当前安装 3.55.1`，请保留宿主现有 openai。v0.1.1 使用 HTTPX 直接请求官方 Responses API，不安装、导入或检查 OpenAI Python SDK。用新 ZIP 替换插件代码；管理器若提示同 ID 已安装，先备份专用数据目录，再按宿主流程移除旧插件代码并安装新版。不要删除插件数据卷，不要在共享 Runner 中安装本项目的精确开发锁。

## 从零开始

1. 先确认 [Docker 手册](docs/docker.md) 的镜像、配置、持久挂载和 Runner Python。开发基线为 MaiBot 1.4.8、SDK 2.23.0、Python 3.12。不把这组版本当作目标环境。若 Host/SDK 不一致，先复查契约；不要放宽 Manifest 或自动升级共享环境。
2. 在桌面或临时目录解压预览 ZIP，进入含 `plugin.py` 的目录。创建**单独**环境（Windows 用 `py -3.12 -m venv .venv`，macOS/Linux 用 `python3.12 -m venv .venv`）。以下 `python` 指这个环境的解释器：Windows `.venv\Scripts\python.exe`，macOS/Linux `.venv/bin/python`。
3. 运行 `python -m pip install -r requirements.txt`、`python -m pip check`、`python scripts/login.py --help`。锁定的运行依赖不是建议覆盖 Host 环境；先在同镜像副本核对冲突。源码开发可用 `uv sync --locked --python 3.12`、`uv run --locked python -m pytest -m offline`（保留任务包相邻 fixtures 目录）。
4. 仅使用白名单打包器生成的插件 ZIP；不要把任务包根目录复制到插件目录。可在源码或解压目录重建：

~~~text
python scripts/package_plugin.py --output-dir OUTPUT --preview
~~~

   构建不上传、不启用，也不代表目标 Runner 的门禁通过。将候选解压到**测试实例**的插件目录，形成 `plugins/maibot_chatgpt_provider_plugin/_manifest.json`（不要双层嵌套）。用该实例实际 validator/Runner 确认发现、依赖、启用及唯一注册。先用 mock 上游和私有测试任务做 G2，再做 G3。源码打相同预览用 `--preview --output-dir OUTPUT`。

## 从插件页面连接 ChatGPT（本测试包新增）

1. 在测试实例的插件管理中上传本 ZIP 并启用插件。打开插件详情的「订阅连接」扩展页；若该版仪表盘把扩展放在侧栏，从「插件扩展 → ChatGPT 订阅 → 订阅连接」进入。仅支持可信 HTTPS 管理地址或经过安全隧道的本机回环地址。明文 LAN 页面不会启动登录。
2. **远端 / Docker（默认）**：在浏览器所在电脑上也解压同一个 ZIP。页面点击「连接 ChatGPT」，复制配对串。桌面终端进入解压后含 plugin.py 的目录，运行 **python scripts/desktop_callback.py**（Windows 也可 py -3 scripts/desktop_callback.py）。桌面只需 Python 3.9+ 和现代浏览器，无第三方依赖。在提示处粘贴配对串并回车。脚本先监听本机 127.0.0.1:1455 再打开官方授权页，不输入或保存账号密码。
3. 在 OpenAI 页面同意后，本机回调页点击「保存登录回执」。回到 MaiBot 原页选择回执文件；若无法下载，可粘贴**加密回执**。切勿粘贴回调网址、授权码或 token。会话仅在 Runner 验签并写入 data_dir 后显示「已连接」。回执和配对串仅供本次使用，五分钟过期，可取消并重试；完成后删除回执。
4. **同机模式**仅适用于浏览器与 Runner 共享 127.0.0.1，或已明确将桌面回环 1455 安全转发到 Runner 同一回环端口的部署。选同机、点击连接，将显示的官方链接在新标签打开；回调后页面自动更新。宿主 iframe 不允许弹出外部窗口，勿把容器的 localhost 当作桌面。无需向 LAN 发布 1455。

模块使用宿主 schema 2 的 custom_pages 与静态 API；不替换宿主 WebUI。桌面助手不会访问 MaiBot、读取浏览器缓存或处理 token。回调用每次授权独有的 RSA-OAEP/SHA256 + AES-GCM 加密；验签、换码与持久化始终在 Runner，沿用 CLI 的 PKCE 与 OIDC 校验。CLI 登录保留为备用。

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
- `config` 只输出 TOML，不改 Host 文件。先备份**实际**模型目录与任务配置，再人工合并；保留原 version、任务映射与其他模型，先绑定只需纯文本的私有测试任务。不要绑定 Planner 或视觉任务。默认 Host timeout 200 秒、max_retry 1（基线含首次），插件总预算 180 秒、并发 1、缓冲 1 MiB。
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
