"""Genera el PDF de estimado de costos de la plataforma A3."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "data" / "estimado-costos-plataforma-a3.html"
PDF = ROOT / "data" / "estimado-costos-plataforma-a3.pdf"


def main() -> int:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome")
        except Exception:
            browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(HTML.as_uri(), wait_until="load")
        try:
            page.wait_for_function("document.fonts.status === 'loaded'", timeout=8000)
        except PlaywrightError:
            pass
        page.pdf(
            path=str(PDF),
            format="A4",
            print_background=True,
            margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
        )
        browser.close()
    print(f"PDF: {PDF} ({PDF.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
