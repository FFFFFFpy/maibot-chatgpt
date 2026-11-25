# 来源和许可边界

本插件按公开协议独立编写；预览 ZIP 不含下列项目的源码、wheel 或许可证再授权。Python 依赖由使用者另行安装，分发依赖/容器时应保留相应许可与 notices。项目作者未指定开源授权，因此本交付不替其授予 MIT 等许可。

| 项目 | 使用范围 | 版本 / wheel 元数据许可证 |
|---|---|---|
| [MaiBot Plugin SDK](https://github.com/Mai-with-u/maibot-plugin-sdk) | 公开 Plugin/Config/LLMProvider 接口 | 2.23.0 · LGPL-3.0-only |
| [HTTPX](https://github.com/encode/httpx) | 有界 HTTP/认证请求/测试 transport | 0.28.1 · BSD-3-Clause |
| [PyJWT](https://github.com/jpadilla/pyjwt) | RS256/JWKS | 2.15.1 · MIT |
| [cryptography](https://github.com/pyca/cryptography) | 签名校验及测试时生成合成密钥 | 50.0.2 · Apache-2.0 OR BSD-3-Clause |

[MaiBot](https://github.com/Mai-with-u/MaiBot/tree/edf42446f123149c57fc79765dd5a8b004b8524c) 仅作协议研究、测试端反序列化，非运行期导入。测试和开发工具未打入 ZIP。传递依赖版本见 requirements.txt；各自 LICENSE 和 NOTICE 见所安装的发行包。

[SIWC 协议](https://developers.openai.com/siwc/token-sharing-open-source/sign-in) 是授权实现依据。[OpenAI DevKit](https://github.com/openai/sign-in-with-chatgpt-devkit/tree/0a36fefeb913055c8c7a1a29b63d82b96b2e841a) 的根许可为 [SIGN-IN WITH CHATGPT DEVKIT NONCOMMERCIAL LICENSE v1.0](https://github.com/openai/sign-in-with-chatgpt-devkit/blob/0a36fefeb913055c8c7a1a29b63d82b96b2e841a/LICENSE)，不是 MIT；没有复制、逐行翻译或捆绑其实现，也未宣称官方认可。
