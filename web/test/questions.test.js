// node --test: the setup questions. No browser, no data files.
import assert from "node:assert/strict";
import { test } from "node:test";
import { answersFromLegacy, chosenOptions, PATHS, QUESTIONS, stepsFor } from "../src/questions.js";
import { weightsFrom } from "../src/weights.js";

// config/atlas.yaml web.default_weights: the factors a visitor can weight.
const BASE = { cost: 16, safety: 15, hazard: 12, climate: 12, food: 10, nature: 9, health: 9,
  airport: 5, community: 6, town: 6, jobs: 0, schools: 0 };
const SCREENS = new Set(["home", "money", "winters", "weights", "picks"]);
const asked = (steps) => steps.filter((id) => id !== "depth" && id !== "weights");

test("simple asks five questions; more asks about fifteen", () => {
  assert.equal(asked(stepsFor({ depth: "simple" })).length, 5);
  assert.equal(asked(stepsFor({ depth: "more", kids: "none" })).length, 16, "15 questions plus the list of places");
  assert.equal(stepsFor({})[0], "depth", "the length is chosen first");
});

test("a follow-up is asked only when it applies", () => {
  assert.ok(stepsFor({ depth: "more", kids: "none" }).includes("kidsFuture"));
  assert.ok(!stepsFor({ depth: "more", kids: "now" }).includes("kidsFuture"));
});

test("every step is a question or a known screen, and every answer moves a real factor", () => {
  for (const id of new Set([...PATHS.simple, ...PATHS.more])) {
    assert.ok(QUESTIONS[id] || SCREENS.has(id), `unknown step ${id}`);
  }
  for (const [id, q] of Object.entries(QUESTIONS)) {
    assert.ok(q.options.length >= 2, id);
    assert.equal(new Set(q.options.map((o) => o.value)).size, q.options.length, `${id}: duplicate value`);
    for (const o of q.options) {
      for (const k of [...Object.keys(o.scale || {}), ...Object.keys(o.share || {})]) {
        assert.ok(k in BASE, `${id}/${o.value} moves '${k}', which is not a factor`);
      }
      for (const m of Object.values(o.scale || {})) assert.ok(m > 0, `${id}/${o.value}: a scale must stay positive`);
    }
  }
});

test("nature and city pull in opposite directions", () => {
  const w = (value) => weightsFrom(BASE, chosenOptions({ depth: "simple", answers: { nature: value } }));
  assert.ok(w("wild").nature > BASE.nature && w("wild").food < BASE.food);
  assert.ok(w("city").food > BASE.food && w("city").nature < BASE.nature);
  assert.deepEqual(w("mix"), BASE);
});

test("answers to questions off the chosen path are not applied", () => {
  const s = { depth: "simple", answers: { safety: "top", nature: "mix" } };
  assert.deepEqual(weightsFrom(BASE, chosenOptions(s)), BASE);
  s.depth = "more";
  assert.ok(weightsFrom(BASE, chosenOptions(s)).safety > BASE.safety);
});

test("settings saved before the questions existed become answers", () => {
  assert.deepEqual(answersFromLegacy({ mode: "couple", kids: "planned", income: "local", flights: "often" }),
    { who: "couple", kidsFuture: "yes", work: "local", flights: "often" });
  assert.deepEqual(answersFromLegacy({ mode: "single", kids: "now" }), { who: "kids" });
});
