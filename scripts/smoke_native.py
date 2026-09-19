import asyncio
import uuid
from pathlib import Path
from dualai.browser import BrowserHost

async def main():
    host = BrowserHost(Path("artifacts") / ("native-profile-" + uuid.uuid4().hex))
    try:
        await asyncio.wait_for(host.start(), 65)
        await host.arrange((0, 300, 1400, 650), 0.5)
        assert len(set(host.window_ids.values())) == 2, "two distinct browser windows required"
        for key, adapter in host.adapters.items():
            try:
                await adapter.page.locator(','.join(adapter.site.editors)).first.wait_for(state="visible", timeout=20000)
            except Exception:
                pass
            print(key, await adapter.probe(), flush=True)
            try:
                await adapter.page.screenshot(path=f"artifacts/{key}-native.png", timeout=8000, animations="disabled")
            except Exception:
                print(key, "screenshot skipped (render timeout)", flush=True)
        await host.browser.contexts[0].add_cookies([{
            "name": "dualai_test", "value": "synthetic-session",
            "url": "https://example.org", "expires": 2000000000
        }])
        print("Closing first browser", flush=True)
        await asyncio.wait_for(host.close(), 20)
        print("Restarting browser", flush=True)
        await asyncio.wait_for(host.start(), 65)
        cookies = await host.browser.contexts[0].cookies("https://example.org")
        assert any(c["name"] == "dualai_test" for c in cookies), "profile persistence"
        print("PASS: distinct native windows, CDP connection, persistent synthetic cookie after restart")
    finally:
        await asyncio.wait_for(host.close(), 20)
asyncio.run(main())
