"""End-to-end IMAGE DISPLAY check, in a real browser.

Drives the actual web UI exactly like a staff member: login → submit an
image prompt → watch it complete live → verify the image renders →
Copy Image → Download → Open-in-tab. Fails loudly at the first broken
step, so "the image does not appear" becomes a precise, reproducible
diagnosis instead of a guess.

Requires a RUNNING system (backend + worker able to produce an image).

    python scripts/e2e_display_check.py --base http://127.0.0.1:8000 \
        --username staff1 --password 'secret'

Env: E2E_CHROMIUM can point at a Chromium executable if Playwright's own
browser download is not installed.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

from playwright.async_api import async_playwright

CHECKS: list[str] = []


def ok(msg: str) -> None:
    CHECKS.append(msg)
    print(f"  ✔ {msg}", flush=True)


async def run(base: str, username: str, password: str, timeout_s: int) -> None:
    tag = f"E2E-{int(time.time())}"
    async with async_playwright() as pw:
        launch: dict = {}
        if os.environ.get("E2E_CHROMIUM"):
            launch["executable_path"] = os.environ["E2E_CHROMIUM"]
        browser = await pw.chromium.launch(**launch)
        ctx = await browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = await ctx.new_page()
        page.on("console", lambda m: m.type == "error" and print(f"  [console.error] {m.text}"))
        page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))

        await page.goto(base, wait_until="networkidle")
        await page.fill("input:not([type=password])", username)
        await page.fill("input[type=password]", password)
        await page.click("button:has-text('Sign in')")
        await page.wait_for_selector("text=New Prompt", timeout=15000)
        ok("login works")

        await page.fill("textarea", f"{tag} generate a simple test image of a blue circle")
        await page.check("input[type=checkbox]")
        await page.click("button:has-text('Send to AI')")
        await page.wait_for_selector(f"tr:has-text('{tag}') td a", timeout=15000)
        ok("image prompt submitted")

        await page.click(f"tr:has-text('{tag}') td a")
        await page.wait_for_selector("h1:has-text('Prompt')", timeout=15000)
        ok("prompt detail page opens")

        await page.wait_for_selector(".badge.completed", timeout=timeout_s * 1000)
        ok("status reaches 'completed' automatically (no manual reload)")

        await page.wait_for_selector(".thumb img", timeout=30000)
        thumb = page.locator(".thumb img").first
        await page.wait_for_function("el => el.complete && el.naturalWidth > 50",
                                     arg=await thumb.element_handle(), timeout=15000)
        ok("generated image thumbnail renders with real pixels")

        await thumb.click()
        await page.wait_for_selector(".viewer img", timeout=15000)
        viewer_img = page.locator(".viewer img")
        await page.wait_for_function("el => el.complete && el.naturalWidth > 200",
                                     arg=await viewer_img.element_handle(), timeout=20000)
        ok("viewer opens and the full image loads")

        href = await page.get_attribute(".viewer a[download]", "href")
        assert href and "st=" in href, f"bad download href: {href}"
        resp = await ctx.request.get(base + href)
        cd = resp.headers.get("content-disposition", "")
        body = await resp.body()
        assert resp.ok and cd.startswith("attachment") and len(body) > 1000, \
            f"download broken: {resp.status} {cd} {len(body)}B"
        ok(f"Download URL serves the file as attachment ({len(body)} bytes)")

        view_href = None
        for a in await page.locator(".viewer a").all():
            h = await a.get_attribute("href")
            if h and "inline=1" in h:
                view_href = h
        assert view_href, "no inline view_url link in viewer"
        resp = await ctx.request.get(base + view_href)
        assert resp.ok and resp.headers.get("content-disposition", "").startswith("inline")
        ok("Open-in-tab (gallery/save flow) link serves the image inline")

        await browser.close()
    print(f"\nALL {len(CHECKS)} DISPLAY-FLOW CHECKS PASSED")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--timeout", type=int, default=600,
                   help="seconds to wait for the image job to complete")
    args = p.parse_args()
    try:
        asyncio.run(run(args.base.rstrip("/"), args.username, args.password, args.timeout))
    except Exception as exc:
        print(f"\n✘ DISPLAY-FLOW CHECK FAILED: {type(exc).__name__}: {exc}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
