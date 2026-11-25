# 兼容性核对 · 2026-11-25

本机 Docker 管道 dockerDesktopLinuxEngine 不存在。目标镜像、Host/SDK/Python、真实请求、data_dir/挂载、任务路由均未取得。没有启动 Docker 或更改任何宿主。

已在临时目录 fetch 并核对 MaiBot edf42446f123149c57fc79765dd5a8b004b8524c（1.4.8）与 SDK f9984673d7e6061832e9306cf0e0daaf375f0f91（2.23.0）。request_snapshot.py 写入 context_items、item_schema_version 与 response_format；plugin_client.py 验证 output_items/schema 并补 meta，RPC 错误成为 RespParseException；runner_main.py 对错误返回 success=False、str(exc)。utils_model.py 中 max_retry=1 含首次，候选模型和显式单模型不同，非插件递归回退。plugin_paths.py 从 project_root 分配目录；插件用 ctx.paths.data_dir。加载器以带 submodule_search_locations 的 spec 执行入口，故使用包内相对导入。仅开发基线，不支持未知 schema 或 scalar 回退。

本机开发为单独的 Python 3.12.13 环境；没有升级宿主。Manifest 仅限制上述单一研究版本。真实仓库 https://github.com/FFFFFFpy/maibot-chatgpt 与作者主页已写入 Manifest；没有替换用户的 Host 或共享依赖。测试夹具均为 synthetic，不是目标抓包。

### 实际运行的源码探针

在临时实例设置 MAIBOT_INITIALIZE_ONLY=1，并仅为 import 阶段提供空模型目录。真实 ResponseRequest → serialize_response_request_snapshot → adapt；真实 PluginLLMClient._build_api_response 对合成 refusal 与 upstream usage 反序列化，再由同一 Host serializer 回放为 assistant/refusal，通过。没有启动 Host、Runner 进程或 RPC，不推断目标 G2。源码探针 tests/baseline_probe.py 仅在开发树内。SDK 工厂独立加载，唯一注册版本 0.1.0；已测试公开加载/配置/卸载回调，但不是目标 Host 发现测试。

首次预览曾缺 author.url 与 urls.repository。本次修复后固定 Host 源码的严格 schema 校验通过；非目标 Runner 发现/加载证明。

### 网络契约与运行限制

公开 discovery 仍在 auth.openai.com；资源固定 api.openai.com/v1。v0.1.1 使用同一 HTTPX 池直连官方 models 与 responses，不依赖 OpenAI Python SDK 或其私有 SSE 解码器。错误体与输入流仍有字节上限，只有合法 response.completed 才提交结果；无 SDK 自动重试，不接受环境中的 OpenAI 身份头。

截图证实旧 v0.1.0 因 openai==2.54.0 与共享环境 3.55.1 冲突被拒。v0.1.1 完全移除该依赖。HTTPX、PyJWT、cryptography 分别声明 >=0.28.1,<0.29、>=2.15.1,<3、>=50.0.2,<51；开发/冷装仍使用精确锁。对无 openai 和已装 3.55.1 两种隔离环境各运行全量离线回归（均 152 passed）。不代表全范围逐版本实测。未改变目标容器的任何包。

目标 data_dir、挂载、UID、依赖兼容性、回退次数仍未知。Unix 私有 mode 约束已编码，Windows 依实际用户 DACL；本轮双进程锁实测为 msvcrt，未实测 Linux flock/Docker volume。目标已有专用目录过宽时先设置为 0700。
