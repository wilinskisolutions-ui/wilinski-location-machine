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
# Every URL here was verified by live probe on 2026-08-22 (status and byte count recorded
# in CONTEXT.md). Three notes worth keeping:
#
#   * api.census.gov now requires a registered key (X-DataWebAPI-KeyError). Everything
#     Census comes from keyless bulk files instead, which suits Principle 3 better anyway:
#     bulk files are versioned and checksummable, an API is a moving target.
#   * hazards.fema.gov and www.fema.gov return 403 to every header combination — a WAF
#     block, not the egress policy. FEMA NRI comes from ArcGIS instead (see ingest/fema_nri).
#   * overpass-api.de and its mirrors are egress-blocked. County Business Patterns replaces
#     OSM for amenity density: authoritative, complete, no rate limits.
DOWNLOADS: dict[str, list[str]] = {
    # --- universe ---
    "census_gazetteer": [
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_counties_national.zip",
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_place_national.zip",
    ],
    "census_pep": [
        # SUMLEV 162 = place totals; SUMLEV 157 = place x county, which supplies the
        # population weights for places straddling county lines.
        "https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/cities/totals/sub-est2024.csv",
        "https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/counties/totals/co-est2024-alldata.csv",
    ],
    "census_acs5": [
        # Table-based summary file, not the API (which now needs a key). B01003 = total
        # population for EVERY geography including CDPs, which PEP omits entirely: of
        # sub-est2024's 19,479 place rows, 19,465 are active incorporated. GEO_IDs are
        # self-describing ("1600000US4232800" = place), so the 92MB geography lookup is
        # unnecessary.
        "https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-b01003.dat",
        # Tier 2 tables. One file per ACS table, same self-describing GEO_ID format.
        *[
            f"https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-{tbl}.dat"
            for tbl in (
                "b25103",  # median real estate taxes paid
                "b25077",  # median home value
                "b19013",  # median household income
                "b01002",  # median age
                "b05002",  # place of birth (foreign-born share)
                "b07003",  # geographic mobility (residential stability)
                "b08013",  # aggregate travel time to work
                "b08303",  # workers by travel time (denominator for mean commute)
            )
        ],
    ],
    "census_place_codes": [
        "https://www2.census.gov/geo/docs/reference/codes2020/national_place2020.txt",
    ],
    "census_cenpop": [
        # Population-weighted county centroids. Materially better than the Gazetteer's
        # geometric centroid for anything experienced where people live: Dauphin County's
        # geometric centre sits 7.5 miles north of its population centre, in higher and
        # colder terrain, which biased its climate reading by ~3F.
        "https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt",
    ],
    "census_cbsa": [
        "https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx",
    ],

    # --- tier 1: climate ---
    "noaa_normals": [
        "https://www.ncei.noaa.gov/data/normals-annualseasonal/1991-2020/archive/us-climate-normals_1991-2020_v1.0.1_annualseasonal_multivariate_by-station_c20230404.tar.gz",
    ],
    "ghcn_stations": [
        "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt",
    ],

    # --- tier 1: things to do ---
    "census_cbp": [
        "https://www2.census.gov/programs-surveys/cbp/datasets/2022/cbp22co.zip",
    ],

    # --- tier 2 ---
    "openflights": [
        "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat",
    ],
    "bea_rpp": ["https://apps.bea.gov/regional/zip/MARPP.zip"],
    "bls_qcew": ["https://data.bls.gov/cew/data/files/2024/csv/2024_annual_singlefile.zip"],
    "epa_aqs": ["https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_2024.zip"],
    "chr_rwjf": [
        "https://www.countyhealthrankings.org/sites/default/files/media/document/analytic_data2025.csv"
    ],
    "zillow_research": [
        # County files, not metro: they join straight to the universe with no CBSA
        # crosswalk. The metro files stay downloaded for later metro-level work.
        "https://files.zillowstatic.com/research/public_csvs/zhvi/County_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
        "https://files.zillowstatic.com/research/public_csvs/zori/County_zori_uc_sfrcondomfr_sm_month.csv",
        "https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
        "https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv",
    ],
    "nhtsa_fars": [
        "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/National/FARS2023NationalCSV.zip"
    ],
    # Diagnostic only, and deliberately so: the hype index measures how much attention a
    # place is already getting, so that a ranking can be checked against it. It is never
    # a scoring input — penalising popularity would be its own bias, and the goal is to
    # find good places the internet ignores, not to prefer obscurity for its own sake.
    # Sensitive layer, opt-in only. Mirrors MIT doi:10.7910/DVN/VOQCHQ, which Dataverse
    # serves only behind a guestbook form.
    "countypres_mirror": [
        "https://raw.githubusercontent.com/tonmcg/US_County_Level_Election_Results_08-24/master/2024_US_County_Level_Presidential_Results.csv",
        "https://raw.githubusercontent.com/tonmcg/US_County_Level_Election_Results_08-24/master/2020_US_County_Level_Presidential_Results.csv",
    ],
    "usreligioncensus": [
        "https://www.usreligioncensus.org/sites/default/files/2023-06/2020_USRC_Summaries.xlsx",
    ],
    "dol_childcare": [
        "https://www.dol.gov/sites/dolgov/files/WB/media/nationaldatabaseofchildcareprices.xlsx",
    ],
    "irs_migration": [
        "https://www.irs.gov/pub/irs-soi/countyinflow2122.csv",
        "https://www.irs.gov/pub/irs-soi/countyoutflow2122.csv",
    ],
}

# Sources fetched through a query API rather than a static file. Handled by their own
# ingest modules, which page through results and write one file per source.
API_SOURCES = {
    "cdc_wonder": "https://data.cdc.gov/resource/489q-934x.json",
    "bts_intl": "https://data.transportation.gov/resource/xgub-n9bw.json",
    "fema_nri": "arcgis",
    "urban_educationdata": "https://educationdata.urban.org/api/v1/school-districts",
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


def stage_universe(args) -> int:
    """Build the real candidate universe from downloaded Census files."""
    from wlm.geo import build_crosswalk, county_name_index, parse_place_codes
    from wlm.ingest import census_acs, census_pep
    from wlm.paths import PROCESSED, RAW
    from wlm.universe.build import build, read_gazetteer

    gaz_counties = RAW / "census_gazetteer" / "2024_Gaz_counties_national.zip"
    gaz_places = RAW / "census_gazetteer" / "2024_Gaz_place_national.zip"
    place_codes = RAW / "census_place_codes" / "national_place2020.txt"
    sub_est = RAW / "census_pep" / "sub-est2024.csv"
    co_est = RAW / "census_pep" / "co-est2024-alldata.csv"
    # Name the table explicitly. This used to glob "*.dat" and take the first match, which
    # silently became b25077 (home values) once the Tier 2 ACS tables were added — the
    # universe build then failed looking for a population column that file has never had.
    acs_bulk = RAW / "census_acs5" / "acsdt5y2023-b01003.dat"
    acs_bulk = acs_bulk if acs_bulk.exists() else None

    missing = [p for p in (gaz_counties, gaz_places, place_codes, sub_est, co_est) if not p.exists()]
    if missing or acs_bulk is None:
        print("universe: missing inputs — run `make data` first:", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)
        if acs_bulk is None:
            print(f"  {RAW / 'census_acs5'}/*.dat", file=sys.stderr)
        return 1

    # Population sources, chosen deliberately:
    #   counties -> PEP 2024, the most current official estimate.
    #   places   -> ACS 5-year for ALL places, incorporated and CDP alike.
    # PEP omits census designated places entirely (19,465 of its 19,479 place rows are
    # active incorporated), so PEP-for-incorporated + ACS-for-CDP would make vintage
    # correlate with place class. One source for all places keeps them comparable, and
    # percentiles are computed within geo_level so places are never ranked against counties.
    county_pop = census_pep.county_population(co_est)
    place_pop = {g: v for g, v in census_acs.population_from_bulk(acs_bulk).items() if len(g) == 7}
    population = {**county_pop, **place_pop}

    county_rows = read_gazetteer(gaz_counties)
    index = county_name_index(county_rows)
    code_rows, place_classes, unmatched = parse_place_codes(place_codes, index)
    crosswalk, xw_stats = build_crosswalk(code_rows, census_pep.place_county_weights(sub_est))

    universe, weights, report = build(
        counties_file=gaz_counties,
        places_file=gaz_places,
        population=population,
        crosswalk=crosswalk,
        place_classes=place_classes,
        write=True,
    )

    print(report.render())
    print()
    print(f"crosswalk: {xw_stats['places_with_population_weights']:,} places with real "
          f"population weights, {xw_stats['places_evenly_split']:,} split evenly")
    if unmatched:
        states = sorted({u.split("/")[0] for u in unmatched})
        print(f"           {len(unmatched):,} county-name lookups failed (states: {', '.join(states)})")
        print("           handled by the nearest-centroid fallback, counted above")
    print(f"\nwrote {PROCESSED / 'universe.parquet'}")
    return 0


def stage_features(args) -> int:
    """Run every ingest module against the real downloads and build the feature table."""
    import polars as pl

    from wlm import baseline
    from wlm.features.build import build as build_features
    from wlm.geo import read_cbsa_delineation, read_population_centroids
    from wlm.ingest import (
        bls_qcew, bts_intl, cdc_mortality, census_acs, census_cbp,
        bea_rpp, chr_rwjf, county_elections, dol_childcare, epa_aqs, fars,
        fema_nri, noaa_normals, religion_census, urban_education, zillow,
    )
    from wlm.paths import PROCESSED, RAW, UNIVERSE

    if not UNIVERSE.exists():
        print("features: run `make universe` first", file=sys.stderr)
        return 1

    universe = baseline.mark(pl.read_parquet(UNIVERSE))
    counties = universe.filter(pl.col("geo_level") == "county")
    population = {g: p for g, p in zip(counties["geo_id"], counties["population"]) if p}
    centroids = read_population_centroids(RAW / "census_cenpop" / "CenPop2020_Mean_CO.txt")

    frames: list[pl.DataFrame] = []

    climate, cstats = noaa_normals.ingest(
        next((RAW / "noaa_normals").glob("*.tar.gz")), counties, centroids=centroids
    )
    frames.append(climate)
    print(f"  climate    {climate.height:>7,} rows  ({cstats['counties_matched']:,} counties, "
          f"{cstats['stations_read']:,} stations)")

    amenities = census_cbp.ingest(RAW / "census_cbp" / "cbp22co.zip", population)
    frames.append(amenities)
    print(f"  amenities  {amenities.height:>7,} rows")

    air, astats, _ = bts_intl.ingest(
        RAW / "bts_intl" / "intl_segments_2024_europe.json",
        RAW / "openflights" / "airports.dat",
        counties,
        centroids=centroids,
    )
    frames.append(air)
    print(f"  air/europe {air.height:>7,} rows  ({astats['hubs']} transatlantic hubs)")

    hazard = fema_nri.ingest(RAW / "fema_nri" / "nri_counties.json")
    frames.append(hazard)
    print(f"  hazard     {hazard.height:>7,} rows")

    # --- Tier 2 ---
    acs = census_acs.build_indicators(RAW / "census_acs5", universe)
    frames.append(acs)
    print(f"  acs        {acs.height:>7,} rows  ({acs['indicator_id'].n_unique()} indicators)")

    health, hstats = chr_rwjf.ingest(RAW / "chr_rwjf" / "analytic_data2025.csv")
    frames.append(health)
    print(f"  health/chr {health.height:>7,} rows  ({hstats['measures_found']} measures)")

    for filename, indicator in (
        ("County_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv", "cost_home_value_median"),
        ("County_zori_uc_sfrcondomfr_sm_month.csv", "cost_rent_median_zori"),
    ):
        z = zillow.ingest(RAW / "zillow_research" / filename, indicator, vintage="2026")
        frames.append(z)
        print(f"  zillow     {z.height:>7,} rows  ({indicator})")

    air, aqstats = epa_aqs.ingest(RAW / "epa_aqs" / "annual_conc_by_monitor_2024.zip")
    frames.append(air)
    print(f"  air/pm2.5  {air.height:>7,} rows  "
          f"({aqstats['counties_with_monitors']:,} counties have a monitor)")

    roads, rstats = fars.ingest(RAW / "nhtsa_fars" / "FARS2023NationalCSV.zip", population)
    frames.append(roads)
    print(f"  road deaths{roads.height:>7,} rows  "
          f"({rstats['counties_with_deaths']:,} counties with a fatal crash)")

    jobs, jstats = bls_qcew.ingest(RAW / "bls_qcew" / "2024_annual_singlefile.zip", vintage="2024")
    frames.append(jobs)
    print(f"  jobs/qcew  {jobs.height:>7,} rows  ({jstats['counties_with_sectors']:,} counties)")

    injury, istats = cdc_mortality.ingest(RAW / "cdc_wonder" / "county_injury_2023.json")
    frames.append(injury)
    print(f"  injury/cdc {injury.height:>7,} rows  (firearm + overdose deaths)")

    schools, sstats = urban_education.ingest(RAW / "urban_educationdata")
    frames.append(schools)
    print(f"  schools    {schools.height:>7,} rows  ({sstats['counties']:,} counties; "
          f"{sstats['sentinels_rejected']:,} withheld cells rejected, "
          f"{sstats['grad_rates_dropped_unrepresentative']} grad rates too thin to represent "
          f"their county)")

    votes, vstats = county_elections.ingest(RAW / "countypres_mirror")
    frames.append(votes)
    print(f"  elections  {votes.height:>7,} rows  ({vstats['counties']:,} counties; "
          f"Alaska excluded - it reports by House district, and 02020 is both Anchorage "
          f"and District 20)")

    faith, fstats = religion_census.ingest(
        RAW / "usreligioncensus" / "2020_USRC_Summaries.xlsx"
    )
    frames.append(faith)
    print(f"  religion   {faith.height:>7,} rows  ({fstats['counties']:,} counties; "
          f"{fstats['over_100pct_dropped']} over 100% adherence dropped)")

    care, cstats = dol_childcare.ingest(
        RAW / "dol_childcare" / "nationaldatabaseofchildcareprices.xlsx"
    )
    frames.append(care)
    print(f"  childcare  {care.height:>7,} rows  ({cstats['counties']:,} counties, "
          f"{cstats['year']} prices annualised)")

    cbsa = read_cbsa_delineation(RAW / "census_cbsa" / "list1_2023.xlsx")
    prices, pstats = bea_rpp.ingest(RAW / "bea_rpp" / "MARPP.zip", cbsa)
    frames.append(prices)
    print(f"  prices/rpp {prices.height:>7,} rows  "
          f"({pstats['counties_matched']:,} of {pstats['counties_in_metros']:,} metro counties)")

    features, coverage, report = build_features(universe=universe, long_frames=frames, write=False)
    features = baseline.compare(features)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    universe.write_parquet(UNIVERSE)
    features.write_parquet(PROCESSED / "features.parquet")
    coverage.write_parquet(PROCESSED / "coverage.parquet")

    print()
    print(report.render())
    print(f"\nbaseline: {baseline.BASELINE_LABEL} "
          f"(place {baseline.BASELINE_PLACE}, county {baseline.BASELINE_COUNTY}) "
          f"— scored, excluded from candidates")
    print(f"wrote {PROCESSED / 'features.parquet'}")
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
            ("fema_nri", "fema_nri_counties.json"),
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
            fema_nri.ingest(fixtures / "fema_nri_counties.json"),
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


def _profiles_or_placeholder(args) -> list[dict]:
    """The elicited profiles, or the placeholder weights with that said out loud.

    Emil and Winsor have not answered yet. Scoring against the placeholders is useful — it
    is how the machinery gets exercised and how they see the format before committing an
    hour each — but a ranking built on numbers nobody chose must never be mistaken for a
    ranking built on their preferences.
    """
    import yaml

    from wlm.paths import CONFIG, ROOT
    from wlm.profile import load_profile
    from wlm.questionnaire.session import REAL_PEOPLE

    found = []
    for person in REAL_PEOPLE:
        path = ROOT / "profiles" / f"{person}.yaml"
        if path.exists():
            found.append(load_profile(path))
    if found:
        return found

    domains = yaml.safe_load((CONFIG / "domains.yaml").read_text())["domains"]
    print(
        "no elicited profile found in profiles/ — using the placeholder weights from\n"
        "  config/domains.yaml. These are numbers nobody chose. Run `make questionnaire`\n"
        "  before treating any of this as an answer.\n"
    )
    return [
        {
            "person": "placeholder",
            "method": "PLACEHOLDER weights from config/domains.yaml — not elicited",
            "domain_weights": {
                d["id"]: float(d["default_weight"])
                for d in domains
                if d.get("scoring") and d["default_weight"] > 0
            },
        }
    ]


def stage_score(args) -> int:
    """Rank counties, then places inside the winners, and band every rank."""
    import polars as pl

    from wlm.ingest.base import registry as load_registry
    from wlm.paths import FEATURES, PROCESSED, UNIVERSE
    from wlm.scoring.engine import apply_knockouts, sensitivity, two_stage

    features = pl.read_parquet(FEATURES)
    universe = pl.read_parquet(UNIVERSE)
    registry = load_registry()
    names = dict(universe.select(["geo_id", "name"]).iter_rows())

    for profile in _profiles_or_placeholder(args):
        person = profile.get("person", "household")
        counties, places, report = two_stage(features, universe, registry, profile)
        counties = apply_knockouts(
            counties, features, profile.get("knockouts"), report, names
        )

        bands = sensitivity(features.filter(pl.col("geo_level") == "county"), registry, profile)
        counties = counties.join(bands, on="geo_id", how="left")

        PROCESSED.mkdir(parents=True, exist_ok=True)
        counties.write_parquet(PROCESSED / f"scores-county-{person}.parquet")
        places.write_parquet(PROCESSED / f"scores-place-{person}.parquet")

        print(f"{person}: {counties.height:,} counties, {places.height:,} places scored")
        for rule in report.knockouts:
            print(f"  knockout {rule['indicator']} {rule['op']} {rule['value']:,.0f} "
                  f"removed {rule['removed']:,} (best: {rule['best_removed']})")
        # two_stage appends the county pass and the place pass, which warn about the same
        # data-less domains twice. Say each thing once.
        for warning in dict.fromkeys(report.warnings):
            print(f"  warning: {warning}")
    return 0


def stage_report(args) -> int:
    """Render the ranking — refusing any rank that arrives without its band."""
    from wlm.report.build import UnbandedRankingError, build

    for profile in _profiles_or_placeholder(args):
        try:
            path, report = build(profile)
        except UnbandedRankingError as exc:
            print(f"refused to write a report: {exc}")
            return 1
        flips = report.counties.coin_flips + report.places.coin_flips
        print(f"{report.person}: wrote {path}")
        print(f"  {len(report.counties.rows)} counties, {len(report.places.rows)} towns, "
              f"{flips} labelled coin flips")
        for warning in list(dict.fromkeys(report.warnings))[:6]:
            print(f"  warning: {warning}")
    return 0


def stage_diagnostics(args) -> int:
    """The anti-bias checks. None of these feeds a score; all of them judge one."""
    import polars as pl

    from wlm.diagnostics import blind, coverage, hype, political
    from wlm.paths import OUTPUT, PROCESSED

    scores_files = sorted(PROCESSED.glob("scores-county-*.parquet"))
    if not scores_files:
        print("diagnostics: run `make score` first — there is nothing to check yet.")
        return 1
    scores = pl.read_parquet(scores_files[0])

    coverage.build()
    print(f"  coverage   -> {OUTPUT / 'coverage.md'}")

    hype.build(scores)
    print(f"  hype       -> {OUTPUT / 'hype.md'}")

    blind.build(list(scores.head(12)["geo_id"]))
    print(f"  blind      -> {OUTPUT / 'blind.md'} (key held separately)")

    for profile in _profiles_or_placeholder(args):
        political.build(profile)
        print(f"  political  -> {OUTPUT / 'political.md'}")
        break

    return 0


def stage_pending(name: str, phase: int, description: str):
    def run(args) -> int:
        print(f"stage '{name}' is not implemented yet — scheduled for Phase {phase}.")
        print(f"  will: {description}")
        return 1

    return run


STAGES = {
    "data": stage_data,
    "universe": stage_universe,
    "features": stage_features,
    "demo": stage_demo,
    "score": stage_score,
    "diagnostics": stage_diagnostics,
    "report": stage_report,
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
