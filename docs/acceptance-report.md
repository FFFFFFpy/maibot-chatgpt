# MaiBot ChatGPT Subscription Provider · 验收记录

## v0.1.2 · 管理页支持 HTTP

[测试包](../implementation/artifacts/maibot-chatgpt-provider-v0.1.2-web-login-preview.zip)：局域网 HTTP 管理页不再阻断授权，只显示明文提示；官方 OAuth、token 和推理端点保持 HTTPS。Chromium 在合成非回环 HTTP 父页面中完成配对、回执上传和状态更新；未使用目标管理口令或真实订阅。冻结离线回归 152 passed、1 live deselected；ZIP 冷装及严格目录校验通过。

## v0.1.1 · 共享 Runner 依赖兼容修订

目标截图确认 v0.1.0 在发现阶段因要求 openai==2.54.0 被拒（宿主已有 3.55.1）。本次移除该包运行依赖，不修改宿主。官方接口、登录页面、流式完成条件保持不变。

- [新版插件 ZIP](../implementation/artifacts/maibot-chatgpt-provider-v0.1.1-web-login-preview.zip)：48,415 字节，SHA-256 `1b1590864bafd6f88a3be428e67adfe46cfe89d5178d78886d22408edf9e7bd9`。
- [无 OpenAI SDK 的冻结环境](../implementation/artifacts/compat-0.1.1-results.xml) 和 [安装 openai 3.55.1 的隔离环境](../implementation/artifacts/compat-openai-3.55.1-results.xml) 各 152 passed，1 live deselected。
- ZIP 冷安装、基线严格目录校验与逐字节重打包均通过。目标 Runner 更新后的实际加载和真实账户推理仍待验证。

以下为 v0.1.0 历史验收。

## 页面登录修订：本次交付

[Web 登录测试包](../implementation/artifacts/maibot-chatgpt-provider-v0.1.0-web-login-preview.zip)，48,786 字节，SHA-256 `49d1365e9d2c38ae75ac9d31d63b6802e5887f2cfb678e6311d852fa0992a808`。与下文初版/网络修订归档区分。

- 全量冻结离线回归：[148 passed，1 live deselected](../implementation/artifacts/web-login-results.xml)。
- Chromium 合成联调：加载基线 Host WebUI schema 和实际沙箱桥脚本，以测试父页代替认证 RPC；明文 LAN 禁止启动，HTTPS 进入页面、发起配对、本机回调、WebCrypto 加密回执、选择文件、验证落盘、显示已连接，均通过。未使用真实订阅或目标容器。
- 单层插件 ZIP 冷解压 26 个白名单文件、安装 23 个运行包、SDK 工厂加载、基线严格目录校验通过，重打包逐字节相同。
- G2 目标实例加载/调用、G3 本人授权及实际模型回复仍待用户实测。测试指南见[页面登录说明](../implementation/README.md)。

## 先前修订的验收记录

**判定：交付开发预览，不发布为可用正式插件。** 固定源码的请求与回复可以往返，G1 全部 25 个矩阵场景通过。尚无证据表明目标 MaiBot 通过订阅收到了真实回复；本次修复后纯插件 ZIP 通过基线严格目录校验，但没有安装到目标实例。

## 基本信息

| 字段 | 实测值 |
|---|---|
| 插件版本 / 源码 revision | 0.1.0；修复基于 fed751d；本次未推送。交付字节由下方 SHA-256 标识 |
| 日期 / 执行环境 | 2026-11-25，Asia/Shanghai；本地自动化，Windows 11 10.0.26200，隔离 CPython 3.12.13，uv 0.13.5 |
| 研究 Host / SDK | MaiBot 1.4.8 @ edf42446f123149c57fc79765dd5a8b004b8524c；SDK 2.23.0 @ f9984673d7e6061832e9306cf0e0daaf375f0f91 |
| 目标 image ID/digest、Host / SDK / Python、data_dir 挂载 | **未知**。远端管理首页未认证 GET 返回 HTTP 200，仅证实页面可达；没有使用密码，没有取得目标容器或 Runner 终端。未启停或重建容器。源码推导路径不能代替目标挂载 |
| 依赖 | HTTPX 0.28.1、OpenAI 2.54.0、PyJWT 2.15.1、cryptography 50.0.2、SDK 2.23.0。开发锁见[uv.lock](../implementation/uv.lock)，冷安装实际用[运行清单](../implementation/requirements.txt) |
| 真实账号授权 | 无；只访问过公开文档、源码、包索引和匿名 discovery。没有使用任何真实账号会话 |

## Gate 状态

| 门槛 | 状态 | 证据及界限 |
|---|---|---|
| G0 研究基线协议对齐 | pass | [源码探针](../implementation/tests/baseline_probe.py)：实际 Host serializer → 插件适配 → Host deserializer → 下一轮 refusal。真实 SDK 工厂注册一个 client_type。仅指冻结提交 |
| G0 目标镜像/目录与协议验证 | blocked | 目标页面已定位；实际 Runner 版本、ctx 路径、挂载与目标请求尚未核实 |
| G1 离线测试 | pass | [JUnit 逐例结果](../implementation/artifacts/offline-results.xml)：139 passed，显式 live 1 deselected；25/25 个 G1 矩阵场景。真实 OS 进程、loopback 浏览器回调、合成签名与 HTTP，无外部账号 |
| G2 Host 加载与请求协议 | blocked | 基线严格目录校验通过；目标 Runner 版本、安装与 RPC 未验证。直接 SDK 调用/源码反序列化不代替发现和 RPC |
| G2 Host 错误/回退 | blocked | 未通过实际路由发起。未测候选顺序、总尝试次数、显式单模型失败或生命周期注销 |
| G3 用户本人 OAuth / 目录 | not_run | 无本人浏览器授权或实际模型目录 |
| G3 CLI 完成推理 | not_run | 未对官方模型发起真实请求 |
| G3 MaiBot 完成推理 | blocked | 缺已验证的目标 Runner 和个人 OAuth 会话；备用模型未参与 |
| G3 真实续期 | not_run | 无真实会话自然到期，没有篡改时间或令牌 |
| G3 持久化重启/重建 | not_run | 无已核实卷，也无重建授权 |

## 用例结果

按[原矩阵](../acceptance/test-matrix.csv)计：**37 项，25 pass、0 个已执行的完整矩阵场景 fail、12 未完成（含 blocked）**。初版 Manifest 曾预检失败，本次已修复；本地目录校验不是 QA001。139 是参数化测试函数实例数，不是矩阵场景数。

| 矩阵 ID | 状态 | 证据、影响或下一步 |
|---|---|---|
| QA001 | blocked | 原样 ZIP 已通过基线目录校验。下一步核对目标版本，在真实 Runner 验证发现和依赖 |
| QA002 | blocked | 源码反序列化已测；仍需真实 Host → Runner RPC，核对 output_items 和 usage |
| QA003 | blocked | 需对有候选与显式单模型分别注入 auth/quota/临时/协议错误，记录实际尝试数 |
| QA004 | blocked | 缺目标挂载；需实测 CLI 与 ctx.paths.data_dir 同址及模型文件前后哈希 |
| QA005 | blocked | SDK 直接 reload/unload 已测；需 Host 反复启停并检查注销、流和在途刷新 |
| QA006–009 | pass | [登录](../implementation/tests/test_login.py)、[边界补测](../implementation/tests/test_edges.py)：实绑随机 loopback、PKCE、direct scope、回调拒绝/取消、RS256/JWKS、多 aud/azp、两次浏览器流程晚提交 |
| QA010–012 | pass | [存储](../implementation/tests/test_store.py)、[Provider](../implementation/tests/test_provider.py)：转移保留目标身份、跨注册拒绝、目的地/重定向、模拟 TLS 失败、earliest 与安全窗口。Unix 权限拒绝分支用模拟；未声称测过 Linux ACL |
| QA013–018 | pass | 双 spawn 进程同步争用只刷新一次；落盘前后取消仍可复用、新旧 generation 在途结果区分、持锁进程终止后重获锁；读中断、损坏/未知文件、替换失败、撤销成功与未确认分开测试 |
| QA019–020 | pass | [模型目录与请求](../implementation/tests/test_provider.py)、[CLI](../implementation/tests/test_cli_sdk.py)：可见模型保序；真实子进程输出 TOML 可解析且不产生宿主配置文件 |
| QA021–023 | pass | schema 1 多轮 developer/user/assistant 与 refusal，工具/多模态/非空 extra 等在网络前失败，采样参数只告知一次、不发出 |
| QA024–027 | pass | [SSE 状态机用例](../implementation/tests/test_provider.py)：逐字节 UTF-8、心跳、多行、usage 映射、拒答、reasoning 隔离；破损、EOF、失败、额度、取消和超限均不返回半段；另重放任务包 5 个合成 SSE 夹具 |
| QA028–030 | pass | SDK 禁重试实发计数、隔离环境头、Retry-After/并发冷却、持久暂停/显式 resume；日志/异常链/CLI canary 与禁止 ctx.llm.generate 的 SDK 假上下文。不是对所有第三方日志配置的安全认证 |
| QA031 | blocked | 真实源码 codec 的 refusal 往返通过，**目标 Host/Runner** 未验证；需在隔离实例再跑一轮助手历史 |
| QA032 | not_run | 本人需在可访问的桌面 loopback 完成 OAuth；不向实施者提供凭据 |
| QA033 | not_run | QA032 后由本人取实际目录，选可用纯文本 slug |
| QA034 | not_run | 用所选 slug 执行一次短 CLI smoke，记录完成终态 |
| QA035 | blocked | G2 及授权后做隔离纯文本任务，确保不是其它供应商回复 |
| QA036 | not_run | 等真实 token 自然接近到期，观察 revision 与 generation 并复测 |
| QA037 | not_run | 待明确授权重建测试实例；核对持久卷、身份与真实最小调用 |

## 实际执行命令与结果

以下为执行记录；相对路径除注明外以 implementation 为起点，BASELINE 代表临时的上述固定 MaiBot checkout。省略安装器下载进度、绝对用户路径和所有会话值。

| 实际动作 / 命令（路径缩写） | 退出码 / 观察 |
|---|---|
| Docker 引擎探测；根目录 git remote、git rev-parse HEAD | Docker 1：dockerDesktopLinuxEngine 命名管道不存在。Git 0：没有 remote；取得上表任务包 revision |
| python -c 导入固定 Host 的 PluginManifest 并对预览 model_validate_json | 1：恰好 author.url、urls.repository 两个缺失字段；没有用假 URL 或绕过 validator 造成功结果 |
| python tests/baseline_probe.py BASELINE | 0：synthetic serializer → adapter → deserializer → refusal replay 通过，并验证修复后的严格 Manifest schema。探针使用仅研究环境安装的 structlog、tomlkit、rich、watchfiles、sqlalchemy；不进入运行依赖 |
| python -m pytest -q tests/test_store.py；python -m pytest -q tests/test_provider.py；python -m pytest -q tests/test_cli_sdk.py | 各 0；开发时分别 26、69、8 passed。随后切到真实 OpenAI SDK 发送路径，网络/CLI 合并重跑 77 passed |
| uv pip compile pyproject.toml [--group dev] --python ../.p0-dev --output-file … --no-header --no-annotate；uv lock --python ../.p0-dev/Scripts/python.exe | 各 0：生成精确依赖清单与锁 |
| uv lock --check；uv sync --frozen --python ../.p0-dev/Scripts/python.exe；uv run --frozen python -m pytest -m offline -q --junitxml=artifacts/offline-results.xml | 各 0；全新锁定测试环境安装 28 包。**132 passed, 1 deselected in 27.30s**；这是初版结果。本次同一冻结环境重跑 **139 passed, 1 deselected in 21.81s**；新增代理 CONNECT、NO_PROXY、CA 优先级/失败关闭测试 |
| python scripts/package_plugin.py --preview --output-dir artifacts | 0；确切文件白名单、单层插件目录、ZIP CRC 校验 |
| python tests/cold_install.py artifacts/maibot-chatgpt-provider-v0.1.0-preview.zip BASELINE | 0：独立临时目录解压 → 新 Python 3.12 环境 → 23 包安装/uv pip check → CLI help/init-host/status/doctor → 真实 SDK 工厂 → 重打包 SHA 完全相同。基线 WebUI ZIP 安装器所用的 ManifestValidator.load_from_plugin_path 对解压目录返回成功；仍非目标安装 |
| Get-FileHash artifacts/maibot-chatgpt-provider-v0.1.0-preview.zip -Algorithm SHA256 | 0；与构建及冷重打包值相同 |

## 真实链路证据

本次真实账号 slug、推理时间、request_id、completed、usage、Host 接收：**均无**。没有正式群消息、真实账号调用、真实续期或容器重建。合成样本不填进真实链路栏。

## 已知差异

见[兼容报告](compatibility-report.md)。只支持经源码核实的 item_schema_version=1，不走旧 message_list/content-only；目标不匹配时显式失败。Windows 文件锁是真实 msvcrt；未在 Linux 上实测 flock 或容器权限。专用代理/额外 CA 环境待独立验证，不允许关闭 TLS。若刷新已经送出但整个磁盘不可写，不可能可靠持久标记不确定状态：停所有进程、恢复磁盘后重新 login，勿用旧文件继续推理。

## 产物与恢复

- [开发预览 ZIP](../implementation/artifacts/maibot-chatgpt-provider-v0.1.0-preview.zip) · **36,712 字节** · SHA-256 `8681f8c9e34289705ab9dfa1592b53b9823dabbe591e02da537c2e8f6f38c9c3`。22 个白名单文件；无凭据、host identity、锁文件、私钥、日志、测试或虚拟环境。完整源码与测试在 implementation，不包含在运行 ZIP 的测试树中。
- [安装/CLI](../implementation/README.md)、[Docker 操作手册](../implementation/docs/docker.md)、[第三方许可](../implementation/THIRD_PARTY_NOTICES.md)。安装根为测试实例 plugins/maibot_chatgpt_provider_plugin；包不捆绑依赖，先核对 Runner 环境。撤回时先恢复任务原模型，禁用插件，撤销新增配置；仅在最终持有端执行 logout，保留卷。

## 最终结论

- [ ] 所有要求在目标环境验收通过。
- [ ] 代码与离线/Host 测试完成，仅真实账号或部署验证待执行。
- [x] **仅作为 G2 测试包，不宣称正式可用。** G1 与基线安装预检已通过；目标 Runner 加载与真实 MaiBot 回复仍未验收。

**下一步（不涉及秘密）：** 提供安全管理通道或由管理员在测试实例上传纯插件 ZIP；用实际 Runner 解释器核对版本和数据卷。未取得目标依赖版本，不扩大兼容声明，不强制升级宿主。先完成 G2；之后由用户本人在本地授权做 G3，无需发送密码、验证码、授权 URL 或 token。
