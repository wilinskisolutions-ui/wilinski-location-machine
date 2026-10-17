"""The website, driven in a real browser as a first-time visitor.

Covers the path a stranger takes: the wizard, the map it produces, opening an area and a
town, and coming back later. Runs against the built site (`make web`) with no Supabase
settings, so it exercises the this-device-only mode; accounts are covered by the
row-level-security checks in web/supabase/tests.
"""

from __future__ import annotations

import functools
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    HAVE_PLAYWRIGHT = True
except ImportError:  # pragma: no cover - optional dependency
    HAVE_PLAYWRIGHT = False

from wlm.paths import ROOT

DIST = ROOT / "web" / "dist"


def _chromium() -> str | None:
    for candidate in sorted(Path("/opt/pw-browsers").glob("chromium*/chrome-linux/chrome")):
        return str(candidate)
    return None


@unittest.skipUnless(HAVE_PLAYWRIGHT and _chromium(), "playwright/chromium unavailable")
@unittest.skipUnless((DIST / "index.html").exists() and (DIST / "data" / "core.json").exists(),
                     "site not built (make atlas web)")
class TestFirstVisit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Quiet(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        handler = functools.partial(Quiet, directory=str(DIST))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/index.html"
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=_chromium())

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()

    def _page(self, width=1440, height=900):
        ctx = self.browser.new_context(viewport={"width": width, "height": height})
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "fonts" not in m.text and "ERR_FAILED" not in m.text else None)
        page.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        return ctx, page, errors

    def _wizard(self, page):
        page.goto(self.url)
        page.wait_for_selector("#wizard:not([hidden]) .wz-card", timeout=30000)
        page.click('.wz-opt[data-value="couple"]')
        page.click("#wz-next")
        page.fill("#wz-home", "Harrisburg")
        page.click('#wz-home-results button[data-id="4232800"]')
        page.click("#wz-next")
        page.click("#wz-next")  # money: defaults
        page.click("#wz-next")  # life: defaults
        page.click('.wz-opt.row[data-preset="mild"]')
        page.click("#wz-next")
        page.click("#wz-next")  # weights: defaults
        page.fill("#wz-pick", "Franklin")
        page.click('#wz-pick-results button[data-id="4727740"]')
        page.click("#wz-next")
        page.wait_for_selector("#wizard", state="hidden")

    def test_wizard_to_map_and_back_again(self):
        ctx, page, errors = self._page()
        try:
            self._wizard(page)
            self.assertEqual(page.locator("#tab-places [data-pin]").count(), 1)
            self.assertGreaterEqual(page.locator("#tab-places [data-rival]").count(), 5)
            page.click('#tab-places [data-pin="p-4727740"]')
            page.wait_for_selector(".l-rtowns path", timeout=15000)
            page.click("#readout [data-town]")
            page.click('.status button[data-s="want"]')

            before = page.locator("#tab-places [data-rival] .t").all_inner_texts()
            page.click('.left .tabs [data-tab="weights"]')
            page.fill("#w-hazard", "30")
            page.dispatch_event("#w-hazard", "input")
            page.wait_for_timeout(200)
            page.click('.left .tabs [data-tab="places"]')
            after = page.locator("#tab-places [data-rival] .t").all_inner_texts()
            self.assertNotEqual(before, after, "challengers did not refresh when a weight moved")

            page.wait_for_timeout(800)  # settings save is debounced
            page.reload()
            page.wait_for_selector("#loading", state="hidden", timeout=30000)
            self.assertEqual(page.locator("#wizard:not([hidden])").count(), 0, "the wizard came back")
            self.assertEqual(page.locator("#tab-places [data-pin]").count(), 1)
            self.assertEqual(page.locator("#tab-places [data-town]").count(), 1, "visit list lost")
            self.assertEqual(page.input_value("#w-hazard"), "30", "weights lost")
            self.assertEqual(errors, [])
        finally:
            ctx.close()

    def test_phone_layout_does_not_scroll_sideways(self):
        ctx, page, errors = self._page(390, 844)
        try:
            self._wizard(page)
            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
            self.assertEqual(errors, [])
        finally:
            ctx.close()

    def test_sensitive_layers_start_switched_off(self):
        ctx, page, _ = self._page()
        try:
            self._wizard(page)
            page.click('.left .tabs [data-tab="weights"]')
            for layer in ("religion", "politics", "foreign"):
                self.assertFalse(page.is_checked(f'#tab-weights input[data-on="{layer}"]'))
                self.assertTrue(page.is_disabled(f"#w-{layer}"))
        finally:
            ctx.close()


if __name__ == "__main__":
    unittest.main()
