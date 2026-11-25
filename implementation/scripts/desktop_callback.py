"""Desktop companion for MaiBot's remote plugin page. Python 3.9+; stdlib only.
No credentials are read or written. Only the official authorize URL opens in a browser.
"""

import base64
import getpass
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import secrets
import socket
import sys
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

PORT = 1455
HOST = f"127.0.0.1:{PORT}"
REDIRECT = "http://" + HOST + "/auth/callback"
AUTHORIZE = "https://auth.openai.com/api/accounts/authorize"


def decode_pair(value):
    if len(value) > 8192 or not value.startswith("MB1."):
        raise ValueError
    obj = json.loads(base64.b64decode(value[4:], altchars=b"-_", validate=True))
    url = obj["url"]
    u = urlsplit(url)
    q = parse_qs(u.query, keep_blank_values=True, max_num_fields=20)
    if (
        url.partition("?")[0] != AUTHORIZE
        or u.fragment
        or not url.isascii()
        or any(ord(ch) < 33 for ch in url)
    ):
        raise ValueError
    fields = {
        "client_id",
        "ext_agent_host_id",
        "response_type",
        "scope",
        "resource",
        "redirect_uri",
        "state",
        "nonce",
        "code_challenge",
        "code_challenge_method",
        "prompt",
        "agent_name_hint",
    }
    if set(q) - fields or any(len(v) != 1 for v in q.values()):
        raise ValueError
    if (
        q.get("redirect_uri") != [REDIRECT]
        or q.get("resource") != ["https://api.openai.com/v1"]
        or q.get("code_challenge_method") != ["S256"]
        or q.get("response_type") != ["code"]
    ):
        raise ValueError
    if not all(
        re.fullmatch("[A-Za-z0-9_-]{32,128}", q[k][0])
        for k in ("state", "nonce", "code_challenge")
    ):
        raise ValueError
    if not re.fullmatch("[A-Za-z0-9_-]{32}", obj["id"]) or not re.fullmatch(
        "[A-Za-z0-9_=-]{200,700}", obj["pub"]
    ):
        raise ValueError
    return obj, q["state"][0]


# The browser encrypts the callback with the Runner's per-attempt public key.
# No request to the MaiBot address, no admin password, no token exchange on the desktop.
HTML = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="referrer" content="no-referrer"><title>返回 MaiBot</title><style>body{font:17px/1.65 system-ui;margin:12vh auto;padding:0 24px;max-width:36em}button{font:inherit;padding:.5em 1em}textarea{width:100%;min-height:6em} :focus-visible{outline:3px solid #28785d}</style><main><h1>返回 MaiBot</h1><p id="msg" role="status">正在为本次登录生成加密回执…</p><button id="save" hidden>保存登录回执</button><details id="fallback" hidden><summary>无法下载？手动复制加密回执</summary><textarea readonly aria-label="加密回执"></textarea></details></main><script nonce="NONCE">(async()=>{const input=location.href;history.replaceState(null,'','/done');const p=PAIR;const enc=new TextEncoder();const b64=b=>btoa(String.fromCharCode(...new Uint8Array(b))).replaceAll('+','-').replaceAll('/','_');try{const der=Uint8Array.from(atob(p.pub.replaceAll('-','+').replaceAll('_','/')),c=>c.charCodeAt(0));const key=await crypto.subtle.importKey('spki',der,{name:'RSA-OAEP',hash:'SHA-256'},false,['encrypt']);const aes=await crypto.subtle.generateKey({name:'AES-GCM',length:256},true,['encrypt']);const iv=crypto.getRandomValues(new Uint8Array(12));const box=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:enc.encode(p.id)},aes,enc.encode(input));const wrap=await crypto.subtle.encrypt({name:'RSA-OAEP',label:enc.encode('maibot-page-v1')},key,await crypto.subtle.exportKey('raw',aes));const receipt=JSON.stringify({id:p.id,key:b64(wrap),iv:b64(iv),box:b64(box)});document.querySelector('textarea').value=receipt;const save=document.querySelector('#save');save.hidden=false;document.querySelector('#fallback').hidden=false;save.onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([receipt],{type:'application/json'}));a.download='maibot-login-receipt.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000)};document.querySelector('#msg').textContent='保存回执，回到 MaiBot 插件页选择此文件。只有页面显示「已连接」才表示完成。';}catch{document.querySelector('#msg').textContent='生成回执失败。请使用支持 Web Crypto 的现代桌面浏览器，并在 MaiBot 重新开始。'}})();</script></html>"""


def handler(pair, state):
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            ok = False
            try:
                u = urlsplit(self.path)
                q = parse_qs(u.query, keep_blank_values=True, max_num_fields=20)
                ok = (
                    len(self.path) < 12000
                    and self.headers.get("Host") == HOST
                    and not u.netloc
                    and not u.scheme
                    and u.path == "/auth/callback"
                    and len(q.get("state", [])) == 1
                    and hmac.compare_digest(q["state"][0], state)
                )
            except (ValueError, TypeError):
                pass
            if not ok:
                self.send_error(400, "Invalid callback")
                return
            nonce = secrets.token_hex(16)
            body = (
                HTML.replace("NONCE", nonce)
                .replace("PAIR", json.dumps({k: pair[k] for k in ("id", "pub")}))
                .encode()
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            self.end_headers()
            self.wfile.write(body)
            self.server.done = True

    return Callback


class Local(HTTPServer):
    allow_reuse_address = False
    done = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def get_request(self):
        sock, addr = super().get_request()
        sock.settimeout(2)
        return sock, addr

    def handle_error(self, *args):
        pass


def main():
    try:
        print("MaiBot 桌面回调 · 仅连接你本人管理的实例。不输入密码或授权码。")
        pair, state = decode_pair(
            getpass.getpass("粘贴插件页面的一次性配对串（不回显），按 Enter：").strip()
        )
        with Local(("127.0.0.1", PORT), handler(pair, state)) as server:
            server.timeout = 0.5
            if not webbrowser.open(pair["url"]):
                raise ValueError
            print("请在官方页面授权；请勿关闭本窗口。")
            deadline = time.monotonic() + 300
            while not server.done and time.monotonic() < deadline:
                server.handle_request()
            if not server.done:
                raise ValueError
        print("请在浏览器保存加密回执，并返回插件页面完成连接。")
        return 0
    except (OSError, ValueError, TypeError, KeyError, EOFError, KeyboardInterrupt):
        print(
            "未完成。请检查配对串、桌面浏览器和本机 1455 端口，然后从插件页重试。",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
