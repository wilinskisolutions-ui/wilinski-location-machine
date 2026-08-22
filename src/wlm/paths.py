"""Canonical filesystem locations. One definition, imported everywhere."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CONFIG = ROOT / "config"
DOCS = ROOT / "docs"
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
OUTPUT = ROOT / "output"

MANIFEST = RAW / "MANIFEST.json"
UNIVERSE = PROCESSED / "universe.parquet"
FEATURES = PROCESSED / "features.parquet"
