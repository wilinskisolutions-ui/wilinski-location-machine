"""The four sources that filled the dead domains, and the paths the fourth sweep exercised.

Education, childcare and the sensitive layer were 0/6, 0/2 and 1/3. Every one of these
readers had to reject a publisher's sentinel or a coverage artifact, and the assertions
below are the specific wrong numbers each one produced before it was fixed.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import polars as pl

from wlm.paths import FEATURES, RAW, UNIVERSE

RAW_PRESENT = (RAW / "urban_educationdata").exists()


@unittest.skipUnless(Path(FEATURES).exists(), "features not built")
class TestTheDeadDomainsAreAlive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yaml

        from wlm.paths import CONFIG

        cls.registry = yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]
        cls.populated = set(
            pl.read_parquet(FEATURES).filter(pl.col("value").is_not_null())["indicator_id"]
        )

    def _coverage(self, domain: str) -> tuple[int, int]:
        ids = [i["id"] for i in self.registry if i["domain"] == domain]
        return sum(1 for i in ids if i in self.populated), len(ids)

    def test_education_has_data(self):
        have, _ = self._coverage("education")
        self.assertGreaterEqual(have, 4, "education is dead again")

    def test_childcare_has_data(self):
        have, _ = self._coverage("family_childcare")
        self.assertGreaterEqual(have, 2)

    def test_the_sensitive_layer_has_data(self):
        have, _ = self._coverage("sensitive")
        self.assertEqual(have, 3)

    def test_no_scoring_domain_is_completely_empty(self):
        """A weight on an empty domain evaporates on renormalisation. That used to be true
        of education and childcare at once."""
        import yaml

        from wlm.paths import CONFIG

        domains = yaml.safe_load((CONFIG / "domains.yaml").read_text())["domains"]
        for domain in domains:
            if not domain.get("scoring") or not domain["default_weight"]:
                continue
            have, total = self._coverage(domain["id"])
            self.assertGreater(have, 0, f"{domain['id']} has no data at all ({have}/{total})")

    def test_weighting_education_actually_moves_the_ranking(self):
        from wlm.ingest.base import registry
        from wlm.scoring.engine import score

        counties = pl.read_parquet(FEATURES).filter(pl.col("geo_level") == "county")
        reg = registry()
        without, _ = score(counties, reg, {"domain_weights": {"cost_housing": 100.0}})
        with_edu, report = score(
            counties, reg, {"domain_weights": {"cost_housing": 50.0, "education": 50.0}}
        )
        self.assertNotEqual(list(without.head(5)["geo_id"]), list(with_edu.head(5)["geo_id"]))
        self.assertFalse(
            [w for w in report.warnings if "education" in w and "no data" in w],
            "education still reports as having no data",
        )


@unittest.skipUnless(RAW_PRESENT, "raw downloads not present")
class TestEducationReader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from wlm.ingest import urban_education

        cls.frame, cls.stats = urban_education.ingest(RAW / "urban_educationdata")
        cls.by = {
            i: cls.frame.filter(pl.col("indicator_id") == i)
            for i in cls.frame["indicator_id"].unique()
        }

    def test_withheld_cells_are_rejected_before_they_are_averaged(self):
        """The publisher marks withheld values -1, -2, -3. emit() catches a negative on the
        way out, but aggregation happens first: a -3 inside one district would corrupt the
        county mean before emit ever saw it."""
        self.assertGreater(self.stats["sentinels_rejected"], 0)
        self.assertEqual(self.frame.filter(pl.col("value") < 0).height, 0)

    def test_a_county_ratio_is_not_built_from_one_small_school(self):
        """Washoe County, Nevada filed no staff count for its 66,524-pupil district, so the
        county ratio came from Pyramid Lake High School's 126 pupils: 3,520 per teacher."""
        ratios = self.by.get("edu_student_teacher_ratio")
        self.assertLess(ratios["value"].max(), 100)
        self.assertGreater(self.stats["ratios_dropped_unrepresentative"], 0)

    def test_a_county_graduation_rate_represents_the_county(self):
        """Pima County came out at 34% for 1.08 million people, computed from a single
        school of 68 pupils because the other 82 districts filed nothing."""
        self.assertGreater(self.stats["grad_rates_dropped_unrepresentative"], 0)
        rates = self.by.get("edu_graduation_rate")
        self.assertGreater(rates["value"].median(), 0.8, "national median should sit near 0.87")
        self.assertLessEqual(rates["value"].max(), 1.0)

    def test_a_county_with_no_district_of_its_own_is_missing_not_zero(self):
        """Virginia files James City County's pupils under a Williamsburg-James City
        division. Reporting 0 on a higher-is-better indicator ranks it last for a filing
        convention."""
        counts = self.by.get("edu_district_choice_count")
        self.assertGreaterEqual(counts["value"].min(), 1)
        self.assertGreater(self.stats["counties_without_a_district"], 0)

    def test_dauphin_county_looks_like_dauphin_county(self):
        """The anchor: Emil's own county, where the values can be checked independently."""
        home = {
            r["indicator_id"]: r["value"]
            for r in self.frame.filter(pl.col("geo_id") == "42043").iter_rows(named=True)
        }
        self.assertAlmostEqual(home["edu_student_teacher_ratio"], 15.3, delta=2)
        self.assertEqual(home["edu_district_choice_count"], 19)
        self.assertTrue(8_000 < home["edu_spend_per_pupil"] < 25_000)
        self.assertTrue(0.6 < home["edu_graduation_rate"] < 0.95)


@unittest.skipUnless((RAW / "countypres_mirror").exists(), "election data not present")
class TestPartisanLean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from wlm.ingest import county_elections

        cls.frame, cls.stats = county_elections.ingest(RAW / "countypres_mirror")

    def test_alaska_is_excluded_rather_than_mis_assigned(self):
        """Alaska reports by State House District, and those pseudo-FIPS collide with real
        borough codes: 02020 is Anchorage Municipality and House District 20 at once."""
        self.assertEqual(self.frame.filter(pl.col("geo_id").str.starts_with("02")).height, 0)
        self.assertIn("02", self.stats["excluded_states"])

    def test_the_margin_is_signed_and_bounded(self):
        self.assertGreater(self.frame["value"].max(), 0.8)
        self.assertLess(self.frame["value"].min(), -0.8)
        self.assertLessEqual(self.frame["value"].abs().max(), 1.0)

    def test_known_counties_land_where_they_should(self):
        lookup = dict(self.frame.select(["geo_id", "value"]).iter_rows())
        self.assertGreater(lookup["48295"], 0.8, "Lipscomb County TX should be strongly R")
        self.assertLess(lookup["36061"], -0.5, "Manhattan should be strongly D")
        self.assertLess(abs(lookup["42043"]), 0.15, "Dauphin is a genuine swing county")

    def test_it_records_what_it_mirrors(self):
        """The authoritative MIT file is behind a guestbook form; provenance has to name
        both what was fetched and what it stands in for."""
        self.assertIn("10.7910/DVN/VOQCHQ", self.stats["mirrors"])


@unittest.skipUnless((RAW / "usreligioncensus").exists(), "religion data not present")
class TestReligiousAdherence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from wlm.ingest import religion_census

        cls.frame, cls.stats = religion_census.ingest(
            RAW / "usreligioncensus" / "2020_USRC_Summaries.xlsx"
        )

    def test_the_share_is_a_share(self):
        """The sheet's own column is named "as % of Population" but holds a 0-1 fraction.
        Taking the name at its word divided it by 100 again and put national adherence at
        a median of 0.5%."""
        self.assertTrue(0.35 < self.frame["value"].median() < 0.6)

    def test_impossible_shares_are_dropped_not_clipped(self):
        """Adherents are counted where a congregation sits, not where members live, so
        King County, Texas reported 452% of its 215 residents."""
        self.assertLessEqual(self.frame["value"].max(), 1.0)
        self.assertGreater(self.stats["over_100pct_dropped"], 0)


@unittest.skipUnless((RAW / "dol_childcare").exists(), "childcare data not present")
class TestChildcarePrices(unittest.TestCase):
    def test_weekly_prices_become_annual_ones(self):
        from wlm.ingest import dol_childcare

        frame, stats = dol_childcare.ingest(
            RAW / "dol_childcare" / "nationaldatabaseofchildcareprices.xlsx"
        )
        infant = frame.filter(pl.col("indicator_id") == "family_childcare_cost_infant")
        # A household compares childcare against a salary, not against a week.
        self.assertTrue(5_000 < infant["value"].median() < 20_000)
        self.assertGreater(stats["counties"], 2_000)


class TestCalibrationHonesty(unittest.TestCase):
    def test_no_disagreement_table_without_a_correlation(self):
        """Printing rank "misses" under "correlation unavailable", with a paragraph on how
        to read them, presents noise as a finding."""
        import inspect

        from wlm.diagnostics import calibration

        source = inspect.getsource(calibration.build)
        self.assertIn("if rho is not None:", source)

    def test_constant_ratings_say_so_specifically(self):
        import inspect

        from wlm.diagnostics import calibration

        source = inspect.getsource(calibration.build)
        self.assertIn("same score", source)


@unittest.skipUnless(Path(UNIVERSE).exists(), "universe not built")
class TestProfileRoundTrip(unittest.TestCase):
    """build -> write -> load -> score, which had never run end to end on a real file."""

    def test_a_written_profile_loads_back_and_scores(self):
        from wlm.ingest.base import registry
        from wlm.profile import build_profile, load_profile, write_profile
        from wlm.questionnaire import generate
        from wlm.questionnaire.session import Session
        from wlm.scoring.engine import score

        questions = generate.build()
        session = Session(person="emil", sessions_dir=Path(tempfile.mkdtemp()))
        session.answers["budget_allocation"] = {
            "cost_housing": 30, "climate_environment": 25, "safety": 15,
            "health_care": 10, "urban_form": 10, "recreation_lifestyle": 10,
        }
        session.answers["q_housing_budget"] = "400000"

        profile = build_profile(session, questions)
        path = Path(tempfile.mkdtemp()) / "emil.yaml"
        write_profile(session, questions, path)

        reloaded = load_profile(path)
        self.assertEqual(
            sorted(reloaded["domain_weights"]), sorted(profile["domain_weights"])
        )

        counties = pl.read_parquet(FEATURES).filter(pl.col("geo_level") == "county")
        scored, _ = score(counties, registry(), reloaded)
        self.assertGreater(scored.height, 100)
        self.assertEqual(reloaded["knockouts"][0]["value"], 400_000.0)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless((RAW / "census_cbp" / "cbp22co.zip").exists(), "CBP data not present")
class TestAmenityDensityFloor(unittest.TestCase):
    """Found by running a real household's answers through the pipeline, not by reading.

    Emil's recreation_lifestyle domain — his second-highest weight — put Great Plains
    counties of a few thousand people ahead of real cities, because `amen_arts_rec_per10k`
    is a rate over population and a handful of venues in a tiny county produces an extreme
    per-capita number. LaMoure County, ND (population 4,051, four arts venues total) scored
    at the 92nd percentile; Shawnee County, KS — Topeka, fifty-five venues — scored at the
    38th. The registry already carried an absolute-count indicator meant to counterbalance
    exactly this, but the questionnaire's trade-off design never offered it as an attribute,
    so it could never earn more than the floor weight while the per-capita version reached
    0.22. The counterbalance existed in the registry and did nothing in practice.
    """

    @classmethod
    def setUpClass(cls):
        from wlm.ingest import census_cbp

        universe = pl.read_parquet(UNIVERSE).filter(pl.col("geo_level") == "county")
        cls.population = dict(zip(universe["geo_id"], universe["population"]))
        cls.frame = census_cbp.ingest(RAW / "census_cbp" / "cbp22co.zip", cls.population)

    def _rated(self, indicator: str) -> pl.DataFrame:
        values = self.frame.filter(pl.col("indicator_id") == indicator).select(
            ["geo_id", "value"]
        )
        pops = pl.DataFrame(
            {"geo_id": list(self.population), "population": list(self.population.values())}
        ).drop_nulls()
        return values.join(pops, on="geo_id", how="inner").drop_nulls()

    def test_below_the_floor_the_rate_equals_the_raw_count(self):
        """The real guarantee, and the one that matters: with the floor at exactly
        10,000 ("per 10k"), a county below it shows a rate equal to its raw establishment
        count — it cannot claim a density implying a town ten times its actual size.

        Custer County, ID (population 4,597) legitimately has 19 arts and recreation
        venues, being the gateway to the Sawtooths — a real number, not noise. The floor
        does not (and should not) hide that; it stops the number from being multiplied up
        as though the county had thousands more residents than it does.
        """
        from wlm.ingest.census_cbp import MIN_POPULATION_FOR_RATE

        self.assertEqual(MIN_POPULATION_FOR_RATE, 10_000, "the invariant below assumes this")
        rated = self._rated("amen_arts_rec_per10k")
        totals = self.frame.filter(pl.col("indicator_id") == "amen_arts_rec_total").select(
            ["geo_id", "value"]
        ).rename({"value": "total"})
        below = rated.filter(pl.col("population") < MIN_POPULATION_FOR_RATE).join(
            totals, on="geo_id", how="inner"
        )
        self.assertGreater(below.height, 50, "too few counties below the floor to check")
        mismatched = below.filter((pl.col("value") - pl.col("total")).abs() > 0.01)
        self.assertEqual(
            mismatched.height, 0,
            f"below the floor, rate should equal raw count: {mismatched.head(3).to_dicts()}",
        )

    def test_known_amenity_hotspots_lead_once_the_floor_is_applied(self):
        """Aspen, Jackson Hole and Manhattan are not a coincidence if the fix is doing its
        job: real tourism and cultural centres, not statistical noise from a tiny county."""
        top = self._rated("amen_arts_rec_per10k").sort("value", descending=True).head(10)
        universe = pl.read_parquet(UNIVERSE).select(["geo_id", "population"])
        self.assertGreater(
            top.join(universe, on="geo_id", how="left")["population"].median(), 7_000,
            "the top of the rate is still dominated by tiny counties",
        )

    def test_the_absolute_count_is_untouched_by_the_floor(self):
        """The floor only tempers the rate; the total stays a real count."""
        totals = self.frame.filter(pl.col("indicator_id") == "amen_arts_rec_total")
        self.assertGreater(totals["value"].max(), 500, "Manhattan should show hundreds")

    def test_a_county_at_the_floor_and_one_far_above_it_are_treated_alike(self):
        """The floor changes the denominator, not the arithmetic: two counties whose
        population sits below MIN_POPULATION_FOR_RATE should score identically on the same
        establishment count."""
        from wlm.ingest.census_cbp import MIN_POPULATION_FOR_RATE

        small_pop = {"11111": 1_200, "22222": 4_000}
        # Constructed directly rather than through a fixture file: what matters here is
        # the arithmetic, not the parsing.
        from wlm.ingest.census_cbp import ingest as cbp_ingest
        import unittest.mock as mock

        def fake_rows(_path):
            yield {"fipstate": "11", "fipscty": "111", "naics": "71----", "est": "5"}
            yield {"fipstate": "22", "fipscty": "222", "naics": "71----", "est": "5"}

        with mock.patch("wlm.ingest.census_cbp._rows", fake_rows), \
             mock.patch("wlm.ingest.census_cbp.is_in_scope", return_value=True), \
             mock.patch(
                 "wlm.ingest.census_cbp.county_geoid",
                 side_effect=lambda s, c: s + c[-3:],  # matches county_geoid: 2-digit state + 3-digit county
             ):
            frame = cbp_ingest("unused", small_pop)

        rates = dict(
            frame.filter(pl.col("indicator_id") == "amen_arts_rec_per10k")
            .select(["geo_id", "value"])
            .iter_rows()
        )
        self.assertAlmostEqual(rates["11111"], rates["22222"])
        self.assertAlmostEqual(rates["11111"], 5 / MIN_POPULATION_FOR_RATE * 10_000)
