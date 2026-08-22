"""Principle 4 in executable form.

Phase 1 is built against fabricated fixtures because the data hosts are blocked. The
guarantee that those numbers cannot reach a result the household would act on is only worth
anything if the refusal actually fires. That is what this file checks.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wlm.fetch import register_fixture
from wlm.manifest import Manifest, SyntheticDataError

from conftest import FIXTURES


class TestSyntheticGuard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "raw"
        self.root.mkdir(parents=True)
        self.manifest = Manifest(entries={}, path=self.root / "MANIFEST.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_manifest_permits_scoring(self):
        self.manifest.record(
            source_id="fema_nri",
            url="https://hazards.fema.gov/x.csv",
            file=self._real_file(),
            root=self.root,
        )
        self.manifest.assert_no_synthetic()  # must not raise

    def test_fixture_registers_as_synthetic(self):
        register_fixture(
            "fema_nri", FIXTURES / "fema_nri_counties.json", root=self.root, manifest=self.manifest
        )
        entries = self.manifest.synthetic_entries()
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].is_placeholder)

    def test_scoring_refuses_synthetic_input(self):
        register_fixture(
            "fema_nri", FIXTURES / "fema_nri_counties.json", root=self.root, manifest=self.manifest
        )
        with self.assertRaises(SyntheticDataError) as ctx:
            self.manifest.assert_no_synthetic("scoring")
        message = str(ctx.exception)
        self.assertIn("scoring refuses to run", message)
        self.assertIn("fema_nri_counties.json", message)  # names the offender
        self.assertIn("Principle 4", message)

    def test_one_synthetic_input_among_real_ones_still_refuses(self):
        self.manifest.record(
            source_id="usda_amenities",
            url="https://www.ers.usda.gov/x.csv",
            file=self._real_file(),
            root=self.root,
        )
        register_fixture(
            "fema_nri", FIXTURES / "fema_nri_counties.json", root=self.root, manifest=self.manifest
        )
        with self.assertRaises(SyntheticDataError):
            self.manifest.assert_no_synthetic()

    def test_synthetic_flag_survives_a_save_load_round_trip(self):
        register_fixture(
            "fema_nri", FIXTURES / "fema_nri_counties.json", root=self.root, manifest=self.manifest
        )
        self.manifest.save()
        reloaded = Manifest.load(self.root / "MANIFEST.json")
        self.assertEqual(len(reloaded.synthetic_entries()), 1)
        with self.assertRaises(SyntheticDataError):
            reloaded.assert_no_synthetic()

    def _real_file(self) -> Path:
        d = self.root / "src"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "real.csv"
        f.write_text("a,b\n1,2\n")
        return f


if __name__ == "__main__":
    unittest.main()
