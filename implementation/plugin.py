"""Runner loads this file as a package (including submodule_search_locations)."""

from typing import Literal
from maibot_sdk import (
    CONFIG_RELOAD_SCOPE_SELF,
    Field,
    API,
    LLMProvider,
    MaiBotPlugin,
    PluginConfigBase,
)
from .maibot_chatgpt_provider.credentials import Store
from .maibot_chatgpt_provider.errors import Error
from .maibot_chatgpt_provider.oauth import OAuth
from .maibot_chatgpt_provider.page_login import PageLogin
from .maibot_chatgpt_provider.provider import Provider, Settings
from .maibot_chatgpt_provider.token_manager import TokenManager


class PluginSection(PluginConfigBase):
    enabled: bool = True
    config_version: str = "0.1.0"


class Request(PluginConfigBase):
    connect_timeout_seconds: int = Field(default=10, ge=1, le=120)
    read_idle_timeout_seconds: int = Field(default=90, ge=1, le=600)
    total_timeout_seconds: int = Field(default=180, ge=1, le=900)
    max_concurrent_requests: int = Field(default=1, ge=1, le=8)
    max_buffered_text_bytes: int = Field(default=1048576, ge=1024, le=8388608)
    pre_admission_retry_limit: int = Field(default=0, ge=0, le=1)


class Credentials(PluginConfigBase):
    lock_timeout_seconds: int = Field(default=30, ge=2, le=180)
    oauth_http_timeout_seconds: int = Field(default=20, ge=1, le=120)
    expiry_safety_margin_seconds: int = Field(default=60, ge=0, le=300)


class Recovery(PluginConfigBase):
    temporary_cooldown_seconds: int = Field(default=30, ge=1, le=300)
    pause_on_usage_limit: Literal[True] = True


class Diagnostics(PluginConfigBase):
    log_request_bodies: Literal[False] = False
    log_credentials: Literal[False] = False


class Config(PluginConfigBase):
    diagnostics: Diagnostics = Field(default_factory=Diagnostics)
    plugin: PluginSection = Field(default_factory=PluginSection)
    request: Request = Field(default_factory=Request)
    credentials: Credentials = Field(default_factory=Credentials)
    recovery: Recovery = Field(default_factory=Recovery)


class Plugin(MaiBotPlugin):
    config_model = Config
    engine = None

    def build(self, config):
        c = config.credentials
        if c.oauth_http_timeout_seconds >= c.lock_timeout_seconds:
            raise Error("invalid_config")
        manager = TokenManager(
            Store(self.ctx.paths.data_dir, c.lock_timeout_seconds, runner_owned=True),
            OAuth(timeout=c.oauth_http_timeout_seconds),
            c.expiry_safety_margin_seconds,
        )
        return Provider(
            manager,
            Settings(
                **config.request.model_dump(),
                temporary_cooldown_seconds=config.recovery.temporary_cooldown_seconds,
            ),
        )

    async def on_load(self):
        self.engine = self.build(Config.model_validate(self.get_plugin_config_data()))
        self.web_login = PageLogin(self.engine.manager, self.engine.models)

    async def on_config_update(self, scope, config_data, version):
        if scope != CONFIG_RELOAD_SCOPE_SELF or self.engine is None:
            return
        try:
            config = Config.model_validate(config_data)
        except ValueError:
            config = None
        if config is None:
            raise Error("invalid_config")
        new = self.build(config)
        old = self.engine
        await self.web_login.close()
        self.engine = new
        self.web_login = PageLogin(new.manager, new.models)
        await old.close()

    async def on_unload(self):
        old = self.engine
        self.engine = None
        if getattr(self, "web_login", None):
            await self.web_login.close()
        if old:
            await old.close()

    @API("connection_status", version="1", description="读取登录事务与会话状态")
    async def connection_status(self):
        return await self.web_login.status()

    @API("connection_start", version="1", description="开始订阅授权")
    async def connection_start(self):
        return await self.web_login.start()

    @API("connection_finish", version="1", description="验证官方登录返回地址")
    async def connection_finish(self, callback_url: str):
        return await self.web_login.finish(callback_url)

    @API("connection_models", version="1", description="刷新订阅账号可用模型")
    async def connection_models(self):
        return await self.web_login.models()

    @API(
        "connection_write_catalog",
        version="1",
        description="确认后向共享模型库备份并追加选中模型",
    )
    async def connection_write_catalog(self, model_ids: list[str], generation: int):
        return await self.web_login.write_catalog(model_ids, generation)

    @API("connection_logout", version="1", description="退出当前订阅账号")
    async def connection_logout(self):
        return await self.web_login.logout()

    @API("connection_cancel", version="1", description="取消未完成授权")
    async def connection_cancel(self, attempt: str):
        return await self.web_login.cancel(attempt)

    @LLMProvider("maibot.chatgpt.subscription", version="0.3.0")
    async def handle_llm(self, operation: str, request: dict) -> dict:
        if not self.engine:
            raise Error("temporarily_unavailable")
        return await self.engine.dispatch(operation, request)


def create_plugin():
    return Plugin()
