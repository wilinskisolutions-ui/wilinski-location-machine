"""The report layer, and the one thing it must never do.

Principle 9 says every ranking ships with a sensitivity band. The failure it guards against
is not a forgotten column — it is a confident-looking list of ranks that a small change in
weights would reshuffle. So the requirement is enforced by refusal rather than by review,
and these tests exist to prove the refusal actually fires.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import polars as pl
import yaml

from wlm.paths import CONFIG
from wlm.report.build import (
    COIN_FLIP_SPREAD,
    Ranking,
    Report,
    UnbandedRankingError,
    _effective_weights,
    explain,
    render_html,
    require_bands,
)

REGISTRY = {
    i["id"]: i for i in yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]
}


def _banded_row(**over) -> dict:
    row = {
        "geo_id": "42043", "name": "Somewhere, PA", "population": 120_000,
        "rank": 3, "score": 0.71, "rank_p05": 2, "rank_p95": 9, "rank_spread": 7,
        "coin_flip": False, "worst_domain": "safety", "worst_domain_score": 0.31,
        "coverage": 0.92, "contributors": [], "drags": [],
    }
    row.update(over)
    return row


class TestBandGuard(unittest.TestCase):
    """Principle 9, made structural."""

    def test_a_ranking_without_band_columns_is_refused(self):
        unbanded = pl.DataFrame({"geo_id": ["42043", "12086"], "rank": [1, 2]})
        with self.assertRaises(UnbandedRankingError) as ctx:
            require_bands(unbanded, what="county ranking")
        self.assertIn("rank_p05", str(ctx.exception))
        self.assertIn("Principle 9", str(ctx.exception))

    def test_a_ranking_with_a_null_band_is_refused(self):
        """The likelier failure: bands were computed, but not for every row."""
        partial = pl.DataFrame(
            {
                "geo_id": ["42043", "12086"],
                "rank": [1, 2],
                "rank_p05": [1, None],
                "rank_p95": [4, None],
            }
        )
        with self.assertRaises(UnbandedRankingError) as ctx:
            require_bands(partial, what="county ranking")
        self.assertIn("1 of 2 rows have no band", str(ctx.exception))
        self.assertIn("12086", str(ctx.exception))

    def test_a_fully_banded_ranking_passes(self):
        banded = pl.DataFrame(
            {"geo_id": ["42043"], "rank": [1], "rank_p05": [1], "rank_p95": [6]}
        )
        require_bands(banded, what="county ranking")  # must not raise

    def test_an_empty_ranking_is_not_an_error(self):
        require_bands(pl.DataFrame(), what="county ranking")

    def test_rendering_refuses_unbanded_rows_too(self):
        """The guard runs again at render time: assembly is not the only way in."""
        report = Report(person="emil", generated_at="now", basis="test")
        report.counties.rows = [_banded_row()]
        del report.counties.rows[0]["rank_p05"]
        with self.assertRaises(UnbandedRankingError):
            render_html(report)

    def test_there_is_no_flag_that_turns_the_guard_off(self):
        """A guard with an escape hatch is a habit, not a guarantee."""
        import inspect

        signature = inspect.signature(require_bands)
        self.assertEqual(set(signature.parameters) - {"frame"}, {"what"})


class TestRendering(unittest.TestCase):
    def _report(self, rows) -> Report:
        report = Report(
            person="emil", generated_at="2026-08-23T00:00:00+00:00",
            basis="trade-off choices", draws=120,
            weights={"climate_environment": 20.0, "safety": 12.0},
        )
        report.counties = Ranking("county", rows, sum(1 for r in rows if r["coin_flip"]))
        return report

    def test_the_band_is_drawn_not_just_stated(self):
        page = render_html(self._report([_banded_row()]))
        self.assertIn('class="band"', page)
        self.assertIn("anywhere from", page)

    def test_a_wide_band_is_labelled_a_coin_flip(self):
        wide = _banded_row(rank_p05=4, rank_p95=200, rank_spread=196, coin_flip=True)
        page = render_html(self._report([wide]))
        self.assertIn("coin flip", page)

    def test_a_narrow_band_is_not_labelled_a_coin_flip(self):
        page = render_html(self._report([_banded_row()]))
        self.assertNotIn("coin flip<", page)

    def test_drags_are_shown_alongside_contributors(self):
        """A place's worst feature is often the decisive one; it is never omitted."""
        row = _banded_row(
            contributors=[{"label": "January mean temperature", "value": 52.0, "unit": "F"}],
            drags=[{"label": "Violent crime rate", "value": 640.0, "unit": ""}],
        )
        page = render_html(self._report([row]))
        self.assertIn("Why it is here", page)
        self.assertIn("What is wrong with it", page)
        self.assertIn("Violent crime rate", page)

    def test_the_page_says_what_it_does_not_know(self):
        page = render_html(self._report([_banded_row()]))
        self.assertIn("does not know", page)
        self.assertIn("Weights used", page)

    def test_the_page_is_theme_aware_and_self_contained(self):
        page = render_html(self._report([_banded_row()]))
        self.assertIn("prefers-color-scheme", page)
        self.assertIn('data-theme="dark"', page)
        for remote in ("http://", "https://", "src="):
            self.assertNotIn(remote, page, "the page must not reach for anything external")

    def test_a_placeholder_ranking_says_so_unmissably(self):
        """A ranking built on weights nobody chose looks exactly like one built on their
        answers. Principle 7 is only real if the page cannot be mistaken for the other."""
        report = self._report([_banded_row()])
        report.placeholder = True
        page = render_html(report)
        self.assertIn("These are not your weights", page)
        self.assertIn("make questionnaire", page)

    def test_a_real_ranking_carries_no_such_warning(self):
        page = render_html(self._report([_banded_row()]))
        self.assertNotIn("These are not your weights", page)

    def test_html_in_a_place_name_cannot_break_the_page(self):
        page = render_html(self._report([_banded_row(name="<script>x</script>")]))
        self.assertNotIn("<script>x", page)
        self.assertIn("&lt;script&gt;", page)


class TestExplanations(unittest.TestCase):
    def test_weight_is_spread_across_a_domains_indicators(self):
        profile = {"domain_weights": {"safety": 30.0}, "indicator_weights": {}}
        effective = _effective_weights(REGISTRY, profile)
        safety = [i for i, e in REGISTRY.items() if e["domain"] == "safety"]
        self.assertAlmostEqual(sum(effective[i] for i in safety), 30.0, places=6)

    def test_an_elicited_indicator_outweighs_an_untouched_one(self):
        """Otherwise a domain weight is diluted evenly over everything it contains — the
        bug that gave a couple asking for 50-70F winters places averaging 48F."""
        safety = sorted(i for i, e in REGISTRY.items() if e["domain"] == "safety")
        profile = {
            "domain_weights": {"safety": 30.0},
            "indicator_weights": {safety[0]: 2.0},
        }
        effective = _effective_weights(REGISTRY, profile)
        self.assertGreater(effective[safety[0]], effective[safety[1]] * 5)

    def test_only_weighted_domains_appear_in_an_explanation(self):
        desir = pl.DataFrame(
            {
                "geo_id": ["42043", "42043"],
                "indicator_id": ["safety_traffic_fatality_rate", "sens_foreign_born_share"],
                "value": [12.0, 0.07],
                "desirability": [0.9, 0.2],
                "vs_baseline": [10.0, -5.0],
            }
        )
        effective = _effective_weights(REGISTRY, {"domain_weights": {"safety": 100.0}})
        best, worst = explain(desir, "42043", effective, REGISTRY)
        mentioned = {r["indicator"] for r in best + worst}
        self.assertNotIn("sens_foreign_born_share", mentioned)

    def test_a_coin_flip_threshold_exists_and_is_not_absurd(self):
        self.assertGreater(COIN_FLIP_SPREAD, 5)
        self.assertLess(COIN_FLIP_SPREAD, 500)


class TestAgainstRealData(unittest.TestCase):
    """The full path, on the real universe. Slow, so one pass covers it."""

    @classmethod
    def setUpClass(cls):
        from wlm.paths import FEATURES

        if not Path(FEATURES).exists():
            raise unittest.SkipTest("features.parquet not built")

        from wlm.report.build import assemble

        domains = yaml.safe_load((CONFIG / "domains.yaml").read_text())["domains"]
        cls.profile = {
            "person": "placeholder",
            "method": "placeholder weights",
            "domain_weights": {
                d["id"]: float(d["default_weight"])
                for d in domains
                if d.get("scoring") and d["default_weight"] > 0
            },
        }
        cls.report = assemble(cls.profile, draws=25, show=5, top_counties=10)

    def test_it_ranks_counties_and_towns_inside_them(self):
        self.assertTrue(self.report.counties.rows)
        self.assertTrue(self.report.places.rows)

    def test_every_published_row_carries_a_real_band(self):
        for ranking in (self.report.counties, self.report.places):
            for row in ranking.rows:
                self.assertIsNotNone(row["rank_p05"], row["name"])
                self.assertIsNotNone(row["rank_p95"], row["name"])
                self.assertLessEqual(row["rank_p05"], row["rank_p95"], row["name"])

    def test_harrisburg_is_scored_but_never_offered_as_a_destination(self):
        from wlm.baseline import BASELINE_COUNTY, BASELINE_PLACE

        listed = {r["geo_id"] for r in self.report.counties.rows + self.report.places.rows}
        self.assertNotIn(BASELINE_COUNTY, listed)
        self.assertNotIn(BASELINE_PLACE, listed)
        self.assertTrue(self.report.baseline, "the baseline should still be reported")

    def test_every_place_gets_reasons_and_a_weakest_area(self):
        for row in self.report.counties.rows:
            self.assertTrue(row["contributors"], f"{row['name']} has no stated reason")
            self.assertTrue(row["worst_domain"])

    def test_the_rendered_page_names_real_places(self):
        page = render_html(self.report)
        self.assertIn(self.report.counties.rows[0]["name"], page)


if __name__ == "__main__":
    unittest.main()
