"""Pipeline entry point.

    python -m wlm.cli <stage>

Stages: data -> universe -> features -> score -> diagnostics -> report
(`docs/methodology.md` section 9). `demo` runs the built stages against synthetic fixtures,
which is how the chain is exercised while the data hosts are blocked.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Concrete download URLs, pinned per source.
#
# These could NOT be verified: every data host is denied by the egress policy (see
# docs/network-allowlist.md), so `make data` is the first thing that will actually resolve
# them. A moved URL is corrected here and in docs/data-sources.md — never worked around.
DOWNLOADS: dict[str, list[str]] = {
    "census_gazetteer": [
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_counties_national.zip",
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_place_national.zip",
    ],
    "census_acs5": [
        "https://api.census.gov/data/2023/acs/acs5?get=NAME,B01003_001E&for=county:*",
        "https://api.census.gov/data/2023/acs/acs5?get=NAME,B01003_001E&for=place:*",
    ],
    "fema_nri": [
        "https://hazards.fema.gov/nri/Content/StaticDocuments/DataDownload/NRI_Table_Counties/NRI_Table_Counties.zip",
    ],
    "usda_amenities": [
        "https://www.ers.usda.gov/webdocs/DataFiles/53058/natamenf_1_.xls",
    ],
}


def stage_data(args) -> int:
    from wlm.fetch import FetchError, fetch
    from wlm.manifest import Manifest

    manifest = Manifest.load()
    failures: list[str] = []

    for source_id, urls in DOWNLOADS.items():
        for url in urls:
            try:
                path = fetch(source_id, url, manifest=manifest, offline=args.offline)
                print(f"  ok    {source_id:<18} {path.name}")
            except FetchError as exc:
                failures.append(f"{source_id}: {exc.host}")
                print(f"  FAIL  {source_id:<18} {exc.host}", file=sys.stderr)

    manifest.save()

    if failures:
        print(
            f"\n{len(failures)} download(s) failed. If these are policy denials, the hosts "
            "need adding to the egress allowlist — see docs/network-allowlist.md.\n"
            "Nothing was partially written; every failure is reported rather than skipped.",
            file=sys.stderr,
        )
        return 1
    print(f"\nall sources present; manifest at {manifest.path}")
    return 0


def stage_needs_real_data(name: str):
    """Built, but refuses to run on anything but real downloads."""

    def run(args) -> int:
        print(
            f"{name}: built, but needs real inputs in data/raw (run `make data` first).\n"
            "  To exercise the code now, run `make demo` — it drives the same builders from\n"
            "  synthetic fixtures and cannot produce a scorable result."
        )
        return 1

    return run


def stage_demo(args) -> int:
    """Run the built stages end to end on fixtures, then prove scoring refuses them."""
    import polars as pl

    from wlm.features.build import build as build_features
    from wlm.fetch import register_fixture
    from wlm.geo import PlaceCountyCrosswalk
    from wlm.ingest import census_acs, fema_nri, usda_amenities
    from wlm.manifest import Manifest, SyntheticDataError
    from wlm.paths import ROOT
    from wlm.universe.build import build as build_universe

    fixtures = ROOT / "tests" / "fixtures"

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw"
        raw.mkdir(parents=True)
        manifest = Manifest(entries={}, path=raw / "MANIFEST.json")
        for source_id, name in [
            ("census_acs5", "acs_population_places.json"),
            ("census_acs5", "acs_population_counties.json"),
            ("fema_nri", "fema_nri_counties.csv"),
            ("usda_amenities", "usda_natural_amenities.csv"),
        ]:
            register_fixture(source_id, fixtures / name, root=raw, manifest=manifest)

        print("=== UNIVERSE ===")
        pop = census_acs.population_map(
            fixtures / "acs_population_places.json", fixtures / "acs_population_counties.json"
        )
        crosswalk = PlaceCountyCrosswalk.from_file(fixtures / "place_county_crosswalk.csv")
        universe, weights, ureport = build_universe(
            counties_file=fixtures / "gazetteer_counties.txt",
            places_file=fixtures / "gazetteer_places.txt",
            population=pop,
            crosswalk=crosswalk,
            write=False,
        )
        print(ureport.render())

        print("\n=== FEATURES ===")
        frames = [
            census_acs.ingest([fixtures / "acs_population_places.json"], vintage="2020-2024"),
            fema_nri.ingest(fixtures / "fema_nri_counties.csv"),
            usda_amenities.ingest(fixtures / "usda_natural_amenities.csv"),
        ]
        features, coverage, freport = build_features(
            universe=universe, long_frames=frames, write=False
        )
        print(freport.render())

        print("\ncoverage, lowest first — missing data lowers coverage, it does not score zero:")
        with pl.Config(tbl_rows=5, tbl_hide_dataframe_shape=True):
            print(
                coverage.sort("coverage").select(
                    ["geo_id", "name", "indicators_present", "indicators_applicable", "coverage"]
                ).head(5)
            )

        print("\n=== GUARDRAIL ===")
        try:
            manifest.assert_no_synthetic("scoring")
        except SyntheticDataError as exc:
            print("scoring correctly refused synthetic input:\n")
            print("  " + str(exc).replace("\n", "\n  "))
            return 0

        print("GUARDRAIL FAILED: synthetic input was not refused", file=sys.stderr)
        return 1


def stage_pending(name: str, phase: int, description: str):
    def run(args) -> int:
        print(f"stage '{name}' is not implemented yet — scheduled for Phase {phase}.")
        print(f"  will: {description}")
        return 1

    return run


STAGES = {
    "data": stage_data,
    "universe": stage_needs_real_data("universe"),
    "features": stage_needs_real_data("features"),
    "demo": stage_demo,
    "score": stage_pending(
        "score", 4, "apply curves, weights, aggregation and knockouts -> scores.parquet"
    ),
    "diagnostics": stage_pending(
        "diagnostics", 4, "hype residual, coverage, sensitivity, political with/without"
    ),
    "report": stage_pending("report", 4, "ranked HTML with per-place explanations"),
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wlm", description=__doc__)
    parser.add_argument("stage", choices=sorted(STAGES))
    parser.add_argument(
        "--offline", action="store_true", help="never touch the network; require local files"
    )
    args = parser.parse_args(argv)
    return STAGES[args.stage](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
