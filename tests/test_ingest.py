"""The ingest contract: one shape, registry-enforced, missing preserved."""

from __future__ import annotations

import unittest

from wlm.ingest.base import LONG_COLUMNS, IngestError, emit, registry
from wlm.ingest import census_acs, fema_nri, usda_amenities

from conftest import FIXTURES


class TestEmitContract(unittest.TestCase):
    def setUp(self):
        self.reg = registry()

    def _emit(self, **over):
        rec = {
            "geo_level": "county",
            "geo_id": "37183",
            "indicator_id": "hazard_nri_composite",
            "value": 12.5,
        }
        rec.update(over)
        return emit([rec], source_file="f.csv", vintage="2023", reg=self.reg)

    def test_produces_the_common_long_form(self):
        self.assertEqual(self._emit().columns, LONG_COLUMNS)

    def test_unregistered_indicator_is_rejected(self):
        # Principle 2: a module cannot invent a dimension for one place and not another.
        with self.assertRaises(IngestError) as ctx:
            self._emit(indicator_id="vibes_score")
        self.assertIn("unregistered indicator_id", str(ctx.exception))
        self.assertIn("vibes_score", str(ctx.exception))

    def test_geo_level_must_match_the_registry(self):
        with self.assertRaises(IngestError) as ctx:
            self._emit(geo_level="place")
        self.assertIn("disagrees with the registry", str(ctx.exception))

    def test_malformed_geoid_is_rejected(self):
        with self.assertRaises(IngestError) as ctx:
            self._emit(geo_id="371")  # 3 chars where a county needs 5
        self.assertIn("malformed GEOIDs", str(ctx.exception))

    def test_none_value_is_preserved_as_null(self):
        df = self._emit(value=None)
        self.assertEqual(df.height, 1)
        self.assertIsNone(df["value"][0])

    def test_unparseable_value_becomes_null_not_zero(self):
        df = self._emit(value="not a number")
        self.assertIsNone(df["value"][0])


class TestCensusACS(unittest.TestCase):
    def test_builds_padded_geoids_from_components(self):
        rows = census_acs.parse_acs(FIXTURES / "acs_population_counties.json")
        level, geoid = census_acs.row_geoid(rows[0])
        self.assertEqual(level, "county")
        self.assertEqual(geoid, "37183")

    def test_population_map_drops_territories(self):
        pm = census_acs.population_map(
            FIXTURES / "acs_population_places.json", FIXTURES / "acs_population_counties.json"
        )
        self.assertNotIn("72127", pm)
        self.assertNotIn("7213100", pm)
        self.assertEqual(pm["3712000"], 50000)

    def test_absent_place_is_absent_not_zero(self):
        pm = census_acs.population_map(FIXTURES / "acs_population_places.json")
        self.assertIsNone(pm.get("2612400"))  # Millford has no ACS row


class TestFemaNri(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = fema_nri.ingest(FIXTURES / "fema_nri_counties.json")

    def test_emits_every_mapped_hazard(self):
        self.assertEqual(
            set(self.df["indicator_id"].unique()),
            {
                "hazard_nri_composite", "hazard_nri_hurricane", "hazard_nri_wildfire",
                "hazard_nri_heatwave", "hazard_nri_drought", "hazard_nri_tornado",
                "hazard_fatality_risk_per100k",
            },
        )

    def test_per_capita_risk_is_normalised_by_population(self):
        # FEMA's headline score ranks expected annual LOSS, which scales with how much
        # property a county contains. This one must not: it is loss of life over people.
        r = self.df.filter(
            (self.df["indicator_id"] == "hazard_fatality_risk_per100k")
            & (self.df["geo_id"] == "37183")
        )
        # (0.9 + 1.2 + 0.4 + 0.1) / 1,150,000 * 100,000
        self.assertAlmostEqual(r["value"][0], 2.6 / 1_150_000 * 100_000, places=6)

    def test_blank_hazard_cell_is_null_not_zero(self):
        # "no hurricane column value" and "zero hurricane risk" are different claims.
        hurricane = self.df.filter(self.df["indicator_id"] == "hazard_nri_hurricane")
        self.assertGreater(hurricane["value"].null_count(), 0)
        self.assertIsNone(hurricane.filter(hurricane["geo_id"] == "41029")["value"][0])

    def test_territory_rows_excluded(self):
        self.assertEqual(self.df.filter(self.df["geo_id"] == "72127").height, 0)


class TestUsdaAmenities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = usda_amenities.ingest(FIXTURES / "usda_natural_amenities.csv")

    def test_reads_spaced_column_headers(self):
        self.assertEqual(self.df.height, 10)

    def test_blank_scale_is_null(self):
        linn = self.df.filter(self.df["geo_id"] == "19113")
        self.assertIsNone(linn["value"][0])


if __name__ == "__main__":
    unittest.main()
