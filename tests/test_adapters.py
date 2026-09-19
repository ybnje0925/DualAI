import asyncio
import unittest
from playwright.async_api import async_playwright
from dualai.adapters import Adapter, SITES, SafeFailure, UnknownDelivery
from dualai.browser import find_browser

PROMPT = '오늘 서울 날씨 알려줘\nEnglish & <tag> "quotes"\n\n```python\nprint("한글")\n```\n' + "긴 질문 🧪 " * 800

def html(key, broken=False, fallback=False):
    editor = '<div id="prompt-textarea" contenteditable="true" role="textbox"></div>' if key == "chatgpt" else '<rich-textarea><div contenteditable="true" role="textbox"></div></rich-textarea>'
    button = '<button aria-label="전송">전송</button>' if fallback else ('<button data-testid="send-button">Send</button>' if key == "chatgpt" else '<button class="send-button">Send</button>')
    return f"""<!doctype html><meta charset="utf-8"><style>[contenteditable] {{ min-height:80px; border:1px solid; white-space:pre-wrap }}</style>
    <main></main>{editor}{button}<script>
    window.sent = [];
    document.querySelector('button').onclick = () => {{
      const e = document.querySelector('[contenteditable]');
      window.sent.push(e.innerText);
      if ({str(broken).lower()}) return;
      const m = document.createElement('{"div" if key == "chatgpt" else "user-query"}');
      {"m.dataset.messageAuthorRole='user';" if key == "chatgpt" else ""}
      m.textContent=e.innerText; document.querySelector('main').appendChild(m); e.innerText='';
    }};
    </script>"""

class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(executable_path=str(find_browser()), headless=True)
        self.context = await self.browser.new_context()

    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()

    async def adapter(self, key, **kw):
        page = await self.context.new_page()
        await page.route("**/*", lambda route: route.fulfill(content_type="text/html", body=html(key, **kw)))
        await page.goto(SITES[key].url)
        return Adapter(SITES[key], page)

    async def test_parallel_multiline_unicode_long_code(self):
        adapters = await asyncio.gather(self.adapter("chatgpt"), self.adapter("gemini"))
        await asyncio.gather(*(a.send_prompt(PROMPT) for a in adapters))
        for adapter in adapters:
            self.assertEqual(await adapter.page.evaluate("window.sent"), [PROMPT])

    async def test_accessible_button_fallback(self):
        adapter = await self.adapter("gemini", fallback=True)
        await adapter.send_prompt("안녕하세요")
        self.assertEqual(await adapter.page.evaluate("window.sent"), ["안녕하세요"])

    async def test_manual_draft_not_overwritten(self):
        adapter = await self.adapter("chatgpt")
        await (await adapter.editor()).fill("직접 작성 중")
        with self.assertRaises(SafeFailure):
            await adapter.send_prompt("새 질문")
        self.assertEqual(await adapter.text(await adapter.editor()), "직접 작성 중")
        self.assertEqual(await adapter.page.evaluate("window.sent"), [])

    async def test_generation_prevents_submission(self):
        adapter = await self.adapter("chatgpt")
        await adapter.page.evaluate("""() => {
          const stop=document.createElement('button');stop.dataset.testid='stop-button';document.body.appendChild(stop);
        }""")
        with self.assertRaises(SafeFailure):
            await adapter.send_prompt("새 질문")
        self.assertEqual(await adapter.page.evaluate("window.sent"), [])

    async def test_partial_failure_does_not_cancel_other(self):
        good = await self.adapter("chatgpt")
        bad = await self.adapter("gemini")
        await bad.page.locator("rich-textarea").evaluate("(e) => e.remove()")
        results = await asyncio.gather(good.send_prompt("같은 질문"), bad.send_prompt("같은 질문"), return_exceptions=True)
        self.assertIsNone(results[0])
        self.assertIsInstance(results[1], SafeFailure)

    async def test_ambiguous_submission_clicks_only_once(self):
        adapter = await self.adapter("gemini", broken=True)
        with self.assertRaises(UnknownDelivery):
            await adapter.send_prompt("한 번만 전송")
        self.assertEqual(await adapter.page.evaluate("window.sent"), ["한 번만 전송"])

    async def test_foreign_origin_rejected(self):
        adapter = await self.adapter("chatgpt")
        await adapter.page.goto("https://accounts.google.com/")
        with self.assertRaises(SafeFailure):
            await adapter.send_prompt("비공개 질문")
        self.assertEqual(await adapter.page.evaluate("window.sent"), [])

    async def test_same_prepared_draft_can_be_retried(self):
        adapter = await self.adapter("chatgpt")
        await (await adapter.editor()).fill("미전송 질문")
        await adapter.send_prompt("미전송 질문")
        self.assertEqual(await adapter.page.evaluate("window.sent"), ["미전송 질문"])

    async def test_new_conversation_navigation(self):
        adapter = await self.adapter("gemini")
        await adapter.page.goto("https://gemini.google.com/app/previous")
        await adapter.new_chat()
        self.assertEqual(adapter.page.url, SITES["gemini"].url)

if __name__ == "__main__":
    unittest.main()
