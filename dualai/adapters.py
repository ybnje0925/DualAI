"""Site-specific UI adapters. No private endpoints or AI APIs."""
import asyncio
import re
from dataclasses import dataclass
from urllib.parse import urlparse

@dataclass(frozen=True)
class Site:
    key: str
    name: str
    url: str
    editors: tuple[str, ...]
    send: tuple[str, ...]
    stop: tuple[str, ...]
    messages: tuple[str, ...]

SITES = {
    "chatgpt": Site("chatgpt", "ChatGPT", "https://chatgpt.com/",
        ('#prompt-textarea', '[contenteditable="true"][data-placeholder]', 'textarea[placeholder]'),
        ('[data-testid="send-button"]', 'button[aria-label="Send prompt"]', 'button[aria-label="프롬프트 보내기"]'),
        ('[data-testid="stop-button"]', 'button[aria-label="Stop streaming"]'),
        ('[data-message-author-role="user"]',)),
    "gemini": Site("gemini", "Gemini", "https://gemini.google.com/app",
        ('rich-textarea [contenteditable="true"]', '[contenteditable="true"][role="textbox"]', 'textarea[aria-label]'),
        ('button.send-button', 'button[aria-label="Send message"]', 'button[aria-label="메시지 보내기"]'),
        ('button[aria-label="Stop response"]', 'button[aria-label="응답 중지"]', 'button.stop-button'),
        ('user-query', '[data-test-id="user-query"]')),
}

class SafeFailure(Exception):
    """Submission has not been attempted; manual retry is safe."""

class UnknownDelivery(Exception):
    """Submission may have happened. Never retry automatically."""

def normalized(text):
    return " ".join(text.replace("\u00a0", " ").split())

class Adapter:
    def __init__(self, site, page):
        self.site, self.page = site, page

    def correct_origin(self):
        url = urlparse(self.page.url)
        return url.scheme == "https" and url.hostname == urlparse(self.site.url).hostname

    async def visible(self, selectors):
        for selector in selectors:
            for loc in await self.page.locator(selector).all():
                if await loc.is_visible():
                    return loc
        return None

    async def editor(self):
        return await self.visible(self.site.editors)

    async def button(self):
        # Stable test IDs and named buttons first, accessible labels as fallback.
        button = await self.visible(self.site.send)
        if button:
            return button
        pattern = re.compile(r"^(send|send message|send prompt|submit|보내기|전송|메시지 보내기|프롬프트 보내기)$", re.I)
        for loc in await self.page.get_by_role("button", name=pattern).all():
            if await loc.is_visible():
                return loc
        return None

    async def text(self, editor):
        return await editor.evaluate("(el) => 'value' in el ? el.value : el.innerText")

    async def fill_prompt(self, editor, prompt):
        if await editor.evaluate("(el) => el.tagName === 'TEXTAREA' || el.tagName === 'INPUT'"):
            await editor.fill(prompt, timeout=5000)
            return
        # Chromium insertText with multiline content can add extra blank DIV lines.
        # Shift+Enter inserts a soft break without invoking the site's submit shortcut.
        lines = prompt.replace("\r\n", "\n").split("\n")
        await editor.fill(lines[0], timeout=5000)
        for line in lines[1:]:
            await editor.press("Shift+Enter", timeout=3000)
            if line:
                await self.page.keyboard.insert_text(line)

    async def busy(self):
        return await self.visible(self.site.stop) is not None

    async def probe(self):
        if self.page.is_closed():
            return "창이 닫혔습니다 · 다시 연결"
        if not self.correct_origin():
            return "로그인 또는 서비스 화면으로 이동 필요"
        if await self.busy():
            return "답변 생성 중"
        if await self.editor():
            return "입력창 준비됨"
        return "로그인 또는 화면 확인 필요"

    async def matching_messages(self, prompt):
        # Only inspect user turns for acknowledgement; never collect assistant replies.
        for selector in self.site.messages:
            nodes = self.page.locator(selector)
            if await nodes.count():
                texts = await nodes.all_inner_texts()
                return sum(normalized(prompt) == normalized(t) for t in texts)
        return 0

    async def send_prompt(self, prompt):
        if not prompt.strip():
            raise SafeFailure("질문을 입력해 주세요.")
        if self.page.is_closed() or not self.correct_origin():
            raise SafeFailure("서비스 화면을 열고 로그인을 확인해 주세요.")
        editor = await self.editor()
        if editor is None:
            raise SafeFailure("입력창을 찾지 못했습니다. 로그인과 화면을 확인해 주세요.")
        if await self.busy():
            raise SafeFailure("이전 답변이 끝난 뒤 다시 전송해 주세요.")
        existing = await self.text(editor)
        if existing.strip() and existing.replace("\r\n", "\n").rstrip("\n") != prompt.replace("\r\n", "\n").rstrip("\n"):
            raise SafeFailure("서비스 입력창에 작성 중인 글이 있습니다. 먼저 정리해 주세요.")
        before = await self.matching_messages(prompt)
        try:
            await self.fill_prompt(editor, prompt)
            if (await self.text(editor)).replace("\r\n", "\n").rstrip("\n") != prompt.replace("\r\n", "\n").rstrip("\n"):
                raise SafeFailure("질문 입력을 확인하지 못했습니다. 서비스 입력창을 확인해 주세요.")
            button = None
            for _ in range(25):
                button = await self.button()
                if button and await button.is_enabled():
                    break
                await asyncio.sleep(0.2)
            if button is None or not await button.is_enabled():
                raise SafeFailure("전송 버튼이 준비되지 않았습니다. 로그인·첨부 상태를 확인해 주세요.")
            # Trial verifies actionability without submission.
            await button.click(trial=True, timeout=3000)
        except SafeFailure:
            raise
        except Exception:
            raise SafeFailure("입력 준비에 실패했습니다. 서비스 화면을 확인한 뒤 다시 시도해 주세요.") from None
        try:
            await button.click(timeout=4000)
            for _ in range(40):
                if await self.matching_messages(prompt) > before:
                    return
                current = await self.editor()
                if current and not (await self.text(current)).strip() and await self.busy():
                    return
                await asyncio.sleep(0.25)
        except Exception:
            pass
        raise UnknownDelivery("전송 여부 확인 필요 · 서비스 화면을 확인하세요. 중복 방지를 위해 재시도를 잠갔습니다.")

    async def new_chat(self):
        if self.page.is_closed():
            raise SafeFailure("창이 닫혔습니다. 다시 연결해 주세요.")
        await self.page.goto(self.site.url, wait_until="domcontentloaded", timeout=30000)
