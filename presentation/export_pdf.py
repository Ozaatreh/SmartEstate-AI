"""Export the presentation to PDF (one 1600 x 900 page per slide, every reveal shown).

Uses Playwright's Chromium. The backend's virtual environment already has it:
    ../apps/api/.venv/Scripts/python export_pdf.py
"""
import pathlib

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "index.html"
OUT = HERE / "SmartEstate-AI-presentation.pdf"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    page.goto(SRC.as_uri() + "?print")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    page.emulate_media(media="print")
    page.evaluate("dispatchEvent(new Event('resize'))")  # re-lay out the zoom callouts for print size
    page.wait_for_timeout(500)
    page.pdf(path=str(OUT), width="1600px", height="900px", print_background=True,
             margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
    browser.close()
print(f"Wrote {OUT}")
