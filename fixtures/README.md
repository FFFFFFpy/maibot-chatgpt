# 合成测试素材说明

本目录所有内容均由任务包编写者人工构造，没有真实账户、token、用户对话或实际 API 捕获。模型 `fixture-chat-model` 是测试标识，不能用于联网推理。

| 文件 | 用途 |
| --- | --- |
| `models.example.json` | 正确解析 models/slug/display_name/visibility、保持顺序 |
| `maibot/context-items-v1.request.json` | 根据固定 Host 源码字段构造的纯文本请求，非目标容器快照 |
| `maibot/context-items-v1.response.json` | 最小 AssistantMessageItem 返回及 usage 字段 |
| `maibot/refusal-v1.response.json` | 合法拒答的最小 AssistantMessageItem（`type=refusal`）返回 |
| `responses/text_completed.sse` | 文本 delta + completed；防重复拼全文 |
| `responses/partial_failed.sse` | 有文字后订阅额度失败；必须丢弃未提交文字 |
| `responses/interrupted.sse` | 有文字但直接 EOF；不能成功 |
| `responses/incomplete.sse` | 未完成终态 |
| `responses/refusal_completed.sse` | 合法拒答完成，作为可见拒答而非网络重试 |
| `admission/usage_limit.json` | 标准 error.code 的额度失败 |
| `admission/permission_detail.json` | 只有 detail 的 admission failure |

SSE 文件是**状态机语义样例**，只包含测试关心的事件和字段，未声称覆盖官方 SDK 当前所有完整 Response 必填字段。实施时应根据锁定 SDK 创建完整 mock HTTP 响应，再用同一业务断言验证；不要为了让这些简化素材通过而放松生产 schema。

务必扩展真实 HTTP chunk 拆分、CRLF/多行 data、UTF-8、心跳、错误体、取消、超时与生成前失败的测试。SDK 解析 SSE 不意味着业务终态检查可以省略。

MaiBot 合成输入在目标 G0/G2 需由实际 Host serializer 验证。未知 Item schema 必须失败。使用已知源码形状不等于任意镜像已通过兼容测试。
