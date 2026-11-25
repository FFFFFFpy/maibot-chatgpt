# 发布、验收与交接

## 必须交付

1. `maibot-chatgpt-provider-v0.1.0.zip`：能够安装的插件，保持插件根目录结构。
2. 完整源码和可重建的开发依赖信息；构建时间、源码 revision、目标 Host/SDK/Python 范围。
3. 中文 README：从零安装、正确 data_dir、登录、导入、models/config/smoke、暂停恢复、退出、Docker。
4. `docs/compatibility-report.md`：核验目标版本及请求/响应、manifest、依赖、目录和 Host 路由依据。
5. `docs/acceptance-report.md`：基于本包模板填写的真实 G0/G1/G2/G3 结果，带命令、日期、脱敏证据。
6. `THIRD_PARTY_NOTICES.md` 或同等来源清单、实际许可证；没有复制的 DevKit 不冒称 bundled dependency。

## 清洁构建

在干净临时目录解压最终 ZIP，安装经过约束的依赖，验证 CLI --help、模块导入、manifest 校验，再通过目标 Host 的冷加载测试。不要仅测试开发工作区中额外存在的文件。

包内容排除：真实 token、identity/credential/runtime 状态、*.lock 运行锁、任何 pending refresh、用户 config、日志、真实聊天、浏览器资料、私钥、.venv、cache、.git、下载的大型源码仓库。

如果测试 JWT 需要私钥，应在测试运行时临时生成；不把有效或貌似真实的凭据提交。synthetic fixtures 用明显的非生产标识。

## 源码与许可

OpenAI DevKit 在核验提交的根许可证为非商业许可证，不能默认可按 MIT 复制和改写。依据公开协议独立实现是本包的技术路线；如果实施者改变路线引入其代码，必须记录准确来源与许可条件，不能把独立代码许可扩大到第三方材料。[DevKit LICENSE](https://github.com/openai/sign-in-with-chatgpt-devkit/blob/0a36fefeb913055c8c7a1a29b63d82b96b2e841a/LICENSE)

MaiBot SDK、HTTP/密码学库也有各自许可证，保持依赖使用和分发方式准确。任务包未替用户创建 GitHub 仓库，因此最终 manifest 的 repository URL 需要填项目真实地址；本地阶段可以采用 validator 允许的真实元数据方案并明确未发布，不能编造公开地址。

## 交接报告必须回答

| 问题 | 应给出的内容 |
| --- | --- |
| 做了什么 | 实际实现的功能及入口；P0 之外仍未实现什么 |
| 对哪个版本 | image digest、Host/SDK/Python、源码 SHA、依赖版本 |
| 测了什么 | 实际执行的命令、通过/失败/未运行的数量与用例 ID |
| 跑通到哪 | CLI、Host mock、真实 CLI、真实 MaiBot、续期、重启分别报告 |
| 还缺什么 | 明确缺哪个环境/授权/证据，用户下一步具体怎么做 |
| 怎么恢复 | 禁用、模型配置恢复、重新授权、远端撤销未确认时的路径 |

不写“理论上可用，所以已验收”。真实账号测试未完成时，产物可以交付为开发预览版，报告中写清 G3 未通过/未运行。

## 后续维护

升级 MaiBot SDK、Host 或 OpenAI SDK 时先跑相应契约测试；模型列表按账户重新获取。文档更新并不自动意味着全部账户获得新能力。每次协议漂移都记录一个新的兼容基线，禁止在未知 schema 下悄悄降级成不完整文本。
