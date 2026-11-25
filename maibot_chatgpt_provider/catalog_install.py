"""Explicit, additive catalog writes. No Host imports, private RPCs or task edits."""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import tomllib

import tomlkit

TARGET = Path("/MaiMBot/host/model_catalog.toml")
CLIENT = "maibot.chatgpt.subscription"
BASE = "https://api.openai.com/v1"
LIMIT = 8 * 1024 * 1024
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,190}")


class CatalogError(Exception):
    """Fixed, non-sensitive strings only; the host catalog may contain unrelated keys."""


def selected_ids(values):
    if (
        not isinstance(values, list)
        or not 1 <= len(values) <= 100
        or not all(isinstance(v, str) and SLUG.fullmatch(v) for v in values)
    ):
        raise CatalogError("请从当前账号的列表中选择 1 至 100 个有效模型。")
    return list(dict.fromkeys(values))


def plain_file(path, flags, mode=0o600):
    if path.is_symlink():
        raise CatalogError("目标或锁是符号链接，未写入。")
    fd = os.open(
        path,
        flags
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_BINARY", 0),
        mode,
    )
    s = os.fstat(fd)
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
        os.close(fd)
        raise CatalogError("目标或锁不是独立的普通文件，未写入。")
    return fd


@contextmanager
def lease(folder):
    with os.fdopen(
        plain_file(folder / "model-config.lock", os.O_RDWR | os.O_CREAT), "r+b"
    ) as lock:
        try:
            if os.name == "nt":
                import msvcrt

                if os.fstat(lock.fileno()).st_size == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise CatalogError(
                "模型库正在被编辑或无法加锁，请关闭其他编辑操作后重试。"
            ) from None
        yield


def snapshot(path):
    with os.fdopen(plain_file(path, os.O_RDONLY), "rb") as stream:
        s = os.fstat(stream.fileno())
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise CatalogError("模型库超过安全读取上限，未写入。")
    return data, s


def plan(raw, ids):
    data = tomllib.loads(raw.decode("utf-8"))
    doc = tomlkit.parse(raw.decode("utf-8"))
    if data.get("inner", {}).get("version") != "3.0.0":
        raise CatalogError("不是受支持的 3.0.0 共享模型库，未写入。")
    for k in ("api_providers", "models"):
        rows = data.get(k, [])
        if (
            not isinstance(rows, list)
            or any(
                not isinstance(r, dict)
                or not isinstance(r.get("name"), str)
                or not r["name"].strip()
                for r in rows
            )
            or len({r["name"] for r in rows}) != len(rows)
        ):
            raise CatalogError("模型库记录格式不正确或已有重复名称，未写入。")
    provider = "ChatGPT"
    providers = data.get("api_providers", [])
    models = data.get("models", [])
    matches = [p for p in providers if p.get("client_type") == CLIENT]
    if len(matches) > 1:
        raise CatalogError("已有多个订阅厂商，请改用手动添加，避免写错厂商。")
    p = matches[0] if matches else None
    if p:
        provider = p["name"]
        if p.get("api_key") or str(p.get("base_url", "")).rstrip("/") != BASE:
            raise CatalogError("已有订阅厂商的地址或鉴权不兼容，未覆盖。")
    elif any(p["name"].casefold() == provider.casefold() for p in providers):
        raise CatalogError("ChatGPT 厂商名称已被其他客户端使用，未覆盖。")
    if len({slug.casefold() for slug in ids}) != len(ids):
        raise CatalogError("所选模型名称冲突，未写入。")
    additions = {
        "api_providers": []
        if p
        else [
            dict(
                name=provider,
                client_type=CLIENT,
                base_url=BASE,
                auth_type="none",
                api_key="",
                max_retry=1,
                timeout=200,
            )
        ],
        "models": [],
    }
    for slug in ids:
        if any(
            m.get("api_provider") == provider
            and m.get("model_identifier") == slug
            and m.get("model_type", "llm") == "llm"
            for m in models
        ):
            continue
        if any(m["name"].casefold() == slug.casefold() for m in models):
            raise CatalogError(
                "模型名称与已有条目冲突，本次整批未写入。请使用手动添加。"
            )
        additions["models"].append(
            dict(
                name=slug,
                model_identifier=slug,
                api_provider=provider,
                model_type="llm",
                send_temperature=False,
                visual=False,
            )
        )
    if not any(additions.values()):
        return raw, 0
    for k, rows in additions.items():
        if not rows:
            continue
        if k not in doc:
            doc[k] = tomlkit.aot()
        for row in rows:
            doc[k].append(row)
        data.setdefault(k, []).extend(rows)
    out = tomlkit.dumps(doc).encode()
    if len(out) > LIMIT or tomllib.loads(out.decode()) != data:
        raise CatalogError("未能无损追加所选记录，未写入。")
    return out, len(additions["models"])


def sync_dir(folder):
    if os.name != "nt":
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def install_at(path, values):
    ids = selected_ids(values)
    folder = path.parent
    if folder.resolve() != folder or path.is_symlink():
        raise CatalogError("目标目录不是预期的真实路径，未写入。")
    with lease(folder):
        if os.path.lexists(folder / "model-config-transaction.json"):
            raise CatalogError("宿主有未完成的配置事务，请先由 MaiBot 恢复，未写入。")
        raw, original = snapshot(path)
        try:
            out, count = plan(raw, ids)
        except CatalogError:
            raise
        except Exception:
            raise CatalogError("模型库 TOML 无法安全解析或追加，未写入。") from None
        if out == raw:
            return dict(ok=True, added=0, skipped=len(ids), backup="")
        fd, tmp = tempfile.mkstemp(prefix=".maibot-chatgpt-", dir=folder)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(out)
                f.flush()
                if os.name != "nt":
                    meta = os.fstat(f.fileno())
                    if (meta.st_uid, meta.st_gid) != (original.st_uid, original.st_gid):
                        os.fchown(f.fileno(), original.st_uid, original.st_gid)
                    os.fchmod(f.fileno(), stat.S_IMODE(original.st_mode) & 0o777)
                os.fsync(f.fileno())
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = folder / (
                "model_catalog.toml." + stamp + "-" + secrets.token_hex(6) + ".bak"
            )
            with os.fdopen(
                plain_file(backup, os.O_WRONLY | os.O_EXCL | os.O_CREAT), "wb"
            ) as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            sync_dir(folder)
            current, meta = snapshot(path)

            def identity(s):
                return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

            if current != raw or identity(original) != identity(meta):
                raise CatalogError(
                    "写入前检测到外部修改，已停止。请检查最新模型库后重试。"
                )
            os.replace(tmp, path)
            try:
                sync_dir(folder)
            except OSError:
                return dict(
                    ok=True,
                    added=count,
                    skipped=len(ids) - count,
                    backup=backup.name,
                    warning="已替换文件，但目录持久化未确认，请检查模型库及备份。",
                )
            return dict(
                ok=True, added=count, skipped=len(ids) - count, backup=backup.name
            )
        finally:
            Path(tmp).unlink(missing_ok=True)


def install(values):
    configured = os.environ.get("MAIBOT_SHARED_MODEL_CATALOG")
    if os.name != "posix" or (configured and Path(configured) != TARGET):
        raise CatalogError("宿主共享模型库位置与授权路径不同；请使用手动添加。")
    return install_at(TARGET, values)
