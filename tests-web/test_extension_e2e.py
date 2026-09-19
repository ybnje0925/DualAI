"""Real MV3 integration with fully local service fixtures; no provider network."""
import asyncio,json,shutil,uuid,sys,threading
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from playwright.async_api import async_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dualai.browser import find_browser
from test_browser import fixture,PROMPT

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(Path("web-dist").resolve()),**kwargs)
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path.startswith("/fixture/"):
            key=self.path.split("/")[-1]
            body=fixture(key).encode()
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
        else:super().do_GET()

async def main():
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f"http://127.0.0.1:{server.server_port}"
    root=Path("artifacts")/("extension-e2e-"+uuid.uuid4().hex)
    ext=root/"extension";shutil.copytree("extension",ext)
    manifest=json.loads((ext/"manifest.json").read_text(encoding="utf-8-sig"))
    manifest["host_permissions"]=["http://127.0.0.1/*"]
    manifest["content_scripts"][0]["matches"]=[origin+"/fixture/*"]
    (ext/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
    protocol=(ext/"protocol.js").read_text(encoding="utf-8-sig").replace("https://chatgpt.com/",origin+"/fixture/chatgpt").replace("https://gemini.google.com/app",origin+"/fixture/gemini")
    (ext/"protocol.js").write_text(protocol,encoding="utf-8")
    adapter=(ext/"adapters.js").read_text(encoding="utf-8-sig").replace('location.hostname==="chatgpt.com"','location.pathname.endsWith("/chatgpt")')
    (ext/"adapters.js").write_text(adapter,encoding="utf-8")
    async with async_playwright() as pw:
        context=await pw.chromium.launch_persistent_context(str(root/"profile"),executable_path=str(find_browser()),
            headless=True,ignore_default_args=["--disable-extensions"],
            args=[f"--disable-extensions-except={ext.resolve()}",f"--load-extension={ext.resolve()}"])
        try:
            worker=context.service_workers[0] if context.service_workers else await context.wait_for_event("serviceworker",timeout=15000)
            await worker.evaluate("""async origin=>{
              await chrome.storage.local.set({siteOrigin:origin});
              await chrome.scripting.registerContentScripts([{id:'dualai-bridge',matches:[origin+'/*'],js:['bridge.js'],runAt:'document_idle'}]);
            }""",origin)
            page=await context.new_page();await page.goto(origin)
            await page.wait_for_function("!document.querySelector('#open').disabled",timeout=15000)
            await page.locator("#open").click()
            await page.wait_for_function("document.body.classList.contains('workspace')",timeout=15000)
            await page.wait_for_function("['chatgpt','gemini'].every(k=>document.querySelector('#'+k+'-status').textContent.includes('입력창 준비'))",timeout=15000)
            await page.locator("#prompt").fill(PROMPT);await page.locator("#send").click()
            await page.wait_for_function("document.querySelectorAll('.success').length===2",timeout=30000)
            managed=(await worker.evaluate("()=>chrome.storage.session.get('managed')"))["managed"]
            async def sent(key):
                return await worker.evaluate("async id=>(await chrome.scripting.executeScript({target:{tabId:id},world:'MAIN',func:()=>window.sent}))[0].result",managed[key])
            for key in managed: assert await sent(key)==[PROMPT]
            await page.locator("#send").click()
            await page.wait_for_function("document.querySelector('#notice').textContent.includes('이미 전송')")
            for key in managed: assert len(await sent(key))==1
            await worker.evaluate("id=>chrome.scripting.executeScript({target:{tabId:id},func:()=>document.querySelector('rich-textarea').remove()})",managed["gemini"])
            await page.locator("#prompt").fill("second question");await page.locator("#send").click()
            await page.wait_for_function("document.querySelector('#chatgpt-result').className==='success' && document.querySelector('#gemini-result').className==='failed'")
            assert await sent("chatgpt")==[PROMPT,"second question"]
            assert await sent("gemini")==[PROMPT]
            await page.screenshot(path="artifacts/extension-e2e.png",timeout=8000)
            await worker.evaluate("()=>chrome.storage.local.remove('siteOrigin')")
            await page.wait_for_function("document.querySelector('#connection').textContent.includes('연결 필요')",timeout=15000)
            print("PASS: real MV3 bridge -> worker -> both content adapters -> UI; duplicate skip, partial failure, origin revocation")
        finally:
            await context.close();server.shutdown()
asyncio.run(main())
