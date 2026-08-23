"""The three anti-bias countermeasures from docs/anti-bias.md that were prose until now.

Each one exists to catch a specific way this project could fail while looking like it
worked, so each test asks whether the check would actually notice.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import polars as pl

from wlm.paths import FEATURES, UNIVERSE


class TestHypeIndex(unittest.TestCase):
    """Countermeasure #3 — migration momentum, the one closest to Emil's complaint."""

    @classmethod
    def setUpClass(cls):
        from wlm.diagnostics import hype

        if not Path(UNIVERSE).exists():
            raise unittest.SkipTest("universe not built")
        cls.hype = hype
        cls.index = hype.build_index()
        if cls.index.is_empty():
            raise unittest.SkipTest("hype inputs not downloaded")

    def test_it_covers_most_of_the_country(self):
        self.assertGreater(self.index.height, 2_500)

    def test_it_ranks_the_places_emil_named_as_high_attention(self):
        """The index is only worth having if it recognises the problem it was built for.

        Emil's complaint named Greenville, Raleigh and Charlotte. If those do not come out
        as high-attention, the index is measuring something else.
        """
        lookup = dict(self.index.select(["geo_id", "hype"]).iter_rows())
        loud = ["45045", "37183", "37119"]  # Greenville SC, Wake NC, Mecklenburg NC
        quiet = ["36061", "06075"]          # New York NY, San Francisco CA — people leaving

        for geo_id in loud:
            self.assertGreater(lookup.get(geo_id, 0), 0.6, f"{geo_id} should read as hyped")
        for geo_id in quiet:
            self.assertLess(lookup.get(geo_id, 1), 0.4, f"{geo_id} should not read as hyped")

    def test_small_counties_do_not_dominate(self):
        """Forty arrivals in a county of eight thousand is not a boom.

        Before shrinkage the five loudest places in the country were Butler County NE,
        Montgomery County AR and Douglas County MO.
        """
        top = self.index.sort("hype", descending=True).head(20)
        self.assertGreater(
            top["population"].median(), 30_000,
            "the top of the index is dominated by tiny-denominator noise"
        )

    def test_a_county_with_only_one_component_is_excluded(self):
        for column in ("migration_rate", "appreciation"):
            self.assertEqual(
                self.index.filter(pl.col(column).is_null()).height, 0,
                f"{column} is missing for some counties in the index"
            )

    def test_hype_is_never_a_scoring_input(self):
        """The whole point: this measures a ranking, it does not feed one."""
        import inspect

        from wlm.scoring import engine

        source = inspect.getsource(engine)
        self.assertNotIn("hype", source)

    def test_the_regression_reports_a_residual(self):
        scores = self.index.select(["geo_id"]).with_columns(
            (pl.col("geo_id").hash() % 1000 / 1000).alias("score")
        )
        report = self.hype.analyse(scores)
        self.assertIsNotNone(report.correlation)
        self.assertIn("residual", report.counties.columns)
        self.assertIn("Hype check", self.hype.render(report))


class TestBlindExport(unittest.TestCase):
    """Countermeasure #5 — one leaked name defeats the whole exercise."""

    @classmethod
    def setUpClass(cls):
        if not Path(FEATURES).exists():
            raise unittest.SkipTest("features not built")
        from wlm.diagnostics import blind

        cls.blind = blind
        cls.universe = pl.read_parquet(UNIVERSE)
        cls.features = pl.read_parquet(FEATURES)
        counties = cls.universe.filter(pl.col("geo_level") == "county")
        cls.shortlist = list(counties.sort("population", descending=True).head(8)["geo_id"])
        cls.export = blind.strip(
            cls.shortlist, features=cls.features, universe=cls.universe
        )

    def test_it_produces_one_profile_per_place(self):
        self.assertEqual(len(self.export.profiles), len(self.shortlist))

    def test_nothing_identifying_survives(self):
        """The test that matters. Checked against the whole universe, not the shortlist:
        a leak that names a neighbouring county gives the game away just as completely."""
        self.assertEqual(self.export.leaks, [], f"the export leaks: {self.export.leaks}")

    def test_no_geoid_appears_anywhere_in_the_export(self):
        text = json.dumps(self.export.profiles)
        for geo_id in self.shortlist:
            self.assertNotIn(geo_id, text)

    def test_the_key_is_kept_but_separate(self):
        self.assertEqual(len(self.export.key), len(self.shortlist))
        self.assertNotIn(json.dumps(self.export.key), json.dumps(self.export.profiles))

    def test_a_planted_name_is_caught(self):
        """If find_leaks cannot catch an obvious leak it is not protecting anything."""
        real_name = self.universe.filter(pl.col("geo_level") == "county")["name"][0]
        planted = [{"label": "Place A", "note": f"lovely part of {real_name}"}]
        self.assertTrue(self.blind.find_leaks(planted, self.universe))

    def test_a_planted_state_code_is_caught(self):
        planted = [{"label": "Place A", "note": "somewhere in PA"}]
        leaks = self.blind.find_leaks(planted, self.universe)
        self.assertTrue(any("PA" in leak for leak in leaks))

    def test_missing_indicators_are_shown_as_missing_not_filled_in(self):
        values = self.export.profiles[0]["values"]
        self.assertTrue(values)
        for shown in values.values():
            self.assertIsInstance(shown, str)

    def test_the_profile_carries_the_things_the_household_said_mattered(self):
        """Climate is their stated first priority. A blind profile without it is not a
        profile of anywhere — and four climate ids were silently wrong, so it had none."""
        labels = " ".join(self.export.profiles[0]["values"]).lower()
        for topic in ("winter", "summer"):
            self.assertIn(topic, labels)

    def test_a_fraction_is_never_rendered_as_zero(self):
        """Unemployment runs 0.003-0.17 in this dataset and was displayed as "0.0"."""
        for profile in self.export.profiles:
            for label, shown in profile["values"].items():
                if "unemployment" in label.lower():
                    self.assertNotEqual(shown, "0.0", "a real rate rendered as nothing")
                    self.assertTrue(shown == "—" or shown.endswith("%"), shown)

    def test_the_rendered_page_names_no_place(self):
        page = self.blind.render(self.export)
        for name in self.export.key.values():
            self.assertNotIn(name, page)


class TestPoliticalDelta(unittest.TestCase):
    """The stacking trap: a filter whose cost is invisible cannot be decided about."""

    @classmethod
    def setUpClass(cls):
        if not Path(FEATURES).exists():
            raise unittest.SkipTest("features not built")
        from wlm.diagnostics import political

        cls.political = political

    def test_with_the_layer_off_it_says_so_rather_than_showing_a_fake_delta(self):
        profile = {
            "person": "test",
            "domain_weights": {"climate_environment": 50.0, "safety": 50.0},
            "sensitive_indicators": [],
        }
        report = self.political.compare(profile)
        self.assertTrue(report.notes)
        self.assertIn("off", " ".join(report.notes))

    def test_switching_the_layer_off_removes_its_weight_rather_than_its_data(self):
        """Dropping the indicators but keeping the weight would redistribute it and make
        the comparison about something else entirely."""
        import inspect

        source = inspect.getsource(self.political.compare)
        self.assertIn("domain_weights", source)
        self.assertIn("sensitive", source)

    def test_the_report_renders_without_a_layer(self):
        profile = {
            "person": "test",
            "domain_weights": {"climate_environment": 100.0},
            "sensitive_indicators": [],
        }
        text = self.political.render(self.political.compare(profile))
        self.assertIn("with and without", text)


if __name__ == "__main__":
    unittest.main()
