# 目标实例操作手册（待实机执行）

不要导出整个 docker inspect 或环境变量，可能含其它供应商的密钥。不覆盖 Compose、代理、CA、NapCat、模型配置或数据目录。命令中的大写路径均是占位符，不是测得的部署位置。

## 1 · 安装前只读取证

~~~sh
docker ps --format 'table {{.Names}}	{{.Image}}	{{.Status}}'
docker inspect --format '{{.Image}}' CONTAINER
docker image inspect --format '{{json .RepoDigests}}' IMAGE_ID
docker inspect --format '{{range .Mounts}}{{println .Type .Source "->" .Destination}}{{end}}' CONTAINER
docker exec CONTAINER RUNNER_PYTHON -c 'import sys,importlib.metadata as m;print(sys.version.split()[0], m.version("maibot-plugin-sdk"))'
~~~

记录镜像/Host 版本与 SDK，脱敏核对共享 host/、Bot 实例 / 插件目录、**实际 ctx.paths.data_dir**、卷与 Runner UID/GID。源码基线推导为 PROJECT_ROOT/data/plugins/github.ffffffpy.chatgpt_subscription，必须运行时确认，不是固定容器路径。未持久化先停止接入。使用本地文件系统 bind/volume，不支持多机共享 NFS/SMB。Unix 将该专用数据目录置 0700，凭据文件 0600，属主为运行插件的用户；不要 chmod 整个卷。v0.1.3 起，若 Host 预建的插件专用 data_dir 是 Runner 所有且仅对其他用户开放读取/遍历（如 0755），插件在首次加锁时仅将该目录收紧到 0700；不会递归改权限、修改父目录、接管其他用户目录或改动 CLI 指定的路径。卷只读、UID/GID 不匹配或凭据文件损坏时，页面会给出相应提示。Windows 必须自己核验 DACL。插件按官方 HTTPS 目标选取 HTTPS_PROXY（或 ALL_PROXY），尊重 NO_PROXY；只有 HTTP_PROXY 不代表 HTTPS 流量也应走代理。显式加载 SSL_CERT_FILE / SSL_CERT_DIR，二者均未设置时可用 REQUESTS_CA_BUNDLE。请在实际 Runner 与 CLI 各自的环境设置可信代理和 CA，不要在聊天、日志或插件配置中填写代理密码。保持证书及主机名校验，不跟随重定向，不继承 OpenAI 账号相关环境头。

### 官方授权链接未出现，提示网络或 TLS 失败

请求由 **Runner** 发出，不由桌面浏览器发出。在 Runner 容器内，以相同用户、解释器及代理/CA 环境进入已解压插件目录，运行以下匿名探针。它只向官方 discovery 发 GET，不读写凭据，不跟随重定向；v0.1.4 会报告脱敏分类和非 200 状态码：

~~~sh
python -c "from maibot_chatgpt_provider.oauth import OAuth; OAuth().discover(); print('discovery OK')"
~~~

若使用宿主机代理，容器内 127.0.0.1 通常不是宿主机；请使用容器可达的受信代理地址。检查 HTTPS_PROXY / ALL_PROXY 及 NO_PROXY 是否符合部署预期。若组织代理使用自签根证书，向 Runner 挂载受信任的 CA 并设置 SSL_CERT_FILE，保持证书及主机名校验。不要粘贴完整环境变量、代理 URL、抓包或凭据。匿名探针成功仅代表 discovery 正常，并非账号已连接。

## 2 · 安装与迁移

按[README](../README.md)生成纯插件 ZIP 并导入候选；只在同版本测试实例启用，保存原模型配置哈希及私有备份。以 Runner 相同用户与解释器在容器内进入插件目录。在目标实际数据目录先执行：

~~~sh
python scripts/login.py --data-dir TARGET_PRIVATE_DIR init-host
python scripts/login.py --data-dir TARGET_PRIVATE_DIR doctor
~~~

推荐直接在「订阅连接」点击「使用 ChatGPT 继续」，按 [页面登录步骤](../README.md) 操作。同机自动返回；远端可将浏览器返回地址交回本插件，不暴露容器端口。以下是管理员的 CLI 备选路线，不是用户登录的准备工作。

1. 桌面用相同版本、另一个本地私有目录执行 login。不要拷贝 host_identity.json。
2. 停止桌面所有使用或刷新会话的进程。只通过私人加密通道传 credentials.json 至目标的临时私有文件。避免公开共享目录；Unix 先 umask 077，导入前 chmod 600。不传到聊天或工单。
3. 容器内执行下列命令。导入保留目标 host ID，拒绝覆盖不同注册，保留同注册的暂停。确认后清理目标传输临时文件及桌面端凭据副本；**不要在转移源执行 logout**。

~~~sh
python scripts/login.py --data-dir TARGET_PRIVATE_DIR import-credentials --from-file PRIVATE_TRANSFER_FILE
python scripts/login.py --data-dir TARGET_PRIVATE_DIR status --json
python scripts/login.py --data-dir TARGET_PRIVATE_DIR doctor --online
python scripts/login.py --data-dir TARGET_PRIVATE_DIR models --json
python scripts/login.py --data-dir TARGET_PRIVATE_DIR config --model ACTUAL_SLUG
~~~

## 3 · 验收顺序

- G2（上游 mock）：不要改生产端点配置。用隔离 Runner 测试夹具在构造时注入 HTTP transport，跑真实发现/加载和 RPC。核对 request schema 1、output_items/usage、refusal 下一轮、reload/unload、路径同一性、配置前后哈希。分别注入 auth/quota/临时错误和未知 schema，记录候选路径/每个模型实际尝试数；另测显式单模型不回退。测试注入不能作为生产配置项。
- G3（仅用户本人授权）：先私有 CLI smoke，再用同一实际 slug 做 MaiBot 私有纯文本任务。人工合并 config 输出到实际 host/model_catalog.toml；Bot 的 config/model_config.toml 只绑定单独测试任务，关闭备用候选，保留原 [inner].version。证据只记时间、slug、完成终态、Host 是否接收、真实 usage/request_id（若有），不要收录正文与授权材料。
- 等自然临近过期检查 revision 增而 session_generation 不变，复测。**另获授权**且验证卷/备份后才重建测试容器，核对同一注册与 host ID，再做小请求。未执行的两项不能用第一次成功代替。

## 4 · 退出与回滚

将测试任务切回原模型 → 禁用插件并确认注销/资源关闭 → 仅撤销本次新增条目（手工或按钮追加）；若整份恢复，须确认期间无其他有效修改，并先停止写入者及备份当前版本。需要断开时，在最终持有端运行 logout；远端未确认时在 ChatGPT 设置里手动断开。额度暂停只用 resume；不要删除凭据锁、改 expiry、换账号或切付费密钥。卸载插件代码不等于撤销授权，也不应连带删除卷。
