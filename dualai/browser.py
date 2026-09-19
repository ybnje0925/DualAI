"""Launch a normal installed browser with a persistent, isolated profile."""
import asyncio
import os
import subprocess
import time
from pathlib import Path
from playwright.async_api import async_playwright
from .adapters import SITES, Adapter

def find_browser():
    paths = [
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    for path in paths:
        if path.is_file():
            return path
    raise RuntimeError("Chrome 또는 Microsoft Edge를 설치한 후 다시 실행해 주세요.")

class BrowserHost:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.browser = self.pw = self.session = self.process = None
        self.adapters = {}
        self.window_ids = {}

    async def start(self):
        exe = find_browser()
        profile = self.data_dir / ("Chrome" if exe.name == "chrome.exe" else "Edge")
        profile.mkdir(parents=True, exist_ok=True)
        port_file = profile / "DevToolsActivePort"
        self.pw = await async_playwright().start()
        # Recover an existing dedicated browser after an app interruption.
        # Never remove a live endpoint file: Chromium will not recreate it
        # when a second launch is forwarded to the existing profile process.
        if port_file.exists():
            try:
                lines = port_file.read_text().splitlines()
                endpoint = f"ws://127.0.0.1:{int(lines[0])}{lines[1]}"
                self.browser = await self.pw.chromium.connect_over_cdp(endpoint, timeout=2000)
            except Exception:
                self.browser = None
        if self.browser is None:
            port_file.unlink(missing_ok=True)
            self.process = subprocess.Popen([
                str(exe), f"--user-data-dir={profile}", "--remote-debugging-port=0",
                "--remote-debugging-address=127.0.0.1", "--no-first-run",
                "--no-default-browser-check", "--disable-background-mode",
                "--new-window", "about:blank",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if port_file.exists():
                    try:
                        lines = port_file.read_text().splitlines()
                        if len(lines) >= 2 and lines[0].isdigit():
                            endpoint = f"ws://127.0.0.1:{lines[0]}{lines[1]}"
                            break
                    except OSError:
                        pass
                await asyncio.sleep(0.2)
            else:
                raise RuntimeError("브라우저 연결에 실패했습니다. 이전 DualAI 브라우저 창을 닫고 다시 실행해 주세요.")
            self.browser = await self.pw.chromium.connect_over_cdp(endpoint, timeout=15000)
        self.session = await self.browser.new_browser_cdp_session()
        context = self.browser.contexts[0]
        blanks = [p for p in context.pages if p.url == "about:blank"]
        first = blanks[0] if blanks else await context.new_page()
        self.adapters["chatgpt"] = Adapter(SITES["chatgpt"], first)
        await self.ensure_page("gemini")
        # Independent navigation: one unavailable service must not block the other.
        await asyncio.gather(*(self.navigate(a) for a in self.adapters.values()))
        await self.refresh_windows()

    async def navigate(self, adapter):
        try:
            await adapter.page.goto(adapter.site.url, wait_until="domcontentloaded", timeout=25000)
        except Exception:
            pass

    async def ensure_page(self, key):
        if key in self.adapters and not self.adapters[key].page.is_closed():
            return
        result = await self.session.send("Target.createTarget", {"url": "about:blank", "newWindow": True})
        target_id = result["targetId"]
        context = self.browser.contexts[0]
        for _ in range(50):
            for page in context.pages:
                session = await context.new_cdp_session(page)
                try:
                    info = await session.send("Target.getTargetInfo")
                    if info["targetInfo"]["targetId"] == target_id:
                        self.adapters[key] = Adapter(SITES[key], page)
                        return
                finally:
                    await session.detach()
            await asyncio.sleep(0.1)
        raise RuntimeError("새 브라우저 창을 연결하지 못했습니다.")

    async def reconnect(self):
        if not self.browser or not self.browser.is_connected():
            await self.close()
            await self.start()
            return
        for key in SITES:
            old = self.adapters.get(key)
            if old is None or old.page.is_closed():
                await self.ensure_page(key)
                await self.navigate(self.adapters[key])
        await self.refresh_windows()

    async def refresh_windows(self):
        self.window_ids.clear()
        for key, adapter in self.adapters.items():
            if adapter.page.is_closed():
                continue
            session = await adapter.page.context.new_cdp_session(adapter.page)
            try:
                info = await session.send("Target.getTargetInfo")
                result = await self.session.send("Browser.getWindowForTarget", {"targetId": info["targetInfo"]["targetId"]})
                self.window_ids[key] = result["windowId"]
            finally:
                await session.detach()

    async def arrange(self, rect, ratio):
        if not self.session:
            return
        x, y, width, height = rect
        left = int(width * ratio)
        for key, bx, bw in (("chatgpt", x, left), ("gemini", x + left, width - left)):
            wid = self.window_ids.get(key)
            if wid is not None:
                try:
                    await self.session.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "normal"}})
                    await self.session.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {
                        "left": bx, "top": y, "width": bw, "height": height}})
                except Exception:
                    pass

    async def close(self):
        if self.session:
            try:
                await asyncio.wait_for(self.session.send("Browser.close"), timeout=4)
            except Exception:
                pass
        if self.process:
            try:
                await asyncio.to_thread(self.process.wait, timeout=8)
            except subprocess.TimeoutExpired:
                pass
            self.process = None
        if self.pw:
            try:
                await asyncio.wait_for(self.pw.stop(), timeout=5)
            except Exception:
                pass
        self.browser = self.session = self.pw = None
        self.adapters.clear()
        self.window_ids.clear()
