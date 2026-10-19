"""The website, driven in a real browser as a first-time visitor.

Covers the path a stranger takes: the start screen, the wizard, the map it produces,
opening an area and a town, and coming back later. Runs against the production build, which
has the Supabase project configured, with every request to Supabase answered in the test:
nothing reaches the real project and no email is sent. Accounts themselves are covered by
the row-level-security checks in web/supabase/tests.
"""

from __future__ import annotations

import functools
import json
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
DONATE_URL = "https://donate.stripe.com/aFa4gzdesgIOgOP3rw3wQ0v"


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

    def _page(self, width=1440, height=900, otp=None):
        """otp: (status, body) Supabase answers a request for a sign-in code with."""
        ctx = self.browser.new_context(viewport={"width": width, "height": height})
        page = ctx.new_page()
        page.otp_requests = []

        def supabase(route):
            url = route.request.url
            if "/auth/v1/settings" in url:
                return route.fulfill(json={"external": {"email": True, "google": False}})
            if "/auth/v1/otp" in url and otp:
                page.otp_requests.append(json.loads(route.request.post_data or "{}"))
                return route.fulfill(status=otp[0], json=otp[1])
            return route.abort()

        page.route("**/*.supabase.co/**", supabase)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "fonts" not in m.text and "ERR_FAILED" not in m.text else None)
        page.route("https://fonts.googleapis.com/**", lambda r: r.abort())
        page.route("https://fonts.gstatic.com/**", lambda r: r.abort())
        return ctx, page, errors

    def _answer(self, page, question, value):
        """Tap an answer; the wizard moves on by itself."""
        page.click(f'.wz-opt[data-q="{question}"][data-value="{value}"]')

    def _wizard(self, page):
        """The simple path: five questions."""
        page.goto(self.url)
        page.wait_for_selector("#wizard:not([hidden]) .wz-card", timeout=30000)
        page.click("#st-guest")  # the start screen: look around without an account
        page.click('.wz-opt[data-depth="simple"]')
        self._answer(page, "who", "couple")
        page.wait_for_selector("#wz-cap")
        page.click("#wz-next")  # money: defaults
        self._answer(page, "nature", "mix")
        page.click('.wz-opt[data-preset="mild"]')
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

    def test_more_questions_shape_the_starting_weights(self):
        ctx, page, errors = self._page(390, 844)
        try:
            page.goto(self.url)
            page.click("#st-guest", timeout=30000)
            page.click('.wz-opt[data-depth="more"]')
            page.wait_for_selector('.wz-opt[data-q="who"]')
            self.assertEqual(page.inner_text(".wz-step"), "Step 1 of 17")
            self._answer(page, "who", "solo")
            self._answer(page, "kidsFuture", "no")
            page.fill("#wz-home", "Harrisburg")
            page.click('#wz-home-results button[data-id="4232800"]')
            page.click("#wz-next")
            page.wait_for_selector("#wz-cap")
            page.click("#wz-next")
            self._answer(page, "cost", "tight")
            page.click(".wz-opt[data-preset]")  # winters, relative to home: the first choice
            self._answer(page, "weather", "some")
            self._answer(page, "nature", "wild")
            self._answer(page, "saturday", "home")
            self._answer(page, "safety", "top")
            self._answer(page, "hazard", "some")
            self._answer(page, "health", "sometimes")
            self._answer(page, "work", "local")
            self._answer(page, "flights", "rarely")
            self._answer(page, "neighbors", "friendly")
            page.wait_for_selector("#wz-total")  # the review screen
            weight = lambda f: int(page.input_value(f"#wz-w-{f}"))
            self.assertEqual(weight("jobs"), 14)
            self.assertEqual(weight("airport"), 2)
            self.assertGreater(weight("safety"), 15)
            self.assertGreater(weight("cost"), 16)
            self.assertGreater(weight("nature"), 9)
            self.assertLess(weight("food"), 10)
            self.assertEqual(page.inner_text("#wz-total"), "100")
            page.click("#wz-next")
            page.wait_for_selector("#wz-pick")
            page.click("#wz-next")  # no places yet: show the map
            page.wait_for_selector("#wizard", state="hidden")
            page.click('.mtabs [data-m="weights"]')  # the phone's tab bar
            self.assertEqual(page.input_value("#w-jobs"), "14", "the map lost the answers' weights")
            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
            self.assertEqual(errors, [])
        finally:
            ctx.close()

    def test_a_quick_tap_on_next_never_skips_a_screen(self):
        ctx, page, _ = self._page()
        try:
            page.goto(self.url)
            page.click("#st-guest", timeout=30000)
            page.click('.wz-opt[data-depth="simple"]')
            page.click('.wz-opt[data-q="who"][data-value="solo"]')
            page.click("#wz-next")  # before the answer moves on by itself
            page.wait_for_timeout(400)
            self.assertEqual(page.locator("#wz-cap").count(), 1, "skipped past the budget")
        finally:
            ctx.close()

    def test_start_screen_offers_log_in_and_set_up(self):
        ctx, page, errors = self._page(390, 844, otp=(200, {}))
        try:
            page.goto(self.url)
            page.wait_for_selector("#st-login", timeout=30000)
            self.assertTrue(page.is_visible("#st-setup"))
            page.click("#st-login")
            page.fill("#cf-email-in", "someone@example.com")
            page.click("#cf-email button[type=submit]")
            page.wait_for_selector("#cf-code-in")
            self.assertEqual(page.otp_requests[0]["email"], "someone@example.com")
            self.assertFalse(page.otp_requests[0]["create_user"], "Log in must not create accounts")
            page.fill("#cf-code-in", "12 34-56")
            self.assertEqual(page.input_value("#cf-code-in"), "123456")
            page.click("#cf-other")
            page.click("#st-back")
            page.click("#st-setup")
            page.fill("#cf-email-in", "new@example.com")
            page.click("#cf-email button[type=submit]")
            page.wait_for_selector("#cf-code-in")
            self.assertTrue(page.otp_requests[1]["create_user"], "Set up account must create one")
            self.assertEqual(errors, [])
        finally:
            ctx.close()

    def test_log_in_with_an_unknown_email_says_what_to_do(self):
        ctx, page, _ = self._page(otp=(422, {"code": "otp_disabled", "msg": "Signups not allowed for otp"}))
        try:
            page.goto(self.url)
            page.click("#st-login", timeout=30000)
            page.fill("#cf-email-in", "nobody@example.com")
            page.click("#cf-email button[type=submit]")
            page.wait_for_function("document.querySelector('#cf-msg').textContent.includes('Set up account')")
            self.assertEqual(page.locator("#cf-code-in").count(), 0)
        finally:
            ctx.close()

    def test_nerd_stats_start_folded_and_stay_open(self):
        ctx, page, errors = self._page()
        try:
            self._wizard(page)
            page.click('#tab-places [data-pin="p-4727740"]')
            page.wait_for_selector(".l-rtowns path", timeout=15000)
            page.click("#readout [data-town]")
            summary = page.locator("#nerd summary")
            self.assertEqual(summary.inner_text().strip().lower(), "click here to view nerd stats")
            self.assertFalse(page.is_visible("#nerd table.facts"))
            summary.click()
            self.assertTrue(page.is_visible("#nerd table.facts"))
            page.click('.status button[data-s="want"]')  # re-renders the readout
            self.assertTrue(page.is_visible("#nerd table.facts"), "the stats folded up again")
            self.assertEqual(errors, [])
        finally:
            ctx.close()

    def test_donate_banner_hides_for_the_visit_and_returns_next_time(self):
        ctx, page, _ = self._page(390, 844)
        try:
            self._wizard(page)
            banner = page.locator("#donate")
            self.assertIn("This project is entirely free", banner.inner_text())
            self.assertEqual(banner.locator("a").get_attribute("href"), DONATE_URL)
            self.assertEqual(banner.locator("a").inner_text(), "Donate here")
            self.assertEqual(banner.locator("svg.donate-ico").count(), 1)
            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
            page.click("#donate .donate-x")
            self.assertEqual(page.locator("#donate").count(), 0)
            page.reload()
            page.wait_for_selector("#loading", state="hidden", timeout=30000)
            self.assertEqual(page.locator("#donate").count(), 0, "came back within the same visit")
            later = ctx.new_page()  # a later visit: same browser, same saved map, new tab
            later.goto(self.url)
            later.wait_for_selector("#loading", state="hidden", timeout=30000)
            self.assertEqual(later.locator("#donate").count(), 1, "stayed hidden on the next visit")
        finally:
            ctx.close()

    def test_sensitive_layers_start_switched_off(self):
        ctx, page, _ = self._page()
        try:
            self._wizard(page)
            page.click('.left .tabs [data-tab="weights"]')
            for layer in ("religion", "politics"):
                self.assertFalse(page.is_checked(f'#tab-weights input[data-on="{layer}"]'))
                self.assertTrue(page.is_disabled(f"#w-{layer}"))
        finally:
            ctx.close()


if __name__ == "__main__":
    unittest.main()
