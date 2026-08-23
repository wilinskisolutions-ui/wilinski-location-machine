"""The logic test Emil asked for.

Component tests cannot answer "will this find the best place for us". This can: push
synthetic couples whose correct answer is known in advance through the whole chain —
choices to weights to ranking — and assert the output matches. A couple who says they want
warmth must get warm places. If they do not, something is broken and this finds it.
"""

from __future__ import annotations

import unittest

import numpy as np
import polars as pl
import yaml

from wlm.elicit import blend, domain_weights_from_choices, fit_choices, normalize_budget
from wlm.paths import CONFIG, PROCESSED
from wlm.scoring.engine import ScoreReport, apply_knockouts, joint, score

REGISTRY = {i["id"]: i for i in yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]}
DOMAIN_OF = {i: e["domain"] for i, e in REGISTRY.items()}


def counties() -> pl.DataFrame:
    return pl.read_parquet(PROCESSED / "features.parquet").filter(pl.col("geo_level") == "county")


def county_meta() -> pl.DataFrame:
    return pl.read_parquet(PROCESSED / "universe.parquet").filter(pl.col("geo_level") == "county")


def synthetic_choices(truth: dict[str, float], n: int = 240, seed: int = 4):
    """Generate choice answers from a known utility function."""
    rng = np.random.default_rng(seed)
    tasks, answers = [], {}
    for i in range(n):
        attrs, utility = [], 0.0
        for name, weight in truth.items():
            a, b = rng.normal(), rng.normal()
            attrs.append({"indicator": name, "a_raw": a, "b_raw": b})
            utility += weight * (a - b)
        tasks.append({"id": f"c{i}", "attributes": attrs})
        answers[f"c{i}"] = "A" if utility > 0 else "B"
    return tasks, answers


class TestEqualPreferences(unittest.TestCase):
    """Regression guard for the worst bug the audit found.

    Domain weight used to be the SUM of its indicator weights, so a domain contributing four
    attributes beat one contributing a single attribute regardless of preference. A
    respondent valuing everything equally produced climate 30.8 against healthcare 7.8 — a
    4x spread measuring the questionnaire's design rather than anyone's values.
    """

    def test_equal_preferences_give_roughly_equal_domain_weights(self):
        attrs = [
            "cost_home_value_median", "cost_rent_median_zori",
            "climate_temp_winter_mean", "climate_summer_high", "env_pm25_annual",
            "hazard_fatality_risk_per100k",           # climate contributes four
            "amen_food_drink_per10k", "amen_arts_rec_per10k",
            "health_life_expectancy",                  # healthcare contributes one
            "safety_traffic_fatality_rate",
        ]
        tasks, answers = synthetic_choices({a: 1.0 for a in attrs}, n=300)
        fit = fit_choices(tasks, answers, directions={a: "higher_better" for a in attrs})
        weights = domain_weights_from_choices(fit, DOMAIN_OF)

        spread = max(weights.values()) / min(weights.values())
        self.assertLess(spread, 1.6, f"attribute count is still inflating weight: {weights}")


class TestBlendDoesNotShrinkUncoveredDomains(unittest.TestCase):
    """The other critical bug: five of eleven domains had no trade-off attributes, so
    blending cut whatever the household said about them to 35%."""

    def test_uncovered_domain_keeps_its_stated_weight(self):
        stated = {"education": 40.0, "cost_housing": 60.0}
        revealed = {"cost_housing": 100.0}          # education never appeared in a trade-off
        blended, notes = blend(stated, revealed)
        self.assertGreater(blended["education"], 30.0, f"education was shrunk: {blended}")
        self.assertTrue(any("stated allocation alone" in n for n in notes))

    def test_dataless_domain_is_reported_not_swallowed(self):
        _, notes = blend({"education": 30.0, "cost_housing": 70.0}, {"cost_housing": 100.0},
                         data_less={"education"})
        self.assertTrue(any("CANNOT AFFECT THE RANKING" in n for n in notes))


class TestSyntheticCouples(unittest.TestCase):
    """Known preferences must produce recognisably correct rankings."""

    @classmethod
    def setUpClass(cls):
        cls.features = counties()
        meta = county_meta()
        cls.names = dict(zip(meta["geo_id"], meta["name"] + ", " + meta["state_usps"]))
        wide = (
            cls.features.pivot(values="value", index="geo_id", on="indicator_id")
            .join(meta.select(["geo_id", "population"]), on="geo_id")
        )
        cls.winter = dict(zip(wide["geo_id"], wide["climate_temp_winter_mean"]))
        cls.homes = dict(zip(wide["geo_id"], wide["cost_home_value_median"]))

    def _top(self, profile, n=40):
        result, _ = score(self.features, REGISTRY, profile)
        return list(result.head(n)["geo_id"])

    def _mean(self, geo_ids, table):
        vals = [table[g] for g in geo_ids if table.get(g) is not None]
        return sum(vals) / len(vals) if vals else None

    def test_a_couple_who_wants_warmth_gets_warm_places(self):
        # Within-domain weights matter here: climate holds sixteen indicators, so a bare
        # domain weight dilutes winter temperature to about 1/16 and the couple's stated
        # preference barely reaches the ranking. This is what indicator_weights fixes.
        emphasis = {"climate_temp_winter_mean": 0.7, "climate_winter_low": 0.2}
        warm = self._top({
            "domain_weights": {"climate_environment": 100.0},
            "indicator_weights": emphasis,
            "curve_overrides": {"climate_temp_winter_mean":
                                {"curve": "ideal_band",
                                 "curve_params": {"lo": 50, "hi": 70, "shoulder": 6}}},
        })
        cold = self._top({
            "domain_weights": {"climate_environment": 100.0},
            "indicator_weights": emphasis,
            "curve_overrides": {"climate_temp_winter_mean":
                                {"curve": "ideal_band",
                                 "curve_params": {"lo": 10, "hi": 28, "shoulder": 6}}},
        })
        warm_mean, cold_mean = self._mean(warm, self.winter), self._mean(cold, self.winter)
        self.assertIsNotNone(warm_mean)
        self.assertGreater(
            warm_mean, cold_mean + 15,
            f"warmth-seeking couple averaged {warm_mean:.0f}F, cold-seeking {cold_mean:.0f}F — "
            "the preference is not reaching the ranking",
        )

    def test_a_cost_driven_couple_gets_cheaper_places(self):
        cheap = self._top({"domain_weights": {"cost_housing": 100.0}})
        indifferent = self._top({"domain_weights": {"recreation_lifestyle": 100.0}})
        self.assertLess(
            self._mean(cheap, self.homes), self._mean(indifferent, self.homes),
            "a cost-driven couple did not get cheaper places",
        )

    def test_different_preferences_produce_different_rankings(self):
        a = set(self._top({"domain_weights": {"cost_housing": 100.0}}))
        b = set(self._top({"domain_weights": {"urban_form": 100.0}}))
        self.assertLess(len(a & b) / len(a), 0.5, "two opposite couples got the same answer")


class TestScoringMechanics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.features = counties()
        cls.profile = {"domain_weights": {"climate_environment": 50.0, "cost_housing": 50.0}}

    def test_one_catastrophic_domain_cannot_be_averaged_away(self):
        """Geometric aggregation is why a fatal weakness disqualifies a place."""
        from wlm.scoring.engine import _geometric

        balanced = _geometric([0.6, 0.6], [1, 1])
        lopsided = _geometric([1.0, 0.02], [1, 1])   # same arithmetic mean-ish, one disaster
        self.assertLess(lopsided, balanced)

    def test_thin_data_candidates_are_excluded_and_counted(self):
        result, report = score(self.features, REGISTRY, self.profile)
        self.assertTrue((result["weight_covered"] >= 0.8).all())

    def test_dataless_domain_raises_a_named_warning(self):
        _, report = score(
            self.features, REGISTRY,
            {"domain_weights": {"education": 50.0, "cost_housing": 50.0}},
        )
        self.assertTrue(any("education" in w and "cannot affect" in w for w in report.warnings))

    def test_knockouts_remove_places_and_report_the_cost(self):
        result, report = score(self.features, REGISTRY, self.profile)
        before = result.height
        after = apply_knockouts(
            result, self.features,
            [{"indicator": "cost_home_value_median", "op": "max", "value": 250_000}],
            report,
        )
        self.assertLess(after.height, before)
        self.assertEqual(report.knockouts[0]["removed"], before - after.height)

    def test_two_people_get_a_joint_score_and_a_disagreement_column(self):
        a, _ = score(self.features, REGISTRY, {"domain_weights": {"cost_housing": 100.0}})
        b, _ = score(self.features, REGISTRY, {"domain_weights": {"climate_environment": 100.0}})
        both = joint(a, b)
        self.assertIn("disagreement", both.columns)
        self.assertGreater(both["disagreement"].max(), 0.0)


if __name__ == "__main__":
    unittest.main()
