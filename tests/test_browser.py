"""Drive the questionnaire in a real browser.

Every other test hits the server through its JSON API. Emil and Winsor will click the page,
and a page can be broken in ways an API test never sees — a handler wired to the wrong
element, a question type that renders but records nothing, a back button that loses an
answer.

Skipped automatically when Playwright or Chromium is unavailable, so the suite stays
runnable anywhere.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    HAVE_PLAYWRIGHT = True
except ImportError:  # pragma: no cover
    HAVE_PLAYWRIGHT = False

CHROMIUM = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def _chromium_path() -> str | None:
    if CHROMIUM.exists():
        return str(CHROMIUM)
    for candidate in Path("/opt/pw-browsers").glob("chromium*/chrome-linux/chrome"):
        return str(candidate)
    return None


@unittest.skipUnless(HAVE_PLAYWRIGHT and _chromium_path(), "playwright/chromium unavailable")
class TestQuestionnaireInBrowser(unittest.TestCase):
    """The path Emil and Winsor will actually walk."""

    @classmethod
    def setUpClass(cls):
        from wlm.questionnaire import generate
        from wlm.questionnaire.server import Handler
        from wlm.questionnaire.session import PRACTICE

        cls.tmp = Path(tempfile.mkdtemp())
        cls.questions = generate.build()

        Handler.questions = cls.questions
        Handler.default_person = PRACTICE

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=_chromium_path())

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.httpd.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from wlm.questionnaire.session import PRACTICE, Session

        Session.load(PRACTICE).reset()  # every test starts clean
        self.page = self.browser.new_page()
        self.errors: list[str] = []
        # A silent JavaScript exception is exactly the failure an API test cannot see.
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto(f"http://127.0.0.1:{self.port}/?person=practice")
        self.page.wait_for_selector("#app .cat, #app h2", timeout=10_000)

    def tearDown(self):
        self.assertEqual(self.errors, [], f"JavaScript errors on the page: {self.errors}")
        self.page.close()

    # ------------------------------------------------------------------ start screen

    def test_start_screen_lists_every_category_with_its_explanation(self):
        from wlm.questionnaire.server import read_domains

        cards = self.page.query_selector_all(".cat")
        self.assertEqual(len(cards), len(read_domains()))
        for card in cards:
            text = card.inner_text()
            self.assertGreater(len(text.split()), 25, f"category explanation too thin: {text[:60]}")

    def test_weight_editor_rejects_a_total_that_is_not_100(self):
        self.page.fill("#w_cost_housing", "99")
        self.page.once("dialog", lambda d: d.accept())
        self.page.click("#savew")
        self.page.wait_for_timeout(200)
        self.assertIn("bad", self.page.get_attribute("#stot", "class") or "")

    def test_begin_moves_from_the_start_screen_to_the_first_question(self):
        self.page.click("#begin")
        self.page.wait_for_selector("#app h2")
        self.assertTrue(self.page.query_selector("#next"))
        self.assertIsNone(self.page.query_selector(".cat"))

    # ---------------------------------------------------------------- question types

    def _advance_to(self, qtype: str, limit: int = 80):
        """Click Begin, then skip forward until a question of `qtype` is on screen."""
        self.page.click("#begin")
        self.page.wait_for_selector("#app h2")
        for _ in range(limit):
            if self._current_type() == qtype:
                return True
            if self.page.query_selector(".done"):
                return False  # walked off the end; no Skip button to click
            self.page.click("#skip")
            self.page.wait_for_timeout(60)
        return False

    def _current_type(self) -> str:
        # Ask the page what it is rendering rather than inferring it from the markup: a
        # multi-select is also an `.opt`, so guessing put it in the wrong bucket.
        return self.page.evaluate("S.done ? 'done' : S.question.type")

    def test_trade_off_pair_renders_both_places_and_records_a_choice(self):
        self.assertTrue(self._advance_to("choice_pair"), "no trade-off question reached")
        cards = self.page.query_selector_all(".pair .card")
        self.assertEqual(len(cards), 2)
        # Both sides must show real values, not blanks.
        for card in cards:
            rows = card.query_selector_all(".attr")
            self.assertGreaterEqual(len(rows), 3)
            for r in rows:
                self.assertNotIn("—", r.inner_text())

        from wlm.questionnaire.session import PRACTICE, Session

        before = Session.load(PRACTICE).answered
        cards[0].click()
        self.page.wait_for_timeout(400)
        self.assertGreater(Session.load(PRACTICE).answered, before, "the choice was not recorded")

    def test_scale_question_shows_the_harrisburg_anchor(self):
        """Absolute numbers are hard to answer; 'compared to home' is easy. That only
        works if the anchor is actually on screen."""
        self.assertTrue(self._advance_to("scale"), "no scale question reached")
        anchor = self.page.query_selector(".anchor")
        self.assertIsNotNone(anchor, "a band question arrived with no anchor")
        self.assertIn("Harrisburg", anchor.inner_text())
        self.assertGreaterEqual(len(self.page.query_selector_all(".opt")), 3)

    def test_budget_question_enforces_the_total(self):
        self.assertTrue(self._advance_to("budget"), "no budget question reached")
        inputs = self.page.query_selector_all(".row input[data-id]")
        self.assertGreater(len(inputs), 5)
        inputs[0].fill("5")
        self.page.once("dialog", lambda d: d.accept())
        self.page.click("#next")
        self.page.wait_for_timeout(200)
        # Still on the budget screen, because 5 is not 100.
        self.assertTrue(self.page.query_selector(".row input[data-id]"))

    def test_rating_grid_allows_blanks(self):
        self.assertTrue(self._advance_to("rating_grid"), "no rating grid reached")
        inputs = self.page.query_selector_all(".row input[data-id]")
        self.assertGreater(len(inputs), 5)
        inputs[0].fill("8")
        self.page.click("#next")
        self.page.wait_for_timeout(300)

        from wlm.questionnaire.session import PRACTICE, Session

        answers = Session.load(PRACTICE).answers
        grid = answers.get("calibration_ratings") or {}
        self.assertEqual(len(grid), 1, "blank ratings should not be recorded as zeros")

    def test_free_text_left_blank_is_not_recorded_as_an_answer(self):
        self.assertTrue(self._advance_to("text"), "no free-text question reached")
        qid = self.page.evaluate("S.question.id")
        self.page.click("#next")
        self.page.wait_for_timeout(250)

        from wlm.questionnaire.session import PRACTICE, Session

        answers = Session.load(PRACTICE).answers
        self.assertNotIn(qid, answers, "an untouched optional box was stored as an answer")

    def test_free_text_records_what_was_typed(self):
        self.assertTrue(self._advance_to("text"), "no free-text question reached")
        qid = self.page.evaluate("S.question.id")
        self.page.fill("textarea", "somewhere without a six-month winter")
        self.page.click("#next")
        self.page.wait_for_timeout(250)

        from wlm.questionnaire.session import PRACTICE, Session

        self.assertEqual(
            Session.load(PRACTICE).answers.get(qid), "somewhere without a six-month winter"
        )

    def test_the_housing_budget_becomes_a_working_knockout(self):
        """The one number on the whole form that can eliminate every candidate."""
        self.assertTrue(self._advance_to("number"), "no number question reached")
        qid = self.page.evaluate("S.question.id")
        self.page.fill("#t", "450000")
        self.page.click("#next")
        self.page.wait_for_timeout(250)

        from wlm.profile import build_profile
        from wlm.questionnaire.session import PRACTICE, Session

        session = Session.load(PRACTICE)
        self.assertEqual(session.answers.get(qid), "450000")

        knockouts = build_profile(session, self.questions)["knockouts"]
        rule = next((k for k in knockouts if k["from"] == qid), None)
        self.assertIsNotNone(rule, "the budget answer produced no knockout")
        self.assertEqual(float(rule["value"]), 450_000)

    def test_multi_select_records_only_what_was_ticked(self):
        self.assertTrue(self._advance_to("multi"), "no multi-select question reached")
        qid = self.page.evaluate("S.question.id")
        options = self.page.query_selector_all(".opt.multi")
        self.assertGreater(len(options), 1)
        first = options[0].inner_text()
        options[0].click()
        self.page.click("#next")
        self.page.wait_for_timeout(250)

        from wlm.questionnaire.session import PRACTICE, Session

        self.assertEqual(Session.load(PRACTICE).answers.get(qid), [first])

    # --------------------------------------------------------------------- navigation

    def test_back_button_returns_to_the_previous_question(self):
        self.page.click("#begin")
        self.page.wait_for_selector("#app h2")
        first = self.page.inner_text("#app h2")
        self.page.click("#skip")
        self.page.wait_for_timeout(150)
        self.assertNotEqual(self.page.inner_text("#app h2"), first)
        self.page.click("#back")
        self.page.wait_for_timeout(150)
        self.assertEqual(self.page.inner_text("#app h2"), first)

    def test_progress_survives_a_reload(self):
        self.page.click("#begin")
        self.page.wait_for_selector("#app h2")
        for _ in range(3):
            self.page.click("#skip")
            self.page.wait_for_timeout(80)
        here = self.page.inner_text("#app h2")

        self.page.reload()
        self.page.wait_for_selector("#app h2", timeout=10_000)
        self.assertEqual(self.page.inner_text("#app h2"), here, "resumed at the wrong question")

    def test_start_over_clears_everything(self):
        self.page.click("#begin")
        self.page.wait_for_selector("#app h2")
        for _ in range(3):
            self.page.click("#skip")
            self.page.wait_for_timeout(80)

        self.page.once("dialog", lambda d: d.accept())
        self.page.click("#reset")
        self.page.wait_for_timeout(400)

        from wlm.questionnaire.session import PRACTICE, Session

        self.assertEqual(Session.load(PRACTICE).position, 0)

    def test_categories_link_returns_to_the_start_screen(self):
        self.page.click("#begin")
        self.page.wait_for_selector("#app h2")
        self.page.click("#cats")
        self.page.wait_for_timeout(200)
        self.assertTrue(self.page.query_selector(".cat"), "categories screen did not reopen")

    # -------------------------------------------------------------------- completion

    def test_reaching_the_end_finishes_cleanly(self):
        """Walking off the end of the questionnaire — never exercised before."""
        self.page.click("#begin")
        self.page.wait_for_selector("#app h2")
        for _ in range(len(self.questions) + 2):
            if self.page.query_selector(".done"):
                break
            self.page.click("#skip")
            self.page.wait_for_timeout(40)

        self.assertTrue(self.page.query_selector(".done"), "never reached the end")
        text = self.page.inner_text(".done")
        self.assertIn("practice", text.lower(), "a practice run must say nothing was saved")

        from wlm.questionnaire.session import PRACTICE, Session

        self.assertIsNotNone(Session.load(PRACTICE).finished_at)

    def test_a_practice_run_writes_no_real_profile(self):
        """The most important guarantee in the whole app: practice cannot destroy answers."""
        from wlm.questionnaire.session import PROFILES, REAL_PEOPLE

        before = {
            person: (PROFILES / f"{person}.yaml").read_bytes()
            if (PROFILES / f"{person}.yaml").exists() else None
            for person in REAL_PEOPLE
        }

        self.page.click("#begin")
        self.page.wait_for_selector("#app h2")
        for _ in range(len(self.questions) + 2):
            if self.page.query_selector(".done"):
                break
            self.page.click("#skip")
            self.page.wait_for_timeout(40)

        for person in REAL_PEOPLE:
            path = PROFILES / f"{person}.yaml"
            after = path.read_bytes() if path.exists() else None
            self.assertEqual(before[person], after, f"{person}'s profile was touched")

    def test_practice_banner_is_visible(self):
        self.page.click("#begin")
        self.page.wait_for_selector("#app h2")
        self.assertIn("PRACTICE", self.page.inner_text(".meta"))


if __name__ == "__main__":
    unittest.main()
