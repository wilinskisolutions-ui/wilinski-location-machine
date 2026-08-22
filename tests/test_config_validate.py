"""Prove the validator fails when it should.

A validator that has only ever passed is untested. Each case below breaks one invariant
from GOAL.md and asserts the specific error is raised.

Run:  make test   (or: PYTHONPATH=src python3 -m unittest discover -s tests -v)
"""

from __future__ import annotations

import unittest

from wlm.config import validate as v


def _reset() -> None:
    v.errors.clear()
    v.warnings.clear()
    v.notes.clear()


def _domain(**kw):
    base = {"id": "d1", "label": "D", "scoring": True, "default_weight": 100}
    base.update(kw)
    return base


def _source(**kw):
    base = {
        "id": "s1", "name": "S", "url": "https://census.gov/x",
        "geo_levels": ["county"], "vintage": "2024", "license": "PD",
    }
    base.update(kw)
    return base


def _indicator(**kw):
    base = {
        "id": "i1", "domain": "d1", "source": "s1",
        "geo_level": "county", "curve": "higher_better", "unit": "x",
    }
    base.update(kw)
    return base


class TestDomains(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_weights_must_sum_to_100(self):
        v.check_domains([_domain(default_weight=42)])
        self.assertTrue(any("sum to" in e for e in v.errors))

    def test_sensitive_domain_at_nonzero_weight_is_principle_10_violation(self):
        v.check_domains([_domain(default_weight=100, sensitive=True)])
        self.assertTrue(any("PRINCIPLE 10" in e for e in v.errors))

    def test_nonscoring_domain_must_have_zero_weight(self):
        v.check_domains([_domain(), _domain(id="d2", scoring=False, default_weight=5)])
        self.assertTrue(any("non-scoring" in e for e in v.errors))

    def test_duplicate_ids_rejected(self):
        v.check_domains([_domain(default_weight=50), _domain(default_weight=50)])
        self.assertTrue(any("duplicate id" in e for e in v.errors))

    def test_valid_domains_pass(self):
        v.check_domains([_domain(default_weight=60), _domain(id="d2", default_weight=40)])
        self.assertEqual(v.errors, [])


class TestSources(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_http_url_rejected(self):
        v.check_sources([_source(url="http://census.gov/x")])
        self.assertTrue(any("must be https" in e for e in v.errors))

    def test_host_absent_from_catalog_is_drift(self):
        v.check_sources([_source(url="https://not-a-real-source.example/x")])
        self.assertTrue(any("absent from docs/data-sources.md" in e for e in v.errors))

    def test_missing_license_rejected(self):
        s = _source()
        del s["license"]
        v.check_sources([s])
        self.assertTrue(any("missing required field 'license'" in e for e in v.errors))

    def test_unknown_geo_level_rejected(self):
        v.check_sources([_source(geo_levels=["planet"])])
        self.assertTrue(any("unknown geo_levels" in e for e in v.errors))


class TestIndicators(unittest.TestCase):
    def setUp(self):
        _reset()

    def _run(self, ind, domains=None, sources=None):
        v.check_indicators([ind], domains or [_domain()], sources or [_source()])

    def test_unknown_source_rejected(self):
        self._run(_indicator(source="nope"))
        self.assertTrue(any("unknown source" in e for e in v.errors))

    def test_geo_level_not_offered_by_source_rejected(self):
        self._run(_indicator(geo_level="metro"))
        self.assertTrue(any("not offered by source" in e for e in v.errors))

    def test_indicator_in_nonscoring_domain_rejected(self):
        self._run(_indicator(), domains=[_domain(scoring=False, default_weight=0)])
        self.assertTrue(any("non-scoring" in e for e in v.errors))

    def test_missing_unit_rejected(self):
        ind = _indicator()
        del ind["unit"]
        self._run(ind)
        self.assertTrue(any("missing 'unit'" in e for e in v.errors))

    def test_sensitive_indicator_outside_sensitive_domain_rejected(self):
        self._run(_indicator(sensitive=True))
        self.assertTrue(any("not a sensitive domain" in e for e in v.errors))

    def test_indicator_in_sensitive_domain_must_be_flagged(self):
        self._run(_indicator(), domains=[_domain(sensitive=True, default_weight=100)])
        self.assertTrue(any("not flagged" in e for e in v.errors))

    def test_scoring_domain_with_no_indicators_rejected(self):
        v.check_indicators(
            [_indicator()],
            [_domain(default_weight=50), _domain(id="d2", default_weight=50)],
            [_source()],
        )
        self.assertTrue(any("no indicators" in e for e in v.errors))

    def test_valid_indicator_passes(self):
        self._run(_indicator())
        self.assertEqual(v.errors, [])


class TestCrosswalk(unittest.TestCase):
    """School districts do not nest inside counties, so district-sourced indicators declare
    `crosswalk_from`. The registry records the derivation instead of hiding it in code."""

    def setUp(self):
        _reset()

    def _run(self, ind, source):
        v.check_indicators([ind], [_domain()], [source])

    def test_district_source_without_crosswalk_is_rejected(self):
        self._run(
            _indicator(geo_level="county"),
            _source(geo_levels=["district"]),
        )
        self.assertTrue(any("add 'crosswalk_from'" in e for e in v.errors))

    def test_crosswalk_from_must_be_offered_by_the_source(self):
        self._run(
            _indicator(geo_level="county", crosswalk_from="metro"),
            _source(geo_levels=["district"]),
        )
        self.assertTrue(any("crosswalk_from 'metro' not offered" in e for e in v.errors))

    def test_crosswalk_equal_to_geo_level_is_redundant(self):
        self._run(
            _indicator(geo_level="county", crosswalk_from="county"),
            _source(geo_levels=["county"]),
        )
        self.assertTrue(any("equals geo_level" in e for e in v.errors))

    def test_valid_district_to_county_crosswalk_passes(self):
        self._run(
            _indicator(geo_level="county", crosswalk_from="district"),
            _source(geo_levels=["district"]),
        )
        self.assertEqual(v.errors, [])


class TestBandShoulders(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_asymmetric_shoulders_accepted(self):
        v.check_curve(
            _indicator(
                curve="ideal_band",
                curve_params={"lo": 1, "hi": 5, "shoulder": 2, "shoulder_lo": 0.5},
            ),
            "i1",
        )
        self.assertEqual(v.errors, [])

    def test_negative_side_shoulder_rejected(self):
        v.check_curve(
            _indicator(
                curve="ideal_band",
                curve_params={"lo": 1, "hi": 5, "shoulder": 2, "shoulder_hi": -1},
            ),
            "i1",
        )
        self.assertTrue(any("shoulder_hi must be a positive number" in e for e in v.errors))


class TestCurves(unittest.TestCase):
    """The band/point distinction is load-bearing — see docs/methodology.md section 3."""

    def setUp(self):
        _reset()

    def test_monotone_curve_rejects_params(self):
        v.check_curve(_indicator(curve="higher_better", curve_params={"lo": 1, "hi": 2}), "i1")
        self.assertTrue(any("takes no curve_params" in e for e in v.errors))

    def test_band_requires_params(self):
        v.check_curve(_indicator(curve="ideal_band"), "i1")
        self.assertTrue(any("requires numeric 'lo' and 'hi'" in e for e in v.errors))

    def test_band_rejects_inverted_bounds(self):
        v.check_curve(_indicator(curve="ideal_band", curve_params={"lo": 9, "hi": 2, "shoulder": 1}), "i1")
        self.assertTrue(any("needs lo < hi" in e for e in v.errors))

    def test_band_requires_shoulder(self):
        v.check_curve(_indicator(curve="ideal_band", curve_params={"lo": 1, "hi": 2}), "i1")
        self.assertTrue(any("requires 'shoulder'" in e for e in v.errors))

    def test_point_rejects_zero_tolerance(self):
        v.check_curve(_indicator(curve="ideal_point", curve_params={"target": 5, "tol": 0}), "i1")
        self.assertTrue(any("positive 'tol'" in e for e in v.errors))

    def test_unknown_curve_rejected(self):
        v.check_curve(_indicator(curve="vibes"), "i1")
        self.assertTrue(any("curve 'vibes' not in" in e for e in v.errors))

    def test_valid_band_passes(self):
        v.check_curve(_indicator(curve="ideal_band", curve_params={"lo": 1, "hi": 5, "shoulder": 2}), "i1")
        self.assertEqual(v.errors, [])


if __name__ == "__main__":
    unittest.main()
