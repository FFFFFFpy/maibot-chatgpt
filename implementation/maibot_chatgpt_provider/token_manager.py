import asyncio
import time

from .credentials import instant
from .errors import Error


class TokenManager:
    def __init__(self, store, oauth, margin=60, clock=time.time):
        self.store = store
        self.oauth = oauth
        self.margin = margin
        self.clock = clock
        self._guard = asyncio.Lock()
        self._task = None
        self.closed = False
        self.poisoned = None

    def _take(self):
        with self.store.lock():
            d = self.store.current()
            if not d or self.poisoned == d["session_generation"]:
                raise Error("auth_required")
            if d["pause"]["usage_paused"]:
                raise Error("usage_paused")
            if d["state"] == "missing_direct_scope":
                raise Error("permission_denied")
            if d["state"] != "active":
                raise Error("auth_required")
            now = self.clock()
            expiry = instant(d["expires_at"])
            raw = d.get("earliest_refresh_at")
            earliest = instant(raw)
            due = expiry - now <= self.margin
            if due and raw is not None and (earliest is None or now < earliest):
                if expiry <= now:
                    raise Error("temporarily_unavailable")
                due = False
            if due:
                try:
                    d = self.oauth.refresh(d)
                except Error as exc:
                    if exc.category in ("auth_required", "refresh_uncertain"):
                        self.poisoned = d["session_generation"]
                        d.update(tokens={}, state=exc.category)
                        self.store.save(d)
                    raise
                try:
                    self.store.save(d)
                except Error:
                    self.poisoned = d["session_generation"]
                    # Best effort: if storage has recovered, persist the no-reuse decision.
                    d.update(tokens={}, state="refresh_uncertain")
                    self.store.save(d)
                    raise
                if d["state"] != "active":
                    raise Error("permission_denied")
            return d["tokens"]["access_token"], d["session_generation"]

    async def take(self):
        async with self._guard:
            if self.closed:
                raise Error("auth_required")
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(asyncio.to_thread(self._take))
                self._task.add_done_callback(
                    lambda t: None if t.cancelled() else t.exception()
                )
            task = self._task
        return await asyncio.shield(task)

    async def close(self):
        self.closed = True
        if self._task:
            done, _ = await asyncio.wait(
                [self._task], timeout=self.store.timeout + self.oauth.timeout + 2
            )
            if not done:
                raise Error("storage_busy")

    def logout(self):
        with self.store.lock():
            self.store.host_locked()
            d = self.store.current()
            if not d:
                return True
            confirmed = False
            try:
                if d["tokens"].get("refresh_token"):
                    self.oauth.revoke(d)
                    confirmed = True
                elif d["state"] == "logged_out":
                    confirmed = True
            except Error:
                pass
            finally:
                d.update(
                    state="logged_out",
                    tokens={},
                    session_generation=d["session_generation"] + 1,
                )
                self.store.save(d)
            return confirmed
