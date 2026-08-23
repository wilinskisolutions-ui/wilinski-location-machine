"""Turn scores into something Emil and Winsor can read — and refuse to do it badly.

GOAL.md Principle 9: *every ranking ships with a sensitivity band; an unstable rank is
reported as unstable.* Adding a band column would satisfy the letter of that and miss the
point, because the failure mode is not "we forgot the column" — it is publishing a
confident-looking list of ranks that a small change in weights would reshuffle.

So the guard is structural, in the same spirit as the synthetic-data guard: `require_bands`
raises on any ranking whose rows lack `rank_p05`/`rank_p95`, and it runs before anything is
rendered. A rank without its uncertainty cannot be published from here by construction, not
by anyone remembering.

Two stages, as the engine already produces them: counties first on their ~39 indicators,
then places inside the winning counties.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import yaml

from wlm.baseline import BASELINE_COUNTY, BASELINE_LABEL, BASELINE_PLACE
from wlm.manifest import Manifest
from wlm.paths import CONFIG, FEATURES, OUTPUT, UNIVERSE
from wlm.units import fmt as unit_fmt
from wlm.scoring.engine import (
    attach_desirability,
    places_with_county_context,
    sensitivity,
    two_stage,
)

# A rank band wider than this many positions is not a rank, it is a coin flip. Reporting
# "12th" for something that lands anywhere between 4th and 90th is the false precision the
# principle exists to prevent.
COIN_FLIP_SPREAD = 40

# Indicators the trade-offs never touched still count, at a small weight — the same floor
# the scoring engine applies, repeated here so explanations match the scores.
WEIGHT_FLOOR = 0.05


class UnbandedRankingError(ValueError):
    """A ranking was about to be published without its sensitivity band."""


def require_bands(frame: pl.DataFrame, *, what: str) -> None:
    """Refuse to publish a ranking that does not carry its own uncertainty.

    This is Principle 9 made mechanical. It is deliberately blunt: no flag disables it and
    no caller can opt out, because the one time it matters is the time someone is in a
    hurry to see the answer.
    """
    if frame.is_empty():
        return  # nothing to mislead anyone with

    missing = [c for c in ("rank_p05", "rank_p95") if c not in frame.columns]
    if missing:
        raise UnbandedRankingError(
            f"{what}: ranking carries no sensitivity band ({', '.join(missing)} absent). "
            "Run scoring.engine.sensitivity() and join it on before reporting — a rank "
            "without its band is false precision (GOAL.md Principle 9)."
        )

    unbanded = frame.filter(pl.col("rank_p05").is_null() | pl.col("rank_p95").is_null())
    if unbanded.height:
        names = ", ".join(unbanded.head(3)["geo_id"])
        raise UnbandedRankingError(
            f"{what}: {unbanded.height} of {frame.height} rows have no band (e.g. {names}). "
            "Every published rank needs one; widen the sensitivity run rather than "
            "dropping the requirement."
        )


# --------------------------------------------------------------------------- explanation


def _effective_weights(registry: dict[str, dict], profile: dict) -> dict[str, float]:
    """One weight per indicator, matching how the engine actually combines them.

    Domain weight spread over the domain's indicators in proportion to their elicited
    within-domain weights. Without this an explanation would attribute a place's score to
    whichever indicator happened to be extreme rather than to what the household weighted.
    """
    domain_weights = {k: v for k, v in (profile.get("domain_weights") or {}).items() if v > 0}
    indicator_weights = profile.get("indicator_weights") or {}

    by_domain: dict[str, list[str]] = {}
    for iid, entry in registry.items():
        if entry["domain"] in domain_weights:
            by_domain.setdefault(entry["domain"], []).append(iid)

    effective: dict[str, float] = {}
    for domain, ids in by_domain.items():
        raw = {i: max(indicator_weights.get(i, 0.0), WEIGHT_FLOOR) for i in ids}
        total = sum(raw.values()) or 1.0
        for iid, w in raw.items():
            effective[iid] = domain_weights[domain] * w / total
    return effective


def explain(
    desir: pl.DataFrame,
    geo_id: str,
    effective: dict[str, float],
    registry: dict[str, dict],
    *,
    contributors: int = 5,
    drags: int = 3,
) -> tuple[list[dict], list[dict]]:
    """Why this place, and what is wrong with it.

    Contribution is weight times distance from neutral: an indicator only earns a mention
    by being both weighted and unusual. A place's biggest drag is often more decisive than
    its biggest strength, which is why the drags are never omitted.
    """
    rows = desir.filter(pl.col("geo_id") == geo_id)
    scored = []
    for row in rows.iter_rows(named=True):
        weight = effective.get(row["indicator_id"], 0.0)
        if weight <= 0:
            continue
        entry = registry[row["indicator_id"]]
        scored.append(
            {
                "indicator": row["indicator_id"],
                "label": entry.get("label", row["indicator_id"]),
                "domain": entry["domain"],
                "value": row["value"],
                "unit": entry.get("unit", ""),
                "desirability": row["desirability"],
                "vs_baseline": row.get("vs_baseline"),
                "contribution": weight * (row["desirability"] - 0.5),
            }
        )
    scored.sort(key=lambda r: r["contribution"], reverse=True)
    best = [r for r in scored if r["contribution"] > 0][:contributors]
    worst = [r for r in scored if r["contribution"] < 0][-drags:][::-1]
    return best, worst


# ------------------------------------------------------------------------------ assembly


@dataclass
class Ranking:
    level: str
    rows: list[dict] = field(default_factory=list)
    coin_flips: int = 0


@dataclass
class Report:
    person: str
    generated_at: str
    basis: str
    counties: Ranking = field(default_factory=lambda: Ranking("county"))
    places: Ranking = field(default_factory=lambda: Ranking("place"))
    warnings: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    draws: int = 0
    baseline: dict = field(default_factory=dict)
    placeholder: bool = False


def _registry() -> dict[str, dict]:
    return {
        i["id"]: i
        for i in yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]
    }


def _fmt(value, unit: str = "") -> str:
    """Unit-aware, from wlm.units. A local version here showed an unemployment rate of
    0.034 as "0.0" — a real figure rendered meaningless on the page meant to decide a move."""
    return unit_fmt(value, unit)


def assemble(
    profile: dict,
    *,
    features: pl.DataFrame | None = None,
    universe: pl.DataFrame | None = None,
    registry: dict[str, dict] | None = None,
    top_counties: int = 25,
    show: int = 15,
    draws: int = 120,
) -> Report:
    """Score, band, explain. Every ranking that leaves here has been through the guard."""
    Manifest.load().assert_no_synthetic("reporting")

    features = features if features is not None else pl.read_parquet(FEATURES)
    universe = universe if universe is not None else pl.read_parquet(UNIVERSE)
    registry = registry or _registry()

    names = {
        r["geo_id"]: f"{r['name']}, {r['state_usps']}"
        for r in universe.select(["geo_id", "name", "state_usps"]).iter_rows(named=True)
    }
    population = dict(universe.select(["geo_id", "population"]).iter_rows())

    county_scores, place_scores, score_report = two_stage(
        features, universe, registry, profile, top_counties=top_counties
    )

    report = Report(
        person=profile.get("person", "household"),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        basis=profile.get("method", "weights as supplied"),
        warnings=list(score_report.warnings),
        weights={k: v for k, v in (profile.get("domain_weights") or {}).items() if v > 0},
        draws=draws,
        # A ranking built on weights nobody chose looks exactly like one built on their
        # answers. Principle 7 says the weights come from forced trade-offs; until they do,
        # the page has to say so where it cannot be skimmed past.
        placeholder="PLACEHOLDER" in profile.get("method", "").upper(),
    )

    effective = _effective_weights(registry, profile)
    desir_all = attach_desirability(features, registry, profile.get("curve_overrides"))

    for level, scores, ranking in (
        ("county", county_scores, report.counties),
        ("place", place_scores, report.places),
    ):
        if scores.is_empty():
            continue

        if level == "county":
            subset = features.filter(pl.col("geo_level") == "county")
        else:
            # Band the places on exactly the frame they were ranked on. Place-level
            # indicators alone are about seven things, none of them climate, hazard, jobs
            # or health — a band computed over those would be honest about a different
            # question than the one the rank answers.
            place_rows = universe.filter(
                (pl.col("geo_level") == "place")
                & pl.col("geo_id").is_in(set(scores["geo_id"]))
            ).select(["geo_id", "county_geoid"])
            subset = places_with_county_context(
                features, place_rows, set(place_rows["county_geoid"])
            )

        bands = sensitivity(subset, registry, profile, draws=draws)

        ranked = (
            scores.with_row_index("rank", offset=1)
            .join(bands, on="geo_id", how="left")
        )
        # The baseline is scored but is not a destination (CONTEXT.md, 2026-08-22).
        candidates = ranked.filter(
            ~pl.col("geo_id").is_in([BASELINE_COUNTY, BASELINE_PLACE])
        ).head(show)

        require_bands(candidates, what=f"{level} ranking")

        for row in candidates.iter_rows(named=True):
            best, worst = explain(desir_all, row["geo_id"], effective, registry)
            spread = row.get("rank_spread")
            ranking.rows.append(
                {
                    "geo_id": row["geo_id"],
                    "name": names.get(row["geo_id"], row["geo_id"]),
                    "population": population.get(row["geo_id"]),
                    "rank": row["rank"],
                    "score": row["score"],
                    "rank_p05": row["rank_p05"],
                    "rank_p95": row["rank_p95"],
                    "rank_spread": spread,
                    "coin_flip": bool(spread is not None and spread > COIN_FLIP_SPREAD),
                    "worst_domain": row["worst_domain"],
                    "worst_domain_score": row["worst_domain_score"],
                    "coverage": row["weight_covered"],
                    "contributors": best,
                    "drags": worst,
                }
            )
        ranking.coin_flips = sum(1 for r in ranking.rows if r["coin_flip"])

    baseline_row = county_scores.filter(pl.col("geo_id") == BASELINE_COUNTY)
    if baseline_row.height:
        rank = county_scores.with_row_index("rank", offset=1).filter(
            pl.col("geo_id") == BASELINE_COUNTY
        )
        report.baseline = {
            "label": BASELINE_LABEL,
            "score": baseline_row["score"][0],
            "rank": int(rank["rank"][0]),
            "of": county_scores.height,
        }

    return report

# ------------------------------------------------------------------------------ rendering
#
# The page is built to look like what it is: a survey document. Ranks, scores and bands are
# set in a monospace so they line up as columns, and the band is drawn as a tolerance rail
# rather than written out — a number cannot show its own uncertainty, and the whole point of
# Principle 9 is that the uncertainty is not a footnote.


def _e(text) -> str:
    return html.escape(str(text))


def _band_bar(row: dict, worst_rank: int) -> str:
    """The rank band as a tolerance rail: the span it occupies, with the point rank marked."""
    lo, hi = row["rank_p05"], row["rank_p95"]
    span = max(worst_rank, 1)
    left = 100 * (lo - 1) / span
    width = max(100 * (hi - lo + 1) / span, 1.5)
    mark = 100 * (row["rank"] - 1) / span
    klass = "rail wide" if row["coin_flip"] else "rail"
    return (
        f'<div class="{klass}" role="img" aria-label="ranks {lo} to {hi}">'
        f'<i style="left:{left:.2f}%;width:{width:.2f}%"></i>'
        f'<b style="left:{mark:.2f}%"></b></div>'
    )


def _factor_list(items: list[dict]) -> str:
    if not items:
        return '<li class="none"><span>nothing notable</span></li>'
    return "".join(
        f'<li><span>{_e(f["label"])}</span><b>{_e(_fmt(f["value"], f["unit"]))}</b></li>'
        for f in items
    )


def _rows_html(ranking: Ranking) -> str:
    if not ranking.rows:
        return '<p class="empty">Nothing ranked at this level.</p>'
    worst = max(r["rank_p95"] for r in ranking.rows)
    out = []
    for row in ranking.rows:
        flip = (
            f'<span class="flip" title="Moves more than {COIN_FLIP_SPREAD} positions '
            'under small changes in weights">coin flip</span>'
            if row["coin_flip"] else ""
        )
        out.append(f"""<article class="place">
  <div class="rk">{row["rank"]}</div>
  <div class="body">
    <h3>{_e(row["name"])}{flip}</h3>
    <p class="stats">
      <span><em>score</em> {row["score"]:.3f}</span>
      <span><em>band</em> {row["rank_p05"]}&ndash;{row["rank_p95"]}</span>
      <span><em>people</em> {_e(_fmt(row["population"], "people"))}</span>
      <span><em>data</em> {row["coverage"]:.0%}</span>
    </p>
    {_band_bar(row, worst)}
    <div class="cols">
      <div class="col">
        <h4>Why it is here</h4>
        <ul class="good">{_factor_list(row["contributors"])}</ul>
      </div>
      <div class="col">
        <h4>What is wrong with it</h4>
        <ul class="bad">{_factor_list(row["drags"])}</ul>
        <p class="weak">Weakest area: <b>{_e(row["worst_domain"].replace("_", " "))}</b>
          at {row["worst_domain_score"]:.2f}</p>
      </div>
    </div>
  </div>
</article>""")
    return "\n".join(out)


def render_html(report: Report) -> str:
    """The page. Bands are drawn, not tucked into a column nobody reads."""
    for ranking in (report.counties, report.places):
        require_bands(pl.DataFrame(ranking.rows) if ranking.rows else pl.DataFrame(),
                      what=f"{ranking.level} ranking at render time")

    weights = "".join(
        f'<li><span>{_e(k.replace("_", " "))}</span><b>{v:.0f}</b></li>'
        for k, v in sorted(report.weights.items(), key=lambda kv: -kv[1])
    )
    warnings = "".join(f"<li>{_e(w)}</li>" for w in dict.fromkeys(report.warnings))
    baseline = (
        f'<p class="baseline"><em>Harrisburg, for comparison.</em> Score '
        f'{report.baseline["score"]:.3f}, ranked {report.baseline["rank"]:,} of '
        f'{report.baseline["of"]:,} counties. Scored, never offered as a destination.</p>'
        if report.baseline else ""
    )
    flips = report.counties.coin_flips + report.places.coin_flips
    alarm = (
        '<div class="alarm"><b>These are not your weights.</b> Nobody has answered the '
        'questionnaire yet, so everything below was produced from the placeholder numbers in '
        '<code>config/domains.yaml</code>. This page shows that the machine works. It does '
        'not show where to live. Run <code>make questionnaire</code> first.</div>'
        if report.placeholder else ""
    )

    return f"""<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Spectral:ital,wght@0,400;0,500;1,400&display=swap">
<title>Where To Live</title>
<style>
:root {{
  --paper:#eef1f5; --card:#ffffff; --ink:#141d29; --dim:#5d6b7d; --rule:#d3dae3;
  --accent:#0d6d78; --caution:#8a6c12; --drag:#9c4030; --rail:#c3d3d6; --alarm:#8a6c12;
  --display:'Archivo',system-ui,sans-serif;
  --read:'Spectral',Georgia,serif;
  --data:'IBM Plex Mono',ui-monospace,Menlo,monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper:#0e141c; --card:#18212c; --ink:#e4eaf1; --dim:#8d9bad; --rule:#2a3745;
    --accent:#4fb3bd; --caution:#d4b04a; --drag:#e08a76; --rail:#2f4a4f; --alarm:#d4b04a;
  }}
}}
:root[data-theme="dark"] {{
  --paper:#0e141c; --card:#18212c; --ink:#e4eaf1; --dim:#8d9bad; --rule:#2a3745;
  --accent:#4fb3bd; --caution:#d4b04a; --drag:#e08a76; --rail:#2f4a4f; --alarm:#d4b04a;
}}

body {{ background:var(--paper); color:var(--ink); margin:0;
  font:400 16px/1.6 var(--read); -webkit-font-smoothing:antialiased; }}
.wrap {{ max-width:920px; margin:0 auto; padding:56px 24px 96px;
  display:flex; flex-direction:column; gap:8px; }}

.eyebrow {{ font:600 11px/1 var(--display); letter-spacing:.16em; text-transform:uppercase;
  color:var(--accent); margin:0 0 14px; }}
h1 {{ font:700 clamp(2rem,5vw,2.9rem)/1.05 var(--display); letter-spacing:-.025em;
  margin:0 0 .35em; text-wrap:balance; }}
.lede {{ margin:0 0 4px; max-width:62ch; color:var(--dim); font-size:1.05rem; }}
h2 {{ font:600 1.5rem/1.2 var(--display); letter-spacing:-.015em;
  margin:56px 0 4px; padding-bottom:10px; border-bottom:2px solid var(--ink); }}
h2 + .sub {{ margin:0 0 18px; color:var(--dim); font-size:.92rem; max-width:60ch; }}

.note, .alarm {{ padding:18px 20px; margin:22px 0 4px; max-width:66ch; font-size:.95rem; }}
.note {{ border-left:3px solid var(--accent); background:var(--card); }}
.alarm {{ border:1px solid var(--alarm); border-left:4px solid var(--alarm);
  background:var(--card); }}
.alarm b {{ color:var(--alarm); }}
code {{ font:500 .88em var(--data); background:var(--paper); padding:.12em .4em;
  border:1px solid var(--rule); }}
.baseline {{ color:var(--dim); font-size:.93rem; margin:18px 0 0; max-width:64ch; }}
.baseline em {{ color:var(--ink); font-style:normal; font-weight:500; }}

.place {{ display:grid; grid-template-columns:auto 1fr; gap:20px;
  background:var(--card); border:1px solid var(--rule); padding:20px 22px; margin-top:12px; }}
.rk {{ font:600 1.75rem/1 var(--data); color:var(--dim); font-variant-numeric:tabular-nums;
  min-width:2.4ch; text-align:right; padding-top:2px; }}
.body {{ min-width:0; }}
.place h3 {{ font:600 1.18rem/1.3 var(--display); margin:0 0 8px; letter-spacing:-.01em; }}
.flip {{ font:600 9.5px/1 var(--display); letter-spacing:.14em; text-transform:uppercase;
  color:var(--caution); border:1px solid var(--caution); padding:.4em .6em;
  margin-left:.9em; vertical-align:middle; white-space:nowrap; }}

.stats {{ display:flex; flex-wrap:wrap; gap:4px 22px; margin:0 0 14px;
  font:500 .82rem/1.4 var(--data); font-variant-numeric:tabular-nums; }}
.stats em {{ font:600 9.5px/1 var(--display); letter-spacing:.13em; text-transform:uppercase;
  color:var(--dim); font-style:normal; margin-right:.55em; }}

.rail {{ position:relative; height:10px; background:var(--paper);
  border:1px solid var(--rule); margin:0 0 18px; }}
.rail i {{ position:absolute; top:0; bottom:0; background:var(--rail); }}
.rail.wide i {{ background:repeating-linear-gradient(135deg,
  var(--rail) 0 5px, transparent 5px 10px); }}
.rail b {{ position:absolute; top:-4px; width:2px; height:16px; background:var(--accent); }}

.cols {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
@media (max-width:660px) {{ .cols {{ grid-template-columns:1fr; }}
  .place {{ grid-template-columns:1fr; gap:6px; }} .rk {{ text-align:left; }} }}
h4 {{ font:600 9.5px/1 var(--display); letter-spacing:.14em; text-transform:uppercase;
  color:var(--dim); margin:0 0 8px; }}
ul {{ list-style:none; margin:0; padding:0; }}
li {{ display:flex; justify-content:space-between; align-items:baseline; gap:14px;
  padding:5px 0; border-bottom:1px solid var(--rule); font-size:.88rem; }}
li:last-child {{ border-bottom:none; }}
li b {{ font:500 .82rem var(--data); font-variant-numeric:tabular-nums; white-space:nowrap; }}
.good b {{ color:var(--accent); }}
.bad b {{ color:var(--drag); }}
li.none span {{ color:var(--dim); font-style:italic; }}
.weak {{ margin:10px 0 0; font-size:.82rem; color:var(--dim); }}
.weak b {{ color:var(--ink); font-weight:500; }}

.side {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.4fr); gap:32px;
  margin-top:20px; }}
@media (max-width:660px) {{ .side {{ grid-template-columns:1fr; }} }}
.side li {{ font-size:.85rem; }}
.side .warn li {{ display:block; color:var(--dim); padding:7px 0; }}
.empty {{ color:var(--dim); font-style:italic; }}

footer {{ margin-top:64px; padding-top:20px; border-top:1px solid var(--rule);
  color:var(--dim); font-size:.83rem; max-width:64ch; }}
a {{ color:var(--accent); }}
:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
</style>
<div class="wrap">

<p class="eyebrow">Wilinski Location Machine</p>
<h1>Where to live</h1>
<p class="lede">Every US county and every town above five thousand people, scored on the same
public data and ranked by weight. Counties first, on the thirty-nine things measured at
county level; then towns inside the counties that won.</p>

{alarm}

<div class="note"><b>Read the range, not the rank.</b> Each place shows where it lands across
{report.draws} runs with the weights nudged. A place ranked 6th that moves between 2nd and
40th is not better than one ranked 9th — they are the same answer. {flips} of the places
below are wide enough to be called coin flips outright, and are marked as such.</div>

{baseline}

<h2>Counties</h2>
<p class="sub">Ranked on the full indicator set. Weights: {_e(report.basis)}.</p>
{_rows_html(report.counties)}

<h2>Towns</h2>
<p class="sub">Inside the winning counties only, each carrying its county's context as well as
its own local detail — a town judged on its seven local indicators alone would be judged on
almost nothing.</p>
{_rows_html(report.places)}

<h2>What this does not know</h2>
<p class="sub">Every ranking has a shape it cannot see. This one says so.</p>
<div class="side">
  <div>
    <h4>Weight per area</h4>
    <ul>{weights}</ul>
  </div>
  <div>
    <h4>Warnings from this run</h4>
    <ul class="warn">{warnings or "<li>None.</li>"}</ul>
  </div>
</div>

<footer>Generated {_e(report.generated_at)} for {_e(report.person)}. Every number traces to a
checksummed public dataset — no article, listicle or search result is an input anywhere in
this pipeline. A rank here is a shortlist for visiting, not a decision.</footer>
</div>"""

# --------------------------------------------------------------------------------- driver


def build(
    profile: dict | Path | str | None = None,
    *,
    out: Path | None = None,
    write: bool = True,
    **kwargs,
) -> tuple[Path, Report]:
    """Assemble and render. Returns the written path and the report behind it."""
    if profile is None:
        raise ValueError("a profile is required; nothing is scored against defaults")
    if isinstance(profile, (str, Path)):
        from wlm.profile import load_profile

        profile = load_profile(Path(profile))

    report = assemble(profile, **kwargs)
    page = render_html(report)

    out = out or OUTPUT / f"report-{report.person}.html"
    if write:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page)
        (out.with_suffix(".json")).write_text(
            json.dumps(
                {
                    "person": report.person,
                    "generated_at": report.generated_at,
                    "counties": report.counties.rows,
                    "places": report.places.rows,
                    "warnings": report.warnings,
                },
                indent=2,
                default=str,
            )
        )
    return out, report
