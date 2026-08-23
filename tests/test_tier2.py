"""Tier 2 reader logic.

Each case here corresponds to a real correction the actual data forced — these are
regression tests for specific mistakes, not coverage for its own sake.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wlm.ingest import bls_qcew, cdc_mortality, chr_rwjf, fars, zillow


class TestIndustryDiversity(unittest.TestCase):
    """Inverse Herfindahl: roughly the effective number of sectors employing people."""

    def test_single_sector_county_scores_one(self):
        self.assertAlmostEqual(bls_qcew.diversity({"10": 1000.0}), 1.0)

    def test_evenly_spread_equals_sector_count(self):
        self.assertAlmostEqual(bls_qcew.diversity({str(i): 100.0 for i in range(4)}), 4.0)

    def test_concentrated_scores_below_spread(self):
        concentrated = bls_qcew.diversity({"a": 900.0, "b": 50.0, "c": 50.0})
        spread = bls_qcew.diversity({"a": 333.0, "b": 333.0, "c": 334.0})
        self.assertLess(concentrated, spread)

    def test_empty_is_none_not_zero(self):
        self.assertIsNone(bls_qcew.diversity({}))
        self.assertIsNone(bls_qcew.diversity({"a": 0.0}))


class TestZillowLatest(unittest.TestCase):
    def test_takes_the_most_recent_non_null(self):
        cols = ["2024-01-31", "2024-02-29", "2024-03-31"]
        self.assertEqual(zillow._latest({"2024-01-31": "100", "2024-02-29": "200", "2024-03-31": ""}, cols), 200.0)

    def test_all_blank_is_none(self):
        # A suppressed thin market must stay missing, not inherit a stale price.
        cols = ["2024-01-31", "2024-02-29"]
        self.assertIsNone(zillow._latest({"2024-01-31": "", "2024-02-29": ""}, cols))


class TestChrInversion(unittest.TestCase):
    def test_pcp_is_inverted_to_people_per_physician(self):
        # CHR publishes providers per head; the registry asks for people per provider,
        # which is what "lower is better" means for this indicator.
        self.assertIn("health_pcp_ratio", chr_rwjf.INVERT)

    def test_only_pcp_is_inverted(self):
        self.assertEqual(chr_rwjf.INVERT, {"health_pcp_ratio"})


class TestFarsRateThreshold(unittest.TestCase):
    def _run(self, population):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "f.zip"
            import zipfile

            with zipfile.ZipFile(src, "w") as z:
                z.writestr("FARS2023NationalCSV/accident.csv", "STATE,COUNTY,FATALS\n42,043,5\n")
            return fars.ingest(src, population)

    def test_tiny_county_rate_is_suppressed(self):
        # Loving County TX (~64 residents) produced 6,250 per 100,000 — an artifact of the
        # denominator, and it would have dominated any ranking it entered.
        df, stats = self._run({"48301": 64})
        self.assertIsNone(df["value"][0])
        self.assertEqual(stats["counties_below_rate_threshold"], 1)

    def test_normal_county_rate_is_computed(self):
        df, _ = self._run({"42043": 293029})
        self.assertAlmostEqual(df["value"][0], 5 / 293029 * 100_000, places=6)

    def test_zero_deaths_is_a_real_zero_not_missing(self):
        df, _ = self._run({"06037": 1_000_000})
        self.assertEqual(df["value"][0], 0.0)


class TestCdcSuppression(unittest.TestCase):
    def _ingest(self, rows):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "c.json"
            p.write_text(json.dumps(rows))
            return cdc_mortality.ingest(p)

    def test_binned_count_still_yields_a_rate(self):
        # Counts are binned for privacy ("1-9") but the rate is published anyway.
        df, stats = self._ingest(
            [{"geoid": "42043", "intent": "FA_Deaths", "count_sup": "1-9", "rate": "13.1"}]
        )
        self.assertAlmostEqual(df["value"][0], 13.1)
        self.assertEqual(stats["suppressed_or_unstable"], 0)

    def test_blank_rate_is_missing(self):
        df, stats = self._ingest(
            [{"geoid": "42043", "intent": "Drug_OD", "count_sup": "0", "rate": ""}]
        )
        self.assertIsNone(df["value"][0])
        self.assertEqual(stats["suppressed_or_unstable"], 1)

    def test_territories_excluded(self):
        df, _ = self._ingest(
            [{"geoid": "72127", "intent": "FA_Deaths", "count_sup": "10", "rate": "5.0"}]
        )
        self.assertEqual(df.height, 0)


if __name__ == "__main__":
    unittest.main()
