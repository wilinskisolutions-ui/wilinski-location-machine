"""How a number is shown to a human. One definition, imported everywhere.

There were three copies of this, and they disagreed. The questionnaire knew that a `share`
runs 0-1 and must be multiplied by 100; the report and the blind export did not, so an
unemployment rate of 0.034 was displayed to Emil as **"0.0"** — a real figure rendered as
a meaningless one, on a page meant to help him choose where to live.

Two rules keep it honest:

  * **A unit is a fact about the data, not a decoration.** `percent` and `share` both hold
    fractions in this dataset, so both are multiplied by 100 here. Getting that wrong is
    how "79%" once became 79.0 on an indicator whose values run 0-1, putting a preference
    band entirely outside the distribution and killing the indicator in silence.
  * **Formatting is one-way.** Nothing parses these strings back into numbers. Every
    consumer that needs the value carries the raw float alongside the display text.
"""

from __future__ import annotations

# Units holding a 0-1 fraction, shown as a percentage.
FRACTIONS = {"share", "percent"}


def fmt(value: float | None, unit: str | None = None) -> str:
    """Render one indicator value for a human. Missing stays visibly missing."""
    if value is None:
        return "—"

    u = (unit or "").strip().lower()

    if u in FRACTIONS:
        return f"{value * 100:.1f}%"
    if u == "usd":
        return f"${value / 1000:,.0f}k" if value >= 10_000 else f"${value:,.0f}"
    if u == "usd/month":
        return f"${value:,.0f}/mo"
    if u == "degf":
        return f"{value:.0f}°F"
    if u == "inches":
        return f'{value:.0f}"'
    if u == "miles":
        return f"{value:,.0f} mi"
    if u == "minutes":
        return f"{value:.0f} min"
    if u in {"people", "count", "passengers/year"}:
        return f"{value:,.0f}"
    if u == "people/sqmi":
        return f"{value:,.0f}/sq mi"
    if u == "per10k":
        return f"{value:.1f} per 10k"
    if u == "per100k":
        return f"{value:.1f} per 100k"
    if u == "years":
        return f"{value:.1f} yrs"
    if u == "ug/m3":
        return f"{value:.1f} µg/m³"
    if u == "degree_days":
        return f"{value:,.0f} deg-days"
    if u in {"index", "score"}:
        return f"{value:,.1f}"
    if u == "ratio":
        # Ratios in this registry span property-tax rates (~0.008) and price-to-income
        # (~4), so the sensible number of decimals depends on the magnitude.
        return f"{value:.3f}" if abs(value) < 1 else f"{value:,.2f}"
    return f"{value:,.1f}"
