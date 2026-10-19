// Turning wizard answers into a starting point. Pure functions, tested in web/test.
//
// These only set where the sliders START. Every visitor then moves the 100-point budget
// themselves (the forced trade-off of GOAL.md Principle 7); nothing here is a preference
// we assume on their behalf beyond what they answered.

// The chosen options' effects (see questions.js), applied to the default weights. A
// `scale` multiplies a factor's default; a `share` fixes a factor's points out of 100,
// the later answer winning. Factors without a fixed share keep their (scaled) relative
// sizes and fill the rest, so the total stays 100.
export function weightsFrom(base, options) {
  const scaled = { ...base };
  const fixed = {};
  for (const o of options) {
    for (const [k, m] of Object.entries(o.scale || {})) if (k in scaled) scaled[k] *= m;
    for (const [k, v] of Object.entries(o.share || {})) if (k in base) fixed[k] = v;
  }
  const fixedTotal = Object.values(fixed).reduce((a, b) => a + b, 0);
  const rest = Object.keys(base).filter((k) => !(k in fixed));
  const restTotal = rest.reduce((a, k) => a + scaled[k], 0);
  const out = { ...fixed };
  for (const k of rest) out[k] = restTotal ? (scaled[k] * (100 - fixedTotal)) / restTotal : 0;
  return roundTo100(out);
}

// Integers that sum to exactly 100: scale to 100 first, then largest-remainder rounding.
// Zero stays zero; nothing gains weight it did not have.
export function roundTo100(input) {
  const keys = Object.keys(input);
  const total = keys.reduce((a, k) => a + input[k], 0);
  const w = Object.fromEntries(keys.map((k) => [k, total > 0 ? (input[k] * 100) / total : 0]));
  const floors = Object.fromEntries(keys.map((k) => [k, Math.floor(w[k])]));
  let short = 100 - keys.reduce((a, k) => a + floors[k], 0);
  const byRemainder = [...keys].sort((a, b) => (w[b] - floors[b]) - (w[a] - floors[a]));
  for (const k of byRemainder) {
    if (short <= 0) break;
    if (w[k] > 0) { floors[k] += 1; short -= 1; }
  }
  return floors;
}

// "Colder, the same or warmer than where you live now". "About the same" is the preset
// whose winter band is centred nearest the home town's winter; each step moves one preset
// colder or warmer, stopping at the ends. Without a home town the visitor picks a preset
// directly and this is not used.
export const CLIMATE_STEPS = [
  { id: -2, label: "Much colder" }, { id: -1, label: "A bit colder" }, { id: 0, label: "About the same" },
  { id: 1, label: "A bit warmer" }, { id: 2, label: "Much warmer" },
];

export function presetFor(homeWinterF, step, presets) {
  let base = 0, dist = Infinity;
  presets.forEach((p, i) => {
    const d = Math.abs((p.winter[0] + p.winter[1]) / 2 - homeWinterF);
    if (d < dist) { dist = d; base = i; }
  });
  const i = Math.max(0, Math.min(presets.length - 1, base + step));
  return presets[i].id;
}

// The steps worth offering from a given home: where two steps land on the same preset
// (a home already in the coldest band has no "much colder"), keep the gentler one.
export function climateChoices(homeWinterF, presets) {
  const seen = new Map();
  for (const step of [...CLIMATE_STEPS].sort((a, b) => Math.abs(a.id) - Math.abs(b.id))) {
    const pid = presetFor(homeWinterF, step.id, presets);
    if (!seen.has(pid)) seen.set(pid, step);
  }
  return [...seen.entries()].map(([pid, step]) => ({ ...step, preset: pid })).sort((a, b) => a.id - b.id);
}
