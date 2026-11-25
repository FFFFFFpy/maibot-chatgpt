"""CLI and real SDK class/factory; not a target Host or RPC test."""

import asyncio
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import traceback
from types import SimpleNamespace
import httpx
import pytest
from maibot_sdk import MaiBotPlugin
from maibot_chatgpt_provider.cli import main
from maibot_chatgpt_provider.errors import Error
from maibot_chatgpt_provider.oauth import OAuth, TOKEN
from .support import setup, CANARY, engine
from .test_provider import final, sse, call, run, REQ

pytestmark = pytest.mark.offline
ROOT = Path(__file__).resolve().parents[1]


def test_QA020(tmp_path):
    slug = 'synthetic-"模型\\a'
    name = '合成\\"显示'
    data = tmp_path / "absent"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/login.py"),
            "--data-dir",
            str(data),
            "config",
            "--model",
            slug,
            "--name",
            name,
        ],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        env=dict(os.environ, PYTHONUTF8="1"),
    )
    assert proc.returncode == 0 and proc.stderr and not list(tmp_path.iterdir())
    d = tomllib.loads(proc.stdout)
    m = d["models"][0]
    p = d["api_providers"][0]
    assert (
        m["model_identifier"] == slug
        and m["name"] == name
        and p["max_retry"] == 1
        and p["timeout"] == 200
        and not p["api_key"]
    )


def load_sdk_plugin():
    name = "synthetic_runner_isolated_plugin"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "plugin.py", submodule_search_locations=[str(ROOT)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod.create_plugin()


class NoHostCalls:
    def generate(self, *a, **kw):
        raise AssertionError("cross-provider recursion")


def test_QA030_sdk(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    plugin = load_sdk_plugin()
    assert isinstance(plugin, MaiBotPlugin)
    (provider,) = plugin.get_llm_providers()
    manifest = json.loads((ROOT / "_manifest.json").read_bytes())
    assert (
        provider["client_type"] == manifest["llm_providers"][0]["client_type"]
        and provider["version"] == manifest["version"]
    )
    plugin._set_context(
        SimpleNamespace(paths=SimpleNamespace(data_dir=tmp_path), llm=NoHostCalls())
    )
    cfg = plugin.build_default_config()
    plugin.set_plugin_config(cfg)

    async def go():
        await plugin.on_load()
        with pytest.raises(Exception, match="auth_required"):
            await plugin.handle_llm("response", REQ)
        for op in ("embedding", "audio_transcription", CANARY):
            with pytest.raises(Exception, match="unsupported_input"):
                await plugin.handle_llm(op, REQ)
        await plugin.on_config_update(
            "self",
            dict(cfg, request=dict(cfg["request"], total_timeout_seconds=25)),
            "0.1.0",
        )
        assert plugin.engine.cfg.total_timeout_seconds == 25
        setup(tmp_path)
        await plugin.engine.http.aclose()
        plugin.engine.http = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: sse(final()))
        )
        assert (await plugin.handle_llm("response", REQ))["status"] == "completed"
        client = plugin.engine.http
        await plugin.on_unload()
        assert client.is_closed and plugin.engine is None

    asyncio.run(go())
    assert CANARY not in caplog.text


@pytest.mark.parametrize(
    "source", ["transport", "broken", "detail", "upstream", "oauth", "cli"]
)
def test_QA030_canary(tmp_path, capsys, caplog, source):
    caplog.set_level(logging.DEBUG)
    if source == "cli":
        setup(tmp_path)
        args = ["--data-dir", str(tmp_path)]
        assert main(args + ["status", "--json"]) == 0 and main(args + ["doctor"]) == 0
        with pytest.raises(SystemExit):
            main(args + [CANARY])
            trace = ""
        trace = ""
    else:

        def fail(_):
            if source in ("oauth", "transport"):
                raise httpx.ReadError(CANARY)
            if source == "broken":
                return sse(("data: " + CANARY + "\n\n").encode())
            return httpx.Response(
                403,
                json={
                    "detail": CANARY,
                    "error": {"code": CANARY, "param": CANARY, "message": CANARY},
                },
                headers={"x-request-id": CANARY},
            )

        with pytest.raises(Error) as info:
            if source == "oauth":
                OAuth(httpx.MockTransport(fail)).http(
                    "POST", TOKEN, form={"code": CANARY}
                )
            else:
                run(engine(tmp_path, fail))
        trace = "".join(traceback.format_exception(info.value))
        assert info.value.__context__ is None and info.value.__cause__ is None
    out, err = capsys.readouterr()
    assert CANARY not in out + err + caplog.text + trace
