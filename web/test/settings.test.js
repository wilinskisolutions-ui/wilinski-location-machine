// node --test: settings saved by an older version of the site.
import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeSettings } from "../src/model.js";

const CORE = { web: { defaultWeights: { cost: 16, safety: 15 }, layers: [{ id: "religion" }, { id: "politics" }] } };

test("a layer the site no longer offers is dropped from saved settings", () => {
  const saved = {
    done: true, cap: 1800,
    weights: { cost: 20, safety: 10, foreign: 7, politics: 4 },
    layers: { foreign: { on: true, dir: "lower" }, politics: { on: true, dir: "even" } },
  };
  const s = normalizeSettings(CORE, saved);
  assert.deepEqual(s.weights, { cost: 20, safety: 10, religion: 0, politics: 4 });
  assert.deepEqual(s.layers, { religion: { on: false, dir: null }, politics: { on: true, dir: "even" } });
  assert.equal(s.cap, 1800);
  assert.equal(s.done, true);
});
