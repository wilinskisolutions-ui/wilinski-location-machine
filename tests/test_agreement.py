"""Whether the household's stated weights predict the choices they actually made.

This replaces weight *estimation* as the trade-off block's main job, and the reason is
measured rather than argued. `fit_choices` estimates one free parameter per attribute from
twenty-five choices. A design sweep over the real data fitted a simulated respondent with
three strong, coherent preferences and compared them against pure random answers, at every
attribute-pool size from eight to seventeen:

    attributes   coherent (median LOO)   random (95th pct)   separation
             8                   0.700               0.748       -0.048
             9                   0.700               0.680       +0.020
            10                   0.680               0.640       +0.040
            17                   0.620               0.640       -0.020

Separation is zero everywhere. The block could not tell a coherent respondent from a coin,
and no choice of attributes fixed it — the shortage was data, not design.

Checking a *stated* weight vector against the same choices has no free parameters, so it is
an ordinary binomial test: under the null it is exactly a coin flip, and twenty-five choices
give it real power. It also asks a question the household can act on — *do your stated
priorities predict how you actually choose?* — rather than one the instrument cannot answer.

On the first real respondent it returns **54% of 24 choices, p=0.42** — his almost-flat
stated allocation does not predict his choices any better than a coin. That is a finding
about his weights, not a failure of the test, and the previous behaviour was to average that
disagreement away in silence.

A correction worth recording, because it is the error this test exists to prevent: an
earlier run of this check reported 75% at p=0.011 for the same respondent. That run scored
his answers against freshly generated pairs — but `choice_tasks` is seeded, so regenerating
after the question rewrite produces `choice_7` showing a DIFFERENT pair. It was comparing
his answers to questions he never saw. The 54% figure is measured at the commit before the
rewrite, against the pairs he actually answered.
"""

from __future__ import annotations

import random
import unittest

from wlm.elicit import _binomial_tail, agreement
from wlm.features.curves import desirability
from wlm.ingest.base import registry as load_registry
from wlm.questionnaire import generate

REGISTRY = load_registry()
DOMAIN_OF = {i: e["domain"] for i, e in REGISTRY.items()}


def _answers_following(tasks, weights, *, flip=0.0, seed=0):
    """Answer every task exactly as the given weights say to, flipping a share of them."""
    rng = random.Random(seed)
    answers = {}
    for task in tasks:
        a_total = b_total = 0.0
        by_domain: dict[str, list] = {}
        for attr in task["attributes"]:
            entry = REGISTRY[attr["indicator"]]
            domain = DOMAIN_OF[attr["indicator"]]
            if weights.get(domain, 0.0) <= 0:
                continue
            da = desirability(
                curve=entry["curve"], value=attr["a_raw"], percentile=attr["a_pct"],
                params=entry.get("curve_params"),
            )
            db = desirability(
                curve=entry["curve"], value=attr["b_raw"], percentile=attr["b_pct"],
                params=entry.get("curve_params"),
            )
            if da is None or db is None:
                continue
            by_domain.setdefault(domain, []).append((da, db))
        for domain, pairs in by_domain.items():
            share = weights[domain] / len(pairs)
            for da, db in pairs:
                a_total += share * da
                b_total += share * db
        pick = "A" if a_total >= b_total else "B"
        if rng.random() < flip:
            pick = "B" if pick == "A" else "A"
        answers[task["id"]] = pick
    return answers


class TestBinomialTail(unittest.TestCase):
    def test_a_coin_flip_is_not_evidence(self):
        self.assertGreater(_binomial_tail(12, 24), 0.4)

    def test_a_clear_majority_is(self):
        self.assertLess(_binomial_tail(18, 24), 0.05)

    def test_it_is_one_sided(self):
        """Agreeing *less* than chance is not evidence the weights are right."""
        self.assertGreater(_binomial_tail(6, 24), 0.9)


class TestAgreement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = [q for q in generate.build() if q["type"] == "choice_pair"]
        cls.weights = {"climate_environment": 40.0, "cost_housing": 35.0, "safety": 25.0}

    def _check(self, answers, weights=None, overrides=None):
        return agreement(
            self.tasks, answers, domain_weights=weights or self.weights,
            domain_of=DOMAIN_OF, registry=REGISTRY, curve_overrides=overrides,
        )

    def test_a_respondent_who_follows_their_weights_is_detected(self):
        check = self._check(_answers_following(self.tasks, self.weights))
        self.assertEqual(check.rate, 1.0)
        self.assertTrue(check.is_significant)

    def test_it_survives_a_realistically_noisy_respondent(self):
        """Nobody answers twenty-five trade-offs perfectly. One in five flipped must still
        read as a preference rather than as noise."""
        check = self._check(_answers_following(self.tasks, self.weights, flip=0.2, seed=3))
        self.assertGreater(check.rate, 0.65)
        self.assertTrue(check.is_significant, check.render())

    def test_random_answers_are_not_called_a_preference(self):
        """The failure that matters: noise reported as a finding. Ten independent random
        respondents, at most two of which may slip through at the 5% level."""
        passed = 0
        for seed in range(10):
            rng = random.Random(seed)
            passed += self._check({t["id"]: rng.choice("AB") for t in self.tasks}).is_significant
        self.assertLessEqual(passed, 2, f"{passed}/10 random respondents called significant")

    def test_the_wrong_weights_do_not_predict_the_choices(self):
        """Answer by one set of priorities, test against a different set."""
        answers = _answers_following(self.tasks, self.weights)
        other = {d: 100.0 / 3 for d in ("recreation_lifestyle", "career_economy", "urban_form")}
        self.assertLess(self._check(answers, weights=other).rate, 0.8)

    def test_an_indifferent_indicator_is_not_held_against_them(self):
        """Saying "don't care" must remove an attribute from the check, not score it."""
        answers = _answers_following(self.tasks, self.weights)
        overrides = {i: {"indifferent": True} for i in REGISTRY}
        self.assertEqual(self._check(answers, overrides=overrides).n_choices, 0)

    def test_repeated_tasks_are_not_double_counted(self):
        """The consistency repeats exist to catch contradictions, not to inflate n."""
        check = self._check(_answers_following(self.tasks, self.weights))
        repeats = sum(1 for t in self.tasks if t.get("repeat_of"))
        self.assertGreater(repeats, 0)
        self.assertLessEqual(check.n_choices, len(self.tasks) - repeats)


if __name__ == "__main__":
    unittest.main()
