"""Explicit Chromium synthetic E2E. Real sandbox, Host bridge script and WebCrypto;
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
from urllib.parse import parse_qs,urlsplit,urlencode
import httpx
from playwright.async_api import async_playwright
from cryptography.hazmat.primitives.asymmetric import rsa
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests.test_page_login import create
from scripts.desktop_callback import decode_pair,Local,handler,PORT,REDIRECT

async def check(host,browser_path,tmp):
    sys.path.insert(0,str(host));from src.plugin_runtime.webui_schema import load_webui_extension
    extension=load_webui_extension(str(ROOT)); page,=extension.pages;assert page.id=='connection' and page.mode=='custom'
    ts=(host/'dashboard/src/lib/plugin-custom-page.ts').read_text(encoding='utf8');sdk=ts.split('const SDK = `',1)[1].split('`',1)[0].replace('__MAIBOT_NONCE__','"synthetic"')
    srcdoc="""<meta http-equiv=Content-Security-Policy content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; form-action 'none'"><script>"""+sdk+"</script>"+page.document
    shell="""<meta charset=utf-8><script>window.addEventListener('message',e=>{if(e.data.type!=='maibot:ready')return;const c=new MessageChannel();c.port1.onmessage=async ev=>{const m=ev.data;if(!m.id)return;try{const result=await window.invoke(m);c.port1.postMessage({id:m.id,result})}catch(err){c.port1.postMessage({id:m.id,error:'synthetic bridge error'})}};e.source.postMessage({type:'maibot:connect',page:{layout:'document'},context:{theme:'light',language:'zh-CN',styles:''},nonce:'synthetic'},'*',[c.port2])})</script>"""+'<iframe style="width:100%;height:90vh;border:0" sandbox="allow-scripts allow-forms" srcdoc="'+html.escape(srcdoc,quote=True)+'"></iframe>'
    site,p=create(tmp,rsa.generate_private_key(public_exponent=65537,key_size=2048));calls=[]
    async def invoke(m):
        calls.append(m['name']);return await getattr(p,m['name'])(**m['args'])
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=str(browser_path),headless=True,args=['--disable-background-networking','--no-proxy-server']);ctx=await browser.new_context();await ctx.expose_binding('invoke',lambda source,m:invoke(m));tab=await ctx.new_page()
        async def route(r):
            if r.request.url in ('http://synthetic.invalid/','https://synthetic.invalid/'):
                await r.fulfill(content_type='text/html; charset=utf-8',body=shell)
            elif r.request.url.startswith(f'http://127.0.0.1:{PORT}/'):await r.continue_()
            else:await r.abort()
        await ctx.route('**/*',route)
        frame=tab.frame_locator('iframe');await tab.goto('https://synthetic.invalid/');await frame.locator('#start').wait_for();assert not await frame.locator('#httpNotice').is_visible()
        await tab.goto('http://synthetic.invalid/');await frame.locator('#httpNotice').wait_for();await frame.locator('#start').click();await frame.locator('#material').wait_for();pair,state=decode_pair(await frame.locator('#material').input_value());site.seen=parse_qs(urlsplit(pair['url']).query)
        with Local(('127.0.0.1',PORT),handler(pair,state)) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                callback=await ctx.new_page();await callback.goto(REDIRECT+'?'+urlencode(dict(state=state,code='synthetic-code',client_id='synthetic-issued')))
                async with callback.expect_download() as download: await callback.get_by_text('保存登录回执',exact=True).click()
                dest=tmp/'synthetic-receipt.json';await (await download.value).save_as(dest);assert 'synthetic-code' not in dest.read_text();assert callback.url.endswith('/done')
            finally: server.shutdown();thread.join()
        await frame.locator('#file').set_input_files(str(dest));await frame.get_by_text('已连接',exact=True).wait_for(timeout=15000);assert site.exchanges==1 and p.manager.store.current()['state']=='active';await p.close()
        for width in (400,1024):
            await tab.set_viewport_size({'width':width,'height':720});assert await frame.locator('main').evaluate('e=>e.scrollWidth<=e.clientWidth');await tab.screenshot(path=str(tmp/f'synthetic-{width}.png'))
        await browser.close()
    print('PASS: HTTPS ready; HTTP LAN sandbox bridge -> start -> real loopback callback -> Chromium WebCrypto receipt download/upload -> verified active session; mobile/desktop fit')

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as d: asyncio.run(check(Path(sys.argv[1]),Path(sys.argv[2]),Path(d)))
