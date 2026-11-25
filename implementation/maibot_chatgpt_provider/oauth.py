"""Public SIWC protocol. No SDK/browser session files and no client secret."""

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import webbrowser

import httpx
import jwt

from .credentials import DIRECT, ISSUER, pause_clear, stamp
from .errors import Error

from .oauth_constants import RESOURCE
from .wire import private_wire

DISCOVERY = ISSUER + "/.well-known/openid-configuration"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
REVOKE = ISSUER + "/api/accounts/oauth/revoke"
JWKS = ISSUER + "/.well-known/jwks.json"
APP = "MaiBot ChatGPT Subscription Provider"
DYNAMIC = "dynamic_agent_client"
SCOPES = "openid profile email offline_access resource.invoke " + DIRECT
TERMINAL = {
    "invalid_grant",
    "invalid_refresh_token",
    "token_expired",
    "refresh_token_expired",
    "refresh_token_invalidated",
    "refresh_token_reused",
}


def text(v):
    return isinstance(v, str) and bool(v.strip())


class OAuth:
    def __init__(self, transport=None, timeout=20):
        self.transport = transport
        self.timeout = timeout

    def http(self, method, url, *, form=None, deadline=None, refresh=False):
        if (method, url) not in {
            ("GET", DISCOVERY),
            ("GET", JWKS),
            ("POST", TOKEN),
            ("POST", REVOKE),
        }:
            raise Error("route_mismatch")
        deadline = deadline or time.monotonic() + self.timeout
        left = deadline - time.monotonic()
        if left <= 0:
            raise Error("transport")
        try:
            with (
                private_wire(),
                httpx.Client(
                    transport=self.transport,
                    follow_redirects=False,
                    timeout=left,
                    trust_env=False,
                ) as client,
            ):
                with client.stream(method, url, data=form) as r:
                    buf = bytearray()
                    status = r.status_code
                    for chunk in r.iter_bytes():
                        if len(buf) + len(chunk) > 2**20 or time.monotonic() > deadline:
                            raise ValueError
                        buf.extend(chunk)
            if url == REVOKE and status == 200:
                return {}
            obj = json.loads(buf)
            if not isinstance(obj, dict):
                raise ValueError
            if status == 200:
                return obj
            code = obj.get("error")
            code = code.get("code") if isinstance(code, dict) else code
            if isinstance(code, str) and code in TERMINAL and refresh:
                raise Error("auth_required")
            if code == "invalid_client":
                raise Error("invalid_client")
            category = "upstream" if not refresh else "refresh_uncertain"
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            category = "transport"
        except (httpx.HTTPError, ValueError, RecursionError):
            category = "refresh_uncertain" if refresh else "transport"
        raise Error(category)

    def discover(self):
        doc = self.http("GET", DISCOVERY)
        for key, url in [
            ("issuer", ISSUER),
            ("authorization_endpoint", AUTHORIZE),
            ("token_endpoint", TOKEN),
            ("jwks_uri", JWKS),
        ]:
            if doc.get(key) != url:
                raise Error("route_mismatch")
        return doc

    def revoke(self, d):
        if self.discover().get("revocation_endpoint") != REVOKE:
            raise Error("route_mismatch")
        form = dict(
            token=d["tokens"]["refresh_token"],
            token_type_hint="refresh_token",
            client_id=d["registration"]["client_id"],
        )
        for i in range(2):
            try:
                self.http("POST", REVOKE, form=form)
                return
            except Error as e:
                if i or e.category not in ("upstream", "transport"):
                    raise

    def verify(self, token, client, keys, nonce=None, deadline=None):
        try:
            head = jwt.get_unverified_header(token)
            kid = head["kid"]
            if not text(kid) or head.get("alg") != "RS256":
                raise ValueError

            def select(jwks):
                return [
                    k
                    for k in jwks.get("keys", [])
                    if isinstance(k, dict)
                    and k.get("kid") == kid
                    and k.get("kty") == "RSA"
                    and k.get("use", "sig") == "sig"
                    and k.get("alg", "RS256") == "RS256"
                ]

            selected = select(keys)
            if not selected:
                keys = self.http("GET", JWKS, deadline=deadline)
                selected = select(keys)
            if len(selected) != 1:
                raise ValueError
            key = jwt.PyJWK.from_dict(selected[0], algorithm="RS256").key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=ISSUER,
                audience=client,
                leeway=5,
                options={"require": ["sub", "iss", "aud", "exp", "iat"]},
            )
            if not text(claims["sub"]):
                raise ValueError
            aud = claims["aud"]
            azp = claims.get("azp")
            if (
                azp is not None or isinstance(aud, list) and len(aud) > 1
            ) and azp != client:
                raise ValueError
            if nonce is not None and not hmac.compare_digest(
                nonce, claims.get("nonce", "")
            ):
                raise ValueError
            return claims, keys
        except (
            jwt.PyJWTError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            OverflowError,
        ):
            pass
        raise Error("invalid_login")

    def record(self, obj, client, *, old=None, nonce=None, deadline=None):
        # On refresh, omitted scope and refresh_token retain their previous grants/values.
        prior = old["tokens"] if old else {}
        keys = old.get("jwks", {}) if old else {}
        access = obj.get("access_token")
        refresh = obj.get("refresh_token", prior.get("refresh_token"))
        ttl = obj.get("expires_in")
        if (
            not text(access)
            or not text(refresh)
            or str(obj.get("token_type", "")).lower() != "bearer"
            or type(ttl) is not int
            or not 0 < ttl <= 315360000
        ):
            raise Error("invalid_login")
        scopes = obj.get("scope", " ".join(old["granted_scopes"]) if old else "")
        if not isinstance(scopes, str):
            raise Error("invalid_login")
        reg = old["registration"] if old else None
        id_token = obj.get("id_token", prior.get("id_token"))
        if not old or "id_token" in obj:
            claims, keys = self.verify(id_token, client, keys, nonce, deadline)
            if reg and claims["sub"] != reg["subject"]:
                raise Error("registration_mismatch")
            reg = dict(
                issuer=ISSUER,
                subject=claims["sub"],
                client_id=client,
                display_label="acct-"
                + hashlib.sha256(claims["sub"].encode()).hexdigest()[:8],
            )
        now = time.time()
        granted = scopes.split()
        return dict(
            schema_version=1,
            registration=reg,
            revision=old["revision"] if old else 0,
            session_generation=old["session_generation"] if old else 0,
            state="active" if DIRECT in granted else "missing_direct_scope",
            tokens=dict(
                token_type="Bearer",
                access_token=access,
                refresh_token=refresh,
                id_token=id_token,
            ),
            granted_scopes=granted,
            received_at=stamp(now),
            expires_at=stamp(now + ttl),
            earliest_refresh_at=obj.get("earliest_refresh_at"),
            jwks=keys,
            pause=old["pause"] if old else pause_clear(),
        )

    def refresh(self, d):
        deadline = time.monotonic() + self.timeout
        client = d["registration"]["client_id"]
        obj = self.http(
            "POST",
            TOKEN,
            form=dict(
                grant_type="refresh_token",
                client_id=client,
                refresh_token=d["tokens"]["refresh_token"],
                resource=RESOURCE,
            ),
            deadline=deadline,
            refresh=True,
        )
        try:
            return self.record(obj, client, old=d, deadline=deadline)
        except Error:
            pass
        raise Error("refresh_uncertain")


async def login(store, oauth, opener=webbrowser.open, timeout=180):
    host, old = await asyncio.to_thread(store.begin)
    generation = old["session_generation"] if old else 0
    client = old["registration"]["client_id"] if old else DYNAMIC
    await asyncio.to_thread(oauth.discover)
    state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    loop = asyncio.get_running_loop()
    answer = loop.create_future()
    handlers = set()

    async def callback(reader, writer):
        job = asyncio.current_task()
        handlers.add(job)
        ok = False
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 4)
            method, target, _ = raw.split(b"\r\n", 1)[0].decode("ascii").split(" ")
            u = urlsplit(target)
            if (
                method != "GET"
                or u.path != "/auth/callback"
                or u.netloc
                or u.scheme
                or answer.done()
            ):
                return
            args = parse_qs(u.query, keep_blank_values=True, max_num_fields=20)
            if len(args.get("state", [])) != 1 or not hmac.compare_digest(
                args["state"][0], state
            ):
                answer.set_result(None)
                return
            issued = args.get("client_id", [None if client == DYNAMIC else client])
            codes = args.get("code", [])
            if (
                "error" in args
                or len(codes) != 1
                or not text(codes[0])
                or len(issued) != 1
                or not text(issued[0])
                or issued[0] == DYNAMIC
                or client not in (DYNAMIC, issued[0])
            ):
                answer.set_result(None)
                return
            answer.set_result((issued[0], codes[0]))
            ok = True
        except (
            ValueError,
            UnicodeError,
            TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            ConnectionError,
        ):
            pass
        finally:
            try:
                writer.write(
                    b"HTTP/1.1 "
                    + (b"200 OK" if ok else b"400 Bad Request")
                    + b"\r\nConnection: close\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\n\r\nReturn to the CLI."
                )
                await writer.drain()
            except (ConnectionError, OSError):
                pass
            finally:
                writer.close()
                handlers.discard(job)

    server = await asyncio.start_server(callback, "127.0.0.1", 0, limit=16384)
    redirect = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/auth/callback"
    params = dict(
        client_id=client,
        ext_agent_host_id=host,
        response_type="code",
        scope=SCOPES,
        resource=RESOURCE,
        redirect_uri=redirect,
        state=state,
        nonce=nonce,
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    if client == DYNAMIC:
        params["agent_name_hint"] = APP
    if old and old["state"] in (
        "missing_direct_scope",
        "auth_required",
        "refresh_uncertain",
    ):
        params["prompt"] = "consent"
    try:
        async with asyncio.timeout(timeout):
            if (
                await asyncio.to_thread(opener, AUTHORIZE + "?" + urlencode(params))
                is False
            ):
                raise Error("invalid_login")
            pair = await answer
    except TimeoutError:
        pair = None
    finally:
        server.close()
        await server.wait_closed()
        jobs = list(handlers)
        for task in jobs:
            task.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
    if not pair:
        raise Error("invalid_login")
    issued, code = pair
    obj = await asyncio.to_thread(
        oauth.http,
        "POST",
        TOKEN,
        form=dict(
            grant_type="authorization_code",
            resource=RESOURCE,
            client_id=issued,
            code=code,
            code_verifier=verifier,
            redirect_uri=redirect,
        ),
    )
    d = await asyncio.to_thread(oauth.record, obj, issued, nonce=nonce)
    await asyncio.to_thread(store.replace, d, generation)
    if d["state"] != "active":
        raise Error("permission_denied")
