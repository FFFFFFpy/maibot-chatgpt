"""Explicit Chromium synthetic E2E. Real sandbox, Host bridge script and loopback callback;
parent routing substitutes for authenticated Host RPC; no external account/network.
Usage: python tests/page_browser_probe.py BASELINE_HOST EDGE_EXECUTABLE
"""

import asyncio
import base64
import html
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit, urlencode
import httpx
from playwright.async_api import async_playwright
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_page_login import create


async def check(host, browser_path, tmp):
    sys.path.insert(0, str(host))
    from src.plugin_runtime.webui_schema import load_webui_extension

    extension = load_webui_extension(str(ROOT))
    (page,) = extension.pages
    assert page.id == "connection" and page.mode == "custom"
    ts = (host / "dashboard/src/lib/plugin-custom-page.ts").read_text(encoding="utf8")
    sdk = (
        ts.split("const SDK = `", 1)[1]
        .split("`", 1)[0]
        .replace("__MAIBOT_NONCE__", '"synthetic"')
    )
    srcdoc = (
        """<meta http-equiv=Content-Security-Policy content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; form-action 'none'"><script>"""
        + sdk
        + "</script>"
        + page.document
    )
    shell = (
        """<meta charset=utf-8><script>window.addEventListener('message',e=>{if(e.data.type!=='maibot:ready')return;const c=new MessageChannel();c.port1.onmessage=async ev=>{const m=ev.data;if(!m.id)return;try{const result=await window.invoke(m);c.port1.postMessage({id:m.id,result})}catch(err){c.port1.postMessage({id:m.id,error:'synthetic bridge error'})}};e.source.postMessage({type:'maibot:connect',page:{layout:'document'},context:{theme:'light',language:'zh-CN',styles:''},nonce:'synthetic'},'*',[c.port2])})</script>"""
        + '<iframe style="width:100%;height:90vh;border:0" sandbox="allow-scripts allow-forms" allow="clipboard-read &apos;none&apos;; clipboard-write &apos;none&apos;" srcdoc="'
        + html.escape(srcdoc, quote=True)
        + '"></iframe>'
    )
    site, p = create(
        tmp, rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    calls = []

    async def invoke(m):
        calls.append(m["name"])
        return await getattr(p, m["name"])(**m["args"])

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path=str(browser_path),
            headless=True,
            args=["--disable-background-networking", "--no-proxy-server"],
        )
        ctx = await browser.new_context()
        await ctx.expose_binding("invoke", lambda source, m: invoke(m))
        tab = await ctx.new_page()

        async def route(r):
            if r.request.url in (
                "http://synthetic.invalid/",
                "https://synthetic.invalid/",
            ):
                await r.fulfill(content_type="text/html; charset=utf-8", body=shell)
            elif r.request.url.startswith("http://127.0.0.1:"):
                await r.continue_()
            else:
                await r.abort()

        await ctx.route("**/*", route)
        frame = tab.frame_locator("iframe")
        await tab.goto("http://synthetic.invalid/")
        for mode in ("remote", "local"):
            await frame.locator("#start").wait_for()
            assert await frame.locator("button:visible").count() == 1
            if len(sys.argv) > 3:
                await tab.screenshot(path=str(Path(sys.argv[3]) / "offline.png"))
            await frame.locator("#start").click()
            await frame.locator("#url").wait_for()
            url = await frame.locator("#url").input_value()
            site.seen = q = parse_qs(urlsplit(url).query)
            await frame.locator("#copy").click()
            await (
                frame.locator("#copied")
                .get_by_text(re.compile("复制|已选中"))
                .wait_for()
            )
            ret = (
                q["redirect_uri"][0]
                + "?"
                + urlencode(
                    dict(
                        state=q["state"][0],
                        code="synthetic-code",
                        client_id="synthetic-issued",
                    )
                )
            )
            if mode == "remote":
                await frame.locator("#back").fill(ret)
                await frame.locator("#finish").click()
            else:
                callback = await ctx.new_page()
                await callback.goto(ret)
                await callback.close()
                await tab.bring_to_front()
            await frame.get_by_text("已连接", exact=True).wait_for()
            await frame.get_by_text("synthetic-test", exact=True).wait_for()
            await frame.get_by_role("button", name="复制模型 ID：synthetic-test").click()
            note = await frame.locator("#copyNote").inner_text()
            if "已选中" in note:
                field = frame.locator("#manualId")
                assert await field.input_value() == "synthetic-test"
                assert await field.evaluate("e=>e.selectionEnd-e.selectionStart===e.value.length")
            else:
                assert "已复制 synthetic-test" in note
            await frame.locator("#guide summary").click()
            assert "maibot.chatgpt.subscription" in await frame.locator("#guide").inner_text()
            await frame.locator("#models").click()
            for width in (400, 1024):
                await tab.set_viewport_size({"width": width, "height": 740})
                assert await frame.locator("main").evaluate(
                    "e=>e.scrollWidth<=e.clientWidth"
                )
                await tab.screenshot(
                    path=str(
                        (Path(sys.argv[3]) if len(sys.argv) > 3 else tmp)
                        / f"signed-{width}.png"
                    )
                )
            await frame.locator("#logout").click()
            await frame.locator("#start").wait_for()
        assert site.exchanges == 2
        await p.close()
        await browser.close()
    print(
        "PASS: non-loopback HTTP sandbox; copy fallback; remote paste and local automatic callback; active account, models, refresh and logout; mobile/desktop fit"
    )


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        asyncio.run(check(Path(sys.argv[1]), Path(sys.argv[2]), Path(d)))
