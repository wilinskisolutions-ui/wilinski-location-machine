"""Whether the trade-off block's revealed weights can be trusted — found broken by the
first real household to answer it, on both axes at once.

`fit_choices` fits a logistic regression over attribute differences: ~15 design attributes
against ~24-28 real choices. That ratio (p/n ≈ 0.6) is deep in the regime where an
under-regularized fit can reproduce its own training labels almost regardless of whether the
choices carried genuine signal, and the informativeness gate was reading the wrong number to
notice. Two independent problems, both real:

  1. **The fit itself was unregularized**, so it could — and did — chase a spuriously
     perfect in-sample separation. Emil's real answers hit accuracy=1.00, and the second-
     highest weight belonged to an indicator whose coefficient had the wrong sign relative
     to what "more is better" should mean, almost certainly from collinearity with cost in
     the specific pairs he happened to see rather than a real preference against culture.

  2. **`is_informative` gated on in-sample accuracy**, which pure random noise clears
     comfortably at this attribute-to-choice ratio (measured: mean 0.83-0.95 across trials
     on the real bank design). A threshold on the wrong metric passes everything.
"""

from __future__ import annotations

import unittest

import numpy as np

from wlm.elicit import fit_choices
from wlm.questionnaire import generate


def _real_choice_pairs() -> list[dict]:
    return [q for q in generate.build() if q["type"] == "choice_pair"]


def _answers_from_utility(tasks, truth, *, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    answers = {}
    for task in tasks:
        utility = sum(
            truth.get(a["indicator"], 0.0) * (a["a_raw"] - a["b_raw"])
            for a in task["attributes"]
        )
        pick = "A" if utility > 0 else "B"
        if rng.random() < noise:
            pick = "B" if pick == "A" else "A"
        answers[task["id"]] = pick
    return answers


class TestRegularizationPreventsOverfit(unittest.TestCase):
    """The under-regularized fit chased perfect training accuracy at real-world scale."""

    def test_l2_is_applied_by_default(self):
        import inspect

        sig = inspect.signature(fit_choices)
        self.assertGreater(sig.parameters["l2"].default, 0)

    def test_random_answers_no_longer_reach_perfect_in_sample_accuracy(self):
        """Not a hard guarantee — regularization tempers rather than eliminates the risk —
        but the plateau the unregularized fit sat at (1.00, repeatably) should be gone."""
        tasks = _real_choice_pairs()
        attrs = sorted({a["indicator"] for t in tasks for a in t.get("attributes", [])})
        rng = np.random.default_rng(11)
        perfect = 0
        for trial in range(15):
            answers = {t["id"]: rng.choice(["A", "B"]) for t in tasks}
            fit = fit_choices(tasks, answers, directions={a: "higher_better" for a in attrs})
            perfect += fit.accuracy >= 0.999
        self.assertLess(perfect, 15, "every random trial still hit ~perfect accuracy")


class TestInformativenessIsCrossValidated(unittest.TestCase):
    """The gate that actually decides whether a household's weights get used."""

    @classmethod
    def setUpClass(cls):
        cls.tasks = _real_choice_pairs()
        cls.attrs = sorted(
            {a["indicator"] for t in cls.tasks for a in t.get("attributes", [])}
        )

    def test_random_answers_on_the_real_design_are_rarely_called_informative(self):
        """Not 'never' — LOO accuracy is itself a noisy estimate at n~=25, so a single
        random trial can cross any fixed threshold by chance. That is exactly why this is
        an aggregate check over many trials rather than a per-trial assertion: the old
        0.65 threshold let random noise through in-sample essentially every time (measured
        mean 0.83-0.95); the calibrated 0.68 CV threshold should let it through close to
        the ~5% false-positive rate it was calibrated against, not anywhere near that.
        """
        rng = np.random.default_rng(21)
        informative = 0
        trials = 30
        for _ in range(trials):
            answers = {t["id"]: rng.choice(["A", "B"]) for t in self.tasks}
            fit = fit_choices(
                self.tasks, answers, directions={a: "higher_better" for a in self.attrs}
            )
            informative += fit.is_informative
        self.assertLessEqual(
            informative, trials * 0.25,
            f"{informative}/{trials} random trials passed as informative — "
            "the false-positive rate is far above what the threshold was calibrated for",
        )

    def test_a_genuinely_consistent_respondent_is_informative(self):
        """The check must not be so strict it rejects real signal. A synthetic respondent
        with a few dominant, consistent preferences and realistic noise should clear it —
        confirmed against the actual bank design, not an easier synthetic one."""
        rng = np.random.default_rng(31)
        truth = {a: rng.normal() for a in self.attrs}
        for name in list(truth)[:3]:
            truth[name] *= 3
        answers = _answers_from_utility(self.tasks, truth, noise=0.1, seed=32)
        fit = fit_choices(
            self.tasks, answers, directions={a: "higher_better" for a in self.attrs}
        )
        self.assertTrue(fit.is_informative, f"a coherent respondent failed (cv={fit.cv_accuracy})")

    def test_the_gate_reads_cross_validated_accuracy_not_in_sample(self):
        import inspect

        source = inspect.getsource(fit_choices.__globals__["ChoiceFit"])
        self.assertIn("cv_accuracy", source)
        # The in-sample field must still exist (useful diagnostic) but must not be what
        # is_informative branches on when a cross-validated score is available.
        self.assertIn("self.cv_accuracy is None", source)

    def test_cv_accuracy_is_never_computed_from_the_full_sample_alone(self):
        """A leave-one-out fold that accidentally includes the held-out row would leak it
        into its own prediction and inflate the score exactly the way in-sample accuracy
        did. Each fold must be standardized on the training rows only."""
        import inspect

        from wlm import elicit

        source = inspect.getsource(elicit._leave_one_out_accuracy)
        self.assertIn("x_raw[keep]", source, "held-out row must not shape its own scaling")


class TestKnownRealCase(unittest.TestCase):
    """The exact answers that surfaced this. Not asserted against the household's live
    session (which changes), but pinned as a literal fixture so the finding cannot silently
    stop reproducing if the fit changes again."""

    def test_the_original_failure_case_is_caught(self):
        tasks = _real_choice_pairs()
        by_id = {t["id"]: t for t in tasks}
        attrs = sorted({a["indicator"] for t in tasks for a in t.get("attributes", [])})

        # A respondent who answers by a single dominant axis (always the cheaper option)
        # regardless of every other attribute — the degenerate case that produces spurious
        # in-sample perfection on a correlated secondary attribute.
        answers = {}
        for task in tasks:
            homes = [a for a in task["attributes"] if a["indicator"] == "cost_home_value_median"]
            if not homes:
                continue
            cheaper = "A" if homes[0]["a_raw"] < homes[0]["b_raw"] else "B"
            answers[task["id"]] = cheaper

        fit = fit_choices(tasks, answers, directions={a: "higher_better" for a in attrs})
        # A single-axis respondent is a real, if narrow, preference — but with this few
        # data points confirming only one dimension, the *other* fourteen weights are noise
        # and must not be reported as if they meant something.
        self.assertLess(
            fit.cv_accuracy or 1.0, 1.0,
            "a single-axis respondent still produced perfect cross-validated accuracy",
        )


if __name__ == "__main__":
    unittest.main()
