"""One independent, never unlinked OS lock. All mutations are transactions."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import errno
import json
import math
import os
import stat
import tempfile
import time
import uuid

from .errors import Error

ISSUER = "https://auth.openai.com"
DIRECT = "chatgpt.tokens.use.direct"


def stamp(seconds=None):
    return datetime.fromtimestamp(
        time.time() if seconds is None else seconds, timezone.utc
    ).isoformat()


def instant(value):
    try:
        if type(value) in (int, float) or isinstance(value, str) and value.isdecimal():
            n = float(value)
        else:
            t = datetime.fromisoformat(value)
            if t.tzinfo is None:
                return None
            n = t.timestamp()
        return n if math.isfinite(n) else None
    except (AttributeError, ValueError, TypeError, OverflowError, OSError):
        return None


def pause_clear():
    return dict(usage_paused=False, paused_at=None, reason=None, request_id=None)


def identity(d):
    return tuple(d["registration"][k] for k in ("issuer", "subject", "client_id"))


def validate(d):
    try:
        issuer, sub, client = identity(d)
        valid = (
            type(d["schema_version"]) is int
            and d["schema_version"] == 1
            and issuer == ISSUER
            and all(isinstance(k, str) and k.strip() for k in (sub, client))
            and client != "dynamic_agent_client"
            and all(
                type(d[k]) is int and d[k] >= 0
                for k in ("revision", "session_generation")
            )
            and d["state"]
            in (
                "active",
                "logged_out",
                "auth_required",
                "refresh_uncertain",
                "missing_direct_scope",
            )
            and type(d["pause"]["usage_paused"]) is bool
            and isinstance(d["tokens"], dict)
            and isinstance(d["granted_scopes"], list)
            and all(isinstance(s, str) for s in d["granted_scopes"])
        )
        if d["state"] in ("active", "missing_direct_scope"):
            valid = (
                valid
                and all(
                    isinstance(d["tokens"].get(k), str) and d["tokens"][k]
                    for k in ("access_token", "refresh_token")
                )
                and d["tokens"].get("token_type", "").lower() == "bearer"
                and instant(d["expires_at"]) is not None
            )
            valid = valid and (
                (DIRECT in d["granted_scopes"]) == (d["state"] == "active")
            )
        elif d["tokens"]:
            valid = False
    except (KeyError, ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise Error("storage_failed")
    return d


def read_json(path, *, optional=False):
    try:
        if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise Error("storage_failed")
        with path.open("rb") as f:
            raw = f.read(2**20 + 1)
        if len(raw) <= 2**20:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
    except FileNotFoundError:
        if optional:
            return None
    except (ValueError, OSError, RecursionError):
        pass
    raise Error("storage_failed")


def atomic(path, data):
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".siwc-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=True, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        tmp = None
        return
    except (OSError, ValueError, TypeError):
        pass
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    raise Error("storage_failed")


class Store:
    def __init__(self, directory, timeout=30):
        self.directory = Path(directory)
        self.timeout = timeout
        self.path = self.directory / "credentials.json"

    @contextmanager
    def lock(self):
        try:
            self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
            if os.name != "nt" and stat.S_IMODE(self.directory.stat().st_mode) & 0o077:
                raise Error("storage_failed")
            f = os.fdopen(
                os.open(
                    self.directory / "credentials.lock", os.O_RDWR | os.O_CREAT, 0o600
                ),
                "r+b",
            )
        except OSError:
            f = None
        if f is None:
            raise Error("storage_failed")
        with f:
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    busy = exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK)
                if not busy:
                    raise Error("storage_failed")
                if time.monotonic() >= deadline:
                    raise Error("storage_busy")
                time.sleep(0.025)
            yield  # closing fd releases OS lock even if worker raises

    def host_locked(self):
        path = self.directory / "host_identity.json"
        d = read_json(path, optional=True)
        if d is None:
            d = dict(
                schema_version=1, ext_agent_host_id=uuid.uuid4().urn, created_at=stamp()
            )
            atomic(path, d)
        try:
            ident = uuid.UUID(d["ext_agent_host_id"])
            ok = (
                ident.version == 4
                and ident.urn == d["ext_agent_host_id"]
                and d["schema_version"] == 1
            )
        except (KeyError, ValueError, TypeError, AttributeError):
            ok = False
        if not ok:
            raise Error("storage_failed")
        return d["ext_agent_host_id"]

    def current(self):
        d = read_json(self.path, optional=True)
        return validate(d) if d is not None else None

    def begin(self):
        with self.lock():
            h = self.host_locked()
            d = self.current()
            return h, d

    def save(self, d):
        d["revision"] += 1
        atomic(self.path, validate(d))

    def replace(self, d, expected=None):
        validate(d)
        with self.lock():
            self.host_locked()
            old = self.current()
            gen = old["session_generation"] if old else 0
            if expected is not None and gen != expected:
                raise Error("stale_attempt")
            if old and identity(old) != identity(d):
                raise Error("registration_mismatch")
            if old and old["pause"]["usage_paused"]:
                d["pause"] = old["pause"]
            if (
                expected is not None
                and old
                and old["state"] == "active"
                and d["state"] != "active"
            ):
                raise Error("permission_denied")
            d["session_generation"] = gen + 1
            d["revision"] = old["revision"] if old else 0
            self.save(d)

    def transfer(self, path):
        d = validate(read_json(Path(path)))
        if d["state"] != "active":
            raise Error("auth_required")
        self.replace(d)

    def check(self, generation):
        with self.lock():
            d = self.current()
            if not d or d["session_generation"] != generation or d["state"] != "active":
                raise Error("stale_attempt")

    def pause(self, value, generation=None, request_id=None):
        with self.lock():
            d = self.current()
            if not d:
                raise Error("auth_required")
            if generation is not None and generation != d["session_generation"]:
                raise Error("stale_attempt")
            d["pause"] = (
                dict(
                    usage_paused=True,
                    paused_at=stamp(),
                    reason="usage_limit",
                    request_id=request_id,
                )
                if value
                else pause_clear()
            )
            self.save(d)
