/* Recombine factor scores with the household's weights.

   The across-domain step of wlm.scoring.engine, unchanged: a weighted geometric mean with
   the EPSILON floor, renormalised over the factors a place has data for, and flagged below
   the coverage floor. `engine.combine_domains` is the reference; tests/test_atlas.py runs
   both over real rows and random weights and requires them to agree.

   Also the one formatter for indicator values, ported from wlm.units.fmt so the page and
   the report never disagree about what a number means. */
(function (root) {
  "use strict";

  /* `shape` is engine.influence_scale: one [k, centre] pair per factor, in log space,
     stretching each factor about its own mean so that a factor's pull on the ranking
     follows the weight the household gave it rather than the number of indicators the
     factor happens to hold. Without it this page would rank by a different rule than the
     report. Omitted or k === 1 leaves a factor untouched, and `worst` is always the RAW
     value, because that is the 0-1 figure shown on screen. */
  function combine(f, w, eps, minCov, shape) {
    let total = 0, den = 0, num = 0, worst = -1, worstV = Infinity;
    for (let i = 0; i < w.length; i++) {
      const wi = w[i];
      if (!(wi > 0)) continue;
      total += wi;
      const v = f[i];
      if (v === null || v === undefined) continue;
      den += wi;
      const sh = shape && shape[i];
      const k = sh ? sh[0] : 1;
      const lg = Math.log(Math.max(v, eps));
      num += wi * (k === 1 ? lg : sh[1] + k * (lg - sh[1]));
      if (v < worstV) { worstV = v; worst = i; }
    }
    if (den === 0) return null;
    const cov = den / total;
    return { score: Math.exp(num / den), cov: cov, worst: worst, ok: cov >= minCov };
  }

  const FRACTIONS = new Set(["share", "percent"]);
  const n0 = (v) => Math.round(v).toLocaleString("en-US");

  function fmt(value, unit) {
    if (value === null || value === undefined || Number.isNaN(value)) return "—";
    const u = String(unit || "").trim().toLowerCase();
    if (FRACTIONS.has(u)) return (value * 100).toFixed(1) + "%";
    if (u === "usd") return value >= 10000 ? "$" + n0(value / 1000) + "k" : "$" + n0(value);
    if (u === "usd/month") return "$" + n0(value) + "/mo";
    if (u === "degf") return value.toFixed(0) + "°F";
    if (u === "inches") return value.toFixed(0) + "\"";
    if (u === "miles") return n0(value) + " mi";
    if (u === "minutes") return value.toFixed(0) + " min";
    if (u === "people" || u === "count" || u === "passengers/year") return n0(value);
    if (u === "people/sqmi") return n0(value) + "/sq mi";
    if (u === "per10k") return value.toFixed(1) + " per 10k";
    if (u === "per100k") return value.toFixed(1) + " per 100k";
    if (u === "years") return value.toFixed(1) + " yrs";
    if (u === "ug/m3") return value.toFixed(1) + " µg/m³";
    if (u === "degree_days") return n0(value) + " deg-days";
    if (u === "index" || u === "score") return value.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    if (u === "ratio") return Math.abs(value) < 1 ? value.toFixed(3) : value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return value.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  }

  /* Delta-encoded rings -> GeoJSON. Mirror of wlm.atlas.geometry.decode_ring. */
  function decodeRing(ring, q) {
    const pts = new Array(ring.length / 2);
    let x = 0, y = 0;
    for (let i = 0, j = 0; i < ring.length; i += 2, j++) {
      if (i === 0) { x = ring[0]; y = ring[1]; } else { x += ring[i]; y += ring[i + 1]; }
      pts[j] = [x / q, y / q];
    }
    return pts;
  }

  const api = { combine: combine, fmt: fmt, decodeRing: decodeRing };
  root.AtlasScore = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
