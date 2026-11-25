"""Synthetic OAuth endpoint + real local loopback callback."""

import asyncio
import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit, urlencode
import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest
from maibot_chatgpt_provider.credentials import Store, DIRECT
from maibot_chatgpt_provider.errors import Error
from maibot_chatgpt_provider.oauth import *
from .support import record, setup, CANARY

pytestmark = pytest.mark.offline


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public(key):
    return dict(
        json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())),
        kid="synthetic-kid",
    )


def sign(key, claims):
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "synthetic-kid"})


def claims(**kw):
    return dict(
        dict(
            iss=ISSUER,
            aud="synthetic-issued",
            sub="synthetic-user",
            nonce="synthetic-nonce",
            iat=int(time.time()),
            exp=int(time.time() + 300),
        ),
        **kw,
    )


class Site:
    def __init__(self, key, mode, scope=DIRECT):
        self.key = key
        self.mode = mode
        self.scope = scope
        self.exchanges = 0
        self.keys = 0
        self.seen = None

    def endpoint(self, r):
        url = str(r.url)
        if url == DISCOVERY:
            data = dict(
                issuer=ISSUER,
                jwks_uri=JWKS,
                token_endpoint=TOKEN,
                authorization_endpoint=AUTHORIZE,
                revocation_endpoint=REVOKE,
            )
        elif url == JWKS:
            data = {"keys": [public(self.key)]}
            self.keys += 1
        else:
            assert url == TOKEN
            self.exchanges += 1
            form = parse_qs(r.content.decode())
            q = self.seen
            assert (
                form["client_id"] == ["synthetic-issued"]
                and form["resource"] == [RESOURCE]
                and form["redirect_uri"] == q["redirect_uri"]
            )
            assert (
                base64.urlsafe_b64encode(
                    hashlib.sha256(form["code_verifier"][0].encode()).digest()
                )
                .decode()
                .rstrip("=")
                == q["code_challenge"][0]
            )
            data = dict(
                access_token=CANARY,
                refresh_token="synthetic-refresh",
                token_type="Bearer",
                expires_in=3600,
                scope=self.scope,
                id_token=sign(self.key, claims(nonce=q["nonce"][0])),
            )
        return httpx.Response(200, json=data)

    def open(self, url):
        assert url.startswith(AUTHORIZE + "?") and "id_token_hint" not in url
        q = self.seen = parse_qs(urlsplit(url).query)
        back = q["redirect_uri"][0]
        assert back.startswith("http://127.0.0.1:") and back.endswith("/auth/callback")
        assert q["code_challenge_method"] == ["S256"] and q["ext_agent_host_id"][
            0
        ].startswith("urn:uuid:")
        args = dict(
            state=q["state"][0], code="synthetic-code", client_id="synthetic-issued"
        )
        if self.mode == "timeout":
            return
        if self.mode == "wrong-state":
            args.update(state="bad")
        if self.mode == "denied":
            args.update(error="access_denied")
        if self.mode == "missing":
            del args["code"]
        if self.mode == "no-issued":
            del args["client_id"]
        if self.mode == "mismatch":
            args.update(client_id="different")
        target = (
            back
            + "?"
            + urlencode(args)
            + ("&code=again" if self.mode == "duplicate-param" else "")
        )
        with httpx.Client(trust_env=False) as h:
            response = h.get(target)
            if self.mode == "success":
                assert response.status_code == 200 and h.get(target).status_code == 400


@pytest.mark.parametrize("scope", [DIRECT, "openid"])
def test_QA006(tmp_path, key, scope):
    site = Site(key, "success", scope)
    s = Store(tmp_path)
    o = OAuth(httpx.MockTransport(site.endpoint))
    if scope == DIRECT:
        asyncio.run(login(s, o, site.open))
        assert (
            s.current()["state"] == "active"
            and site.seen["client_id"] == [DYNAMIC]
            and site.seen["agent_name_hint"] == [APP]
        )
        asyncio.run(login(s, o, site.open))
        assert (
            site.seen["client_id"] == ["synthetic-issued"]
            and "agent_name_hint" not in site.seen
        )
    else:
        with pytest.raises(Error, match="permission_denied"):
            asyncio.run(login(s, o, site.open))
        assert s.current()["state"] == "missing_direct_scope"
    assert s.current()["jwks"]["keys"] and site.keys == site.exchanges


@pytest.mark.parametrize(
    "mode",
    ["wrong-state", "missing", "denied", "duplicate-param", "timeout", "mismatch"],
)
def test_QA007(tmp_path, key, mode):
    site = Site(key, mode)
    s = setup(tmp_path)
    before = s.path.read_bytes()
    with pytest.raises(Error, match="invalid_login"):
        asyncio.run(
            login(
                s,
                OAuth(httpx.MockTransport(site.endpoint)),
                site.open,
                timeout=0.25 if mode == "timeout" else 3,
            )
        )
    assert s.path.read_bytes() == before and site.exchanges == 0
    with httpx.Client(trust_env=False) as h, pytest.raises(httpx.ConnectError):
        h.get(site.seen["redirect_uri"][0])


def test_QA007_cancel(tmp_path, key):
    async def run():
        site = Site(key, "timeout")
        s = setup(tmp_path)
        before = s.path.read_bytes()
        task = asyncio.create_task(
            login(s, OAuth(httpx.MockTransport(site.endpoint)), site.open)
        )
        async with asyncio.timeout(3):
            while site.seen is None:
                await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert before == s.path.read_bytes()
        with httpx.Client(trust_env=False) as h, pytest.raises(httpx.ConnectError):
            h.get(site.seen["redirect_uri"][0])

    asyncio.run(run())


@pytest.mark.parametrize(
    "case", ["sig", "iss", "aud", "exp", "iat", "nonce", "azp", "sub", "alg"]
)
def test_QA008(key, case):
    c = claims()
    signer = key
    if case == "sig":
        signer = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    elif case == "azp":
        c["aud"] = ["synthetic-issued", "other"]
    elif case == "exp":
        c[case] = time.time() - 30
    elif case == "iat":
        c[case] = time.time() + 300
    elif case == "sub":
        c[case] = ""
    else:
        c[case] = "bad"
    token = (
        jwt.encode(
            c,
            "synthetic-other-key" * 3,
            algorithm="HS256",
            headers={"kid": "synthetic-kid"},
        )
        if case == "alg"
        else sign(signer, c)
    )
    with pytest.raises(Error, match="invalid_login"):
        OAuth().verify(
            token, "synthetic-issued", {"keys": [public(key)]}, "synthetic-nonce"
        )


def test_QA008_cached_rotation(key):
    site = Site(key, "success")
    o = OAuth(httpx.MockTransport(site.endpoint))
    c = claims(aud=["synthetic-issued", "other"], azp="synthetic-issued")
    token = sign(key, c)
    _, cache = o.verify(token, "synthetic-issued", {})
    o.verify(token, "synthetic-issued", cache)
    assert site.keys == 1
    old = record()
    old["registration"]["client_id"] = "synthetic-issued"
    old["jwks"] = cache
    new = o.record(
        dict(access_token=CANARY, token_type="Bearer", expires_in=60, id_token=token),
        "synthetic-issued",
        old=old,
    )
    assert new["state"] == "active" and site.keys == 1


def test_QA009(tmp_path):
    s = Store(tmp_path)
    _, first = s.begin()
    assert first is None
    s.replace(record(), 0)
    before = s.path.read_bytes()
    with pytest.raises(Error, match="stale_attempt"):
        s.replace(record(), 0)
    assert before == s.path.read_bytes()
