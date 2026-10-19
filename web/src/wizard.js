// The setup wizard. Its result is a settings object and a list of pinned areas, saved to
// this browser or, for an account, to Supabase. The visitor first picks a length: five
// questions, or about fifteen (questions.js); every answer sets where the weights start.
// A couple can answer separately: each person takes the preference questions in turn and
// the map uses the blend of the two.
import { answersFromLegacy, blend, chosenOptions, PATHS, QUESTIONS, separately, stepsFor } from "./questions.js";
import { climateChoices, presetFor, weightsFrom } from "./weights.js";
import { debounce, esc } from "./util.js";

// Titles of the screens that are not plain questions.
const SCREEN_TITLES = {
  depth: "How do you want to set this up?",
  home: "Where do you live now?",
  money: "What can you spend?",
  winters: "What should January feel like?",
  weights: "Here's what your answers add up to",
  handoff: "Over to your partner",
  blend: "How your answers blend",
  picks: "Any places already on your list?",
};
const MAX_PICKS = 5;
const ADVANCE_MS = 220; // a tapped answer shows as chosen for a moment, then moves on

// Close the wizard. On completion the caller closes it once the new map is drawn, so the
// visitor never sees an empty map between the last step and their result.
export function closeWizard() {
  const root = document.getElementById("wizard");
  root.hidden = true;
  root.innerHTML = "";
  root.onkeydown = null;
  document.body.classList.remove("wizard-open");
}

// only: "partner" runs just the second person's questions and the blend.
export function runWizard(model, { settings, pins, cancellable = false, only = null }) {
  const root = document.getElementById("wizard");
  const s = structuredClone(settings);
  if (!s.answers) s.answers = s.done ? answersFromLegacy(s) : {};
  // Two people's own answers, when a couple answers separately. people[1] === null means the
  // second person will answer later.
  const ensurePeople = () => {
    if (!Array.isArray(s.people)) s.people = [{ answers: {} }, { answers: {} }];
    if (!s.people[0]) s.people[0] = { answers: {} };
    if (s.people[1] === undefined || (only && !s.people[1])) s.people[1] = { answers: {} };
  };
  if (separately(s) || only) ensurePeople();
  const stepsNow = () => stepsFor(s, { only });
  const person = (st) => (st.p == null ? null : s.people[st.p]);
  const answersAt = (st) => (st.p == null ? s.answers : (person(st).answers ||= {}));
  const climateAt = (st) => (st.p == null ? s.climate : person(st).climate);
  let picks = structuredClone(pins || []);
  let step = 0;
  let weightsTouched = false; // set once the visitor moves a slider on the review screen
  let advance = null;
  const base = model.core.web.defaultWeights;

  return new Promise((resolve) => {
    root.hidden = false;
    document.body.classList.add("wizard-open");

    function finish(result) {
      if (!result) closeWizard(); // cancelled: nothing to wait for
      resolve(result);
    }

    // Weights follow the answers until the visitor adjusts them by hand on the review screen.
    // Answered separately, the map takes the blend of the two people.
    function refreshWeights() {
      if (separately(s)) {
        const b = blend(base, s, model.presets);
        if (b) {
          for (const k of Object.keys(b.weights)) s.weights[k] = b.weights[k];
          s.climate = b.climate;
        }
        return;
      }
      if (weightsTouched) return;
      const w = weightsFrom(base, chosenOptions(s));
      for (const k of Object.keys(w)) s.weights[k] = w[k];
    }

    function render() {
      clearTimeout(advance);
      const steps = stepsNow(), st = steps[step], id = st.id, q = QUESTIONS[id];
      const first = steps[0].id === "depth" ? 0 : 1; // the length choice is not counted
      const at = step + first, n = steps.length - 1 + first, last = step === steps.length - 1;
      const unanswered = q && !answersAt(st)[id];
      root.innerHTML = `
        <div class="wz-card" role="dialog" aria-modal="true" aria-labelledby="wz-title">
          <div class="wz-top">
            <span class="wz-brand">WILINSKI <i>ATLAS</i></span>
            <span class="wz-step num">${at ? `Step ${at} of ${n}` : ""}</span>
            ${cancellable ? `<button type="button" class="link" id="wz-cancel">Close</button>` : ""}
          </div>
          <div class="wz-bar"><i style="width:${(at / n) * 100}%"></i></div>
          ${st.p != null ? `<p class="wz-who p${st.p}">Person ${st.p + 1}</p>` : ""}
          <h2 id="wz-title">${esc(q ? q.title : SCREEN_TITLES[id])}</h2>
          <div class="wz-body" id="wz-body">${body(st)}</div>
          <div class="wz-nav">
            <button type="button" class="btn" id="wz-back" ${step === 0 ? "disabled" : ""}>Back</button>
            <button type="button" class="btn${unanswered ? "" : " primary"}" id="wz-next" ${id === "depth" && !s.depth ? "disabled" : ""}>${last ? "Show my map" : unanswered ? "Skip" : "Next"}</button>
          </div>
        </div>`;
      wire(st);
      root.querySelector("#wz-next").focus({ preventScroll: true });
    }

    // Choosing an answer moves on by itself; Next (or Back) cancels the pending move, so a
    // quick tap on Next never skips a screen.
    function chooseAndAdvance() {
      const at = step;
      render();
      advance = setTimeout(() => { if (step === at) next(); }, ADVANCE_MS);
    }

    // ------------------------------------------------------------- step bodies
    function choice(name, value, label, sub) {
      return `<button type="button" class="wz-opt" data-name="${name}" data-value="${esc(value)}" aria-pressed="${s[name] === value}">
        <b>${esc(label)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}</button>`;
    }

    function question(id, answers) {
      const q = QUESTIONS[id];
      const cls = q.layout === "rows" ? "" : q.layout;
      return `${q.sub ? `<p class="wz-lede">${esc(q.sub)}</p>` : ""}
        <div class="wz-opts ${cls}">${q.options.map((o) => `<button type="button" class="wz-opt" data-q="${id}" data-value="${esc(o.value)}" aria-pressed="${answers[id] === o.value}">
          <b>${esc(o.label)}</b>${o.sub ? `<span>${esc(o.sub)}</span>` : ""}</button>`).join("")}</div>`;
    }

    function body(st) {
      const id = st.id;
      if (QUESTIONS[id]) return question(id, answersAt(st));
      if (id === "depth") {
        const count = (d) => PATHS[d].filter((x) => x !== "weights" && x !== "answering").length;
        return `<p class="wz-lede">The Atlas scores every US county and every town over 5,000 people against what you tell it, then puts the areas you already like next to the ones the data says you should see.</p>
          <div class="wz-opts two">
            <button type="button" class="wz-opt depth" data-depth="simple" aria-pressed="${s.depth === "simple"}"><em>Simple</em><b>${count("simple")} questions</b><span>Short and easy: about a minute. Fine-tune later on the map.</span></button>
            <button type="button" class="wz-opt depth" data-depth="more" aria-pressed="${s.depth === "more"}"><em>More questions</em><b>About ${count("more") - 1}</b><span>More specific results: each answer sharpens your ranking. About four minutes.</span></button>
          </div>`;
      }
      if (id === "home") {
        const h = s.home ? model.places.get(s.home) : null;
        const wt = model.homeWinter(s.home);
        return `<p class="wz-lede">Optional. It anchors the questions that follow ("warmer than here?") and shows where you live now on the map, scored the same way. Anything worth moving to should beat it.</p>
          <div class="field"><label for="wz-home">Your town</label>
          <input id="wz-home" type="search" autocomplete="off" placeholder="Start typing a town" value="">
          <ul class="wz-results" id="wz-home-results" hidden></ul></div>
          ${h ? `<p class="wz-chip">Home: <b>${esc(h.name)}, ${esc(h.st)}</b>${wt != null ? ` · winters average ${Math.round(wt)}°F` : ""} <button type="button" class="link" id="wz-home-clear">Clear</button></p>`
            : `<p class="muted small">Skip this if you'd rather not say.</p>`}`;
      }
      if (id === "money") {
        return `<div class="wz-opts two">${choice("tenure", "rent", "Rent first", "Rent for a while, buy once you know the place.")}
          ${choice("tenure", "buy", "Buy", "Buy when you arrive.")}</div>
          <div class="field"><label for="wz-cap">${s.tenure === "buy" ? "Most you'd pay for a home" : "Most you'd pay in rent, per month"}</label>
          <div class="money-input"><span>$</span><input id="wz-cap" type="number" inputmode="numeric" min="300" step="${s.tenure === "buy" ? 10000 : 50}" value="${s.cap}"><span>${s.tenure === "buy" ? "" : "/mo"}</span></div></div>
          <p class="muted small">Places over this stay on the map, marked red. Nothing is hidden for being over budget.</p>`;
      }
      if (id === "winters") {
        const wt = model.homeWinter(s.home);
        if (wt != null) {
          return `<p class="wz-lede">Winters where you live now average <b class="num">${Math.round(wt)}°F</b> (December to February). Compared with that, you want:</p>
            <div class="wz-opts">${climateChoices(wt, model.presets).map((c) => {
              const p = model.presets.find((x) => x.id === c.preset);
              return `<button type="button" class="wz-opt row" data-preset="${p.id}" aria-pressed="${climateAt(st) === p.id}"><b>${esc(c.label)}</b><span>${esc(p.label)} · ${p.winter[0]}-${p.winter[1]}°F</span></button>`;
            }).join("")}</div>`;
        }
        return `<p class="wz-lede">Average winter temperature (December to February) you'd be happiest with:</p>
          <div class="wz-opts">${model.presets.map((p) => `<button type="button" class="wz-opt row" data-preset="${p.id}" aria-pressed="${climateAt(st) === p.id}"><b>${esc(p.label)}</b><span>${p.winter[0]}-${p.winter[1]}°F</span></button>`).join("")}</div>`;
      }
      if (id === "handoff") {
        const count = stepsFor({ ...s, people: [{}, {}] }).filter((x) => x.p === 1).length;
        return `<p class="wz-lede">Person 1 is done. Your partner answers the same ${count} questions, without seeing Person 1's answers.</p>
          <div class="wz-opts">
            <button type="button" class="wz-opt" data-handoff="now" aria-pressed="${s.people[1] !== null}"><b>Hand it over now</b><span>Your partner answers on this device.</span></button>
            <button type="button" class="wz-opt" data-handoff="later" aria-pressed="${s.people[1] === null}"><b>They'll answer later</b><span>On this device or their own phone: Menu, then Add Person 2's answers. Until then the map follows Person 1.</span></button>
          </div>`;
      }
      if (id === "blend") return blendSummary();
      if (id === "weights") {
        refreshWeights();
        const total = model.factors.reduce((a, f) => a + (s.weights[f.id] || 0), 0)
          + model.layers.reduce((a, l) => a + (s.layers[l.id]?.on ? s.weights[l.id] || 0 : 0), 0);
        return `<p class="wz-lede">Your answers set these. Move any of them if something looks off: what counts is each factor's share of the total, so giving more to one gives less to the rest.</p>
          <div class="total"><span>total points</span><b class="num" id="wz-total">${total}</b></div>
          <div class="weights">${model.factors.map((f) => slider(f.id, f.label, f.blurb, s.weights[f.id] || 0, false)).join("")}</div>
          <details class="sens" ${model.layers.some((l) => s.layers[l.id]?.on) ? "open" : ""}>
            <summary>Optional: sensitive layers</summary>
            <p class="small muted">Off unless you switch one on. You choose the direction; the Atlas never assumes one, and a layer only shifts scores. It never hides a place. These describe who lives somewhere, which some people weigh and many deliberately don't.</p>
            ${model.layers.map((l) => layer(l)).join("")}
          </details>`;
      }
      if (id === "picks") {
        return `<p class="wz-lede">Add up to ${MAX_PICKS} areas you're already curious about. Each becomes a ring on the map, with every town inside it scored. You'll also see the machine's own picks beside them.</p>
          <div class="field"><label for="wz-pick">Add an area</label>
          <input id="wz-pick" type="search" autocomplete="off" placeholder="A town or county" ${picks.length >= MAX_PICKS ? "disabled" : ""}>
          <ul class="wz-results" id="wz-pick-results" hidden></ul></div>
          <ul class="wz-picks">${picks.map((p) => `<li><b>${esc(p.label)}</b>
            <label class="small muted">radius <select data-radius="${esc(p.id)}">${[10, 15, 20, 25, 30, 40, 50].map((r) => `<option ${r === p.radius_mi ? "selected" : ""}>${r}</option>`).join("")}</select> mi</label>
            <button type="button" class="link" data-remove="${esc(p.id)}">Remove</button></li>`).join("")}</ul>
          ${picks.length ? "" : `<p class="muted small">No areas yet. You can skip this and add them from the map later.</p>`}`;
      }
      return "";
    }

    // Each person's starting weights next to the map's, and where the two differ most.
    function blendSummary() {
      const b = blend(base, s, model.presets);
      if (!b) return `<p class="wz-lede">Nobody has answered the questions yet, so the map starts from the defaults. Go back to answer them.</p>`;
      const [a, c] = b.each;
      const rows = model.factors.map((f) => ({ f, a: a?.[f.id], c: c?.[f.id], m: b.weights[f.id] }))
        .filter((r) => r.m || r.a || r.c).sort((x, y) => y.m - x.m);
      const gaps = a && c ? rows.filter((r) => Math.abs(r.a - r.c) >= 4)
        .sort((x, y) => Math.abs(y.a - y.c) - Math.abs(x.a - x.c)).slice(0, 2) : [];
      const winter = (id) => model.presets.find((p) => p.id === id)?.label || "—";
      const cell = (v) => (v == null ? "—" : v);
      return `<p class="wz-lede">${a && c ? "The map starts from the average of your two sets of answers. Points are out of 100."
          : `${a ? "Person 2" : "Person 1"} hasn't answered yet, so the map follows ${a ? "Person 1" : "Person 2"} for now. Add the missing answers any time from the menu.`}</p>
        <div class="blend" role="table" aria-label="Each person's weights and the map's">
          <div class="bl-row bl-head" role="row"><span>Factor</span><b class="p0" title="Person 1">P1</b><b class="p1" title="Person 2">P2</b><b class="map">Map</b></div>
          ${rows.map((r) => `<div class="bl-row${gaps.includes(r) ? " gap" : ""}" role="row"><span>${esc(r.f.label)}</span><b class="num">${cell(r.a)}</b><b class="num">${cell(r.c)}</b><b class="num map">${r.m}</b></div>`).join("")}
        </div>
        <p class="small bl-winter">${a && c && s.people[0]?.climate && s.people[1]?.climate
          ? `Winters: Person 1 wants <b>${esc(winter(s.people[0].climate))}</b>, Person 2 <b>${esc(winter(s.people[1].climate))}</b>. The map uses <b class="map">${esc(winter(b.climate))}</b>.`
          : `Winters: the map uses <b class="map">${esc(winter(b.climate))}</b>.`}</p>
        ${gaps.length ? `<p class="small">You differ most on ${gaps.map((r) => `<b>${esc(r.f.label)}</b> (${r.a} vs ${r.c})`).join(" and ")}. Worth talking over before you visit anywhere.</p>`
          : a && c ? `<p class="small">You two are remarkably in sync.</p>` : ""}`;
    }

    function slider(id, label, blurb, value, disabled) {
      return `<div class="w-row${value ? "" : " zero"}">
        <label for="wz-w-${id}">${esc(label)}</label><output for="wz-w-${id}" class="num" id="wz-o-${id}">${value}</output>
        <input type="range" id="wz-w-${id}" min="0" max="30" step="1" value="${value}" data-w="${id}" ${disabled ? "disabled" : ""}>
        <p>${esc(blurb)}</p></div>`;
    }
    function layer(l) {
      const set = s.layers[l.id] || { on: false, dir: null };
      return `<div class="layer" data-layer="${l.id}">
        <label class="check"><input type="checkbox" data-on="${l.id}" ${set.on ? "checked" : ""}> <b>${esc(l.label)}</b></label>
        <p class="small muted">${esc(l.blurb)}</p>
        <div class="seg" role="group" aria-label="${esc(l.label)} direction">${Object.entries(l.directions).map(([k, v]) =>
          `<button type="button" data-dir="${l.id}:${k}" aria-pressed="${set.dir === k}" ${set.on ? "" : "disabled"}>${esc(v)}</button>`).join("")}</div>
        ${slider(l.id, "Weight", "", set.on ? s.weights[l.id] || 0 : 0, !set.on || !set.dir)}
      </div>`;
    }

    // ------------------------------------------------------------- behaviour
    function searchBox(inputId, listId, opts, onPick) {
      const input = root.querySelector(inputId), list = root.querySelector(listId);
      if (!input) return;
      input.addEventListener("input", debounce(() => {
        const hits = model.search(input.value, opts);
        list.innerHTML = hits.map((h) => `<li><button type="button" data-id="${esc(h.id)}" data-kind="${h.kind}" data-label="${esc(h.label)}"><span>${esc(h.label)}</span><small>${h.kind} · ${h.pop.toLocaleString("en-US")}</small></button></li>`).join("")
          || `<li class="muted small" style="padding:8px 10px">No town over 5,000 people${opts.counties ? " or county" : ""} by that name.</li>`;
        list.hidden = input.value.trim().length < 2;
        list.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => onPick(b.dataset)));
      }, 120));
    }

    function wire(st) {
      const id = st.id;
      root.querySelector("#wz-back").addEventListener("click", () => { step = Math.max(0, step - 1); render(); });
      root.querySelector("#wz-next").addEventListener("click", next);
      const cancel = root.querySelector("#wz-cancel");
      if (cancel) cancel.addEventListener("click", () => finish(null));
      root.querySelectorAll(".wz-opt[data-name]").forEach((b) => b.addEventListener("click", () => {
        const name = b.dataset.name, value = b.dataset.value;
        if (name === "tenure" && s.tenure !== value) s.cap = value === "buy" ? 400000 : 2000;
        s[name] = value;
        render();
      }));
      root.querySelectorAll(".wz-opt[data-preset]").forEach((b) => b.addEventListener("click", () => {
        if (st.p == null) s.climate = b.dataset.preset; else person(st).climate = b.dataset.preset;
        chooseAndAdvance();
      }));
      root.querySelectorAll(".wz-opt[data-handoff]").forEach((b) => b.addEventListener("click", () => {
        if (b.dataset.handoff === "later") s.people[1] = null;
        else if (!s.people[1]) s.people[1] = { answers: {} };
        chooseAndAdvance();
      }));
      root.querySelectorAll(".wz-opt[data-depth]").forEach((b) => b.addEventListener("click", () => { s.depth = b.dataset.depth; chooseAndAdvance(); }));
      root.querySelectorAll(".wz-opt[data-q]").forEach((b) => b.addEventListener("click", () => {
        const q = QUESTIONS[b.dataset.q], opt = q.options.find((o) => o.value === b.dataset.value);
        answersAt(st)[b.dataset.q] = opt.value;
        Object.assign(s, opt.set || {});
        if (separately(s)) ensurePeople();
        chooseAndAdvance();
      }));

      if (id === "home") {
        searchBox("#wz-home", "#wz-home-results", { counties: false }, (d) => {
          s.home = d.id;
          // A home outside the winter presets' reach keeps the visitor's last choice.
          const wt = model.homeWinter(s.home);
          if (wt != null) s.climate = presetFor(wt, 0, model.presets);
          render();
        });
        const clear = root.querySelector("#wz-home-clear");
        if (clear) clear.addEventListener("click", () => { s.home = null; render(); });
      }
      if (id === "money") {
        root.querySelector("#wz-cap").addEventListener("change", (e) => {
          const v = Math.round(+e.target.value);
          if (v > 0) s.cap = v;
        });
      }
      if (id === "weights") {
        const total = () => {
          const t = model.factors.reduce((a, f) => a + (s.weights[f.id] || 0), 0)
            + model.layers.reduce((a, l) => a + (s.layers[l.id]?.on && s.layers[l.id]?.dir ? s.weights[l.id] || 0 : 0), 0);
          root.querySelector("#wz-total").textContent = t;
        };
        root.querySelectorAll("input[data-w]").forEach((inp) => inp.addEventListener("input", () => {
          weightsTouched = true;
          s.weights[inp.dataset.w] = +inp.value;
          root.querySelector(`#wz-o-${inp.dataset.w}`).textContent = inp.value;
          inp.closest(".w-row").classList.toggle("zero", !+inp.value);
          total();
        }));
        root.querySelectorAll("input[data-on]").forEach((c) => c.addEventListener("change", () => {
          const l = c.dataset.on;
          s.layers[l] = { on: c.checked, dir: c.checked ? s.layers[l]?.dir || null : null };
          if (!c.checked) s.weights[l] = 0;
          render();
        }));
        root.querySelectorAll("[data-dir]").forEach((b) => b.addEventListener("click", () => {
          const [l, dir] = b.dataset.dir.split(":");
          s.layers[l] = { on: true, dir };
          if (!s.weights[l]) s.weights[l] = 5;
          render();
          root.querySelector("details.sens").open = true;
        }));
      }
      if (id === "picks") {
        searchBox("#wz-pick", "#wz-pick-results", { counties: true }, (d) => {
          const anchor = d.kind === "county" ? bestTownIn(d.id) || d.id : d.id;
          const pid = "p-" + anchor;
          if (!picks.some((p) => p.id === pid) && picks.length < MAX_PICKS) {
            picks.push({ id: pid, label: d.label, anchor, radius_mi: 25, order: picks.length });
          }
          render();
          root.querySelector("#wz-pick")?.focus();
        });
        root.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", () => {
          picks = picks.filter((p) => p.id !== b.dataset.remove);
          render();
        }));
        root.querySelectorAll("[data-radius]").forEach((sel) => sel.addEventListener("change", () => {
          const p = picks.find((x) => x.id === sel.dataset.radius);
          if (p) p.radius_mi = +sel.value;
        }));
      }
    }

    // A county pin centres on its most populous town, so the ring sits where people live.
    function bestTownIn(countyId) {
      const c = model.counties.get(countyId);
      if (!c || !c.places.length) return null;
      return [...c.places].sort((a, b) => (b.pop || 0) - (a.pop || 0))[0].id;
    }

    function next() {
      clearTimeout(advance);
      const steps = stepsNow();
      if (steps[step].id === "money") {
        const v = Math.round(+root.querySelector("#wz-cap").value);
        if (v > 0) s.cap = v;
      }
      if (step < steps.length - 1) { step += 1; render(); return; }
      refreshWeights();
      s.done = true;
      const btn = root.querySelector("#wz-next");
      btn.disabled = true;
      btn.textContent = "Scoring 9,885 places…";
      finish({ settings: s, pins: picks });
    }

    root.onkeydown = (e) => { if (e.key === "Escape" && cancellable) finish(null); };
    render();
  });
}
