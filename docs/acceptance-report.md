# MaiBot ChatGPT Subscription Provider · v0.1.0 验收报告

**判定：交付开发预览，不发布为可用正式插件。** 固定源码的请求与回复可以往返，G1 全部 25 个矩阵场景通过。尚无证据表明目标 MaiBot 通过订阅收到了真实回复；当前 ZIP 的 Manifest 缺少两项真实发布元数据，不能原样安装到严格 Host。

## 基本信息

| 字段 | 实测值 |
|---|---|
| 插件版本 / 源码 revision | 0.1.0；基于任务包 HEAD `2cee41e2341505c1294672a7fb57ce1c7f591337` 的未提交工作树，无推送。交付字节由下方 SHA-256 标识 |
| 日期 / 执行环境 | 2026-11-25，Asia/Shanghai；本地自动化，Windows 11 10.0.26200，隔离 CPython 3.12.13，uv 0.13.5 |
| 研究 Host / SDK | MaiBot 1.4.8 @ edf42446f123149c57fc79765dd5a8b004b8524c；SDK 2.23.0 @ f9984673d7e6061832e9306cf0e0daaf375f0f91 |
| 目标 image ID/digest、Host / SDK / Python、data_dir 挂载 | **未知**。Docker Desktop Linux Engine 命名管道不存在；未启动或重建容器。源码推导路径不能代替目标挂载 |
| 依赖 | HTTPX 0.28.1、OpenAI 2.54.0、PyJWT 2.15.1、cryptography 50.0.2、SDK 2.23.0。开发锁见[uv.lock](../implementation/uv.lock)，冷安装实际用[运行清单](../implementation/requirements.txt) |
| 真实账号授权 | 无；只访问过公开文档、源码、包索引和匿名 discovery。没有使用任何真实账号会话 |

## Gate 状态

| 门槛 | 状态 | 证据及界限 |
|---|---|---|
| G0 研究基线协议对齐 | pass | [源码探针](../implementation/tests/baseline_probe.py)：实际 Host serializer → 插件适配 → Host deserializer → 下一轮 refusal。真实 SDK 工厂注册一个 client_type。仅指冻结提交 |
| G0 目标镜像/目录与协议验证 | blocked | 无运行中的目标，无法取得版本、实际 ctx 路径、挂载和目标请求 |
| G1 离线测试 | pass | [JUnit 逐例结果](../implementation/artifacts/offline-results.xml)：132 passed，显式 live 1 deselected；25/25 个 G1 矩阵场景。真实 OS 进程、loopback 浏览器回调、合成签名与 HTTP，无外部账号 |
| G2 Host 加载与请求协议 | blocked | 目标 Runner 不可用；真实基线严格校验器拒绝预览 Manifest 的 author.url、urls.repository。直接 SDK 调用/源码反序列化不代替发现和 RPC |
| G2 Host 错误/回退 | blocked | 未通过实际路由发起。未测候选顺序、总尝试次数、显式单模型失败或生命周期注销 |
| G3 用户本人 OAuth / 目录 | not_run | 无本人浏览器授权或实际模型目录 |
| G3 CLI 完成推理 | not_run | 未对官方模型发起真实请求 |
| G3 MaiBot 完成推理 | blocked | 缺目标实例、合格的 Manifest 和个人授权；备用模型未参与 |
| G3 真实续期 | not_run | 无真实会话自然到期，没有篡改时间或令牌 |
| G3 持久化重启/重建 | not_run | 无已核实卷，也无重建授权 |

## 用例结果

按[原矩阵](../acceptance/test-matrix.csv)计：**37 项，25 pass、0 个已执行的完整矩阵场景 fail、12 未完成（含 blocked）**。Manifest 另有一次明确的预检失败，不掩盖成 QA001 通过。132 是参数化测试函数实例数，不是矩阵场景数。

| 矩阵 ID | 状态 | 证据、影响或下一步 |
|---|---|---|
| QA001 | blocked | 原样 Manifest 在固定校验器失败。取得真实作者/仓库 URL，构建候选，在目标 Runner 验证发现和依赖 |
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
| python tests/baseline_probe.py BASELINE | 0：synthetic serializer → adapter → deserializer → refusal replay 通过，并断言预览只缺上述两项。探针使用仅研究环境安装的 structlog、tomlkit、rich、watchfiles、sqlalchemy；不进入运行依赖 |
| python -m pytest -q tests/test_store.py；python -m pytest -q tests/test_provider.py；python -m pytest -q tests/test_cli_sdk.py | 各 0；开发时分别 26、69、8 passed。随后切到真实 OpenAI SDK 发送路径，网络/CLI 合并重跑 77 passed |
| uv pip compile pyproject.toml [--group dev] --python ../.p0-dev --output-file … --no-header --no-annotate；uv lock --python ../.p0-dev/Scripts/python.exe | 各 0：生成精确依赖清单与锁 |
| uv lock --check；uv sync --frozen --python ../.p0-dev/Scripts/python.exe；uv run --frozen python -m pytest -m offline -q --junitxml=artifacts/offline-results.xml | 各 0；全新锁定测试环境安装 28 包。**132 passed, 1 deselected in 27.30s**；另在研究环境全量跑 132 passed |
| python scripts/package_plugin.py --preview --output-dir artifacts | 0；确切文件白名单、单层插件目录、ZIP CRC 校验 |
| python tests/cold_install.py artifacts/maibot-chatgpt-provider-v0.1.0-preview.zip BASELINE | 0：独立临时目录解压 → 新 Python 3.12 环境 → 23 包安装/uv pip check → CLI help/init-host/status/doctor → 真实 SDK 工厂 → 重打包 SHA 完全相同。**此脚本预期且断言 Manifest 被拒绝，不表示严格 Host 冷安装成功** |
| Get-FileHash artifacts/maibot-chatgpt-provider-v0.1.0-preview.zip -Algorithm SHA256 | 0；与构建及冷重打包值相同 |

## 真实链路证据

本次真实账号 slug、推理时间、request_id、completed、usage、Host 接收：**均无**。没有正式群消息、真实账号调用、真实续期或容器重建。合成样本不填进真实链路栏。

## 已知差异

见[兼容报告](compatibility-report.md)。只支持经源码核实的 item_schema_version=1，不走旧 message_list/content-only；目标不匹配时显式失败。Windows 文件锁是真实 msvcrt；未在 Linux 上实测 flock 或容器权限。专用代理/额外 CA 环境待独立验证，不允许关闭 TLS。若刷新已经送出但整个磁盘不可写，不可能可靠持久标记不确定状态：停所有进程、恢复磁盘后重新 login，勿用旧文件继续推理。

## 产物与恢复

- [开发预览 ZIP](../implementation/artifacts/maibot-chatgpt-provider-v0.1.0-preview.zip) · **35,848 字节** · SHA-256 `73c9062d3a3ec050dea9f632300d612b8663ccdf3e9494fc083762270b101bc0`。22 个白名单文件；无凭据、host identity、锁文件、私钥、日志、测试或虚拟环境。完整源码与测试在 implementation，不包含在运行 ZIP 的测试树中。
- [安装/CLI](../implementation/README.md)、[Docker 操作手册](../implementation/docs/docker.md)、[第三方许可](../implementation/THIRD_PARTY_NOTICES.md)。安装根为测试实例 plugins/maibot_chatgpt_provider_plugin；包不捆绑依赖，先核对 Runner 环境。撤回时先恢复任务原模型，禁用插件，撤销新增配置；仅在最终持有端执行 logout，保留卷。

## 最终结论

- [ ] 所有要求在目标环境验收通过。
- [ ] 代码与离线/Host 测试完成，仅真实账号或部署验证待执行。
- [x] **尚有安装预检失败，不能作为可用插件发布。** 源码基线与 G1 已完成；严格 Manifest、目标 Runner 和真实 MaiBot 回复是独立门槛。

**下一步（不涉及秘密）：** 提供真实作者主页与项目仓库 URL；提供可用于隔离测试的容器名、镜像 digest 及脱敏挂载映射。先完成 G2；之后由用户本人在本地授权做 G3，无需发送密码、验证码、授权 URL 或 token。
