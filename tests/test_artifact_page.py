"""The phone questionnaire, driven at phone size in a real browser.

The localhost version has 18 browser tests; this is the same discipline applied to the page
Emil and Winsor will actually hold. It runs at a 390x844 viewport with touch, because the
bugs this surface produces are layout bugs and they are invisible at desktop width — the
first run here found the page laying itself out at 980px and scaling down, which would have
made every question unreadable on a phone.

Skipped automatically when Playwright or Chromium is unavailable.
"""

from __future__ import annotations

import functools
import glob
import http.server
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    HAVE_PLAYWRIGHT = True
except ImportError:  # pragma: no cover
    HAVE_PLAYWRIGHT = False

PHONE = {"width": 390, "height": 844}


def _chromium() -> str | None:
    found = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    return found[0] if found else None


@unittest.skipUnless(HAVE_PLAYWRIGHT and _chromium(), "playwright/chromium unavailable")
class TestQuestionnaireOnAPhone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from wlm.questionnaire import artifact

        cls.tmp = Path(tempfile.mkdtemp())
        cls.page_path = artifact.write_page("practice", out_dir=cls.tmp)
        cls.questions = artifact.generate.build()

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):  # a passing test should print nothing
                pass

        handler = functools.partial(Quiet, directory=str(cls.tmp))
        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=_chromium())

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.httpd.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.page = self.browser.new_page(
            viewport=PHONE, is_mobile=True, has_touch=True
        )
        self.errors: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(f"http://127.0.0.1:{self.port}/{self.page_path.name}")
        self.page.wait_for_selector("#app h2", timeout=15_000)

    def tearDown(self):
        self.assertEqual(self.errors, [], f"JavaScript errors: {self.errors}")
        self.page.close()

    def _advance_to(self, selector: str, limit: int = 60) -> bool:
        for _ in range(limit):
            if self.page.query_selector(selector):
                return True
            if not self.page.query_selector("#skip"):
                return False
            self.page.click("#skip")
            self.page.wait_for_timeout(40)
        return False

    def _stored(self) -> int:
        return self.page.evaluate(
            "[...document.querySelectorAll('#store .slot')].filter(s=>s.dataset.v).length"
        )

    # ---------------------------------------------------------------- phone layout

    def test_it_lays_out_at_the_phone_width_not_a_desktop_one(self):
        """Without a viewport meta a phone renders at 980px and scales down. The head
        belongs to the artifact wrapper, so the page has to add the tag itself."""
        self.assertEqual(self.page.evaluate("document.documentElement.clientWidth"), 390)

    def test_the_page_never_scrolls_sideways(self):
        self.assertTrue(
            self.page.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
            )
        )

    def test_trade_off_cards_stack_rather_than_squeezing_side_by_side(self):
        self.assertTrue(self._advance_to(".pair"), "no trade-off question reached")
        cards = self.page.query_selector_all(".pair .card")
        self.assertEqual(len(cards), 2)
        self.assertGreater(
            cards[0].bounding_box()["width"], 300,
            "cards are side by side on a phone; they should stack",
        )

    def test_every_control_is_big_enough_to_tap(self):
        """Apple and Google both put the floor near 44px; nothing here may be smaller
        than the 38px stepper, which is the tightest deliberate size."""
        self._advance_to(".opt")
        for element in self.page.query_selector_all(".opt, .nav button"):
            box = element.bounding_box()
            if box:
                self.assertGreaterEqual(box["height"], 44, element.inner_text()[:30])

    # ------------------------------------------------------------------- recording

    def test_a_tap_records_an_answer_and_moves_on(self):
        first = self.page.inner_text("#app h2")
        self.page.query_selector_all(".opt")[0].click()
        self.page.wait_for_timeout(400)
        self.assertEqual(self._stored(), 1)
        self.assertNotEqual(self.page.inner_text("#app h2"), first)

    def test_answers_survive_a_reload(self):
        self.page.query_selector_all(".opt")[0].click()
        self.page.wait_for_timeout(400)
        here = self.page.inner_text("#app h2")
        self.page.reload()
        self.page.wait_for_selector("#app h2", timeout=15_000)
        self.assertEqual(self.page.inner_text("#app h2"), here)

    def test_the_answer_lives_in_the_document_so_it_can_be_read_back(self):
        """The artifact capability persists what a gesture changes in the DOM. If answers
        lived only in a JS variable there would be nothing to save."""
        self.page.query_selector_all(".opt")[0].click()
        self.page.wait_for_timeout(400)
        self.assertTrue(
            self.page.evaluate(
                "[...document.querySelectorAll('#store .slot')].some(s=>s.dataset.v)"
            )
        )

    def test_skipping_records_nothing(self):
        self.page.click("#skip")
        self.page.wait_for_timeout(250)
        self.assertEqual(self._stored(), 0)

    def test_the_budget_uses_steppers_and_holds_the_total(self):
        """Typing eleven numbers on a phone keyboard is miserable; steppers are the point."""
        self.assertTrue(self._advance_to("#tot"), "no budget question reached")
        plus = self.page.query_selector_all('.step button[data-d="1"]')
        self.assertGreater(len(plus), 5)
        self.assertIn("bad", self.page.get_attribute("#tot", "class") or "")
        for _ in range(3):
            plus[0].click()
        self.page.wait_for_timeout(150)
        self.assertIn("3 of 100", self.page.inner_text("#tot"))

        self.page.once("dialog", lambda d: d.accept())
        self.page.click("#next")
        self.page.wait_for_timeout(250)
        self.assertTrue(self.page.query_selector("#tot"), "advanced without a full budget")

    def test_reaching_the_end_offers_the_answers_as_a_file(self):
        for _ in range(len(self.questions) + 3):
            if self.page.query_selector(".done"):
                break
            self.page.click("#skip")
            self.page.wait_for_timeout(25)
        self.assertTrue(self.page.query_selector(".done"), "never reached the end")
        self.assertTrue(self.page.query_selector("#export"), "no way to get the answers out")
        self.assertIn("practice", self.page.inner_text(".done").lower())

    def test_start_over_clears_everything(self):
        self.page.query_selector_all(".opt")[0].click()
        self.page.wait_for_timeout(400)
        self.page.once("dialog", lambda d: d.accept())
        self.page.click("#reset")
        self.page.wait_for_timeout(400)
        self.assertEqual(self._stored(), 0)

    # ----------------------------------------------------------------- independence

    def test_each_person_gets_their_own_page_and_their_own_storage(self):
        """Principle 8 only means something if neither saw the other's answers first."""
        from wlm.questionnaire import artifact

        emil = artifact.build_page("emil")
        winsor = artifact.build_page("winsor")
        self.assertIn('"wlm:" + PERSON', emil)
        self.assertIn('const PERSON = "emil"', emil)
        self.assertIn('const PERSON = "winsor"', winsor)

    def test_a_practice_page_is_marked_as_practice(self):
        from wlm.questionnaire import artifact

        self.assertIn("const PRACTICE = true", artifact.build_page("practice"))
        self.assertIn("const PRACTICE = false", artifact.build_page("emil"))

    def test_the_page_reaches_for_no_host_but_the_font_service(self):
        import re

        from wlm.questionnaire import artifact

        hosts = set(re.findall(r"https?://([a-z0-9.-]+)", artifact.build_page("emil")))
        self.assertTrue(hosts <= {"fonts.googleapis.com", "fonts.gstatic.com"}, sorted(hosts))


if __name__ == "__main__":
    unittest.main()
