// node --test: the wizard's arithmetic. No browser, no data files.
import assert from "node:assert/strict";
import { test } from "node:test";
import { climateChoices, presetFor, roundTo100, weightsFrom } from "../src/weights.js";

const BASE = { cost: 16, safety: 15, hazard: 12, climate: 12, food: 10, nature: 9, health: 9,
  airport: 5, community: 6, town: 6, jobs: 0, schools: 0 };
const PRESETS = [
  { id: "snowy", winter: [15, 30] }, { id: "cold", winter: [25, 36] }, { id: "mild", winter: [34, 46] },
  { id: "warm", winter: [44, 58] }, { id: "hot", winter: [55, 72] },
];
const sum = (w) => Object.values(w).reduce((a, b) => a + b, 0);

test("no answers leave the defaults untouched", () => {
  assert.deepEqual(weightsFrom(BASE, []), BASE);
  assert.deepEqual(weightsFrom(BASE, [{}, { scale: {} }]), BASE, "a neutral answer changes nothing");
});

test("a share fixes its factor and the rest rescale to keep 100", () => {
  const w = weightsFrom(BASE, [{ share: { schools: 14 } }, { share: { jobs: 14 } }, { share: { airport: 12 } }]);
  assert.equal(sum(w), 100);
  assert.equal(w.schools, 14);
  assert.equal(w.jobs, 14);
  assert.equal(w.airport, 12);
  assert.ok(w.cost > w.safety && w.safety > w.food, "untouched factors keep their order");
});

test("a scale moves its factor against the rest, and the later share wins", () => {
  const w = weightsFrom(BASE, [{ scale: { cost: 1.6 } }]);
  assert.equal(sum(w), 100);
  assert.ok(w.cost > BASE.cost && w.safety < BASE.safety);
  const twice = weightsFrom(BASE, [{ share: { schools: 14 } }, { share: { schools: 4 } }]);
  assert.equal(twice.schools, 4);
  assert.deepEqual(weightsFrom(BASE, [{ scale: { nonsense: 3 }, share: { nonsense: 50 } }]), BASE,
    "a factor the site does not have is ignored");
});

test("rounding always lands on exactly 100 and never invents weight", () => {
  for (let i = 0; i < 200; i++) {
    const w = Object.fromEntries(Object.keys(BASE).map((k) => [k, Math.random() * 20]));
    w.jobs = 0;
    const r = roundTo100(w); // input deliberately does not sum to 100
    assert.equal(sum(r), 100);
    assert.equal(r.jobs, 0, "a zero stays zero");
  }
});

test("climate steps move one preset at a time and stop at the ends", () => {
  assert.equal(presetFor(32, 0, PRESETS), "cold");   // Harrisburg
  assert.equal(presetFor(32, 1, PRESETS), "mild");
  assert.equal(presetFor(32, 2, PRESETS), "warm");
  assert.equal(presetFor(32, -2, PRESETS), "snowy"); // clamped
  assert.equal(presetFor(70, 2, PRESETS), "hot");    // clamped
});

test("climate choices never offer two steps that mean the same thing", () => {
  const harrisburg = climateChoices(32, PRESETS);
  assert.deepEqual(harrisburg.map((c) => c.preset), ["snowy", "cold", "mild", "warm"]);
  assert.equal(harrisburg[0].label, "A bit colder", "the gentler step is kept");
  const miami = climateChoices(68, PRESETS);
  assert.deepEqual(miami.map((c) => c.preset), ["mild", "warm", "hot"]);
});
