// The data model and scoring for one visitor's settings.
//
// Everything here recombines numbers the Python build computed: factor scores from
// engine.domain_scores, climate scores per winter preset, and sensitive-layer percentiles.
// The only arithmetic is AtlasScore.combine (held to engine.combine_domains by
// tests/test_atlas.py) and, for a layer's direction, the engine's own monotone and
// ideal_point curves.
import "../../src/wlm/atlas/page/score.js";
import { cleanName, miles, MI_PER_DEG } from "./util.js";

export const A = globalThis.AtlasScore;

export const STATUSES = [
  ["want", "Want to visit"], ["visited", "Visited"], ["favorite", "Favorite"], ["ruled-out", "Ruled out"],
];
export const STATUS_LABEL = Object.fromEntries(STATUSES);

export function defaultSettings(core) {
  return {
    version: 1,
    mode: "single",
    home: null,
    tenure: "rent",
    cap: 2000,
    kids: "none",
    income: "portable",
    flights: "sometimes",
    climate: "mild",
    weights: { ...core.web.defaultWeights, ...Object.fromEntries(core.web.layers.map((l) => [l.id, 0])) },
    layers: Object.fromEntries(core.web.layers.map((l) => [l.id, { on: false, dir: null }])),
    budgetOnly: true,
    done: false,
  };
}

// Settings saved by an older version gain any field added since, without losing theirs.
export function normalizeSettings(core, saved) {
  const d = defaultSettings(core);
  if (!saved) return d;
  return {
    ...d, ...saved,
    weights: { ...d.weights, ...(saved.weights || {}) },
    layers: { ...d.layers, ...(saved.layers || {}) },
  };
}

export class Model {
  constructor(core) {
    this.core = core;
    this.counties = new Map();
    this.places = new Map();
    this.rawIdx = { county: new Map(), place: new Map() };
    this.ind = new Map(core.inds.map((d) => [d.id, d]));
    core.counties.raw.forEach((id, i) => this.rawIdx.county.set(id, i));
    core.places.raw.forEach((id, i) => this.rawIdx.place.set(id, i));

    // The household-only factor (their church opt-in) is not offered here; religion is a
    // visitor-directed sensitive layer instead.
    this.factors = core.factors
      .map((f, fi) => ({ ...f, fi }))
      .filter((f) => !f.householdOnly);
    this.layers = core.web.layers;
    this.presets = core.web.climatePresets;
    this.climateFi = core.factors.findIndex((f) => f.id === "climate");
    // Slots the visitor weights: the factors, then the layers.
    this.slots = [...this.factors.map((f) => ({ ...f, kind: "factor" })),
      ...this.layers.map((l) => ({ ...l, kind: "layer" }))];

    for (const r of core.counties.rows) {
      const [id, name, st, lat, lon, pop, f, raw, cp, sens] = r;
      this.counties.set(id, { id, name, st, lat, lon, pop, f, raw, cp, sens, places: [], level: "county" });
    }
    for (const r of core.places.rows) {
      const [id, name, st, county, lat, lon, pop, f, raw, rent, rentShare, home, homeShare, sens] = r;
      const p = { id, name: cleanName(name), full: name, st, county, lat, lon, pop, f, raw,
        rent, rentShare, home, homeShare, sens, level: "place" };
      this.places.set(id, p);
      const c = this.counties.get(county);
      if (c) c.places.push(p);
    }
    this.settings = defaultSettings(core);
    this.challengers = [];
    this.rankN = 0;
    this.countyRankN = 0;
  }

  rawVal(obj, level, id) {
    const i = this.rawIdx[level].get(id);
    return i === undefined ? null : obj.raw[i];
  }
  countyOf(o) { return o.level === "county" ? o : this.counties.get(o.county); }

  // ---------------------------------------------------------------- money
  rentOf(p) {
    if (p.rent != null) return { v: p.rent, src: "town", share: p.rentShare };
    const c = this.countyOf(p);
    const v = c ? this.rawVal(c, "county", "cost_rent_median_zori") : null;
    return { v, src: v == null ? null : "county" };
  }
  homeOf(p) {
    if (p.home != null) return { v: p.home, src: "town", share: p.homeShare };
    const c = this.countyOf(p);
    const v = c ? this.rawVal(c, "county", "cost_home_value_median") : null;
    return { v, src: v == null ? null : "county" };
  }
  priceOf(p) { return this.settings.tenure === "buy" ? this.homeOf(p) : this.rentOf(p); }
  budgetOf(p) {
    const r = this.priceOf(p);
    if (r.v == null) return "unk";
    return r.v <= this.settings.cap ? "ok" : "over";
  }

  // ---------------------------------------------------------------- scoring
  presetIndex() {
    const i = this.presets.findIndex((p) => p.id === this.settings.climate);
    return i < 0 ? null : i;
  }
  weightVector() {
    const s = this.settings;
    return this.slots.map((slot) => {
      if (slot.kind === "layer") return s.layers[slot.id]?.on && s.layers[slot.id]?.dir ? (s.weights[slot.id] || 0) : 0;
      return s.weights[slot.id] || 0;
    });
  }
  layerValue(o, layer, k) {
    const set = this.settings.layers[layer.id];
    if (!set?.on || !set.dir) return null;
    const src = layer.level === "place" ? (o.level === "place" ? o.sens : null) : this.countyOf(o)?.sens;
    if (!src) return null;
    const pct = src[2 * k], raw = src[2 * k + 1];
    if (set.dir === "higher") return pct;
    if (set.dir === "lower") return pct == null ? null : 1 - pct;
    if (set.dir === "even" && layer.even) return A.idealPoint(raw, layer.even.target, layer.even.tol);
    return null;
  }
  vector(o) {
    const pi = this.presetIndex();
    const c = this.countyOf(o);
    const out = this.factors.map((f) => {
      if (f.fi === this.climateFi && pi != null && c?.cp) return c.cp[pi];
      return o.f[f.fi];
    });
    this.layers.forEach((l, k) => out.push(this.layerValue(o, l, k)));
    return out;
  }

  // engine.influence_scale, aligned with the slots: so that a factor's weight decides its
  // pull on the ranking, exactly as in the report. The winter preset in use replaces the
  // climate factor's stretch, and a layer carries the stretch of the direction chosen.
  shapeVector() {
    const web = this.core.web, pi = this.presetIndex();
    const out = this.factors.map((f) => {
      if (f.fi === this.climateFi && pi != null && this.presets[pi].shape) return this.presets[pi].shape;
      return (web.shape && web.shape[f.fi]) || null;
    });
    this.layers.forEach((l) => {
      const set = this.settings.layers[l.id];
      out.push(set?.on && set.dir && l.shape ? l.shape[set.dir] || null : null);
    });
    return out;
  }

  compute() {
    const { eps, minCov } = this.core;
    const w = this.weightVector();
    const shape = this.shapeVector();
    const home = this.settings.home ? this.places.get(this.settings.home) : null;
    const ok = (o) => o.s && o.s.ok;
    for (const c of this.counties.values()) { c.v = this.vector(c); c.s = A.combine(c.v, w, eps, minCov, shape); }
    for (const p of this.places.values()) { p.v = this.vector(p); p.s = A.combine(p.v, w, eps, minCov, shape); }

    const towns = [...this.places.values()].filter((p) => ok(p) && p !== home).sort((a, b) => b.s.score - a.s.score);
    for (const p of this.places.values()) p.rank = null;
    towns.forEach((p, i) => { p.rank = i + 1; });
    this.rankN = towns.length;
    if (home && ok(home)) home.rank = 1 + towns.filter((t) => t.s.score > home.s.score).length;
    for (const p of this.places.values()) p.pct = p.rank ? 1 - (p.rank - 1) / Math.max(1, this.rankN - 1) : null;

    const cs = [...this.counties.values()].filter(ok).sort((a, b) => b.s.score - a.s.score);
    for (const c of this.counties.values()) c.pct = null;
    cs.forEach((c, i) => { c.pct = 1 - i / Math.max(1, cs.length - 1); });
    this.countyRankN = cs.length;

    // Challengers: engine.two_stage in miniature. The best counties that contain a town,
    // each shown through its best town (under the visitor's cap when that switch is on).
    this.challengers = [];
    const homeCounty = home ? home.county : null;
    for (const c of cs) {
      if (c.id === homeCounty || !c.places.length) continue;
      const inside = c.places.filter(ok).sort((a, b) => b.s.score - a.s.score);
      const pick = this.settings.budgetOnly ? inside.find((p) => this.budgetOf(p) !== "over") : inside[0];
      if (!pick) continue;
      this.challengers.push({ county: c, town: pick });
      if (this.challengers.length >= this.core.challengers) break;
    }
  }

  // ---------------------------------------------------------------- areas
  anchorOf(pin) { return this.places.get(pin.anchor) || this.counties.get(pin.anchor) || null; }
  townsNear(lat, lon, r) {
    const out = [];
    for (const p of this.places.values()) {
      if (Math.abs(p.lat - lat) > r / MI_PER_DEG + 0.1) continue;
      const d = miles(lat, lon, p.lat, p.lon);
      if (d <= r) { p._d = d; out.push(p); }
    }
    return out.sort((a, b) => (b.s ? b.s.score : -1) - (a.s ? a.s.score : -1));
  }
  pinSummary(pin) {
    const a = this.anchorOf(pin);
    if (!a) return null;
    const ts = this.townsNear(a.lat, a.lon, pin.radius_mi).filter((p) => p.s && p.s.ok);
    return {
      anchor: a, towns: ts, best: ts[0] || null,
      bestOk: ts.find((p) => this.budgetOf(p) === "ok") || null,
      under: ts.filter((p) => this.budgetOf(p) === "ok").length,
    };
  }

  // ---------------------------------------------------------------- search
  search(q, { towns = true, counties = true, limit = 8 } = {}) {
    q = q.trim().toLowerCase();
    if (q.length < 2) return [];
    if (!this._index) {
      this._index = [...this.places.values()].map((p) => ({ id: p.id, kind: "town", label: `${p.name}, ${p.st}`, key: `${p.name} ${p.st}`.toLowerCase(), pop: p.pop || 0 }))
        .concat([...this.counties.values()].map((c) => ({ id: c.id, kind: "county", label: `${c.name}, ${c.st}`, key: `${c.name} ${c.st}`.toLowerCase(), pop: c.pop || 0 })));
    }
    return this._index
      .filter((x) => (towns || x.kind !== "town") && (counties || x.kind !== "county") && x.key.includes(q))
      .sort((a, b) => (b.key.startsWith(q) - a.key.startsWith(q)) || b.pop - a.pop)
      .slice(0, limit);
  }

  homeWinter(placeId = this.settings.home) {
    const h = placeId ? this.places.get(placeId) : null;
    const c = h ? this.countyOf(h) : null;
    return c ? this.rawVal(c, "county", "climate_temp_winter_mean") : null;
  }
}
