"""Short-lived WebUI transactions. No tokens, codes or callback URL in RPCs."""

import asyncio
import base64
import hmac
import json
import secrets
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .errors import Error, MESSAGES
from .oauth import DYNAMIC, authorize_url, callback_pair, exchange, login, pkce_material

PORT = 1455
REDIRECT = f"http://127.0.0.1:{PORT}/auth/callback"
TTL = 300


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii")


def unb64(value):
    if not isinstance(value, str):
        raise ValueError
    return base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True)


def oaep():
    return padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=b"maibot-page-v1",
    )


class PageLogin:
    def __init__(self, manager):
        self.manager = manager
        self.task = None
        self.phase = "idle"
        self.problem = ""
        self.timer = None
        self.bundle = ""
        self.attempt = ""
        self.pending = None
        self.closed = False

    def clear(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None
        self.bundle = ""
        self.pending = None

    def expire(self):
        if self.phase in ("waiting", "preparing"):
            self.clear()
            self.phase = "expired"
            if self.task and not self.task.done():
                self.task.cancel()

    async def start(self, mode):
        if self.closed or mode not in ("desktop", "local"):
            return {"ok": False}
        if self.phase in ("preparing", "waiting", "finishing"):
            return {"ok": False}
        self.clear()
        self.attempt = secrets.token_urlsafe(24)
        self.phase = "preparing"
        self.problem = ""
        self.timer = asyncio.get_running_loop().call_later(TTL, self.expire)
        self.task = asyncio.create_task(self.prepare(mode))
        return {"ok": True}

    async def prepare(self, mode):
        store = self.manager.store
        oauth = self.manager.oauth
        try:
            if mode == "local":
                loop = asyncio.get_running_loop()
                identity = self.attempt

                def publish(url):
                    def ready():
                        if self.phase == "preparing" and identity == self.attempt:
                            self.bundle = url
                            self.phase = "waiting"

                    loop.call_soon_threadsafe(ready)

                def exchanging():
                    self.clear()
                    self.phase = "finishing"

                await login(
                    store, oauth, publish, TTL, port=PORT, on_exchange=exchanging
                )
                self.phase = "complete"
                self.clear()
                return
            host, old = await asyncio.to_thread(store.begin)
            await asyncio.to_thread(oauth.discover)
            key = await asyncio.to_thread(
                rsa.generate_private_key, public_exponent=65537, key_size=2048
            )
            state, nonce, verifier, challenge = pkce_material()
            client = old["registration"]["client_id"] if old else DYNAMIC
            url = authorize_url(host, client, old, state, nonce, challenge, REDIRECT)
            pub = key.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            self.pending = (
                key,
                old["session_generation"] if old else 0,
                client,
                state,
                nonce,
                verifier,
            )
            self.bundle = "MB1." + b64(
                json.dumps(
                    {"id": self.attempt, "url": url, "pub": b64(pub)},
                    separators=(",", ":"),
                ).encode()
            )
            self.phase = "waiting"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.fail(exc)

    def fail(self, exc):
        self.clear()
        self.phase = "failed"
        self.problem = (
            MESSAGES[exc.category]
            if isinstance(exc, Error)
            else "无法开始或完成授权；请检查网络、证书或本机 1455 端口。"
        )

    async def status(self):
        data = await asyncio.to_thread(self.manager.store.current)
        return {
            "phase": self.phase,
            "problem": self.problem,
            "material": self.bundle,
            "attempt": self.attempt,
            "session": data["state"] if data else "not_connected",
        }

    async def finish(self, envelope):
        if (
            self.phase != "waiting"
            or not self.pending
            or not isinstance(envelope, str)
            or len(envelope) > 24576
        ):
            return {"ok": False}
        key, gen, client, state, nonce, verifier = self.pending
        try:
            obj = json.loads(envelope)
            if obj["id"] != self.attempt:
                raise ValueError
            aes = key.decrypt(unb64(obj["key"]), oaep())
            raw = (
                AESGCM(aes)
                .decrypt(unb64(obj["iv"]), unb64(obj["box"]), self.attempt.encode())
                .decode()
            )
            u = urlsplit(raw)
            if len(raw) > 12000 or u.fragment or raw.partition("?")[0] != REDIRECT:
                raise ValueError
            args = parse_qs(u.query, keep_blank_values=True, max_num_fields=20)
            if len(args.get("state", [])) != 1 or not hmac.compare_digest(
                args["state"][0], state
            ):
                raise ValueError
        except Exception:
            return {"ok": False}
        pair = callback_pair(args, client)
        self.clear()
        if not pair:
            self.fail(Error("invalid_login"))
            return {"ok": False}
        self.phase = "finishing"

        async def commit():
            try:
                await exchange(
                    self.manager.store,
                    self.manager.oauth,
                    gen,
                    *pair,
                    verifier,
                    REDIRECT,
                    nonce,
                )
                self.phase = "complete"
            except Exception as exc:
                self.fail(exc)

        self.task = asyncio.create_task(commit())
        return {"ok": True}

    async def cancel(self, attempt):
        if attempt != self.attempt or self.phase not in ("waiting", "preparing"):
            return {"ok": False}
        self.phase = "cancelled"
        self.clear()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        return {"ok": True}

    async def close(self):
        self.closed = True
        await self.cancel(self.attempt)
        if self.task:
            await asyncio.gather(self.task, return_exceptions=True)
        self.clear()
