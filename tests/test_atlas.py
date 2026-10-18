"""The atlas: a map is only allowed to recombine, never to recompute.

The page scores places in the browser as the household moves the weights, so it carries a
second implementation of the across-domain step. These tests hold that copy to the engine
over random inputs, hold its unit formatter to `wlm.units.fmt`, and pin the pieces of the
build that turn Census and Zillow files into what the page draws.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from shapely.geometry import Polygon

from wlm.atlas import build, geometry
from wlm.paths import CONFIG, FEATURES
from wlm.scoring.engine import EPSILON, MIN_WEIGHT_COVERED, combine_domains
from wlm.units import fmt

PAGE = Path(build.__file__).parent / "page"
NODE = shutil.which("node")


def run_node(script: str, payload) -> object:
    """Load score.js in node and evaluate `script` with `input` bound to `payload`."""
    prog = (
        f"const A = require({json.dumps(str(PAGE / 'score.js'))});"
        "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{const input=JSON.parse(s);"
        f"process.stdout.write(JSON.stringify(({script})(input)));}});"
    )
    out = subprocess.run([NODE, "-e", prog], input=json.dumps(payload), capture_output=True,
                         text=True, check=True, timeout=60)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "node unavailable")
class TestPageScoresMatchTheEngine(unittest.TestCase):
    def test_combine_agrees_with_engine_over_random_inputs(self):
        rng = random.Random(7)
        domains = [f"d{i}" for i in range(13)]
        cases = []
        for _ in range(400):
            per = {d: rng.random() ** rng.choice([0.5, 1, 3]) for d in domains if rng.random() > 0.2}
            if rng.random() < 0.1 and per:
                per[next(iter(per))] = 0.0  # below the epsilon floor
            weights = {d: rng.choice([0, 0, 1, 4, 8, 12, 16, 30]) for d in domains}
            # The influence reshaping changes the ranking, so the page has to apply it
            # identically or moving the weights there ranks by a different rule than the
            # report. Identity pairs are included so the unshaped path stays covered.
            shape = {
                d: (rng.choice([1.0, 1.0, 0.5, 0.78, 1.4, 2.5]), rng.uniform(-2.5, -0.1))
                for d in domains
            }
            cases.append((per, weights, shape))

        payload = [
            {
                "f": [per.get(d) for d in domains],
                "w": [weights[d] for d in domains],
                "s": [list(shape[d]) for d in domains],
            }
            for per, weights, shape in cases
        ]
        got = run_node(
            f"(xs)=>xs.map(x=>A.combine(x.f,x.w,{EPSILON},{MIN_WEIGHT_COVERED},x.s))", payload
        )
        compared = 0
        for (per, weights, shape), js in zip(cases, got):
            ref = combine_domains(per, weights, shape)
            if ref is None:
                self.assertIsNone(js)
                continue
            score, covered, _ = ref
            self.assertAlmostEqual(js["score"], score, places=12)
            self.assertAlmostEqual(js["cov"], covered, places=12)
            self.assertEqual(js["ok"], covered >= MIN_WEIGHT_COVERED)
            compared += 1
        self.assertGreater(compared, 300, "too few cases exercised the comparison")

    def test_fmt_agrees_with_units(self):
        cases = [
            (0.034, "percent"), (0.7930, "share"), (412345, "USD"), (9500, "USD"),
            (2068.4, "USD/month"), (34.7, "degF"), (25.8, "inches"), (17.2, "miles"),
            (26.4, "minutes"), (45272, "people"), (153900, "passengers/year"),
            (1074.3, "people/sqmi"), (28.8, "per10k"), (5.9, "per100k"), (81.5, "years"),
            (7.4, "ug/m3"), (3699, "degree_days"), (-0.9, "index"), (88.9, "score"),
            (0.0091, "ratio"), (5.02, "ratio"), (12.7, None), (None, "USD"),
        ]
        got = run_node("(xs)=>xs.map(([v,u])=>A.fmt(v,u))", cases)
        for (value, unit), js in zip(cases, got):
            self.assertEqual(js, fmt(value, unit), f"{value} {unit}")

    def test_ideal_point_agrees_with_curves(self):
        from wlm.features.curves import ideal_point

        cases = [(-0.9, 0, 0.25), (0.0, 0, 0.25), (0.33, 0, 0.25), (0.12, 0.1, 1.0), (5, 0, 3)]
        got = run_node("(xs)=>xs.map(([v,t,tol])=>A.idealPoint(v,t,tol))", cases)
        for (v, t, tol), js in zip(cases, got):
            self.assertAlmostEqual(js, ideal_point(v, target=t, tol=tol), places=12)

    def test_ring_decoding_agrees(self):
        ring = geometry.encode_ring([(-86.85, 35.91), (-86.80, 35.91), (-86.80, 35.95), (-86.85, 35.91)], 10000)
        got = run_node("(x)=>A.decodeRing(x.ring, x.q)", {"ring": ring, "q": 10000})
        self.assertEqual([tuple(p) for p in got], geometry.decode_ring(ring, 10000))


class TestGeometry(unittest.TestCase):
    def test_exterior_is_clockwise_whatever_the_input(self):
        # Counter-clockwise in, as GeoJSON stores it. d3 would fill the whole globe.
        ccw = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        self.assertTrue(ccw.exterior.is_ccw)
        packed = geometry.encode(ccw, tolerance=0, q=100)
        ext = geometry.decode_ring(packed[0][0], 100)
        self.assertFalse(Polygon(ext).exterior.is_ccw)

    def test_a_collapsed_exterior_takes_its_holes_with_it(self):
        tiny = Polygon([(0, 0), (0.00001, 0), (0.00001, 0.00001), (0, 0.00001)])
        self.assertEqual(geometry.encode(tiny, tolerance=0, q=100), [])

    def test_quantisation_drops_repeated_vertices(self):
        ring = geometry.encode_ring([(0, 0), (0.00001, 0), (1, 0), (1, 1), (0, 0)], 100)
        self.assertEqual(len(ring), 8)


class TestConfig(unittest.TestCase):
    def setUp(self):
        from wlm.ingest.base import registry

        self.registry = registry()
        self.cfg = build.load_config()

    def test_every_indicator_is_placed_once_or_excluded_with_a_reason(self):
        placed = build.factor_of(self.cfg, self.registry)
        self.assertEqual(set(placed) | set(self.cfg["excluded"]), set(self.registry))

    def test_an_indicator_left_out_is_refused(self):
        cfg = json.loads(json.dumps(self.cfg))
        cfg["factors"][0]["indicators"].pop()
        with self.assertRaises(build.AtlasError):
            build.factor_of(cfg, self.registry)

    def test_an_indicator_in_two_factors_is_refused(self):
        cfg = json.loads(json.dumps(self.cfg))
        cfg["factors"][1]["indicators"].append(cfg["factors"][0]["indicators"][0])
        with self.assertRaises(build.AtlasError):
            build.factor_of(cfg, self.registry)

    def test_only_the_opted_in_sensitive_indicator_is_switched_on(self):
        _, profile = build.factor_profile(self.cfg, self.registry)
        self.assertEqual(profile["sensitive_indicators"], ["sens_religious_adherence"])
        self.assertEqual(profile["curve_overrides"]["sens_religious_adherence"]["curve"], "higher_better")

    def test_wishlist_is_a_list_of_existing_places_not_new_candidates(self):
        import polars as pl

        from wlm.paths import UNIVERSE

        if not UNIVERSE.exists():
            self.skipTest("universe not built")
        ids = set(pl.read_parquet(UNIVERSE)["geo_id"])
        for w in self.cfg["wishlist"]:
            self.assertIn(w["anchor"], ids, f"{w['label']} anchors on a place outside the universe")


class TestPublicSite(unittest.TestCase):
    """The web section of atlas.yaml: weights, winter presets, visitor-directed layers."""

    def setUp(self):
        from wlm.ingest.base import registry

        self.registry = registry()
        self.cfg = build.load_config()

    def test_real_config_passes(self):
        build.check_web(self.cfg, self.registry)

    def test_web_weights_must_cover_every_public_factor(self):
        cfg = json.loads(json.dumps(self.cfg))
        cfg["web"]["default_weights"].pop("cost")
        with self.assertRaises(build.AtlasError):
            build.check_web(cfg, self.registry)

    def test_household_only_factor_is_not_offered_publicly(self):
        self.assertNotIn("church", self.cfg["web"]["default_weights"])

    def test_a_layer_must_point_at_a_sensitive_indicator(self):
        cfg = json.loads(json.dumps(self.cfg))
        cfg["web"]["sensitive_layers"][0]["indicator"] = "cost_rent_median_zori"
        with self.assertRaises(build.AtlasError):
            build.check_web(cfg, self.registry)

    def test_layers_never_assume_a_direction(self):
        for layer in self.cfg["web"]["sensitive_layers"]:
            self.assertGreaterEqual(len(layer["directions"]), 2, layer["id"])

    def test_public_site_offers_no_birthplace_layer(self):
        # Taken off on 2026-10-18: national origin is protected under the Fair Housing Act.
        indicators = {layer["indicator"] for layer in self.cfg["web"]["sensitive_layers"]}
        self.assertNotIn("sens_foreign_born_share", indicators)

    @unittest.skipUnless(Path(FEATURES).exists(), "features not built")
    def test_winter_presets_reorder_cold_and_warm_places(self):
        import polars as pl

        cp = build.climate_preset_scores(pl.read_parquet(FEATURES), self.cfg, self.registry)
        ids = [p["id"] for p in self.cfg["web"]["climate_presets"]]
        snowy, hot = ids.index("snowy"), ids.index("hot")
        duluth, sarasota = cp["27137"], cp["12115"]  # St. Louis County MN, Sarasota County FL
        self.assertGreater(duluth[snowy], sarasota[snowy])
        self.assertGreater(sarasota[hot], duluth[hot])

    @unittest.skipUnless(Path(FEATURES).exists(), "features not built")
    def test_sensitive_values_carry_percentile_and_raw_at_their_own_level(self):
        import polars as pl

        sv = build.sensitive_values(pl.read_parquet(FEATURES), self.cfg)
        county = sv[("county", "47187")]  # Williamson County TN
        self.assertEqual(len(county), 2 * len(self.cfg["web"]["sensitive_layers"]))
        self.assertTrue(0 <= county[0] <= 1)   # religion percentile
        self.assertIsNotNone(county[3])        # political lean, raw margin
        self.assertNotIn(("place", "4727740"), sv)  # Franklin TN: both layers are county-level


class TestPublicSiteRanksByTheReportsRule(unittest.TestCase):
    """The site's winter presets and layer directions are each stretched like a factor."""

    CORE = Path(build.OUT) / "data" / "core.json"

    @unittest.skipUnless((Path(build.OUT) / "data" / "core.json").exists(), "atlas not built")
    def test_every_variant_carries_a_stretch_within_the_engines_limits(self):
        from wlm.scoring.engine import INFLUENCE_SCALE_LIMITS

        low, high = INFLUENCE_SCALE_LIMITS
        core = json.loads(self.CORE.read_text())
        web = core["web"]
        for f, shape in zip(core["factors"], web["shape"]):
            if f["householdOnly"]:
                self.assertIsNone(shape, f"{f['id']} is not offered publicly")
            elif shape is not None:
                self.assertTrue(low <= shape[0] <= high, f["id"])
        for preset in web["climatePresets"]:
            self.assertIsNotNone(preset["shape"], preset["id"])
            self.assertTrue(low <= preset["shape"][0] <= high, preset["id"])
        for layer in web["layers"]:
            self.assertEqual(set(layer["shape"]), set(layer["directions"]), layer["id"])
            for direction, shape in layer["shape"].items():
                self.assertTrue(low <= shape[0] <= high, f"{layer['id']}:{direction}")

    def test_an_explicit_target_changes_nothing_when_it_is_the_default(self):
        from wlm.scoring.engine import influence_scale, influence_target

        rng = random.Random(11)
        rows = {i: {"a": rng.random(), "b": rng.random() ** 4} for i in range(300)}
        self.assertEqual(influence_scale(rows), influence_scale(rows, target=influence_target(rows)))


class TestRents(unittest.TestCase):
    def test_town_rent_is_land_weighted_and_needs_coverage(self):
        rel = [
            ("37064", "4727740", 30.0, 100.0),  # 30% of the town, $2,000
            ("37067", "4727740", 50.0, 100.0),  # 50%, $2,400
            ("37069", "4727740", 20.0, 100.0),  # 20%, no Zillow figure
            ("37000", "4700001", 10.0, 100.0),  # 10% covered: too thin to stand for the town
        ]
        values = {"37064": 2000.0, "37067": 2400.0, "37000": 1200.0}
        out = build.town_values(rel, values, {"4727740", "4700001"})
        rent, share = out["4727740"]
        self.assertAlmostEqual(rent, (30 * 2000 + 50 * 2400) / 80)
        self.assertAlmostEqual(share, 0.8)
        self.assertNotIn("4700001", out)

    def test_zip_reader_keeps_zeros_and_drops_dead_markets(self):
        months = [f"2025-{m:02d}-28" for m in range(1, 13)] + [f"2026-{m:02d}-28" for m in range(1, 9)]
        head = ["RegionID", "SizeRank", "RegionName", "RegionType", "StateName", "State"] + months
        rows = [
            ["1", "1", "8701", "zip", "NJ", "NJ"] + [""] * 19 + ["2100"],   # leading zero lost
            ["2", "2", "37064", "zip", "TN", "TN"] + ["1800"] + [""] * 19,   # stopped 19 months ago
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "zips.csv"
            p.write_text("\n".join(",".join(r) for r in [head, *rows]))
            out, month = build.read_zillow_zips(p)
        self.assertEqual(out, {"08701": ("NJ", 2100.0)})
        self.assertEqual(month, "2026-08")


class TestConfigFileIsValidYaml(unittest.TestCase):
    def test_default_weights_sum_to_100(self):
        import yaml

        cfg = yaml.safe_load((CONFIG / "atlas.yaml").read_text())
        self.assertEqual(sum(f["default_weight"] for f in cfg["factors"]), 100)


if __name__ == "__main__":
    unittest.main()
