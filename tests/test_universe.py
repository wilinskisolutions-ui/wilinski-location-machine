"""The universe must be exactly what it claims to be.

Every count here corresponds to a deliberately-constructed case in the fixtures, so a
regression shows up as a specific wrong number rather than a vague failure.
"""

from __future__ import annotations

import unittest

from wlm.geo import GeoError, PlaceCountyCrosswalk, classify_place, county_geoid, is_in_scope, place_geoid
from wlm.ingest.census_acs import population_map
from wlm.universe.build import build

from conftest import FIXTURES


def _build(write=False):
    pop = population_map(
        FIXTURES / "acs_population_places.json", FIXTURES / "acs_population_counties.json"
    )
    xw = PlaceCountyCrosswalk.from_file(FIXTURES / "place_county_crosswalk.csv")
    return build(
        counties_file=FIXTURES / "gazetteer_counties.txt",
        places_file=FIXTURES / "gazetteer_places.txt",
        population=pop,
        crosswalk=xw,
        write=write,
    )


class TestGeoIdentifiers(unittest.TestCase):
    def test_pads_lost_leading_zeros(self):
        # Spreadsheets strip these constantly; an unpadded id joins to nothing.
        self.assertEqual(county_geoid(6, 37), "06037")
        self.assertEqual(place_geoid(37, "12000"), "3712000")

    def test_rejects_non_numeric_and_overlong(self):
        with self.assertRaises(GeoError):
            county_geoid("XX", 37)
        with self.assertRaises(GeoError):
            county_geoid(6, "12345")

    def test_territories_are_out_of_scope(self):
        self.assertFalse(is_in_scope("72127"))  # Puerto Rico
        self.assertTrue(is_in_scope("37183"))
        self.assertTrue(is_in_scope("11001"))  # DC is in scope

    def test_cdp_classification(self):
        self.assertEqual(classify_place("57"), "cdp")
        self.assertEqual(classify_place("25"), "incorporated")
        self.assertEqual(classify_place(None), "incorporated")


class TestCrosswalk(unittest.TestCase):
    def test_weights_normalize_per_place(self):
        xw = PlaceCountyCrosswalk.from_rows(
            [
                {"place_geoid": "3712000", "county_geoid": "37183", "weight": 82000},
                {"place_geoid": "3712000", "county_geoid": "37101", "weight": 18000},
            ]
        )
        weights = {ln.county_geoid: ln.weight for ln in xw.counties_for("3712000")}
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["37183"], 0.82)

    def test_primary_county_is_the_largest_share(self):
        xw = PlaceCountyCrosswalk.from_file(FIXTURES / "place_county_crosswalk.csv")
        self.assertEqual(xw.primary_county("3712000"), "37183")

    def test_zero_weights_split_evenly_rather_than_drop_the_place(self):
        xw = PlaceCountyCrosswalk.from_rows(
            [
                {"place_geoid": "9900001", "county_geoid": "11111", "weight": 0},
                {"place_geoid": "9900001", "county_geoid": "22222", "weight": 0},
            ]
        )
        self.assertEqual([round(ln.weight, 3) for ln in xw.counties_for("9900001")], [0.5, 0.5])

    def test_unmatched_places_are_reported(self):
        xw = PlaceCountyCrosswalk.from_file(FIXTURES / "place_county_crosswalk.csv")
        self.assertEqual(xw.unmatched(["3712000", "3713000"]), ["3713000"])


class TestUniverseBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.universe, cls.weights, cls.report = _build()

    def test_counties_exclude_territories(self):
        # 11 county rows in the fixture, one of them Puerto Rico.
        self.assertEqual(self.report.counties, 10)

    def test_population_floor_is_applied(self):
        self.assertEqual(self.report.places_below_floor, 1)  # Little Hollow, 4,000

    def test_place_without_population_is_counted_not_assumed(self):
        # Millford has no ACS row. It must be reported, not treated as zero-population.
        self.assertEqual(self.report.places_no_population, 1)

    def test_name_lookup_failure_falls_back_to_nearest_centroid(self):
        # Nowhere city has no crosswalk entry but does have coordinates. Dropping it would
        # be worse than an approximate county, so it is rescued -- and counted, never
        # silently. Connecticut's 2022 switch to planning regions is the real case.
        self.assertEqual(self.report.places_county_by_centroid, 1)

    def test_place_that_cannot_be_placed_at_all_is_excluded_and_warned(self):
        # Voidtown has neither a crosswalk entry nor coordinates: nothing can locate it.
        self.assertEqual(self.report.places_unmatched_county, 1)
        self.assertTrue(any("no county match" in w for w in self.report.warnings))

    def test_cdps_are_included(self):
        # Excluding unincorporated communities would be a systematic coverage bias against
        # exactly the overlooked places this project exists to surface.
        self.assertEqual(self.report.cdp, 2)
        self.assertEqual(self.report.incorporated, 7)  # includes centroid-rescued Nowhere

    def test_expected_universe_size(self):
        self.assertEqual(self.report.places_kept, 9)
        self.assertEqual(self.universe.height, 19)

    def test_geo_ids_are_unique_and_correctly_shaped(self):
        self.assertEqual(self.universe["geo_id"].n_unique(), self.universe.height)
        for row in self.universe.iter_rows(named=True):
            want = 5 if row["geo_level"] == "county" else 7
            self.assertEqual(len(row["geo_id"]), want, row)

    def test_multi_county_place_keeps_both_shares(self):
        self.assertEqual(self.report.places_multi_county, 1)
        rows = self.weights.filter(self.weights["place_geoid"] == "3712000")
        self.assertEqual(rows.height, 2)
        self.assertAlmostEqual(rows["weight"].sum(), 1.0)

    def test_counties_are_their_own_county_geoid(self):
        counties = self.universe.filter(self.universe["geo_level"] == "county")
        self.assertTrue((counties["geo_id"] == counties["county_geoid"]).all())

    def test_no_territory_rows_survive(self):
        self.assertFalse(any(g.startswith("72") for g in self.universe["geo_id"]))


if __name__ == "__main__":
    unittest.main()
