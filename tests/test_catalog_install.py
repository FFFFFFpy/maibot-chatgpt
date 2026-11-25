"""Synthetic catalog only. Never invoke the production catalog writer on a host."""

import asyncio
import os
import stat
import tomllib
from types import SimpleNamespace
import pytest
from maibot_chatgpt_provider import catalog_install as ci
from maibot_chatgpt_provider.credentials import Store
from maibot_chatgpt_provider.page_login import PageLogin
from .support import record

pytestmark = pytest.mark.offline
EMPTY = b'api_providers = [] # synthetic empty providers\nmodels = []\n[inner]\nversion="3.0.0"\n'
EXISTING = b'# keep me\n[inner]\nversion="3.0.0"\n[[api_providers]]\nname="Existing"\nclient_type="openai"\napi_key="synthetic-secret"\n[[models]]\nname="existing"\nmodel_identifier="existing"\napi_provider="Existing"\n[web.services.synthetic]\nactive=true\n'


@pytest.mark.parametrize("source", [EMPTY, EXISTING, b'[inner]\nversion="3.0.0"\n'])
def test_backup_add_and_repeat(tmp_path, source):
    p = tmp_path / "model_catalog.toml"
    p.write_bytes(source)
    before = p.stat()
    r = ci.install_at(p, ["synthetic-test", "synthetic-test"])
    assert r["ok"] and r["added"] == 1
    b = tmp_path / r["backup"]
    assert b.read_bytes() == source and "synthetic-secret" not in str(r)
    if os.name != "nt":
        assert stat.S_IMODE(b.stat().st_mode) == 0o600 and stat.S_IMODE(
            p.stat().st_mode
        ) == stat.S_IMODE(before.st_mode)
    raw = p.read_bytes()
    obj = tomllib.loads(raw.decode())
    assert obj["models"][-1]["api_provider"] == "ChatGPT"
    assert obj["api_providers"][-1]["api_key"] == ""
    assert obj["models"][-1]["model_identifier"] == "synthetic-test"
    if source == EXISTING:
        assert (
            b"# keep me" in raw
            and obj["api_providers"][0]["api_key"] == "synthetic-secret"
            and obj["web"]["services"]["synthetic"]["active"]
        )
    r2 = ci.install_at(p, ["synthetic-test"])
    assert (
        r2["skipped"] == 1
        and not r2["backup"]
        and p.read_bytes() == raw
        and len(list(tmp_path.glob("*.bak"))) == 1
    )


@pytest.mark.parametrize(
    "case",
    [
        "lock",
        "journal",
        "model-conflict",
        "provider-conflict",
        "invalid",
        "version",
        "backup-io",
        "changed",
        "replace-io",
        "slug",
        "unsafe-path",
    ],
)
def test_fail_closed(tmp_path, monkeypatch, case):
    p = tmp_path / "model_catalog.toml"
    orig = EXISTING
    ids = (
        ["synthetic-test", "existing"]
        if case == "model-conflict"
        else ["synthetic-test"]
    )
    if case == "provider-conflict":
        orig = orig.replace(b'name="Existing"', b'name="ChatGPT"')
    if case == "invalid":
        orig = b"not toml"
    if case == "version":
        orig = orig.replace(b"3.0.0", b"2.0.0")
    if case == "slug":
        ids = ["bad\nname"]
    p.write_bytes(orig)
    if case == "lock":
        with ci.lease(tmp_path), pytest.raises(ci.CatalogError):
            ci.install_at(p, ids)
        assert p.read_bytes() == orig
        return
    if case == "journal":
        (tmp_path / "model-config-transaction.json").write_bytes(b"{}")
    if case == "unsafe-path":
        monkeypatch.setenv("MAIBOT_SHARED_MODEL_CATALOG", str(p))
        with pytest.raises(ci.CatalogError):
            ci.install(ids)
        return
    if case == "backup-io":
        old = ci.plain_file

        def fail(path, *args):
            if path.suffix == ".bak":
                raise PermissionError()
            return old(path, *args)

        monkeypatch.setattr(ci, "plain_file", fail)
    if case == "replace-io":

        def denied(*args):
            raise PermissionError()

        monkeypatch.setattr(ci.os, "replace", denied)
    if case == "changed":
        monkeypatch.setattr(
            ci, "sync_dir", lambda _: p.write_bytes(orig + b"# concurrent edit\n")
        )
    with pytest.raises((ci.CatalogError, OSError)):
        ci.install_at(p, ids)
    assert p.read_bytes() == (
        orig + b"# concurrent edit\n" if case == "changed" else orig
    )
    assert not list(tmp_path.glob(".maibot-chatgpt-*"))


def test_write_action_uses_current_account_list(tmp_path, monkeypatch):
    store = Store(tmp_path / "private")
    out = tmp_path / "model_catalog.toml"
    out.write_bytes(EMPTY)
    store.replace(record(), 0)
    p = PageLogin(SimpleNamespace(store=store))
    p.catalog_generation = 1
    p.catalog = [{"slug": "synthetic-test"}]
    monkeypatch.setattr(ci, "install", lambda ids: ci.install_at(out, ids))

    async def go():
        for ids, gen in [([], 1), (["other"], 1), (["synthetic-test"], 2)]:
            assert not (await p.write_catalog(ids, gen))["ok"]
        assert out.read_bytes() == EMPTY
        assert (await p.write_catalog(["synthetic-test"], 1))["added"] == 1
        store.replace(record(), 1)
        assert not (await p.write_catalog(["synthetic-test"], 1))["ok"]

    asyncio.run(go())
