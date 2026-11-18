"""HTML → PDF / PNG with headless Chromium (Playwright).

Chromium shapes Arabic and lays out right-to-left text properly, and the exported file is the same page the user
previewed. The page is offline: the context has no network, every request is aborted, and the page's own CSP allows
only inline styles and data: fonts/images. One-off install: ``python -m playwright install --only-shell chromium``.
"""

from __future__ import annotations

import asyncio
import sys
import threading

from app.core.errors import ExternalServiceUnavailable

_slots = threading.BoundedSemaphore(2)  # at most two renders at once


class RendererUnavailable(ExternalServiceUnavailable):
    code = "renderer_unavailable"
    message = "The document renderer isn't installed on the server. Run: python -m playwright install --only-shell chromium"


async def _render(html: str, *, pdf: bool, width: int, height: int) -> bytes:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                ctx = await browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1, offline=True)
                await ctx.route("**/*", lambda route: route.continue_() if route.request.url.startswith("data:") else route.abort())
                page = await ctx.new_page()
                await page.set_content(html, wait_until="load")
                await page.evaluate("document.fonts.ready.then(() => true)")
                if pdf:
                    return await page.pdf(prefer_css_page_size=True, print_background=True)
                return await page.screenshot(type="png", clip={"x": 0, "y": 0, "width": width, "height": height})
            finally:
                await browser.close()
    except PlaywrightError as e:
        if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
            raise RendererUnavailable() from e
        raise


def _run(html: str, *, pdf: bool, width: int, height: int) -> bytes:
    # Own event loop per render (we're in a worker thread). On Windows it must be a Proactor loop to start Chromium.
    factory = asyncio.ProactorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
    with _slots, asyncio.Runner(loop_factory=factory) as runner:
        return runner.run(_render(html, pdf=pdf, width=width, height=height))


def render_pdf(html: str) -> bytes:
    return _run(html, pdf=True, width=794, height=1123)  # A4 at 96 dpi; the page size itself comes from CSS @page


def render_png(html: str, width: int, height: int) -> bytes:
    return _run(html, pdf=False, width=width, height=height)
