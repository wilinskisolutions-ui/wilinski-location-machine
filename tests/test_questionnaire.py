"""Questionnaire: question sanity, session safety, and weight recovery.

The first class encodes Emil's objection — that asking a human whether they prefer high
homicide rates is not a question — as a check that cannot be forgotten.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import yaml

from wlm.elicit import compare, fit_choices, normalize_budget
from wlm.paths import CONFIG, ROOT
from wlm.questionnaire import generate
from wlm.questionnaire.session import (
    PRACTICE,
    REAL_PEOPLE,
    Session,
    SessionError,
    normalize_person,
)

REGISTRY = {i["id"]: i for i in yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]}


class TestNoNonsenseQuestions(unittest.TestCase):
    """No question may ask a direction on an indicator where direction is universal."""

    @classmethod
    def setUpClass(cls):
        cls.bank = generate.load_bank()

    def test_every_indicator_declares_a_direction(self):
        missing = [i for i, e in REGISTRY.items() if e.get("direction") not in ("universal", "personal")]
        self.assertEqual(missing, [])

    def test_band_questions_only_target_personal_indicators(self):
        # This is the actual guard: an anchored band asks "more or less than Harrisburg?",
        # which is meaningless for crime, life expectancy or air quality.
        for section in self.bank["sections"]:
            spec = section.get("generated") or {}
            if spec.get("kind") != "anchored_band":
                continue
            for indicator in spec["indicators"]:
                with self.subTest(indicator=indicator):
                    self.assertEqual(
                        REGISTRY[indicator]["direction"], "personal",
                        f"{indicator} has a universal direction — asking which way they want "
                        "it is a wasted question",
                    )

    def test_universal_indicators_appear_only_as_tradeoffs(self):
        """Universal indicators may still be measured — by what people give up for them."""
        for section in self.bank["sections"]:
            spec = section.get("generated") or {}
            for indicator in spec.get("attributes", []):
                self.assertIn(indicator, REGISTRY)

    def test_every_question_maps_to_something_real(self):
        domains = {d["id"] for d in yaml.safe_load((CONFIG / "domains.yaml").read_text())["domains"]}
        for section in self.bank["sections"]:
            for q in section.get("questions", []):
                maps = q.get("maps_to")
                self.assertIsNotNone(maps, f"{q['id']} maps to nothing and should be cut")
                if maps["kind"] in ("indicator", "knockout"):
                    self.assertIn(maps["target"], REGISTRY, q["id"])
                elif maps["kind"] == "weight_domain" and maps["target"] != "all":
                    self.assertIn(maps["target"], domains, q["id"])


class TestGeneratedQuestions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.questions = generate.build()

    def test_produces_a_full_questionnaire(self):
        self.assertGreater(len(self.questions), 40)

    def test_tradeoff_pairs_use_real_values_and_never_dominate(self):
        pairs = [q for q in self.questions if q["type"] == "choice_pair"]
        self.assertGreater(len(pairs), 15)
        for task in pairs:
            wins_a = wins_b = 0
            for attr in task["attributes"]:
                self.assertIsNotNone(attr["a_raw"])
                self.assertIsNotNone(attr["b_raw"])
                lower_better = REGISTRY[attr["indicator"]]["curve"] == "lower_better"
                a_better = (attr["a_raw"] < attr["b_raw"]) if lower_better else (attr["a_raw"] > attr["b_raw"])
                wins_a += a_better
                wins_b += not a_better
            # A pair where one side wins everything teaches nothing about trade-offs.
            self.assertGreater(wins_a, 0, task["id"])
            self.assertGreater(wins_b, 0, task["id"])

    def test_band_questions_are_anchored_to_harrisburg(self):
        bands = [q for q in self.questions if q["type"] == "scale"]
        self.assertGreater(len(bands), 5)
        for q in bands:
            self.assertIn("Harrisburg", q["anchor"])

    def test_consistency_repeats_exist(self):
        repeats = [q for q in self.questions if q.get("repeat_of")]
        self.assertGreater(len(repeats), 0)


class TestSessionSafety(unittest.TestCase):
    """Emil practises before the real run. Practice must not be able to destroy answers."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_practice_cannot_write_a_profile(self):
        s = Session.load(PRACTICE, sessions_dir=self.dir)
        self.assertFalse(s.can_write_profile())
        with self.assertRaises(SessionError):
            s.profile_path()
        self.assertIsNone(s.finish())

    def test_real_people_can(self):
        for person in REAL_PEOPLE:
            s = Session.load(person, sessions_dir=self.dir)
            self.assertTrue(s.can_write_profile())
            self.assertTrue(str(s.profile_path()).endswith(f"{person}.yaml"))

    def test_path_traversal_rejected(self):
        for bad in ("../../etc/passwd", "emil/../winsor", "EMIL; rm -rf /", "", "nobody"):
            with self.assertRaises(SessionError, msg=bad):
                normalize_person(bad)

    def test_names_are_case_insensitive(self):
        self.assertEqual(normalize_person("Emil"), "emil")

    def test_reset_clears_everything(self):
        s = Session.load("emil", sessions_dir=self.dir)
        s.record("q1", "yes")
        s.position = 5
        s.save()
        self.assertTrue(s.path.exists())
        s.reset()
        self.assertEqual(s.answers, {})
        self.assertEqual(s.position, 0)
        self.assertFalse(s.path.exists())

    def test_resume_picks_up_where_it_stopped(self):
        s = Session.load("emil", sessions_dir=self.dir)
        s.record("q1", "yes")
        s.position = 7
        s.save()
        again = Session.load("emil", sessions_dir=self.dir)
        self.assertEqual(again.position, 7)
        self.assertEqual(again.answers["q1"], "yes")

    def test_sessions_are_isolated_between_people(self):
        emil = Session.load("emil", sessions_dir=self.dir)
        emil.record("q1", "emil-answer")
        winsor = Session.load("winsor", sessions_dir=self.dir)
        self.assertEqual(winsor.answers, {})


class TestWeightRecovery(unittest.TestCase):
    """If the elicitation maths cannot recover a known weight vector, every weight is a guess."""

    def _synthetic(self, truth, n=60, noise=0.0, seed=3):
        rng = np.random.default_rng(seed)
        tasks, answers = [], {}
        for i in range(n):
            attrs, utility = [], 0.0
            for name, weight in truth.items():
                a, b = rng.normal(), rng.normal()
                attrs.append({"indicator": name, "a_raw": a, "b_raw": b})
                utility += weight * (a - b)
            tasks.append({"id": f"c{i}", "attributes": attrs})
            flip = rng.random() < noise
            answers[f"c{i}"] = ("A" if utility > 0 else "B") if not flip else ("B" if utility > 0 else "A")
        return tasks, answers

    def test_recovers_ordering_from_clean_choices(self):
        truth = {"cost_home_value_median": -3.0, "climate_temp_winter_mean": 2.0,
                 "amen_food_drink_per10k": 1.0}
        tasks, answers = self._synthetic(truth)
        fit = fit_choices(tasks, answers, directions={k: "higher_better" for k in truth})
        self.assertGreater(fit.accuracy, 0.9)
        self.assertTrue(fit.is_informative)
        order = sorted(fit.weights, key=lambda k: -fit.weights[k])
        self.assertEqual(order[0], "cost_home_value_median")
        self.assertEqual(order[-1], "amen_food_drink_per10k")

    def test_random_answers_are_reported_as_uninformative(self):
        # Fatigue or genuinely equal pairs produce noise. Presenting that as a finding
        # would be worse than admitting it.
        truth = {"a": 1.0, "b": 1.0, "c": 1.0}
        tasks, answers = self._synthetic(truth, noise=0.5, seed=9)
        fit = fit_choices(tasks, answers, directions={})
        self.assertFalse(fit.is_informative)

    def test_contradicting_a_repeated_task_is_flagged(self):
        tasks = [
            {"id": "c1", "attributes": [{"indicator": "x", "a_raw": 1.0, "b_raw": 0.0}]},
            {"id": "c1_repeat", "repeat_of": "c1",
             "attributes": [{"indicator": "x", "a_raw": 1.0, "b_raw": 0.0}]},
        ]
        fit = fit_choices(tasks, {"c1": "A", "c1_repeat": "B"}, directions={})
        self.assertIn("c1", fit.contradictions)

    def test_budget_normalises_to_100(self):
        self.assertAlmostEqual(sum(normalize_budget({"a": 3, "b": 1}).values()), 100.0)
        self.assertEqual(normalize_budget({}), {})

    def test_stated_versus_revealed_gap_is_reported(self):
        notes = compare({"cost_housing": 40.0}, {"cost_housing": 10.0})
        self.assertTrue(any("cost_housing" in n for n in notes))


if __name__ == "__main__":
    unittest.main()


class TestWeightEditor(unittest.TestCase):
    """The start-screen weight editor.

    Emil wanted to adjust category weights and see what each contains, without having to
    remember six months later what 'urban_form' meant.
    """

    def test_every_domain_has_a_real_explanation(self):
        from wlm.questionnaire.server import read_domains

        for d in read_domains():
            with self.subTest(domain=d["id"]):
                # Terse one-liners were the original problem; these must actually explain.
                self.assertGreater(len(d["description"].split()), 25, d["id"])
                self.assertIn(".", d["description"])

    def test_weights_must_total_100(self):
        from wlm.questionnaire.server import save_domains

        with self.assertRaises(ValueError) as ctx:
            save_domains({"cost_housing": 50.0}, [])
        self.assertIn("total 100", str(ctx.exception))

    def test_locked_weights_survive_elicitation(self):
        """Locking is an explicit, recorded override of Principle 7 — not a silent one."""
        from wlm.elicit import blend

        blended, _ = blend({"safety": 10.0, "cost_housing": 90.0}, {"cost_housing": 100.0})
        locked = {"safety": 25.0}
        blended.update(locked)
        self.assertEqual(blended["safety"], 25.0)


class TestSensitiveOptIn(unittest.TestCase):
    """Principle 10, in both directions.

    The first version stored the option labels and nothing read them. Opting in changed
    nothing, while allocating budget points to the sensitive domain gave it weight with no
    opt-in at all — and `make audit` still reported Principle 10 as passing, because it
    only inspected the default weight in config/domains.yaml.
    """

    BUDGET = {
        "cost_housing": 15, "climate_environment": 15, "urban_form": 10,
        "career_economy": 10, "education": 5, "family_childcare": 5,
        "health_care": 10, "safety": 10, "recreation_lifestyle": 10,
        "community_culture": 5, "sensitive": 5,
    }

    @classmethod
    def setUpClass(cls):
        cls.questions = generate.build()
        cls.registry = {
            i["id"]: i
            for i in yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]
        }

    def _profile(self, opt_in=None, sensitive_points=5):
        from wlm.profile import build_profile

        session = Session(person="emil", sessions_dir=Path(tempfile.mkdtemp()))
        session.answers["budget_allocation"] = {**self.BUDGET, "sensitive": sensitive_points}
        if opt_in is not None:
            session.answers["q_sensitive_optin"] = opt_in
        return build_profile(session, self.questions)

    def test_budget_points_alone_cannot_switch_the_sensitive_domain_on(self):
        """The bug: five points allocated, never opted in, and it reached the ranking."""
        profile = self._profile(opt_in=None)
        self.assertEqual(profile["sensitive_indicators"], [])
        self.assertEqual(profile["domain_weights"].get("sensitive"), 0.0)

    def test_dropping_the_weight_is_reported_not_silent(self):
        profile = self._profile(opt_in=None)
        notes = " ".join(profile["quality"]["weighting_notes"])
        self.assertIn("sensitive", notes)
        self.assertIn("5", notes, "the forfeited points should be named")

    def test_opting_in_actually_reaches_the_profile(self):
        """The other direction: opting in used to change nothing at all."""
        profile = self._profile(opt_in=["Political climate"])
        self.assertEqual(profile["sensitive_indicators"], ["sens_partisan_lean"])
        self.assertGreater(profile["domain_weights"]["sensitive"], 0)

    def test_opting_into_one_does_not_switch_on_the_others(self):
        profile = self._profile(opt_in=["Political climate"])
        for other in ("sens_religious_adherence", "sens_foreign_born_share"):
            self.assertNotIn(other, profile["sensitive_indicators"])

    def test_none_of_these_is_treated_as_opting_out(self):
        profile = self._profile(opt_in=["None of these"])
        self.assertEqual(profile["sensitive_indicators"], [])
        self.assertEqual(profile["domain_weights"].get("sensitive"), 0.0)

    def test_every_option_names_the_indicator_it_switches_on(self):
        """Rewording an option must not silently disconnect it from its indicator."""
        question = next(
            q for q in self.questions
            if q.get("maps_to", {}).get("kind") == "sensitive_opt_in"
        )
        mapping = question["option_indicators"]
        for option in question["options"]:
            self.assertIn(option, mapping, f"option {option!r} maps to no indicator")
            target = mapping[option]
            if target is not None:
                self.assertIn(target, self.registry)
                self.assertTrue(self.registry[target].get("sensitive"), target)

    def test_an_unmapped_option_raises_rather_than_being_dropped(self):
        from wlm.profile import OptInError, resolve_sensitive_opt_in

        with self.assertRaises(OptInError):
            resolve_sensitive_opt_in(self.questions, {"q_sensitive_optin": ["Something else"]})

    def test_the_engine_excludes_sensitive_indicators_nobody_opted_into(self):
        """The weight floor means a zero weight still counts; only absence is opting out."""
        import polars as pl

        from wlm.paths import PROCESSED
        from wlm.scoring.engine import score

        features = pl.read_parquet(PROCESSED / "features.parquet").filter(
            pl.col("geo_level") == "county"
        )
        _, report = score(features, self.registry, {"domain_weights": {"sensitive": 100.0}})
        excluded = " ".join(report.warnings)
        for indicator in ("sens_partisan_lean", "sens_foreign_born_share"):
            self.assertIn(indicator, excluded)


class TestKnockoutsReduceToNumbers(unittest.TestCase):
    """A deal-breaker is compared against a number, so every route to one must produce one.

    `q_max_hub_drive` asked a sensible human question — "the longest drive to an airport
    you'd accept" — and mapped it straight to a mileage threshold. The answer reached the
    scoring engine as the string "Under an hour", failed to parse, and the filter never ran.
    Found by driving two complete profiles through the real API for the first time.
    """

    @classmethod
    def setUpClass(cls):
        cls.questions = generate.build()
        cls.knockouts = [
            q for q in cls.questions if q.get("maps_to", {}).get("kind") == "knockout"
        ]

    def test_there_is_at_least_one_knockout_to_check(self):
        self.assertTrue(self.knockouts)

    def test_every_knockout_answer_can_become_a_number(self):
        for q in self.knockouts:
            with self.subTest(question=q["id"]):
                if q["type"] == "number":
                    continue
                values = q.get("option_values")
                self.assertIsNotNone(
                    values,
                    f"{q['id']} offers phrases but declares no option_values, so its "
                    "deal-breaker can never be applied",
                )
                for option in q["options"]:
                    self.assertIn(option, values, f"{q['id']}: {option!r} has no value")
                    target = values[option]
                    if target is not None:
                        self.assertIsInstance(target, (int, float))

    def test_a_phrase_answer_is_translated_before_it_reaches_the_engine(self):
        from wlm.profile import build_profile

        session = Session(person="emil", sessions_dir=Path(tempfile.mkdtemp()))
        session.answers["q_max_hub_drive"] = "Under an hour"
        rule = next(
            k for k in build_profile(session, self.questions)["knockouts"]
            if k["from"] == "q_max_hub_drive"
        )
        self.assertIsInstance(rule["value"], float)
        self.assertEqual(rule["value"], 55.0)

    def test_no_limit_produces_no_knockout_at_all(self):
        from wlm.profile import build_profile

        session = Session(person="emil", sessions_dir=Path(tempfile.mkdtemp()))
        session.answers["q_max_hub_drive"] = "Distance doesn't matter much"
        rules = build_profile(session, self.questions)["knockouts"]
        self.assertFalse([k for k in rules if k["from"] == "q_max_hub_drive"])

    def test_an_untranslatable_answer_raises_rather_than_being_skipped(self):
        from wlm.profile import OptInError, build_profile

        session = Session(person="emil", sessions_dir=Path(tempfile.mkdtemp()))
        session.answers["q_max_hub_drive"] = "Whenever, honestly"
        with self.assertRaises(OptInError):
            build_profile(session, self.questions)
