"""Coverage report — what the pipeline actually knows, and what it does not.

Countermeasure #4 from `docs/anti-bias.md` made legible. Large, well-instrumented places
report more data; if that goes unwatched, place size quietly becomes a scoring dimension.

It also answers "what is still missing" from the registry rather than from memory, which is
the only version of that answer worth trusting.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import yaml

from wlm.paths import CONFIG, OUTPUT, PROCESSED

# Why an indicator has no data. Anything not listed here is simply not attempted yet.
KNOWN_BLOCKERS: dict[str, str] = {
    "seda_stanford": "download links are JavaScript-gated; needs one manual download",
    "hud_fmr": "returns HTTP 202 with an empty body; superseded by Zillow ZORI",
    "eia_electricity": "API requires a registered key",
    "medsl_elections": "Dataverse persistent identifier not yet resolved",
    "usda_amenities": "published as .xls behind a changed path; URL not yet re-found",
    "osm_overpass": "egress-blocked, replaced by County Business Patterns",
    "bts_t100": "superseded by bts_intl for the Europe question",
    "bls_laus": "superseded — County Health Rankings republishes the same BLS series",
}


def build(
    *,
    features: Path = PROCESSED / "features.parquet",
    coverage: Path = PROCESSED / "coverage.parquet",
    out: Path = OUTPUT / "coverage.md",
    write: bool = True,
) -> str:
    reg = yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]
    domains = yaml.safe_load((CONFIG / "domains.yaml").read_text())["domains"]
    labels = {d["id"]: d["label"] for d in domains}
    scoring = [d["id"] for d in domains if d.get("scoring")]

    f = pl.read_parquet(features)
    populated = set(f.filter(pl.col("value").is_not_null())["indicator_id"].unique())
    cov = pl.read_parquet(coverage) if Path(coverage).exists() else None

    lines = ["# Coverage report", ""]
    total_reg = len(reg)
    lines.append(f"**{len(populated)} of {total_reg} registered indicators have data.**")
    lines.append("")

    lines += ["## By domain", "", "| Domain | Registered | Populated | Missing |", "|---|---|---|---|"]
    for did in scoring:
        members = [i for i in reg if i["domain"] == did]
        have = [i for i in members if i["id"] in populated]
        lines.append(
            f"| {labels[did]} | {len(members)} | {len(have)} | {len(members) - len(have)} |"
        )
    lines.append("")

    missing = [i for i in reg if i["id"] not in populated]
    if missing:
        lines += [
            "## Unpopulated indicators, and why",
            "",
            "Kept registered rather than deleted: the registry describes what the project",
            "intends to measure, and removing an indicator because its source is awkward",
            "would quietly shrink the question to fit the data.",
            "",
            "| Indicator | Domain | Source | Reason |",
            "|---|---|---|---|",
        ]
        for i in sorted(missing, key=lambda x: (x["source"], x["id"])):
            reason = KNOWN_BLOCKERS.get(i["source"], "not yet attempted")
            lines.append(
                f"| `{i['id']}` | {labels.get(i['domain'], i['domain'])} | `{i['source']}` | {reason} |"
            )
        lines.append("")

    # Populated is not the same as measuring what was specified. Four education indicators
    # stand in for SEDA learning growth because SEDA is form-gated, and they are weaker on
    # exactly the axis that decision was taken to avoid. A reader who sees "education 4 of 6"
    # and nothing else would draw the wrong conclusion.
    substitutes = [i for i in reg if i.get("quality") == "substitute"]
    if substitutes:
        lines += [
            "## Populated, but not with what was specified",
            "",
            "These carry real data and are weaker than the measure the charter asked for.",
            "They are labelled `quality: substitute` in the registry with the reason attached.",
            "",
        ]
        for i in sorted(substitutes, key=lambda x: x["id"]):
            note = " ".join((i.get("quality_note") or "").split())
            lines += [f"**`{i['id']}`** — {labels.get(i['domain'], i['domain'])}", "", note, ""]

    if cov is not None:
        lines += ["## Per-place data coverage", ""]
        for level in ("county", "place"):
            sub = cov.filter(pl.col("geo_level") == level)
            if not sub.height:
                continue
            thin = sub.filter(pl.col("coverage") < 0.25).height
            lines.append(
                f"- **{level}**: {sub.height:,} rows, mean coverage "
                f"{sub['coverage'].mean():.1%}, {thin:,} below 25%"
            )
        lines += [
            "",
            "Coverage is the share of applicable indicators a place actually has. It is",
            "never used to penalise a place — aggregation renormalises over present",
            "indicators — but a systematically thin group is a finding in itself.",
            "",
        ]

    text = "\n".join(lines)
    if write:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text)
    return text


if __name__ == "__main__":
    print(build())
