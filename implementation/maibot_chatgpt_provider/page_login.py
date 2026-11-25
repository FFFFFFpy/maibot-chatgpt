"""One short-lived transaction for both local and pasted loopback callbacks."""

import asyncio
import secrets
from .errors import Error, MESSAGES
from .oauth import login

TTL = 300


class PageLogin:
    def __init__(self, manager, list_models=None):
        self.manager = manager
        self.list_models = list_models
        self.task = self.timer = self.accept = None
        self.phase = "idle"
        self.problem = self.url = self.attempt = ""
        self.closed = False
        self.catalog_task = None
        self.catalog_generation = 0
        self.catalog = []
        self.catalog_error = ""

    def clear(self):
        self.accept = None
        self.url = ""
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def expire(self):
        if self.phase in ("preparing", "waiting"):
            self.phase = "expired"
            self.clear()
            self.task.cancel()

    async def start(self):
        if self.closed or self.phase in (
            "preparing",
            "waiting",
            "finishing",
            "logging_out",
        ):
            return {"ok": False}
        self.clear()
        self.attempt = secrets.token_urlsafe(24)
        self.problem = ""
        self.phase = "preparing"
        self.timer = asyncio.get_running_loop().call_later(TTL, self.expire)
        self.task = asyncio.create_task(self.prepare())
        return {"ok": True}

    async def prepare(self):
        def ready(url, accept):
            self.url, self.accept, self.phase = url, accept, "waiting"

        def consumed():
            self.clear()
            self.phase = "finishing"

        try:
            await login(
                self.manager.store,
                self.manager.oauth,
                timeout=TTL,
                page_ready=ready,
                on_exchange=consumed,
            )
            self.phase = "complete"
        except asyncio.CancelledError:
            raise
        except Error as exc:
            self.phase = "failed"
            self.problem = getattr(exc, "hint", MESSAGES[exc.category])
        except Exception:
            self.phase = "failed"
            self.problem = (
                "无法准备或完成登录。请检查插件能否监听本机回环端口，然后重试。"
            )
        finally:
            self.clear()

    async def finish(self, callback_url):
        # Do not echo or log even a malformed address. PKCE verifier never leaves the Runner.
        return {
            "ok": bool(
                self.phase == "waiting" and self.accept and self.accept(callback_url)
            )
        }

    async def status(self):
        problem = self.problem
        account = ""
        generation = 0
        try:
            data = await asyncio.to_thread(self.manager.store.current)
            session = data["state"] if data else "not_connected"
            if data and session == "active":
                account = data["registration"].get("display_label") or "ChatGPT 账号"
                generation = data["session_generation"]
        except Error as exc:
            session = "unreadable"
            problem = getattr(exc, "hint", MESSAGES[exc.category])
        return dict(
            phase=self.phase,
            problem=problem,
            authorize_url=self.url,
            attempt=self.attempt,
            session=session,
            account=account,
            generation=generation,
            models=self.catalog
            if generation and generation == self.catalog_generation
            else [],
            models_pending=bool(
                self.catalog_task
                and not self.catalog_task.done()
                and generation == self.catalog_generation
            ),
            models_problem=self.catalog_error
            if generation and generation == self.catalog_generation
            else "",
        )

    async def models(self):
        data = await asyncio.to_thread(self.manager.store.current)
        if (
            self.closed
            or self.phase == "logging_out"
            or not data
            or data["state"] != "active"
        ):
            return {"ok": False}
        if self.catalog_task and not self.catalog_task.done():
            return {"ok": True}
        gen = data["session_generation"]
        if self.catalog_generation != gen:
            self.catalog = []
        self.catalog_generation = gen
        self.catalog_error = ""

        async def fetch():
            try:
                items = await self.list_models()
                if self.catalog_generation == gen:
                    self.catalog = items
            except Exception as exc:
                if self.catalog_generation == gen:
                    self.catalog_error = (
                        MESSAGES[exc.category]
                        if isinstance(exc, Error)
                        else "暂时无法获取模型，请稍后刷新。"
                    )

        self.catalog_task = asyncio.create_task(fetch())
        return {"ok": True}

    async def logout(self):
        if self.closed or self.phase in (
            "finishing",
            "logging_out",
            "preparing",
            "waiting",
        ):
            return {"ok": False}
        self.phase = "logging_out"
        self.problem = ""
        self.catalog_generation = 0
        self.catalog = []
        self.catalog_error = ""
        if self.catalog_task:
            self.catalog_task.cancel()

        async def leave():
            try:
                confirmed = await asyncio.to_thread(self.manager.logout)
                self.phase = "idle"
                if not confirmed:
                    self.problem = "已在此实例退出。未能确认官方撤销授权。"
            except Exception:
                self.phase = "failed"
                self.problem = "未能确认退出，请检查存储后重试。"

        self.task = asyncio.create_task(leave())
        return {"ok": True}

    async def cancel(self, attempt):
        if self.phase not in ("waiting", "preparing") or attempt != self.attempt:
            return {"ok": False}
        self.phase = "cancelled"
        self.clear()
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        return {"ok": True}

    async def close(self):
        self.closed = True
        await self.cancel(self.attempt)
        if self.catalog_task:
            self.catalog_task.cancel()
            await asyncio.gather(self.catalog_task, return_exceptions=True)
        if self.task:
            await asyncio.gather(self.task, return_exceptions=True)
        self.clear()
