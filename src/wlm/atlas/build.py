"""Build the atlas: an interactive map over the evidence the ranking already uses.

    python -m wlm.atlas.build          (make atlas)

Writes `output/atlas/`:

    index.html, atlas.js, score.js   the page (copied from wlm/atlas/page)
    data/core.json                   every county and place: factor scores, raw values, rents
    geo/us.json                      national state and county outlines
    geo/<ST>.json                    one state's counties, towns and rent-bearing ZIPs

**No number here is new evidence.** Factor scores come from `engine.domain_scores` run
over the registry with domains regrouped into the atlas factors (config/atlas.yaml), so the
curves, the sensitive gate and the within-factor geometric mean are the engine's own. The
page only recombines factors with the weights the household sets, and `score.js` is held
to `engine.score` by `tests/test_atlas.py`.

The new inputs are Census boundary shapes, the Census ZCTA-to-place relationship file and
Zillow's ZIP-level rent and home-value files — all downloaded through `wlm.fetch`, so each
carries a checksum in the manifest like everything else (Principle 3).
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import polars as pl
import yaml

from wlm.atlas import geometry
from wlm.geo import is_in_scope
from wlm.paths import CONFIG, FEATURES, OUTPUT, RAW, UNIVERSE

OUT = OUTPUT / "atlas"
PAGE = Path(__file__).parent / "page"

ATLAS_DOWNLOADS: dict[str, list[str]] = {
    "census_tiger": [
        "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip",
        "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_500k.zip",
        "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_place_500k.zip",
        # ZCTAs are only redrawn after a decennial census; 2020 is current.
        "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip",
    ],
    "census_rel2020": [
        "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_place20_natl.txt",
    ],
    "zillow_research": [
        "https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_month.csv",
        "https://files.zillowstatic.com/research/public_csvs/zhvi/Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
    ],
}

# Simplification tolerance (degrees) and quantisation per layer. National outlines are drawn
# a few pixels per county; a state file is drawn zoomed to a 50-mile region, where 0.0006°
# (~60 m) is under a pixel.
NATIONAL = {"tolerance": 0.012, "q": 1000, "min_area": 0.0005}
STATE_COUNTY = {"tolerance": 0.0015, "q": 10000, "min_area": 1e-6}
TOWN = {"tolerance": 0.0006, "q": 10000, "min_area": 2e-7}
ZIP = {"tolerance": 0.0008, "q": 10000, "min_area": 1e-6}

# A town's rent is the land-area-weighted mean over the ZIPs that overlap it. Below this
# share of the town's land carrying a Zillow figure, the estimate says more about one
# corner than the town, so it is left missing and the county's rent stands in, labelled.
MIN_ZIP_SHARE = 0.25


class AtlasError(ValueError):
    """The atlas config disagrees with the registry."""


def load_config(path: Path = CONFIG / "atlas.yaml") -> dict:
    return yaml.safe_load(path.read_text())


def factor_of(cfg: dict, registry: dict[str, dict]) -> dict[str, str]:
    """indicator -> factor. Every registered indicator is placed exactly once or excluded."""
    placed: dict[str, str] = {}
    for f in cfg["factors"]:
        for ind in f["indicators"]:
            if ind in placed:
                raise AtlasError(f"{ind} is in both '{placed[ind]}' and '{f['id']}'")
            placed[ind] = f["id"]
    excluded = set(cfg.get("excluded") or {})
    unknown = (set(placed) | excluded) - set(registry)
    if unknown:
        raise AtlasError(f"atlas.yaml names unregistered indicators: {sorted(unknown)}")
    orphans = set(registry) - set(placed) - excluded
    if orphans:
        raise AtlasError(
            f"registered indicators with no atlas factor and no exclusion reason: {sorted(orphans)}"
        )
    for ind in cfg.get("sensitive_opt_in") or {}:
        if not registry[ind].get("sensitive"):
            raise AtlasError(f"{ind} is opted in as sensitive but is not a sensitive indicator")
        if ind not in placed:
            raise AtlasError(f"{ind} is opted in but sits in no factor")
    weights = sum(f["default_weight"] for f in cfg["factors"])
    if weights != 100:
        raise AtlasError(f"factor default weights sum to {weights}, not 100")
    return placed


def factor_profile(cfg: dict, registry: dict[str, dict]) -> tuple[dict, dict]:
    """The registry regrouped by factor, and a profile weighting every factor equally.

    Equal weights here only decide which factors are computed — `domain_scores` returns each
    factor's own value, untouched by the others. The household's weights are applied later,
    on the page.
    """
    placed = factor_of(cfg, registry)
    regrouped = {i: {**e, "domain": placed[i]} for i, e in registry.items() if i in placed}
    opt_in = cfg.get("sensitive_opt_in") or {}
    profile = {
        "domain_weights": {f["id"]: 1.0 for f in cfg["factors"]},
        "sensitive_indicators": sorted(opt_in),
        "curve_overrides": {i: dict(v) for i, v in opt_in.items()},
    }
    return regrouped, profile


def factor_scores(
    features: pl.DataFrame, universe: pl.DataFrame, cfg: dict, registry: dict[str, dict]
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]], list[str]]:
    """Per-factor desirability for every county, and for every place with county context."""
    from wlm.scoring.engine import ScoreReport, domain_scores, places_with_county_context

    regrouped, profile = factor_profile(cfg, registry)
    report = ScoreReport()
    counties = features.filter(pl.col("geo_level") == "county")
    county_f = domain_scores(counties, regrouped, profile, report=report)

    place_rows = universe.filter(
        (pl.col("geo_level") == "place") & pl.col("county_geoid").is_not_null()
    ).select(["geo_id", "county_geoid"])
    all_counties = set(universe.filter(pl.col("geo_level") == "county")["geo_id"])
    combined = places_with_county_context(features, place_rows, all_counties)
    place_f = domain_scores(combined, regrouped, profile, report=report)
    return county_f, place_f, report.warnings


# ---------------------------------------------------------------- the public site

PRESET_CURVES = {
    "winter": ("climate_temp_winter_mean", "ideal_band"),
    "low": ("climate_winter_low", "ideal_band"),
    "snow": ("climate_annual_snowfall", "ideal_point"),
}


def check_web(cfg: dict, registry: dict[str, dict]) -> None:
    """The public-site section must agree with the factors and the registry."""
    web = cfg.get("web") or {}
    expected = {f["id"] for f in cfg["factors"] if not f.get("household_only")}
    weights = web.get("default_weights") or {}
    if set(weights) != expected:
        raise AtlasError(f"web.default_weights must name exactly {sorted(expected)}, got {sorted(weights)}")
    if sum(weights.values()) != 100:
        raise AtlasError(f"web.default_weights sum to {sum(weights.values())}, not 100")
    for layer in web.get("sensitive_layers") or []:
        entry = registry.get(layer["indicator"])
        if not entry or not entry.get("sensitive"):
            raise AtlasError(f"layer '{layer['id']}' must point at a sensitive indicator")
        if "even" in layer["directions"] and "even" not in layer:
            raise AtlasError(f"layer '{layer['id']}' offers 'even' without a target")
    for preset in web.get("climate_presets") or []:
        for key, (ind, _) in PRESET_CURVES.items():
            if key not in preset:
                raise AtlasError(f"climate preset '{preset['id']}' has no '{key}' curve")
            if registry[ind]["curve"] not in ("ideal_band", "ideal_point"):
                raise AtlasError(f"{ind} is no longer a band curve; the presets would mean nothing")


def climate_preset_scores(
    features: pl.DataFrame, cfg: dict, registry: dict[str, dict]
) -> dict[str, list[float | None]]:
    """county -> the climate factor under each winter preset, in config order.

    Every climate indicator is county-level, so a town's climate is its county's: places
    need no pass of their own. Each preset is a curve override handed to the engine, the
    same way a household's elicited band would be.
    """
    from wlm.scoring.engine import domain_scores

    presets = (cfg.get("web") or {}).get("climate_presets") or []
    regrouped, _ = factor_profile(cfg, registry)
    climate = {i: e for i, e in regrouped.items() if e["domain"] == "climate"}
    counties = features.filter(
        (pl.col("geo_level") == "county") & pl.col("indicator_id").is_in(list(climate))
    )
    out: dict[str, list[float | None]] = defaultdict(lambda: [None] * len(presets))
    for k, preset in enumerate(presets):
        overrides = {
            ind: {"curve": curve, "curve_params": preset[key]}
            for key, (ind, curve) in PRESET_CURVES.items()
        }
        overrides["climate_heating_degree_days"] = {"indifferent": True}
        profile = {"domain_weights": {"climate": 1.0}, "curve_overrides": overrides}
        for gid, per in domain_scores(counties, climate, profile).items():
            out[gid][k] = per.get("climate")
    return out


def sensitive_values(features: pl.DataFrame, cfg: dict) -> dict[tuple[str, str], list]:
    """(level, geo) -> [percentile, raw] per sensitive layer, flattened in config order.

    The page applies the visitor's chosen direction: higher is the percentile, lower is
    its complement (the engine's own monotone curves), and "even" is the engine's
    ideal_point on the raw value. Nothing here assumes a direction.
    """
    layers = (cfg.get("web") or {}).get("sensitive_layers") or []
    index = {layer["indicator"]: k for k, layer in enumerate(layers)}
    out: dict[tuple[str, str], list] = {}
    rows = features.filter(pl.col("indicator_id").is_in(list(index))).select(
        ["geo_level", "geo_id", "indicator_id", "value", "percentile"]
    )
    for level, gid, ind, val, pct in rows.iter_rows():
        row = out.setdefault((level, gid), [None] * (2 * len(layers)))
        k = index[ind]
        row[2 * k], row[2 * k + 1] = pct, val
    return out


# ---------------------------------------------------------------- ZIP rents and prices


def _zip_file(kind: str) -> Path:
    name = next(Path(u).name for u in ATLAS_DOWNLOADS["zillow_research"] if f"/{kind}/" in u)
    return RAW / "zillow_research" / name


def read_zillow_zips(path: Path) -> tuple[dict[str, tuple[str, float]], str]:
    """ZIP -> (state, latest value), and the newest month in the file.

    Uses `zillow._latest`, so a ZIP Zillow stopped publishing a year ago stays missing
    rather than presenting an old price as today's.
    """
    from wlm.ingest.zillow import _latest

    out: dict[str, tuple[str, float]] = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        dates = [f for f in fields if len(f) == 10 and f[4] == "-" and f[:4].isdigit()]
        for row in reader:
            value = _latest(row, dates)
            zcta = (row.get("RegionName") or "").strip().zfill(5)
            if value is not None and zcta.isdigit():
                out[zcta] = ((row.get("State") or "").strip(), value)
    return out, (dates[-1][:7] if dates else "")


def read_zcta_place(path: Path) -> list[tuple[str, str, float, float]]:
    """(zcta, place, overlapping land m², place land m²) from the Census relationship file."""
    rows = []
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            z, p = r.get("GEOID_ZCTA5_20") or "", r.get("GEOID_PLACE_20") or ""
            if z and p:
                rows.append((z, p, float(r["AREALAND_PART"] or 0), float(r["AREALAND_PLACE_20"] or 0)))
    return rows


def town_values(
    rel: list[tuple[str, str, float, float]], values: dict[str, float], places: set[str]
) -> dict[str, tuple[float, float]]:
    """place -> (land-weighted mean over overlapping ZIPs that have a value, share covered)."""
    num: dict[str, float] = defaultdict(float)
    den: dict[str, float] = defaultdict(float)
    land: dict[str, float] = {}
    for z, p, part, place_land in rel:
        if p not in places or part <= 0:
            continue
        land[p] = place_land
        if z in values:
            num[p] += part * values[z]
            den[p] += part
    out = {}
    for p, d in den.items():
        share = d / land[p] if land.get(p) else 0.0
        if d > 0 and share >= MIN_ZIP_SHARE:
            out[p] = (num[p] / d, min(share, 1.0))
    return out


# ---------------------------------------------------------------- outlines


def _shapes(name: str):
    return geometry.read_shapes(RAW / "census_tiger" / name)


def build_geometry(place_ids: set[str], zips: dict[str, dict], out: Path) -> dict[str, int]:
    """Write geo/us.json and one geo/<ST>.json per state. Returns bytes per file."""
    out.mkdir(parents=True, exist_ok=True)
    usps: dict[str, str] = {}
    states, us_counties = [], []
    per_state: dict[str, dict[str, list]] = defaultdict(lambda: {"counties": [], "towns": [], "zips": []})

    for attrs, geom in _shapes("cb_2024_us_state_500k.zip"):
        fips = attrs["STATEFP"]
        if not is_in_scope(fips + "000"):
            continue
        usps[fips] = attrs["STUSPS"]
        states.append({"id": fips, "n": attrs["NAME"], "p": geometry.encode(geom, **NATIONAL)})

    for attrs, geom in _shapes("cb_2024_us_county_500k.zip"):
        gid = attrs["GEOID"]
        if attrs["STATEFP"] not in usps:
            continue
        us_counties.append({"id": gid, "p": geometry.encode(geom, **NATIONAL)})
        per_state[usps[attrs["STATEFP"]]]["counties"].append(
            {"id": gid, "n": attrs["NAMELSAD"], "p": geometry.encode(geom, **STATE_COUNTY)}
        )

    for attrs, geom in _shapes("cb_2024_us_place_500k.zip"):
        gid = attrs["GEOID"]
        if gid in place_ids and attrs["STATEFP"] in usps:
            per_state[usps[attrs["STATEFP"]]]["towns"].append(
                {"id": gid, "p": geometry.encode(geom, **TOWN)}
            )

    for attrs, geom in _shapes("cb_2020_us_zcta520_500k.zip"):
        z = attrs.get("ZCTA5CE20") or attrs.get("GEOID20")
        info = zips.get(z)
        if not info or info["st"] not in per_state:
            continue
        per_state[info["st"]]["zips"].append(
            {"id": z, "r": info.get("r"), "h": info.get("h"), "p": geometry.encode(geom, **ZIP)}
        )

    sizes = {}

    def write(path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, separators=(",", ":")))
        sizes[path.name] = path.stat().st_size

    write(out / "us.json", {"q": NATIONAL["q"], "states": states, "counties": us_counties})
    for st, layers in per_state.items():
        write(out / f"{st}.json", {"q": TOWN["q"], **layers})
    return sizes


# ---------------------------------------------------------------- core data


def _r(x: float | None, sig: int = 4) -> float | None:
    if x is None:
        return None
    return float(f"{x:.{sig}g}")


def _sources() -> dict[str, dict]:
    reg = yaml.safe_load((CONFIG / "sources.yaml").read_text())["sources"]
    return {s["id"]: {"name": s["name"], "url": s["url"], "license": s["license"]} for s in reg}


def _shape(cfg: dict, county_f: dict, place_f: dict) -> list[list[float]]:
    """Per-factor influence reshaping, in the page's factor order.

    Measured over counties and towns together, because the page ranks towns while showing
    county context and a factor's spread should be the one the household actually sees.
    """
    from wlm.scoring.engine import influence_scale

    combined = {("c", k): v for k, v in county_f.items()}
    combined.update({("p", k): v for k, v in place_f.items()})
    shape = influence_scale(combined)
    return [
        [_r(shape.get(f, (1.0, 0.0))[0], 6), _r(shape.get(f, (1.0, 0.0))[1], 6)]
        for f in (x["id"] for x in cfg["factors"])
    ]


def build_core(
    cfg: dict,
    registry: dict[str, dict],
    universe: pl.DataFrame,
    features: pl.DataFrame,
    county_f: dict,
    place_f: dict,
    rents: dict,
    homes: dict,
    months: dict[str, str],
    climate_cp: dict | None = None,
    sens: dict | None = None,
) -> dict:
    factors = [f["id"] for f in cfg["factors"]]
    climate_cp, sens = climate_cp or {}, sens or {}

    def rvec(values) -> list | None:
        return [_r(v, 4) for v in values] if values else None
    placed = factor_of(cfg, registry)

    def fvec(scores: dict[str, float] | None) -> list:
        return [_r((scores or {}).get(f), 3) for f in factors]

    raw: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    vintages: dict[str, Counter] = defaultdict(Counter)
    for level, gid, ind, val, vint in features.select(
        ["geo_level", "geo_id", "indicator_id", "value", "vintage"]
    ).iter_rows():
        if val is not None and ind in placed:
            raw[(level, gid)][ind] = val
            vintages[ind][vint] += 1

    present = {lvl: sorted({i for (l, _), v in raw.items() if l == lvl for i in v})
               for lvl in ("county", "place")}

    counties, places = [], []
    for row in universe.sort("geo_id").iter_rows(named=True):
        gid, lvl = row["geo_id"], row["geo_level"]
        vals = raw.get((lvl, gid), {})
        base = [gid, row["name"], row["state_usps"]]
        loc = [_r(row["lat"], 7), _r(row["lon"], 7), row["population"]]
        if lvl == "county":
            counties.append(base + loc + [fvec(county_f.get(gid)),
                                          [_r(vals.get(i)) for i in present["county"]],
                                          [_r(v, 3) for v in climate_cp[gid]] if gid in climate_cp else None,
                                          rvec(sens.get(("county", gid)))])
        else:
            rent, rent_share = rents.get(gid, (None, None))
            home, home_share = homes.get(gid, (None, None))
            places.append(base + [row["county_geoid"]] + loc + [
                fvec(place_f.get(gid)),
                [_r(vals.get(i)) for i in present["place"]],
                _r(rent), _r(rent_share, 2), _r(home), _r(home_share, 2),
                rvec(sens.get(("place", gid))),
            ])

    from wlm.baseline import BASELINE_COUNTY, BASELINE_LABEL, BASELINE_PLACE
    from wlm.scoring.engine import EPSILON, MIN_WEIGHT_COVERED

    inds = [
        {
            "id": i, "label": registry[i]["label"], "unit": registry[i].get("unit"),
            "factor": placed[i], "source": registry[i].get("source"),
            "curve": (cfg.get("sensitive_opt_in") or {}).get(i, {}).get("curve", registry[i]["curve"]),
            "vintage": vintages[i].most_common(1)[0][0] if vintages[i] else None,
        }
        for i in registry if i in placed
    ]
    return {
        "built": date.today().isoformat(),
        "eps": EPSILON,
        "minCov": MIN_WEIGHT_COVERED,
        # One [k, centre] pair per factor, in factor order. The page applies it in
        # score.js exactly as engine.combine_domains does, so moving the weights here
        # ranks by the same rule as the report.
        "shape": _shape(cfg, county_f, place_f),
        "factors": [{k: f[k] for k in ("id", "label", "blurb", "default_weight")} for f in cfg["factors"]],
        "inds": inds,
        "sources": _sources(),
        "zillowMonth": months,
        "home": {"place": BASELINE_PLACE, "county": BASELINE_COUNTY, "label": BASELINE_LABEL},
        "budget": cfg.get("budget") or {},
        "wishlist": cfg.get("wishlist") or [],
        "challengers": cfg.get("challengers", 8),
        "counties": {
            "cols": ["id", "name", "st", "lat", "lon", "pop", "f", "raw", "climatePresets", "sens"],
            "raw": present["county"],
            "rows": counties,
        },
        "places": {
            "cols": ["id", "name", "st", "county", "lat", "lon", "pop", "f", "raw",
                     "rent", "rentShare", "home", "homeShare", "sens"],
            "raw": present["place"],
            "rows": places,
        },
    }


# ---------------------------------------------------------------- orchestration


def fetch_inputs(offline: bool = False) -> list[str]:
    from wlm.fetch import FetchError, fetch
    from wlm.manifest import Manifest

    manifest = Manifest.load()
    failures = []
    for source_id, urls in ATLAS_DOWNLOADS.items():
        for url in urls:
            try:
                fetch(source_id, url, manifest=manifest, offline=offline, timeout=600)
            except FetchError as exc:
                failures.append(f"{source_id}: {exc.reason}")
    manifest.save()
    return failures


def main(argv: list[str] | None = None) -> int:
    from wlm.ingest.base import registry as load_registry

    argv = argv if argv is not None else sys.argv[1:]
    if not FEATURES.exists() or not UNIVERSE.exists():
        print("atlas: run `make universe features` first", file=sys.stderr)
        return 1
    failures = fetch_inputs(offline="--offline" in argv)
    if failures:
        print("atlas: downloads failed:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1

    cfg = load_config()
    reg = load_registry()
    universe = pl.read_parquet(UNIVERSE)
    features = pl.read_parquet(FEATURES)

    check_web(cfg, reg)
    county_f, place_f, warnings = factor_scores(features, universe, cfg, reg)
    print(f"  factor scores  {len(county_f):,} counties, {len(place_f):,} places")
    climate_cp = climate_preset_scores(features, cfg, reg)
    sens = sensitive_values(features, cfg)
    print(f"  web extras     {len(climate_cp):,} counties x "
          f"{len(cfg['web']['climate_presets'])} climate presets, "
          f"{len(sens):,} geographies with sensitive layers")
    for w in warnings:
        print(f"    warning: {w}")

    zori, zori_month = read_zillow_zips(_zip_file("zori"))
    zhvi, zhvi_month = read_zillow_zips(_zip_file("zhvi"))
    print(f"  zillow zips    {len(zori):,} with rent ({zori_month}), "
          f"{len(zhvi):,} with home value ({zhvi_month})")
    zips: dict[str, dict] = {}
    for z, (st, v) in zori.items():
        zips.setdefault(z, {"st": st})["r"] = round(v)
    for z, (st, v) in zhvi.items():
        zips.setdefault(z, {"st": st})["h"] = round(v, -2)

    place_ids = set(universe.filter(pl.col("geo_level") == "place")["geo_id"])
    rel = read_zcta_place(RAW / "census_rel2020" / "tab20_zcta520_place20_natl.txt")
    rents = town_values(rel, {z: v for z, (_, v) in zori.items()}, place_ids)
    homes = town_values(rel, {z: v for z, (_, v) in zhvi.items()}, place_ids)
    print(f"  town rents     {len(rents):,} of {len(place_ids):,} towns "
          f"(ZIPs with rent cover >= {MIN_ZIP_SHARE:.0%} of the town)")

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)
    core = build_core(cfg, reg, universe, features, county_f, place_f, rents, homes,
                      {"rent": zori_month, "home": zhvi_month}, climate_cp, sens)
    (OUT / "data" / "core.json").write_text(json.dumps(core, separators=(",", ":")))
    print(f"  core.json      {(OUT / 'data' / 'core.json').stat().st_size / 1e6:.1f} MB")

    sizes = build_geometry(place_ids, zips, OUT / "geo")
    print(f"  outlines       {len(sizes)} files, {sum(sizes.values()) / 1e6:.1f} MB total, "
          f"largest {max(sizes, key=sizes.get)} {max(sizes.values()) / 1e6:.1f} MB")

    for f in PAGE.iterdir():
        if f.is_file():
            shutil.copy2(f, OUT / f.name)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
