"""Countermeasure #3: is this ranking just tracking what everyone is already talking about?

This is the closest thing in the repo to Emil's original complaint. Search for where to
live and the same names keep surfacing — Greenville, Raleigh, Charlotte, Florida, Texas —
not because they fit anyone in particular but because places that grew got written about,
and being written about makes them grow. `docs/anti-bias.md` calls that migration momentum.

The counter is measurement, not exclusion. Build an index of how much attention a county is
already receiving, regress fit score on it, and report the residual. If fit tracks hype
closely, the ranking has learned the internet's preferences rather than the household's.

**The hype index is never a scoring input.** Penalising popularity would be its own bias:
somewhere can be both popular and right. The goal is to see the correlation, and to keep a
standing list of places that score well while nobody is looking at them.

Two components, both measurable from files already in the manifest:
  * net domestic migration per 1,000 residents — IRS SOI county-to-county flows
  * home price appreciation over five years — Zillow ZHVI
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl

from wlm.paths import OUTPUT, PROCESSED, RAW, UNIVERSE

# IRS marks summary rows with pseudo-FIPS in the state column: 96 = all migration including
# foreign, 97 = domestic only, 98 = foreign only, 57-59 = non-migrants. 97 is the one that
# means "everyone who moved here from somewhere else in the US".
DOMESTIC_TOTAL = "97"

# A county needs enough people for a rate to mean anything. Loving County TX (population 64)
# produced 6,250 road deaths per 100k for the same reason.
MIN_POPULATION = 1_000

# Shrinkage constant for the migration rate. Without it the index was topped by counties of
# eight thousand people where forty arrivals reads as a boom: the five loudest places in the
# country came out as Butler County NE, Montgomery County AR and Douglas County MO. Those
# are not what anyone means by hype. Multiplying the rate by pop/(pop+K) pulls small
# denominators toward the national average and leaves large ones essentially untouched,
# which is the standard treatment for a rate whose noise scales with 1/n.
SHRINK_K = 50_000


@dataclass
class HypeReport:
    counties: pl.DataFrame = field(default_factory=pl.DataFrame)
    correlation: float | None = None
    r_squared: float | None = None
    slope: float | None = None
    quiet_winners: pl.DataFrame = field(default_factory=pl.DataFrame)
    loud_losers: pl.DataFrame = field(default_factory=pl.DataFrame)
    notes: list[str] = field(default_factory=list)


def _read_flows(path: Path, county_cols: tuple[int, int], marker_col: int) -> dict[str, int]:
    """Total domestic movers per county, from one IRS flow file.

    The two files have mirrored column orders — inflow keys on the destination, outflow on
    the origin — so the caller says which pair of columns identifies "this county".
    """
    totals: dict[str, int] = {}
    # IRS ships these latin-1: county names like "Doña Ana" break a utf-8 read.
    with path.open(newline="", encoding="latin-1") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if len(row) < 8 or row[marker_col].strip() != DOMESTIC_TOTAL:
                continue
            state, county = row[county_cols[0]].strip(), row[county_cols[1]].strip()
            try:
                people = int(row[7])
            except ValueError:
                continue
            if people < 0:  # IRS uses negatives for suppressed cells
                continue
            totals[f"{int(state):02d}{int(county):03d}"] = people
    return totals


def migration(raw: Path = RAW) -> pl.DataFrame:
    """Net domestic migration per county, people rather than tax returns."""
    folder = raw / "irs_migration"
    inflow_path = folder / "countyinflow2122.csv"
    outflow_path = folder / "countyoutflow2122.csv"
    if not (inflow_path.exists() and outflow_path.exists()):
        return pl.DataFrame(schema={"geo_id": pl.Utf8, "net_migration": pl.Int64})

    # Inflow rows: y2 (cols 0,1) is where people arrived; the marker sits in y1_statefips.
    inflow = _read_flows(inflow_path, county_cols=(0, 1), marker_col=2)
    # Outflow rows: y1 (cols 0,1) is where they left; the marker sits in y2_statefips.
    outflow = _read_flows(outflow_path, county_cols=(0, 1), marker_col=2)

    rows = [
        {"geo_id": geo_id, "net_migration": inflow.get(geo_id, 0) - outflow.get(geo_id, 0)}
        for geo_id in sorted(set(inflow) | set(outflow))
    ]
    return pl.DataFrame(rows) if rows else pl.DataFrame(
        schema={"geo_id": pl.Utf8, "net_migration": pl.Int64}
    )


def appreciation(raw: Path = RAW, years: int = 5) -> pl.DataFrame:
    """Five-year home price change per county, from Zillow ZHVI's wide monthly columns."""
    path = raw / "zillow_research" / "County_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
    if not path.exists():
        return pl.DataFrame(schema={"geo_id": pl.Utf8, "appreciation": pl.Float64})

    frame = pl.read_csv(path, infer_schema_length=0)
    months = [c for c in frame.columns if c[:4].isdigit() and "-" in c]
    if len(months) < years * 12 + 1:
        return pl.DataFrame(schema={"geo_id": pl.Utf8, "appreciation": pl.Float64})
    latest, earlier = months[-1], months[-(years * 12 + 1)]

    rows = []
    for row in frame.select(["StateCodeFIPS", "MunicipalCodeFIPS", earlier, latest]).iter_rows():
        state, county, then, now = row
        if not state or not county or not then or not now:
            continue
        try:
            then_v, now_v = float(then), float(now)
        except ValueError:
            continue
        if then_v <= 0:
            continue
        rows.append(
            {
                "geo_id": f"{int(state):02d}{int(county):03d}",
                "appreciation": (now_v - then_v) / then_v,
            }
        )
    return pl.DataFrame(rows) if rows else pl.DataFrame(
        schema={"geo_id": pl.Utf8, "appreciation": pl.Float64}
    )


def build_index(raw: Path = RAW, universe: pl.DataFrame | None = None) -> pl.DataFrame:
    """One hype score per county: the mean of two attention percentiles."""
    universe = universe if universe is not None else pl.read_parquet(UNIVERSE)
    counties = universe.filter(
        (pl.col("geo_level") == "county") & (pl.col("population") >= MIN_POPULATION)
    ).select(["geo_id", "name", "state_usps", "population"])

    frame = (
        counties.join(migration(raw), on="geo_id", how="left")
        .join(appreciation(raw), on="geo_id", how="left")
        .with_columns(
            (1000 * pl.col("net_migration") / pl.col("population")).alias("migration_rate")
        )
        .with_columns(
            (
                1000
                * pl.col("net_migration")
                / (pl.col("population") + SHRINK_K)
            ).alias("migration_shrunk")
        )
    )

    # Both components required. A county with only one was scoring off that one alone, which
    # put Garfield County MT at the very top of the index on a price series and no migration
    # figure at all.
    frame = frame.drop_nulls(["migration_shrunk", "appreciation"])

    frame = frame.with_columns(
        (pl.col("migration_shrunk").rank("average") / frame.height).alias("p_migration"),
        (pl.col("appreciation").rank("average") / frame.height).alias("p_appreciation"),
    )
    return frame.with_columns(
        ((pl.col("p_migration") + pl.col("p_appreciation")) / 2).alias("hype")
    )


def analyse(
    scores: pl.DataFrame,
    *,
    raw: Path = RAW,
    universe: pl.DataFrame | None = None,
    top_decile: float = 0.10,
    show: int = 15,
) -> HypeReport:
    """Regress fit on hype and report what is left over.

    A high correlation is not proof of failure — desirable places genuinely do attract
    people — but it is the number that decides whether this ranking is telling the
    household anything the internet was not already telling them.
    """
    report = HypeReport()
    index = build_index(raw, universe)
    if index.is_empty() or scores.is_empty():
        report.notes.append("hype index could not be built: migration or price data missing")
        return report

    joined = index.join(scores.select(["geo_id", "score"]), on="geo_id", how="inner")
    if joined.height < 30:
        report.notes.append(f"only {joined.height} counties overlap; correlation not reported")
        report.counties = joined
        return report

    hype = joined["hype"].to_numpy()
    fit = joined["score"].to_numpy()
    slope, intercept = np.polyfit(hype, fit, 1)
    predicted = slope * hype + intercept
    residual = fit - predicted

    report.correlation = float(np.corrcoef(hype, fit)[0, 1])
    report.r_squared = float(report.correlation**2)
    report.slope = float(slope)
    report.counties = joined.with_columns(
        pl.Series("fit_expected_from_hype", predicted),
        pl.Series("residual", residual),
    ).sort("residual", descending=True)

    # The standing table: places in the top decile of fit and the bottom half of hype.
    # These are the ones the internet is not going to mention.
    fit_cut = float(np.quantile(fit, 1 - top_decile))
    report.quiet_winners = (
        report.counties.filter((pl.col("score") >= fit_cut) & (pl.col("hype") < 0.5))
        .sort("score", descending=True)
        .head(show)
    )
    # The mirror image, included because it is the honest half of the same claim: places
    # everyone is moving to that this ranking does not rate.
    hype_cut = float(np.quantile(hype, 0.9))
    report.loud_losers = (
        report.counties.filter((pl.col("hype") >= hype_cut) & (pl.col("score") < np.median(fit)))
        .sort("hype", descending=True)
        .head(show)
    )
    return report


def render(report: HypeReport) -> str:
    lines = [
        "# Hype check",
        "",
        "Is this ranking tracking fit, or tracking what is already being written about?",
        "",
        "The hype index combines net domestic migration (IRS county-to-county flows) with",
        "five-year home price appreciation (Zillow ZHVI). It is a diagnostic and never a",
        "scoring input — penalising popularity would be its own bias.",
        "",
    ]

    if report.correlation is None:
        lines += ["Not computed.", ""] + [f"- {n}" for n in report.notes]
        return "\n".join(lines) + "\n"

    strength = (
        "strong — the ranking is largely reproducing where people already move"
        if report.r_squared >= 0.30
        else "moderate — some overlap, but fit is doing its own work"
        if report.r_squared >= 0.10
        else "weak — fit is substantially independent of how much attention a place gets"
    )
    lines += [
        f"**Correlation between fit and hype: {report.correlation:+.3f}** "
        f"(r² = {report.r_squared:.3f}). That is {strength}.",
        "",
        f"Across {report.counties.height:,} counties with both figures.",
        "",
        "## High fit, low hype",
        "",
        "Top decile of fit, bottom half of attention. These are the places the search",
        "results were never going to surface.",
        "",
    ]
    lines += _table(report.quiet_winners)
    lines += [
        "",
        "## High hype, low fit",
        "",
        "The honest other half: where everyone is moving, that this ranking does not rate.",
        "Worth reading as a challenge to the weights rather than as a verdict on the places.",
        "",
    ]
    lines += _table(report.loud_losers)
    return "\n".join(lines) + "\n"


def _table(frame: pl.DataFrame) -> list[str]:
    if frame.is_empty():
        return ["_None._"]
    out = [
        "| County | Fit | Hype | Net migration /1k | 5-yr prices |",
        "|---|---|---|---|---|",
    ]
    for row in frame.iter_rows(named=True):
        rate = row.get("migration_rate")
        appr = row.get("appreciation")
        out.append(
            f"| {row['name']}, {row['state_usps']} "
            f"| {row['score']:.3f} "
            f"| {row['hype']:.2f} "
            f"| {f'{rate:+.1f}' if rate is not None else '—'} "
            f"| {f'{appr:+.0%}' if appr is not None else '—'} |"
        )
    return out


def build(scores: pl.DataFrame | None = None, *, write: bool = True) -> str:
    if scores is None:
        candidates = sorted(PROCESSED.glob("scores-county-*.parquet"))
        if not candidates:
            return render(HypeReport(notes=["no scores found; run `make score` first"]))
        scores = pl.read_parquet(candidates[0])

    text = render(analyse(scores))
    if write:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "hype.md").write_text(text)
    return text


if __name__ == "__main__":
    print(build())
