"""Curves and features.

The band-versus-percentile distinction gets the most attention here because it is the one
that fails silently — the output still looks like a ranking when it is wrong.
"""

from __future__ import annotations

import unittest

import polars as pl

from wlm.features.build import build as build_features
from wlm.features.curves import CurveError, desirability, ideal_band, ideal_point
from wlm.geo import PlaceCountyCrosswalk
from wlm.ingest import census_acs, fema_nri, usda_amenities
from wlm.universe.build import build as build_universe

from conftest import FIXTURES

POP_BAND = {"lo": 25000, "hi": 250000, "shoulder": 50000, "shoulder_lo": 8000}


class TestCurves(unittest.TestCase):
    def test_monotone_curves_read_the_percentile(self):
        self.assertAlmostEqual(desirability(curve="higher_better", value=1, percentile=0.8), 0.8)
        self.assertAlmostEqual(desirability(curve="lower_better", value=1, percentile=0.8), 0.2)

    def test_band_reads_the_raw_value_not_the_percentile(self):
        # A 4M-person county is at the top of the percentile distribution and still wrong.
        got = desirability(curve="ideal_band", value=4_000_000, percentile=1.0, params=POP_BAND)
        self.assertEqual(got, 0.0)
        self.assertEqual(
            desirability(curve="higher_better", value=4_000_000, percentile=1.0), 1.0
        )

    def test_band_is_flat_inside_the_band(self):
        for pop in (25000, 120000, 250000):
            self.assertEqual(ideal_band(pop, **POP_BAND), 1.0)

    def test_asymmetric_shoulders_treat_too_small_and_too_large_differently(self):
        # Population is effectively logarithmic; a symmetric shoulder scored a 500-person
        # village 0.51, which is not what "too small" means.
        self.assertEqual(ideal_band(500, **POP_BAND), 0.0)
        self.assertGreater(ideal_band(20000, **POP_BAND), 0.0)

    def test_band_rejects_inverted_bounds_and_bad_shoulders(self):
        with self.assertRaises(CurveError):
            ideal_band(5, lo=10, hi=1, shoulder=1)
        with self.assertRaises(CurveError):
            ideal_band(5, lo=1, hi=10, shoulder=0)

    def test_ideal_point_peaks_at_the_target(self):
        self.assertAlmostEqual(ideal_point(50, target=50, tol=10), 1.0)
        self.assertLess(ideal_point(80, target=50, tol=10), 0.01)

    def test_missing_input_yields_none_never_zero(self):
        # A place with no data is not a place that scored badly (Principle 6).
        self.assertIsNone(desirability(curve="ideal_band", value=None, percentile=0.9, params=POP_BAND))
        self.assertIsNone(desirability(curve="higher_better", value=5, percentile=None))

    def test_unknown_curve_is_rejected(self):
        with self.assertRaises(CurveError):
            desirability(curve="vibes", value=1, percentile=0.5)


class TestFeatureBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pop = census_acs.population_map(
            FIXTURES / "acs_population_places.json", FIXTURES / "acs_population_counties.json"
        )
        xw = PlaceCountyCrosswalk.from_file(FIXTURES / "place_county_crosswalk.csv")
        cls.universe, _, _ = build_universe(
            counties_file=FIXTURES / "gazetteer_counties.txt",
            places_file=FIXTURES / "gazetteer_places.txt",
            population=pop,
            crosswalk=xw,
            write=False,
        )
        frames = [
            census_acs.ingest([FIXTURES / "acs_population_places.json"], vintage="2020-2024"),
            fema_nri.ingest(FIXTURES / "fema_nri_counties.csv"),
            usda_amenities.ingest(FIXTURES / "usda_natural_amenities.csv"),
        ]
        cls.features, cls.coverage, cls.report = build_features(
            universe=cls.universe, long_frames=frames, write=False
        )

    def test_percentiles_span_zero_to_one(self):
        wildfire = self.features.filter(pl.col("indicator_id") == "hazard_nri_wildfire")
        self.assertAlmostEqual(wildfire["percentile"].min(), 0.0)
        self.assertAlmostEqual(wildfire["percentile"].max(), 1.0)

    def test_percentile_ordering_follows_value_ordering(self):
        w = self.features.filter(pl.col("indicator_id") == "hazard_nri_wildfire").sort("value")
        self.assertEqual(list(w["percentile"]), sorted(w["percentile"]))

    def test_missing_value_has_no_percentile(self):
        nulls = self.features.filter(pl.col("value").is_null())
        self.assertGreater(nulls.height, 0)
        self.assertEqual(nulls["percentile"].null_count(), nulls.height)

    def test_missing_data_lowers_coverage_rather_than_scoring_zero(self):
        # Linn County's natural-amenities cell is blank in the fixture. It must show up as
        # less-covered, not as a county with terrible amenities.
        linn = self.coverage.filter(pl.col("geo_id") == "19113")["coverage"][0]
        wake = self.coverage.filter(pl.col("geo_id") == "37183")["coverage"][0]
        self.assertLess(linn, wake)
        amenity = self.features.filter(
            (pl.col("geo_id") == "19113") & (pl.col("indicator_id") == "env_natural_amenities")
        )
        self.assertIsNone(amenity["value"][0])

    def test_every_universe_row_gets_a_coverage_figure(self):
        self.assertEqual(self.coverage.height, self.universe.height)
        self.assertEqual(self.coverage["coverage"].null_count(), 0)

    def test_rows_outside_the_universe_are_dropped_and_reported(self):
        self.assertGreater(self.report.rows_dropped_no_geo, 0)
        self.assertTrue(self.report.warnings)

    def test_nulls_are_preserved_through_the_whole_chain(self):
        self.assertGreater(self.report.null_values, 0)


if __name__ == "__main__":
    unittest.main()
