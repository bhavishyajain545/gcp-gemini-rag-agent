"""One-time: open a Chrome profile for the demo and sign in to the Google Cloud console.

    python demo/login.py

Sign in in the window that opens; the script exits once the console loads.
The profile is stored in demo/_chrome-profile (git-ignored) and reused by scenes.py.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

PROFILE = Path(__file__).resolve().parent / "_chrome-profile"


async def main() -> None:
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(PROFILE), channel="chrome", headless=False, viewport={"width": 1400, "height": 900},
            ignore_default_args=["--enable-automation"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://console.cloud.google.com/firestore/databases/-default-/data/panel/tickets?project=bj-gemini-agent")
        print("Sign in to Google in the browser window... (waiting up to 10 minutes)")
        for _ in range(600):
            await asyncio.sleep(1)
            if "console.cloud.google.com" in page.url and "accounts.google.com" not in page.url:
                try:
                    await page.wait_for_selector("text=tickets", timeout=15000)
                    break
                except Exception:
                    continue
        print("signed in:", page.url)
        await asyncio.sleep(2)
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
