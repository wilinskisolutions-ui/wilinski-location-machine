// node --test: the setup questions. No browser, no data files.
import assert from "node:assert/strict";
import { test } from "node:test";
import { answersFromLegacy, blend, chosenOptions, PATHS, QUESTIONS, stepsFor } from "../src/questions.js";
import { weightsFrom } from "../src/weights.js";

// config/atlas.yaml web.default_weights: the factors a visitor can weight.
const BASE = { cost: 16, safety: 15, hazard: 12, climate: 12, food: 10, nature: 9, health: 9,
  airport: 5, community: 6, town: 6, jobs: 0, schools: 0 };
const SCREENS = new Set(["home", "money", "winters", "weights", "picks"]);
const ids = (steps) => steps.map((x) => x.id);
const asked = (steps) => ids(steps).filter((id) => id !== "depth" && id !== "weights");

test("simple asks five questions; more asks about fifteen", () => {
  assert.equal(asked(stepsFor({ depth: "simple" })).length, 5);
  assert.equal(asked(stepsFor({ depth: "more", kids: "none" })).length, 16, "15 questions plus the list of places");
  assert.equal(stepsFor({})[0].id, "depth", "the length is chosen first");
});

test("a follow-up is asked only when it applies", () => {
  assert.ok(ids(stepsFor({ depth: "more", kids: "none" })).includes("kidsFuture"));
  assert.ok(!ids(stepsFor({ depth: "more", kids: "now" })).includes("kidsFuture"));
  assert.ok(!ids(stepsFor({ depth: "simple", mode: "single" })).includes("answering"));
  assert.ok(ids(stepsFor({ depth: "simple", mode: "couple" })).includes("answering"), "couples choose how to answer");
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

// A couple answering separately.
const PRESETS = [{ id: "snowy" }, { id: "cold" }, { id: "mild" }, { id: "warm" }, { id: "hot" }];
const couple = (people) => ({ depth: "simple", mode: "couple", blend: "separately", answers: { who: "couple", answering: "separately" }, people });

test("answering separately: the household's questions once, then each person's, then the blend", () => {
  const steps = stepsFor(couple([{ answers: {} }, { answers: {} }]));
  assert.deepEqual(steps.map((x) => (x.p == null ? x.id : `${x.id}:${x.p}`)),
    ["depth", "who", "answering", "money", "nature:0", "winters:0", "handoff", "nature:1", "winters:1", "blend", "picks"]);
  const later = stepsFor(couple([{ answers: {} }, null]));
  assert.deepEqual(ids(later).slice(-3), ["handoff", "blend", "picks"], "no second person's questions until later");
  assert.deepEqual(stepsFor(couple([{}, {}]), { only: "partner" }).map((x) => `${x.id}:${x.p ?? "-"}`),
    ["nature:1", "winters:1", "blend:-"]);
});

test("the blend is the average of the two, and winters land halfway", () => {
  const s = couple([{ answers: { nature: "wild" }, climate: "snowy" }, { answers: { nature: "city" }, climate: "hot" }]);
  const b = blend(BASE, s, PRESETS);
  const [a, c] = b.each;
  assert.ok(a.nature > BASE.nature && c.nature < BASE.nature, "each person's own answers");
  for (const k of Object.keys(BASE)) assert.ok(Math.abs(b.weights[k] - (a[k] + c[k]) / 2) <= 1, k);
  assert.equal(Object.values(b.weights).reduce((x, y) => x + y, 0), 100);
  assert.equal(b.climate, "mild");
  assert.equal(blend(BASE, couple([{ climate: "cold" }, { climate: "mild" }]), PRESETS).climate, "mild", "a tie rounds warmer");
});

test("until the second person answers, the map follows the first", () => {
  const s = couple([{ answers: { nature: "wild" } }, null]);
  const b = blend(BASE, s, PRESETS);
  assert.deepEqual(b.weights, b.each[0]);
  assert.equal(b.each[1], null);
  assert.equal(blend(BASE, couple([{ answers: {} }, { answers: {} }]), PRESETS), null, "nobody has answered");
});

test("an answer left from answering together never stands in for a person's skipped question", () => {
  const s = couple([{ answers: { nature: "wild" } }, { answers: { nature: "wild" } }]);
  s.answers.safety = "top"; // from an earlier run answered together
  s.depth = "more";
  assert.equal(blend(BASE, s, PRESETS).weights.safety < BASE.safety, true, "safety was not raised");
});
