import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import webbrowser
from importlib.metadata import version

from .adapter import smoke_request
from .credentials import Store, instant, stamp
from .errors import Error
from .oauth import OAuth, login
from .provider import Provider
from .token_manager import TokenManager


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "参数无效；请使用 --help。\n")  # argparse may echo secrets in argv


def parser():
    p = Parser(
        description="MaiBot 个人 SIWC 会话（不要输入 token）",
        epilog=r"Windows: python scripts/login.py --data-dir D:\private\siwc status | macOS/Linux: python scripts/login.py --data-dir ~/private/siwc status",
    )
    p.add_argument(
        "--data-dir",
        required=True,
        type=Path,
        help="Runner 的实际持久化目录，不是插件源码目录",
    )
    subs = p.add_subparsers(dest="cmd", required=True)
    for cmd in (
        "init-host",
        "login",
        "status",
        "doctor",
        "models",
        "config",
        "smoke",
        "import-credentials",
        "resume",
        "logout",
    ):
        s = subs.add_parser(cmd)
        if cmd == "login":
            s.add_argument(
                "--no-browser",
                action="store_true",
                help="在本机浏览器手工打开；不能在远端访问 loopback",
            )
        if cmd in ("models", "status"):
            s.add_argument("--json", action="store_true")
        if cmd == "doctor":
            s.add_argument("--online", action="store_true")
        if cmd in ("config", "smoke"):
            s.add_argument("--model", required=True)
        if cmd == "config":
            s.add_argument("--name", default="chatgpt-subscription-text")
        if cmd == "smoke":
            s.add_argument("--prompt", required=True)
        if cmd == "import-credentials":
            s.add_argument("--from-file", type=Path, required=True)
    return p


def quote(value):
    if not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise Error("invalid_config")
    return json.dumps(value, ensure_ascii=False)


def fragment(slug, name):
    return f"""[[api_providers]]
name = "chatgpt_subscription"
client_type = "maibot.chatgpt.subscription"
base_url = "https://api.openai.com/v1"
auth_type = "none"
api_key = ""
max_retry = 1
timeout = 200

[[models]]
model_type = "llm"
model_identifier = {quote(slug)}
name = {quote(name)}
api_provider = "chatgpt_subscription"
send_temperature = false
visual = false"""


def emit(data, machine):
    if machine:
        print(json.dumps(data, ensure_ascii=False))
        return
    if isinstance(data, list):
        for row in data:
            print(row["slug"], row["display_name"], sep="\t")
    else:
        for key, value in data.items():
            print(f"{key}: {value}")


async def execute(a):
    store = Store(a.data_dir)
    oauth = OAuth()
    m = TokenManager(store, oauth)
    cmd = a.cmd
    if cmd == "init-host":
        print(store.begin()[0])
    elif cmd == "login":

        def manual(url):
            print("仅在本机浏览器打开；勿分享：" + url, file=sys.stderr)

        await login(store, oauth, manual if a.no_browser else webbrowser.open)
        print("已连接")
    elif cmd in ("status", "doctor"):
        with store.lock():
            d = store.current()
        if cmd == "status":
            out = {"state": d["state"] if d else "not_connected"}
            if d:
                out.update(
                    account="acct-"
                    + hashlib.sha256(d["registration"]["subject"].encode()).hexdigest()[
                        :8
                    ],
                    usage_paused=d["pause"]["usage_paused"],
                    revision=d["revision"],
                    session_generation=d["session_generation"],
                )
                if instant(d.get("expires_at")) is not None:
                    out["expires_at"] = stamp(instant(d["expires_at"]))
            emit(out, a.json)
        else:
            if os.name != "nt" and stat.S_IMODE(store.directory.stat().st_mode) & 0o077:
                raise Error("storage_failed")
            out = {
                "data_dir": str(store.directory.resolve()),
                "python": sys.version.split()[0],
                **{
                    p: version(p)
                    for p in (
                        "maibot-plugin-sdk",
                        "httpx",
                        "cryptography",
                        "PyJWT",
                    )
                },
                "storage": "local lock OK",
                "permissions": "Windows: 人工核对用户 DACL"
                if os.name == "nt"
                else "private",
                "online": a.online,
            }
            if a.online:
                await asyncio.to_thread(oauth.discover)
            emit(out, False)
    elif cmd == "config":
        print(fragment(a.model, a.name))
        print("仅供人工合并，请备份原配置。", file=sys.stderr)
    elif cmd in ("models", "smoke"):
        engine = Provider(m)
        try:
            if cmd == "models":
                emit(await engine.models(), a.json)
            else:
                result = await engine.dispatch(
                    "response", smoke_request(a.model, a.prompt)
                )
                print(
                    "".join(
                        p[p["type"]]
                        for item in result["output_items"]
                        for p in item["parts"]
                    )
                )
        finally:
            await engine.close()
    elif cmd == "import-credentials":
        store.transfer(a.from_file)
        print("已导入；请清理传输副本，源端勿 revoke。")
    elif cmd == "resume":
        store.pause(False)
        print("已解除本地额度暂停；下次请求验证。")
    elif cmd == "logout":
        confirmed = await asyncio.to_thread(m.logout)
        print(
            "已清空本地会话。"
            if confirmed
            else "已清空本地会话；远端未确认，请到 ChatGPT 设置断开。"
        )
        return 0 if confirmed else 6
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return asyncio.run(execute(args))
    except Error as e:
        print(str(e), file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        return 130
    except Exception:
        print("操作失败；请用 doctor 检查本地环境。", file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
