// The setup wizard. Runs before any account exists; its result is a settings object and
// a list of pinned areas, saved to this browser until the visitor chooses to sign up.
import { climateChoices, presetFor, startingWeights } from "./weights.js";
import { debounce, esc } from "./util.js";

const STEPS = ["who", "home", "money", "life", "winters", "weights", "picks"];
const STEP_TITLES = {
  who: "Who's moving?",
  home: "Where do you live now?",
  money: "What can you spend?",
  life: "A few facts about your life",
  winters: "What winters do you want?",
  weights: "What matters most?",
  picks: "Which areas are on your list?",
};
const MAX_PICKS = 5;

// Close the wizard. On completion the caller closes it once the new map is drawn, so the
// visitor never sees an empty map between the last step and their result.
export function closeWizard() {
  const root = document.getElementById("wizard");
  root.hidden = true;
  root.innerHTML = "";
  root.onkeydown = null;
  document.body.classList.remove("wizard-open");
}

export function runWizard(model, { settings, pins, cancellable = false }) {
  const root = document.getElementById("wizard");
  const s = structuredClone(settings);
  let picks = structuredClone(pins || []);
  let step = 0;
  let weightsTouched = s.done; // a returning visitor keeps their own weights
  const base = model.core.web.defaultWeights;

  return new Promise((resolve) => {
    root.hidden = false;
    document.body.classList.add("wizard-open");

    function finish(result) {
      if (!result) closeWizard(); // cancelled: nothing to wait for
      resolve(result);
    }

    function refreshWeights() {
      if (weightsTouched) return;
      const w = startingWeights(base, s);
      for (const k of Object.keys(w)) s.weights[k] = w[k];
    }

    function render() {
      const id = STEPS[step];
      root.innerHTML = `
        <div class="wz-card" role="dialog" aria-modal="true" aria-labelledby="wz-title">
          <div class="wz-top">
            <span class="wz-brand">WILINSKI <i>ATLAS</i></span>
            <span class="wz-step num">Step ${step + 1} of ${STEPS.length}</span>
            ${cancellable ? `<button type="button" class="link" id="wz-cancel">Close</button>` : ""}
          </div>
          <div class="wz-bar"><i style="width:${((step + 1) / STEPS.length) * 100}%"></i></div>
          <h2 id="wz-title">${esc(STEP_TITLES[id])}</h2>
          <div class="wz-body" id="wz-body">${body(id)}</div>
          <div class="wz-nav">
            <button type="button" class="btn" id="wz-back" ${step === 0 ? "disabled" : ""}>Back</button>
            <button type="button" class="btn primary" id="wz-next">${step === STEPS.length - 1 ? "Show my map" : "Next"}</button>
          </div>
        </div>`;
      wire(id);
      root.querySelector("#wz-next").focus({ preventScroll: true });
    }

    // ------------------------------------------------------------- step bodies
    function choice(name, value, label, sub) {
      return `<button type="button" class="wz-opt" data-name="${name}" data-value="${esc(value)}" aria-pressed="${s[name] === value}">
        <b>${esc(label)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}</button>`;
    }

    function body(id) {
      if (id === "who") {
        return `<p class="wz-lede">The Atlas scores every US county and every town over 5,000 people against what you tell it, then puts the areas you already like next to the ones the data says you should see.</p>
          <div class="wz-opts two">${choice("mode", "single", "Just me", "One login, one set of weights.")}
          ${choice("mode", "couple", "The two of us", "Invite your partner after setup; you share one map and one set of weights.")}</div>`;
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
      if (id === "life") {
        return `<div class="wz-q"><h3>Children</h3><div class="wz-opts three">
            ${choice("kids", "none", "None planned")}${choice("kids", "planned", "Planning to")}${choice("kids", "now", "Have kids now")}</div></div>
          <div class="wz-q"><h3>Work</h3><div class="wz-opts three">
            ${choice("income", "portable", "Works anywhere")}${choice("income", "partly", "Partly tied")}${choice("income", "local", "Need local jobs")}</div></div>
          <div class="wz-q"><h3>Flights abroad</h3><div class="wz-opts three">
            ${choice("flights", "often", "Often")}${choice("flights", "sometimes", "Now and then")}${choice("flights", "rarely", "Rarely")}</div></div>
          <p class="muted small">These set where the sliders start on the next steps. You decide the final weights.</p>`;
      }
      if (id === "winters") {
        const wt = model.homeWinter(s.home);
        if (wt != null) {
          return `<p class="wz-lede">Winters where you live now average <b class="num">${Math.round(wt)}°F</b> (December to February). Compared with that, you want:</p>
            <div class="wz-opts">${climateChoices(wt, model.presets).map((c) => {
              const p = model.presets.find((x) => x.id === c.preset);
              return `<button type="button" class="wz-opt row" data-preset="${p.id}" aria-pressed="${s.climate === p.id}"><b>${esc(c.label)}</b><span>${esc(p.label)} · ${p.winter[0]}-${p.winter[1]}°F</span></button>`;
            }).join("")}</div>`;
        }
        return `<p class="wz-lede">Average winter temperature (December to February) you'd be happiest with:</p>
          <div class="wz-opts">${model.presets.map((p) => `<button type="button" class="wz-opt row" data-preset="${p.id}" aria-pressed="${s.climate === p.id}"><b>${esc(p.label)}</b><span>${p.winter[0]}-${p.winter[1]}°F</span></button>`).join("")}</div>`;
      }
      if (id === "weights") {
        refreshWeights();
        const total = model.factors.reduce((a, f) => a + (s.weights[f.id] || 0), 0)
          + model.layers.reduce((a, l) => a + (s.layers[l.id]?.on ? s.weights[l.id] || 0 : 0), 0);
        return `<p class="wz-lede">Split your points. What counts is each factor's share of the total, so giving more to one gives less to the rest.</p>
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

    function wire(id) {
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
      root.querySelectorAll(".wz-opt[data-preset]").forEach((b) => b.addEventListener("click", () => { s.climate = b.dataset.preset; render(); }));

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
      if (STEPS[step] === "money") {
        const v = Math.round(+root.querySelector("#wz-cap").value);
        if (v > 0) s.cap = v;
      }
      if (STEPS[step] === "life") refreshWeights();
      if (step < STEPS.length - 1) { step += 1; render(); return; }
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
