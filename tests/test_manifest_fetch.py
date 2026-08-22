"""Provenance layer: checksums, resumability, and loud failure."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wlm.fetch import FetchError, fetch
from wlm.manifest import Manifest, sha256_file


class TestManifest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.manifest = Manifest(entries={}, path=self.root / "MANIFEST.json")
        self.file = self.root / "src" / "data.csv"
        self.file.parent.mkdir(parents=True)
        self.file.write_text("geoid,value\n37183,1.0\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _record(self):
        return self.manifest.record(
            source_id="src", url="https://example.gov/data.csv", file=self.file, root=self.root
        )

    def test_records_checksum_and_size(self):
        entry = self._record()
        self.assertEqual(entry.sha256, sha256_file(self.file))
        self.assertEqual(entry.bytes, self.file.stat().st_size)
        self.assertFalse(entry.synthetic)

    def test_verify_detects_an_altered_file(self):
        self._record()
        self.assertTrue(self.manifest.verify("src/data.csv", self.root))
        self.file.write_text("geoid,value\n37183,999.0\n")  # tamper
        self.assertFalse(self.manifest.verify("src/data.csv", self.root))

    def test_verify_detects_a_deleted_file(self):
        self._record()
        self.file.unlink()
        self.assertFalse(self.manifest.verify("src/data.csv", self.root))
        self.assertEqual(self.manifest.verify_all(self.root), ["src/data.csv"])

    def test_round_trips_through_disk(self):
        self._record()
        self.manifest.save()
        reloaded = Manifest.load(self.manifest.path)
        self.assertEqual(len(reloaded.entries), 1)
        self.assertEqual(reloaded.get("src/data.csv").url, "https://example.gov/data.csv")

    def test_unknown_path_does_not_verify(self):
        self.assertFalse(self.manifest.verify("nope/missing.csv", self.root))


class TestFetch(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.manifest = Manifest(entries={}, path=self.root / "MANIFEST.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_offline_mode_fails_naming_the_host(self):
        with self.assertRaises(FetchError) as ctx:
            fetch(
                "fema_nri",
                "https://hazards.fema.gov/nri/data.csv",
                root=self.root,
                manifest=self.manifest,
                offline=True,
            )
        err = ctx.exception
        self.assertEqual(err.host, "hazards.fema.gov")
        self.assertIn("network-allowlist", str(err))

    def test_existing_verified_file_is_not_refetched(self):
        # offline=True would raise if it tried to download, so returning proves the skip.
        dest = self.root / "src" / "data.csv"
        dest.parent.mkdir(parents=True)
        dest.write_text("x\n")
        self.manifest.record(source_id="src", url="https://example.gov/data.csv", file=dest, root=self.root)

        got = fetch(
            "src", "https://example.gov/data.csv", root=self.root, manifest=self.manifest, offline=True
        )
        self.assertEqual(got, dest)

    def test_altered_file_is_reported_not_silently_reused(self):
        dest = self.root / "src" / "data.csv"
        dest.parent.mkdir(parents=True)
        dest.write_text("x\n")
        self.manifest.record(source_id="src", url="https://example.gov/data.csv", file=dest, root=self.root)
        dest.write_text("tampered\n")

        with self.assertRaises(FetchError) as ctx:
            fetch(
                "src", "https://example.gov/data.csv", root=self.root, manifest=self.manifest, offline=True
            )
        self.assertIn("checksum", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
