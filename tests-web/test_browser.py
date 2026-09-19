"""Real-browser tests on local fixtures; no prompts sent to AI services."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dualai.browser import find_browser

PROMPT = '한글 English <tag> & "quotes"\n\n```python\n    print("코드")\n```\n' + '긴 질문 🧪 ' * 800
ADAPTER = Path("extension/adapters.js").read_text(encoding="utf-8-sig")
STUB = """
window.chrome={runtime:{id:'test-extension',onMessage:{addListener(fn){window.handler=fn}}}};
window.ask=(command,payload={})=>new Promise(resolve=>handler({type:'dualai-site',command,...payload},{id:'test-extension'},resolve));
"""

def fixture(key, broken=False):
    editor = '<div id="prompt-textarea" role="textbox" contenteditable="true"></div>' if key=='chatgpt' else '<rich-textarea><div role="textbox" contenteditable="true"></div></rich-textarea>'
    button = '<button data-testid="send-button">전송</button>' if key=='chatgpt' else '<button aria-label="전송">전송</button>'
    return f"""<!doctype html><meta charset="utf-8"><style>[contenteditable]{{white-space:pre-wrap;min-height:50px}}button{{position:fixed;bottom:10px;right:10px}}</style>{editor}{button}<main></main><script>
    window.sent=[];document.querySelector('button').onclick=()=>{{
      const e=document.querySelector('[contenteditable]');sent.push(e.innerText);
      if({str(broken).lower()})return;
      const msg=document.createElement('{"div" if key=="chatgpt" else "user-query"}');
      {"msg.dataset.messageAuthorRole='user';" if key=="chatgpt" else ""}
      msg.textContent=e.innerText;document.querySelector('main').appendChild(msg);e.innerText='';
    }}
    </script>"""

async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=str(find_browser()),headless=True)
        async def page(key, broken=False):
            p=await browser.new_page()
            await p.route("**/*",lambda r:r.fulfill(body=fixture(key,broken),content_type="text/html"))
            await p.goto("https://chatgpt.com/" if key=="chatgpt" else "https://gemini.google.com/app")
            await p.evaluate("() => {" + STUB + "}")
            await p.evaluate(ADAPTER)
            return p
        chat,gem=await asyncio.gather(page("chatgpt"),page("gemini"))
        for p in [chat,gem]:
            result=await p.evaluate("prompt=>ask('send',{prompt,requestId:'same-request'})",PROMPT)
            assert result['state']=='success',result
            assert await p.evaluate("sent")==[PROMPT],"Prompt was changed"
            await p.evaluate("prompt=>ask('send',{prompt,requestId:'same-request'})",PROMPT)
            assert len(await p.evaluate("sent"))==1,"Duplicate submission"
        await chat.locator('[contenteditable]').fill('작성 중인 글')
        result=await chat.evaluate("()=>ask('send',{prompt:'new question',requestId:'new-request'})")
        assert result['state']=='failed'
        assert await chat.locator('[contenteditable]').inner_text()=='작성 중인 글'
        broken=await page("gemini",True)
        result=await broken.evaluate("()=>ask('send',{prompt:'ambiguous',requestId:'unknown-request'})")
        assert result['state']=='unknown'
        await broken.evaluate("()=>ask('send',{prompt:'ambiguous',requestId:'unknown-request'})")
        assert await broken.evaluate("sent")==['ambiguous']
        print("PASS: two site adapters, exact multiline/long/unicode/code input, fallback button, duplicate guard, draft protection, ambiguous guard")
        await browser.close()
if __name__ == "__main__":
    asyncio.run(main())
