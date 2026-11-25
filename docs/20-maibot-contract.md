# MaiBot 接入契约与版本核验

核验日期：2026-11-25。此文是开发约束和静态源码核验记录，不代表已经在用户容器完成集成。

## 1. 三类证据必须分开

| 类别 | 本包掌握的证据 | 可以得出的结论 |
| --- | --- | --- |
| 官方文档 | 插件指南、LLMProvider、Manifest、模型配置文档 | SDK 的公开使用方式和设计边界 |
| 固定源码快照 | MaiBot `edf42446f123149c57fc79765dd5a8b004b8524c`；SDK `f9984673d7e6061832e9306cf0e0daaf375f0f91` | 该快照实际序列化、异常封装、模型调度行为 |
| 用户目标环境 | 尚未取得镜像 digest、运行版本和实际请求 | 安装兼容性、登录和真实推理仍待实施验证 |

源码基线的 MaiBot 版本为 `1.4.8`，Python 要求 `>=3.12`，Host 依赖 `maibot-plugin-sdk>=2.23.0`；SDK 快照版本为 `2.23.0`。这些数值是研究基线，不构成自动升级用户环境的授权，也不是插件已经支持的版本声明。

实施时先记录目标容器的镜像 digest、Host/SDK/Python 版本、Bot 根目录和当前请求协议。文档示例版本不能直接照抄进最终 Manifest。不得开启“强制兼容”来掩盖协议不匹配。

来源：[Host pyproject](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/pyproject.toml)、[SDK pyproject](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/f9984673d7e6061832e9306cf0e0daaf375f0f91/pyproject.toml)。

## 2. 插件入口与注册

安装包使用 `maibot-plugin-sdk`，Python 导入使用 `maibot_sdk`。

```python
# 接口签名示意；不是已经实现的插件。
from maibot_sdk import MaiBotPlugin, LLMProvider, LLMProviderBase

# MaiBotPlugin 生命周期：
# async def on_load(self) -> None
# async def on_unload(self) -> None
# async def on_config_update(self, scope: str, config_data: dict, version: str) -> None

# @LLMProvider("maibot.chatgpt.subscription")
# async def handle_llm(self, operation: str, request: dict) -> dict

# 可选：LLMProviderBase 子类实现 get_response(self, request)。
# handle_llm 内调用 await provider.dispatch(operation, request)。
# 入口：def create_plugin(): return 实际插件实例
```

实现要求：

- `_manifest.json` 顶层 `llm_providers` 与代码装饰器的 `client_type` 必须一致，使用 `maibot.chatgpt.subscription`。
- P0 只实现 `response`；收到 embedding、audio_transcription 或未知 operation 时明确抛出不支持错误。
- Manifest 中不要自行增加 `handler_name`、`metadata` 等字段。遵守目标版严格校验器。
- 正常 Provider 不需要反向调用 Host；保持 `capabilities: []`。若另做测试调用器，其能力声明单独处理。
- `on_load` 初始化路径、客户端和配置，不自动弹浏览器，也不把“尚未登录”变成整个 Runner 崩溃。模型请求遇到未登录状态时给可操作的脱敏错误。
- `on_unload` 释放 HTTP 客户端和后台任务，等待或正确取消仍在进行的工作；不要随卸载删除授权文件。
- `on_config_update` 只应用本插件允许热更新的设置，不修改宿主模型目录。
- 最终 Manifest 必填字段、作者信息、仓库 URL、版本范围和依赖均需通过真实 Host 校验。不能把虚构仓库地址当成发布信息。

来源：[LLMProvider 文档](https://docs.maibot.chat/develop/plugin/llmprovider)、[SDK 基类](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/f9984673d7e6061832e9306cf0e0daaf375f0f91/maibot_sdk/llm_provider.py)、[生命周期与入口](https://docs.maibot.chat/develop/plugin/)。

## 3. 依赖必须同时考虑 Runner 的共享环境

Manifest 的 Python 依赖结构为 `type="python_package"`、`name`、`version_spec`。Host 会统一检查与宿主及其他插件的约束冲突；不要只写 requirements.txt 后假定插件自动具备依赖。

开发环境锁定用于复现；发布 Manifest 的兼容范围应与测试结果一致。SDK 兼容范围写入 `sdk` 字段。若采用 `PyJWT[crypto]`，Manifest 不能直接把带方括号的 extras 当包名，应分别声明 `PyJWT` 与 `cryptography` 并验证依赖安装。

运行时不导入 Host 的 `src.*`。Host 源码只供兼容性研究和集成测试使用。插件私有模块采用相对导入或唯一命名的包，验证 Runner 动态加载和 CLI 直接执行两种入口，避免 `auth`、`provider` 等顶级包名冲突。

来源：[Manifest 与依赖](https://docs.maibot.chat/develop/plugin/manifest)、[目标版插件加载器](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/plugin_runtime/runner/plugin_loader.py)。

## 4. 请求协议：当前源码使用 context_items

**不能把 `message_list` 写成唯一支持的输入。** 官方页面仍以该字段描述请求，但核验源码已经改成 `context_items`。G0 需要以目标 Host 实际序列化结果决定适配器；不凭字段名称猜测旧协议。

当前源码的 `CONTEXT_ITEM_SCHEMA_VERSION = 1`。插件必须显式支持经过测试的版本；收到未知版本时在发网络请求前拒绝。不能将未知版本简单回显到输出并假装兼容。

以下是依据源码构造的合成示例，**不是用户容器的捕获数据**：

```json
{
  "item_schema_version": 1,
  "context_items": [
    {
      "item_type": "SystemMessageItem",
      "meta": {
        "item_id": "s1",
        "logical_turn_id": null,
        "timestamp": "2026-11-25T00:00:00"
      },
      "parts": [{"type": "text", "text": "你是一个中文助手。"}]
    },
    {
      "item_type": "UserMessageItem",
      "meta": {
        "item_id": "u1",
        "logical_turn_id": null,
        "timestamp": "2026-11-25T00:00:00"
      },
      "parts": [{"type": "text", "text": "请回复一句你好。"}]
    }
  ],
  "logical_turn_id": "turn-example",
  "model_info": {
    "model_type": "llm",
    "model_identifier": "REPLACE_WITH_AUTHORIZED_MODEL_SLUG",
    "name": "chatgpt-subscription-text",
    "api_provider": "chatgpt_subscription"
  },
  "api_provider": {
    "name": "chatgpt_subscription",
    "client_type": "maibot.chatgpt.subscription",
    "base_url": "https://api.openai.com/v1",
    "auth_type": "none",
    "api_key": "",
    "timeout": 120,
    "max_retry": 1
  },
  "request_kind": "response",
  "extra_params": {},
  "max_tokens": null,
  "temperature": null,
  "response_format": null,
  "tool_options": [],
  "tool_choice": null
}
```

实际 `model_info` 还包含媒体、温度、流式和 extra_params 等配置。仅提取适配必需字段，不透传整个请求。元数据中的 Host item ID、时间和 logical_turn_id 也不应无目的地发送给 OpenAI。

P0 输入处理表：

| Host 类型 | P0 处理 |
| --- | --- |
| SystemMessageItem + 文字 parts | 按 OpenAI 接口约定转换指令，保留权限层级和顺序 |
| UserMessageItem + 文字 parts | 转成用户文本 |
| AssistantMessageItem + 文字 parts | 转成助手历史文本 |
| 图片、音频、工具调用、工具结果 | 网络调用前明确拒绝，不能丢弃后继续 |
| ReasoningItem、ProviderOpaqueItem、ProviderActivityItem | 未实现的形态明确拒绝，不混为用户文本 |
| 助手历史的拒答 part | P0 接受 type=refusal/refusal，作为助手可见文本按序映射；验证拒答后下一轮往返 |
| 未知 item_type、part.type、schema 版本 | 协议错误，输出升级/兼容提示 |

若目标版需要旧协议，单独实现并测试 `legacy` 分支；先拿到真实字段形状，不把 message_list 默认视为标准 Chat Completions messages。目标版不需要的旧协议不为扩大支持范围而增加。

来源：[请求序列化](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/llm_models/request_snapshot.py)、[Item 定义](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/llm_models/payload_content/context_item.py)、[Item 序列化](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/llm_models/payload_content/context_snapshot.py)。

## 5. 最小文本返回：按目标版验证 output_items

对当前源码基线，推荐以下最小结构：

```json
{
  "item_schema_version": 1,
  "output_items": [
    {
      "item_type": "AssistantMessageItem",
      "parts": [{"type": "text", "text": "你好！"}]
    }
  ],
  "response_id": "resp_example",
  "status": "completed",
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 4,
    "total_tokens": 16
  }
}
```

数值和 response_id 只是合成示例；实现中只使用上游真实数据。usage 缺失时省略，不造计数。上游 input_tokens/output_tokens 转为 prompt_tokens/completion_tokens，total_tokens 只按上游实际提供值返回，不自行派生。缓存统计仅映射有证据的字段。

正常模型拒答是成功完成的一种内容。schema 1 输出为 AssistantMessageItem，其 parts 使用 `{ "type": "refusal", "refusal": "拒答文字" }`；Host 把该字段纳入可见正文。输入端也接受后续助手历史中的相同片段，防止第一轮合法拒答导致第二轮协议错误。旧标量兼容分支可投影为文字，但必须单独测试。

该基线的 Host 会为每个 output_item 生成 meta，并绑定当前 logical_turn_id，所以最小输出不需要自造 meta。随后 Host 校验 schema、反序列化和 MODEL_OUTPUT 关系。

`content` 单字段目前仍有兼容分支，但源码明确说明下一个 Item schema 将移除该分支。前期讨论中“P0 永远只回 content”的决定由此次源码证据修正：**使用目标版本已经验证的返回协议**。对支持 schema 1 的目标版，实现最小 AssistantMessageItem；对旧版仅在证实兼容时采用 content 返回。

Provider 内部消费 SSE；Host 不接受插件自定义的 stream_response_handler 或 async_response_parser。只有上游 `response.completed` 确认成功、且最终输出符合 P0 能力范围后，才构造成功字典。不要把部分文本、错误提示或未支持的工具输出包装成成功。

来源：[Host PluginLLMClient](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/llm_models/model_client/plugin_client.py)。

## 6. 异常传递与 Host 回退

在研究基线中，失败链路为：

1. 插件抛异常；Runner 捕获后将 `str(exc)` 放入 `InvokeResultPayload(success=False, result=...)`。
2. PluginLLMClient 将该失败及 RPC 错误统一转换为 Host 的 `RespParseException`。
3. Host 的 LLMOrchestrator 按该 provider 的尝试次数处理；耗尽后变成 `ModelAttemptFailed`。
4. 任务调用从本次未失败的候选模型中再选择；显式指定 `model_name` 的调用仅尝试该模型。

由此落实以下要求：

- 插件自定义异常用于内部分类和稳定错误码，不能期待其 Python 类型跨 RPC 保留。
- 不导入 Host 异常，不伪造 HTTP 429 为某个所谓 SDK 官方异常。
- 失败必须抛出异常，不能返回普通 `{"success": false}` 字典期待 Runner 自动视为失败，也不能把错误塞入成功文本。
- 错误字符串包含稳定插件错误码、可操作的中文提示和安全的 request ID；不包含 Token、授权码、凭据文件内容或原始敏感请求。
- Runner 会记录异常堆栈，所以对底层 SDK/HTTP 异常的链式传播也要去敏；仅给最外层字符串打码不足。
- 额度耗尽等错误在插件内打开冷却/暂停状态，后续调用快速报错；不调用其它 provider，不使用 `ctx.llm.generate()` 递归回退。
- 当前 Host 有模型回退路径，但实际触发仍需用目标镜像、任务候选列表和调用方式验证。不得把源码推断标成已完成端到端测试。

`api_provider.max_retry` 的实际语义为 **包含首次请求的总尝试次数**；0 或 1 都没有额外重试。P0 片段采用 1，防止 Host、OpenAI SDK 和插件三层重试相乘。需要优先模型时，仅在目标版本证实支持后由用户设置任务的 sequential 策略；单模型任务没有可回退候选。

来源：[Runner 调用器](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/plugin_runtime/runner/runner_main.py)、[Host 调度器](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/llm_models/utils_model.py)、[Provider 配置定义](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/config/model_configs.py)。

## 7. ctx.paths 与 CLI 共用目录

`ctx.paths.data_dir` 和 `ctx.paths.runtime_dir` 都是 Path。Runner 根据当前 Bot 的 project_root 分配持久化和临时目录；多实例下 Bot 根目录不一定是 `/MaiMBot`。

| 使用者 | 路径来源 |
| --- | --- |
| 插件运行时 | Host 注入的 `self.ctx.paths.data_dir` |
| 独立 CLI | 用户明确传入的 `--data-dir`，必须等于插件的实际持久化目录 |
| 临时非凭据产物 | `self.ctx.paths.runtime_dir` |

CLI 不能凭空访问 PluginContext，也不能在导入时创建自己的随机 data_dir。记录实际目录，验证写权限、Owner、容器内外路径映射；凭据模块的锁和写入算法供两者共用。不要把持久凭据放 plugins 源码目录、临时目录或镜像层。

来源：[SDK PluginPaths](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/f9984673d7e6061832e9306cf0e0daaf375f0f91/maibot_sdk/context.py)、[Host 路径分配](https://github.com/Mai-with-u/MaiBot/blob/edf42446f123149c57fc79765dd5a8b004b8524c/src/plugin_runtime/runner/plugin_paths.py)。

## 8. 模型目录写入边界

公开 SDK 的 `ctx.llm` 提供调用和列表读取，`ctx.config` 提供读取。此次核验未发现公开的模型目录写 API，因此 P0 仅输出配置片段并给人工应用步骤，不自行写入 host/model_catalog.toml，也不调用未公开 WebUI 接口。

当前布局中供应商和模型定义位于工作区 `host/model_catalog.toml`，各 Bot 的 `config/model_config.toml` 保存任务分配。示例见 [model_catalog.fragment.toml](../examples/model_catalog.fragment.toml)。该文件是片段，不包含完整宿主配置，不应覆盖现有文件。不要重写现有 `[inner].version`。

`ctx.llm.get_available_models()` 在 SDK 源码中返回宿主可见模型任务名列表，它不等于 OpenAI 账号的可用模型目录。OpenAI 模型发现须使用授权后的官方目录接口；配置中 model_identifier 用实际 slug。

Docker 集成必须确认 host/ 和 Bot 对应 data/plugins 路径持久化。用户原有 Compose、证书设置、NapCat 等服务保持由部署流程管理；安装插件不构成覆盖 Compose 或删除数据的理由。

来源：[SDK LLM 能力](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/f9984673d7e6061832e9306cf0e0daaf375f0f91/maibot_sdk/capabilities/llm.py)、[API 参考](https://docs.maibot.chat/develop/plugin/api-reference)、[模型配置](https://docs.maibot.chat/manual/configuration/model-config)、[多实例](https://docs.maibot.chat/manual/multi-bot-host)、[部署](https://docs.maibot.chat/faq/deployment)。

## 9. 集成验收证据

实施者应提交以下记录，内容中不得含真实聊天正文或凭据：

1. 目标 Host/SDK/Python/镜像 digest 及选用协议版本。
2. Manifest 验证成功、Provider 注册成功的脱敏记录。
3. 根据目标 Host 序列化器生成的纯文本合成输入，以及 Host 对最小输出成功反序列化的测试结果。
4. 未知 schema、非文本输入、缺失模型标识在网络前失败的测试。
5. 人工授权后的 CLI 纯文本推理记录。
6. MaiBot 通过该 client_type 完成纯文本调用，实际模型归属没有被备用模型掩盖。
7. 额度异常模拟如何穿过 RPC，Host 最终如何处理；有候选和无候选两种情况分别验证。
8. 容器重启后使用原持久化凭据成功；若未能执行，明确列为未完成验收。

第一条真实回复仅作为最小链路通过的证据，不代表工具、视觉、所有任务与所有 MaiBot 版本兼容。
