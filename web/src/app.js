// The map and its panels: one visitor's (or one couple's) live view over the model.
// Carried over from the household's own atlas (src/wlm/atlas/page/atlas.js); what changed
// is where state lives (the Model's settings, and a Store) and that every visitor brings
// their own home town, budget, climate preset and opt-in layers.
import * as d3 from "d3";
import { A, STATUS_LABEL, STATUSES } from "./model.js";
import { debounce, esc, fitNum, MI_PER_DEG, money } from "./util.js";

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = (sel) => document.querySelector(sel);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

export function createApp({ model, store, onEditSetup }) {
  const M = model;
  const st = {
    store, pins: [], towns: new Map(), region: null, regionTowns: [], town: null,
    colorBy: "fit", showZips: false, geo: new Map(), k: 1, ready: false,
  };

  // ------------------------------------------------------------------ prices
  const priceWord = () => (M.settings.tenure === "buy" ? "home" : "rent");
  function pricePill(p) {
    const r = M.priceOf(p), b = M.budgetOf(p);
    const txt = r.v == null ? `${priceWord()} n/a`
      : M.settings.tenure === "buy" ? "$" + Math.round(r.v / 1000).toLocaleString("en-US") + "k" + (r.src === "county" ? " cty" : "")
        : money(r.v) + (r.src === "county" ? " cty" : "");
    const why = b === "unk" ? `No Zillow ${priceWord()} figure for this town or county`
      : r.src === "county" ? "County median (too little ZIP coverage inside this town)"
        : M.settings.tenure === "buy" ? "Typical home value, ZIPs covering this town" : "Typical market rent, ZIPs covering this town";
    return `<span class="pill ${b}" title="${esc(why)}">${esc(txt)}</span>`;
  }
  const capText = () => (M.settings.tenure === "buy" ? `${money(M.settings.cap)} home budget` : `${money(M.settings.cap)}/mo rent cap`);

  // ------------------------------------------------------------------ colour
  let fitRamp, priceScale;
  function makeScales() {
    fitRamp = d3.interpolateRgbBasis(["--fit0", "--fit1", "--fit2", "--fit3", "--fit4"].map(css));
    const ok = css("--ok"), over = css("--over"), cap = M.settings.cap;
    priceScale = d3.scaleLinear().domain([cap * 0.55, cap * 0.95, cap * 1.05, cap * 1.7])
      .range([ok, d3.interpolateRgb(ok, "#d9f2e6")(0.45), d3.interpolateRgb(over, "#ffe1e4")(0.45), over]).clamp(true);
  }
  const fitColor = (pct) => (pct == null ? "#1a2232" : fitRamp(pct));
  function townFill(p) {
    if (st.colorBy === "rent") { const r = M.priceOf(p).v; return r == null ? "#1a2232" : priceScale(r); }
    return fitColor(p.pct);
  }

  // ------------------------------------------------------------------ map
  const svg = d3.select("#map");
  const gRoot = svg.append("g");
  const L = {};
  ["us", "states", "rzips", "rcounties", "rtowns", "ring", "labels", "pins"].forEach((k) => { L[k] = gRoot.append("g").attr("class", "l-" + k); });
  let projection, path, usStates, usCounties;
  const zoom = d3.zoom().scaleExtent([1, 900]).on("zoom", (e) => {
    gRoot.attr("transform", e.transform);
    st.k = e.transform.k;
    rescale();
  });
  svg.call(zoom).on("dblclick.zoom", null);

  function decodeFeature(f, q) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    const coords = f.p.map((poly) => poly.map((ring) => {
      const pts = A.decodeRing(ring, q);
      for (const [x, y] of pts) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      return pts;
    }));
    return { id: f.id, n: f.n, r: f.r, h: f.h, bbox: [x0, y0, x1, y1], type: "Feature", properties: {}, geometry: { type: "MultiPolygon", coordinates: coords } };
  }
  const intersects = (b, box) => !(b[2] < box[0] || b[0] > box[2] || b[3] < box[1] || b[1] > box[3]);
  function scopeSize() {
    const r = $("#scope").getBoundingClientRect();
    return { w: Math.max(200, r.width), h: Math.max(200, r.height) };
  }
  function fitProjection() {
    const { w, h } = scopeSize();
    svg.attr("viewBox", `0 0 ${w} ${h}`);
    projection = d3.geoAlbersUsa().fitExtent([[16, 40], [w - 16, h - 16]], { type: "FeatureCollection", features: usStates });
    path = d3.geoPath(projection);
  }
  const project = (lat, lon) => projection([lon, lat]);

  function drawUS() {
    L.us.selectAll("path").data(usCounties, (d) => d.id).join("path")
      .attr("class", "c-us").attr("d", path)
      .on("mousemove", (e, d) => showTip(e, countyTip(d)))
      .on("mouseleave", hideTip)
      .on("click", (e, d) => openCounty(d.id));
    L.states.selectAll("path").data(usStates, (d) => d.id).join("path").attr("class", "st-us").attr("d", path);
    paintUS();
  }
  function paintUS() {
    L.us.selectAll("path").attr("fill", (d) => { const c = M.counties.get(d.id); return fitColor(c ? c.pct : null); });
  }
  function countyTip(d) {
    const c = M.counties.get(d.id);
    if (!c) return "";
    const price = M.settings.tenure === "buy" ? M.rawVal(c, "county", "cost_home_value_median") : M.rawVal(c, "county", "cost_rent_median_zori");
    return `<b>${esc(c.name)}, ${esc(c.st)}</b>fit ${c.s && c.s.ok ? fitNum(c.s) : "—"} · ${priceWord()} ${price == null ? "n/a" : money(price)}<br>${c.places.length} town${c.places.length === 1 ? "" : "s"} over 5,000 · click to explore`;
  }

  function homePlace() { return M.settings.home ? M.places.get(M.settings.home) : null; }

  function drawPins() {
    const items = [];
    const home = homePlace();
    if (home) items.push({ key: "home", kind: "home", lat: home.lat, lon: home.lon, label: "Home · " + home.name, act: () => openPin({ id: "home", label: `${home.name} (home)`, anchor: home.id, radius_mi: 20, kind: "home" }) });
    M.challengers.forEach((c, i) => items.push({
      key: "rv" + c.county.id, kind: "rival", lat: c.town.lat, lon: c.town.lon, label: (i + 1) + " · " + c.town.name,
      act: () => openPin({ id: "rv-" + c.town.id, label: `${c.town.name}, ${c.town.st}`, anchor: c.town.id, radius_mi: 20, kind: "rival" }),
    }));
    st.pins.forEach((p) => { const a = M.anchorOf(p); if (a) items.push({ key: "pin" + p.id, kind: "pick", lat: a.lat, lon: a.lon, label: p.label, act: () => openPin(p) }); });
    const { w } = scopeSize();
    for (const it of items) {
      const xy = project(it.lat, it.lon);
      it.x = xy ? xy[0] : null; it.y = xy ? xy[1] : null;
      it.flip = xy != null && xy[0] > w - 130;
    }
    const g = L.pins.selectAll("g.pin").data(items.filter((d) => d.x != null), (d) => d.key).join((enter) => {
      const e = enter.append("g").attr("tabindex", 0).attr("role", "button");
      e.append("circle").attr("class", "halo").attr("r", 9);
      e.append("circle").attr("class", "core");
      e.append("text").attr("y", 4);
      return e;
    });
    g.attr("class", (d) => "pin " + d.kind + (d.flip ? " flip" : "")).attr("aria-label", (d) => d.label);
    g.select(".core").attr("r", (d) => (d.kind === "home" ? 4.5 : d.kind === "rival" ? 5 : 6.5))
      .attr("transform", (d) => (d.kind === "home" ? "rotate(45)" : null));
    g.select("text").attr("x", (d) => (d.flip ? -11 : 11)).text((d) => d.label);
    g.on("click", (e, d) => { e.stopPropagation(); d.act(); })
      .on("keydown", (e, d) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); d.act(); } });
    rescale();
  }

  function rescale() {
    const k = st.k;
    const a = st.region ? M.anchorOf(st.region) : null;
    L.pins.selectAll("g.pin").attr("transform", (d) => `translate(${d.x},${d.y}) scale(${1 / k})`)
      .select("text").attr("display", (d) => {
        if (a && d.lat === a.lat && d.lon === a.lon) return "none"; // the HUD names the open region
        return d.kind === "rival" && k < 2.2 && !st.region ? "none" : null;
      });
    L.labels.selectAll("g.lbl").attr("transform", (d) => `translate(${d.x},${d.y}) scale(${1 / k})`);
  }

  function zoomToBox(lat, lon, r, dur) {
    const dLat = r / MI_PER_DEG, dLon = dLat / Math.cos(lat * Math.PI / 180);
    const pts = [[lon - dLon, lat - dLat], [lon + dLon, lat - dLat], [lon - dLon, lat + dLat], [lon + dLon, lat + dLat]]
      .map((c) => projection(c)).filter(Boolean);
    if (!pts.length) return;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const { w, h } = scopeSize();
    const k = Math.min(900, 0.9 / Math.max((x1 - x0) / w, (y1 - y0) / (h - 30)));
    const t = d3.zoomIdentity.translate(w / 2, h / 2 + 12).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
    svg.interrupt().transition().duration(reduceMotion ? 0 : dur).call(zoom.transform, t);
  }
  function zoomHome(dur) {
    svg.interrupt().transition().duration(reduceMotion ? 0 : dur).call(zoom.transform, d3.zoomIdentity);
  }

  function loadState(code) {
    if (!st.geo.has(code)) {
      st.geo.set(code, fetch(`geo/${code}.json`).then((r) => {
        if (!r.ok) throw new Error(`geo/${code}.json: ${r.status}`);
        return r.json();
      }).then((j) => ({
        counties: j.counties.map((f) => decodeFeature(f, j.q)),
        towns: j.towns.map((f) => decodeFeature(f, j.q)),
        zips: j.zips.map((f) => decodeFeature(f, j.q)),
      })).catch((e) => { st.geo.delete(code); throw e; }));
    }
    return st.geo.get(code);
  }

  async function openPin(pin, opts = {}) {
    const a = M.anchorOf(pin);
    if (!a) return;
    st.region = pin;
    st.town = null;
    st.regionTowns = M.townsNear(a.lat, a.lon, pin.radius_mi);
    $("#scope").classList.add("zoomed");
    $("#btn-us").hidden = false;
    $("#hud-mode").innerHTML = `Region <b>${esc(pin.label)}</b> · radius ${pin.radius_mi} mi · ${st.regionTowns.length} towns`;
    zoomToBox(a.lat, a.lon, pin.radius_mi * 1.08, opts.instant ? 0 : 1300);
    rescale();
    renderReadout();
    renderPlaces();
    if (!opts.keepTab) mobileTab("detail");
    const codes = new Set(st.regionTowns.map((p) => p.st));
    codes.add(a.st);
    const dLat = (pin.radius_mi * 1.7) / MI_PER_DEG, dLon = dLat / Math.cos(a.lat * Math.PI / 180);
    const box = [a.lon - dLon, a.lat - dLat, a.lon + dLon, a.lat + dLat];
    for (const c of M.counties.values()) if (c.lat > box[1] - 0.3 && c.lat < box[3] + 0.3 && c.lon > box[0] - 0.3 && c.lon < box[2] + 0.3) codes.add(c.st);
    let layers;
    try {
      layers = await Promise.all([...codes].map(loadState));
    } catch {
      $("#hud-mode").innerHTML += " · <b>outlines failed to load</b>";
      return;
    }
    if (st.region !== pin) return;
    drawRegion(pin, a, box, layers);
  }

  function drawRegion(pin, a, box, layers) {
    const inR = new Set(st.regionTowns.map((p) => p.id));
    const pick = (key) => layers.flatMap((l) => l[key]).filter((f) => intersects(f.bbox, box));
    L.rcounties.selectAll("path").data(pick("counties"), (d) => d.id).join("path").attr("class", "rc").attr("d", path);
    const zipKey = M.settings.tenure === "buy" ? "h" : "r";
    L.rzips.selectAll("path").data(pick("zips").filter((f) => f[zipKey] != null), (d) => d.id).join("path").attr("class", "rz").attr("d", path)
      .attr("fill", (d) => priceScale(d[zipKey])).attr("fill-opacity", 0.55);
    L.rzips.attr("display", st.showZips ? null : "none");
    const towns = pick("towns").filter((f) => M.places.has(f.id));
    L.rtowns.selectAll("path").data(towns, (d) => d.id).join("path")
      .attr("d", path)
      .attr("class", (d) => "rt" + (inR.has(d.id) ? "" : " out") + (st.town && st.town.id === d.id ? " sel" : ""))
      .on("mousemove", (e, d) => showTip(e, townTip(M.places.get(d.id))))
      .on("mouseleave", hideTip)
      .on("click", (e, d) => { e.stopPropagation(); selectTown(d.id); });
    paintRegion();
    const circle = d3.geoCircle().center([a.lon, a.lat]).radius(pin.radius_mi / MI_PER_DEG)();
    L.ring.selectAll("path").data([circle]).join("path").attr("class", "ring").attr("d", path);
    drawLabels();
  }
  function paintRegion() {
    L.rtowns.selectAll("path").attr("fill", (d) => townFill(M.places.get(d.id)))
      .attr("fill-opacity", st.showZips ? 0.25 : 0.9);
  }
  function drawLabels() {
    const top = st.regionTowns.filter((p) => p.s && p.s.ok).slice(0, 9);
    const a = st.region ? M.anchorOf(st.region) : null;
    if (a && a.level === "place" && !top.includes(a)) top.push(a);
    const items = top.map((p) => { const xy = project(p.lat, p.lon); return xy && { p, x: xy[0], y: xy[1], key: p.id }; }).filter(Boolean);
    const g = L.labels.selectAll("g.lbl").data(items, (d) => d.key).join((enter) => {
      const e = enter.append("g").attr("class", "lbl");
      e.append("text").attr("text-anchor", "middle").attr("y", 4);
      return e;
    });
    // The anchor town sits under its own pin dot; its label goes below the dot.
    g.select("text").attr("y", (d) => (a && d.p === a ? 20 : 4));
    g.select("text").each(function (d) {
      const t = d3.select(this);
      t.text(null);
      t.append("tspan").text(d.p.name + " ");
      t.append("tspan").attr("class", "sc").text(d.p.s && d.p.s.ok ? fitNum(d.p.s) : "—");
    });
    rescale();
  }
  function clearRegion() {
    ["rzips", "rcounties", "rtowns", "ring", "labels"].forEach((k) => L[k].selectAll("*").remove());
  }
  function townTip(p) {
    if (!p) return "";
    const r = M.priceOf(p), note = st.towns.get(p.id);
    return `<b>${esc(p.name)}, ${esc(p.st)}</b>fit ${p.s && p.s.ok ? fitNum(p.s) : "—"}${p.rank ? " · #" + p.rank.toLocaleString("en-US") : ""} · ${priceWord()} ${r.v == null ? "n/a" : money(r.v)}${r.src === "county" ? " (county)" : ""}<br>pop ${p.pop ? p.pop.toLocaleString("en-US") : "—"}${note && note.status ? " · " + STATUS_LABEL[note.status] : ""}`;
  }

  function goUS() {
    st.region = null; st.town = null; st.regionTowns = [];
    clearRegion();
    $("#scope").classList.remove("zoomed");
    $("#btn-us").hidden = true;
    hudUS();
    zoomHome(1000);
    renderReadout();
    renderPlaces();
  }
  const hudUS = () => { $("#hud-mode").innerHTML = `Continental US · <b>${M.countyRankN.toLocaleString("en-US")}</b> counties scored`; };

  function openCounty(id) {
    const c = M.counties.get(id);
    if (!c) return;
    const towns = c.places.filter((p) => p.s && p.s.ok).sort((a, b) => b.s.score - a.s.score);
    const anchor = towns[0] || c;
    openPin({ id: "cty-" + id, label: `${c.name}, ${c.st}`, anchor: anchor.id, radius_mi: 20, kind: "temp" });
  }

  function selectTown(id) {
    const p = M.places.get(id);
    if (!p) return;
    if (!st.region) {
      openPin({ id: "t-" + id, label: `${p.name}, ${p.st}`, anchor: id, radius_mi: 15, kind: "temp" }).then(() => selectTown(id));
      return;
    }
    st.town = p;
    L.rtowns.selectAll("path").classed("sel", (d) => d.id === id);
    renderReadout();
    mobileTab("detail");
  }

  // tooltip + coordinates
  const tip = $("#tip");
  function showTip(e, html) {
    if (!html || window.matchMedia("(hover: none)").matches) return;
    tip.innerHTML = html;
    tip.hidden = false;
    const r = $("#scope").getBoundingClientRect();
    let x = e.clientX - r.left + 14, y = e.clientY - r.top + 14;
    if (x + 250 > r.width) x -= 270;
    if (y + 80 > r.height) y -= 90;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  function hideTip() { tip.hidden = true; }
  svg.on("pointermove.coords", (e) => {
    const t = d3.zoomTransform(svg.node());
    const [mx, my] = d3.pointer(e, svg.node());
    const ll = projection && projection.invert(t.invert([mx, my]));
    $("#coords").textContent = ll ? `${Math.abs(ll[1]).toFixed(3)}°${ll[1] >= 0 ? "N" : "S"}  ${Math.abs(ll[0]).toFixed(3)}°${ll[0] >= 0 ? "E" : "W"}  ×${t.k.toFixed(1)}` : "";
  });

  // ------------------------------------------------------------------ legend
  function renderLegend() {
    const cap = M.settings.cap;
    const priceView = (st.colorBy === "rent" || st.showZips) && st.region;
    const stops = d3.range(0, 1.0001, 0.1).map((t) => fitColor(t)).join(",");
    const rstops = d3.range(0, 1.0001, 0.1).map((t) => priceScale(cap * (0.55 + t * 1.15))).join(",");
    $("#legend").innerHTML = priceView
      ? `<div>${M.settings.tenure === "buy" ? "Home value" : "Rent"} vs your ${esc(capText())}</div><div class="ramp" style="background:linear-gradient(90deg,${rstops})"></div>
         <div class="ramp-l"><span>${money(cap * 0.55)}</span><span>cap</span><span>${money(cap * 1.7)}+</span></div>`
      : `<div>Fit under your weights (national rank)</div><div class="ramp" style="background:linear-gradient(90deg,${stops})"></div>
         <div class="ramp-l"><span>bottom</span><span>median</span><span>top</span></div>
         <div class="legend-keys"><span><i style="background:var(--pick)"></i>your picks</span><span><i style="background:var(--rival)"></i>challengers</span>${homePlace() ? `<span><i style="background:var(--home);border-radius:1px"></i>home</span>` : ""}</div>`;
  }

  // ------------------------------------------------------------------ panels
  function scoreChip(o) {
    if (!o || !o.s || !o.s.ok) return `<span class="chip" style="background:#2a3446;color:var(--dim)">—</span>`;
    return `<span class="chip" style="background:${fitColor(o.pct)}">${fitNum(o.s)}</span>`;
  }
  function openRival(id) {
    const t = M.places.get(id);
    openPin({ id: "rv-" + t.id, label: `${t.name}, ${t.st}`, anchor: t.id, radius_mi: 20, kind: "rival" });
  }

  function renderPlaces() {
    const home = homePlace();
    const pinCards = st.pins.map((pin) => {
      const sm = M.pinSummary(pin);
      if (!sm) return "";
      const b = sm.best;
      return `<button type="button" class="card" data-pin="${esc(pin.id)}" aria-current="${!!(st.region && st.region.id === pin.id)}">
        <span class="dot pick"></span><span class="t">${esc(pin.label)}</span><span class="score num">${b ? fitNum(b.s) : "—"}</span>
        <span class="s">best ${b ? esc(b.name) : "—"} ${b ? pricePill(b) : ""}<br>${sm.under} of ${sm.towns.length} towns within your ${esc(capText())}${sm.bestOk && sm.bestOk !== b ? ` · best within it: ${esc(sm.bestOk.name)} ${fitNum(sm.bestOk.s)}` : ""}</span></button>`;
    });
    const rivals = M.challengers.map((c, i) => `<button type="button" class="card" data-rival="${esc(c.town.id)}" aria-current="${!!(st.region && st.region.anchor === c.town.id)}">
        <span class="dot rival"></span><span class="t">${i + 1}. ${esc(c.town.name)}, ${esc(c.town.st)}</span><span class="score num">${fitNum(c.town.s)}</span>
        <span class="s">${esc(c.county.name)} ${pricePill(c.town)} · #${c.town.rank.toLocaleString("en-US")} of ${M.rankN.toLocaleString("en-US")}</span></button>`);
    const visits = [...st.towns.entries()].filter(([, v]) => v && v.status).map(([id, v]) => ({ p: M.places.get(id), v })).filter((x) => x.p);
    const order = { favorite: 0, want: 1, visited: 2, "ruled-out": 3 };
    visits.sort((a, b) => order[a.v.status] - order[b.v.status] || (b.p.s ? b.p.s.score : 0) - (a.p.s ? a.p.s.score : 0));
    const box = $("#tab-places");
    box.innerHTML = `
      <section><h3 class="eyebrow">Your picks <em>${st.pins.length} areas</em></h3>
        <div class="cards">${pinCards.join("") || `<p class="empty">No areas pinned. Search for a town above, or click any county on the map, then pin it.</p>`}</div></section>
      <section><h3 class="eyebrow">Challengers <em>machine picks, live</em></h3>
        <p class="small muted" style="margin-bottom:10px">The best-fitting counties in America under your current weights${M.settings.budgetOnly ? `, each shown through its best town within your ${esc(capText())}` : ""}. They change every time you move a weight. Visit one of these for every two of yours.</p>
        <div class="cards">${rivals.join("") || `<p class="empty">No county clears the coverage floor under these weights.</p>`}</div></section>
      <section><h3 class="eyebrow">Visit list <em>${visits.length} towns</em></h3>
        ${visits.length ? `<table class="towns"><tbody>${visits.map((x) => `<tr data-town="${esc(x.p.id)}"><td>${scoreChip(x.p)}</td><td>${esc(x.p.name)}, ${esc(x.p.st)}<span class="st muted">${esc(STATUS_LABEL[x.v.status])}</span></td><td class="r">${pricePill(x.p)}</td></tr>`).join("")}</tbody></table>`
          : `<p class="empty">Mark towns as Want to visit, Visited, Favorite or Ruled out from the details panel. They collect here.</p>`}</section>
      ${home ? `<section><h3 class="eyebrow">Where you live now</h3><button type="button" class="card" data-home="1"><span class="dot home"></span><span class="t">${esc(home.name)}, ${esc(home.st)}</span><span class="score num">${fitNum(home.s) ?? "—"}</span>
        <span class="s">Scored the same way. Anything worth moving to should beat it. ${pricePill(home)}</span></button></section>` : ""}`;
    box.querySelectorAll("[data-pin]").forEach((b) => b.addEventListener("click", () => openPin(st.pins.find((p) => p.id === b.dataset.pin))));
    box.querySelectorAll("[data-rival]").forEach((b) => b.addEventListener("click", () => openRival(b.dataset.rival)));
    box.querySelectorAll("[data-town]").forEach((r) => r.addEventListener("click", () => selectTown(r.dataset.town)));
    const hb = box.querySelector("[data-home]");
    if (hb) hb.addEventListener("click", () => openPin({ id: "home", label: `${home.name} (home)`, anchor: home.id, radius_mi: 20, kind: "home" }));
  }

  function totalPoints() {
    const w = M.weightVector();
    return w.reduce((a, b) => a + b, 0);
  }

  function renderWeights() {
    const s = M.settings, total = totalPoints();
    const share = (v) => (total ? Math.round((100 * v) / total) : 0);
    const box = $("#tab-weights");
    box.innerHTML = `
      <section><h3 class="eyebrow">Weights <em>${esc(st.store.label)}</em></h3>
        <p class="small muted">${s.mode === "couple" ? "One set for the two of you. " : ""}Points are relative: what matters is each factor's share of the total. Every score and every challenger updates as you move them.</p></section>
      <div class="total"><span>total points</span><b class="num" id="w-total">${total}</b></div>
      <div class="weights">${M.factors.map((f) => `
        <div class="w-row${s.weights[f.id] ? "" : " zero"}">
          <label for="w-${f.id}">${esc(f.label)}</label><output id="o-${f.id}" for="w-${f.id}">${s.weights[f.id] || 0}<span class="muted"> · ${share(s.weights[f.id] || 0)}%</span></output>
          <input type="range" id="w-${f.id}" min="0" max="30" step="1" value="${s.weights[f.id] || 0}" data-w="${f.id}">
          <p>${esc(f.blurb)}</p>
        </div>`).join("")}</div>
      <details class="sens" ${M.layers.some((l) => s.layers[l.id]?.on) ? "open" : ""}><summary>Optional: sensitive layers</summary>
        <p class="small muted">Off unless you switch one on. You choose the direction; a layer only shifts scores and never hides a place.</p>
        ${M.layers.map((l) => {
          const set = s.layers[l.id] || {};
          const on = set.on && set.dir;
          return `<div class="layer"><label class="check"><input type="checkbox" data-on="${l.id}" ${set.on ? "checked" : ""}> <b>${esc(l.label)}</b></label>
            <div class="seg" role="group" aria-label="${esc(l.label)} direction">${Object.entries(l.directions).map(([k, v]) => `<button type="button" data-dir="${l.id}:${k}" aria-pressed="${set.dir === k}" ${set.on ? "" : "disabled"}>${esc(v)}</button>`).join("")}</div>
            <div class="w-row${on && s.weights[l.id] ? "" : " zero"}"><label for="w-${l.id}">Weight</label><output id="o-${l.id}">${on ? s.weights[l.id] || 0 : 0}<span class="muted"> · ${on ? share(s.weights[l.id] || 0) : 0}%</span></output>
            <input type="range" id="w-${l.id}" min="0" max="30" step="1" value="${on ? s.weights[l.id] || 0 : 0}" data-w="${l.id}" ${on ? "" : "disabled"}></div></div>`;
        }).join("")}</details>
      <div class="field"><label for="climate" class="eyebrow" style="margin:0">Winters</label>
        <select id="climate">${M.presets.map((p) => `<option value="${p.id}" ${p.id === s.climate ? "selected" : ""}>${esc(p.label)} (${p.winter[0]}-${p.winter[1]}°F)</option>`).join("")}</select></div>
      <div class="field"><label for="cap" class="eyebrow" style="margin:0">${s.tenure === "buy" ? "Home budget" : "Rent cap, per month"}</label>
        <input type="number" id="cap" min="300" step="${s.tenure === "buy" ? 10000 : 50}" value="${s.cap}"></div>
      <label class="check"><input type="checkbox" id="budget-only" ${s.budgetOnly ? "checked" : ""}> Challengers must have a town within budget</label>
      <div class="row-btns"><button type="button" class="btn" id="edit-setup">Redo setup</button></div>`;
    box.querySelectorAll("input[data-w]").forEach((inp) => inp.addEventListener("input", () => {
      s.weights[inp.dataset.w] = +inp.value;
      const t = totalPoints();
      $("#w-total").textContent = t;
      M.slots.forEach((slot) => {
        const o = $("#o-" + slot.id);
        if (!o) return;
        const v = slot.kind === "layer" && !(s.layers[slot.id]?.on && s.layers[slot.id]?.dir) ? 0 : s.weights[slot.id] || 0;
        o.innerHTML = `${v}<span class="muted"> · ${t ? Math.round((100 * v) / t) : 0}%</span>`;
        o.parentElement.classList.toggle("zero", !v);
      });
      rescoreSoon();
      saveSettings();
    }));
    box.querySelectorAll("input[data-on]").forEach((c) => c.addEventListener("change", () => {
      const l = c.dataset.on;
      s.layers[l] = { on: c.checked, dir: c.checked ? s.layers[l]?.dir || null : null };
      if (!c.checked) s.weights[l] = 0;
      renderWeights(); rescore(); saveSettings();
    }));
    box.querySelectorAll("[data-dir]").forEach((b) => b.addEventListener("click", () => {
      const [l, dir] = b.dataset.dir.split(":");
      s.layers[l] = { on: true, dir };
      if (!s.weights[l]) s.weights[l] = 5;
      renderWeights(); rescore(); saveSettings();
    }));
    $("#climate").addEventListener("change", (e) => { s.climate = e.target.value; rescore(); saveSettings(); });
    $("#cap").addEventListener("change", (e) => {
      const v = Math.round(+e.target.value);
      if (v > 0) { s.cap = v; makeScales(); rescore(); saveSettings(); }
    });
    $("#budget-only").addEventListener("change", (e) => { s.budgetOnly = e.target.checked; rescore(); saveSettings(); });
    $("#edit-setup").addEventListener("click", () => onEditSetup());
  }

  function factorBars(p) {
    const w = M.weightVector();
    const total = w.reduce((a, b) => a + b, 0) || 1;
    const order = M.slots.map((_, i) => i).filter((i) => M.slots[i].kind === "factor" || w[i] > 0).sort((a, b) => w[b] - w[a]);
    return `<div class="bars">${order.map((i) => {
      const v = p.v ? p.v[i] : null, slot = M.slots[i];
      const label = slot.kind === "layer" ? `${slot.label}: ${slot.directions[M.settings.layers[slot.id].dir]}` : slot.label;
      return `<div class="bar-row${w[i] ? "" : " off"}" title="${esc(slot.blurb || "")}"><span>${esc(label)} <span class="muted num small">${Math.round((100 * w[i]) / total)}%</span></span>
        <span class="track"><i style="width:${v == null ? 0 : Math.max(2, v * 100)}%;background:${v == null ? "transparent" : fitColor(v)}"></i></span>
        <span class="v">${v == null ? "n/a" : Math.round(v * 100)}</span></div>`;
    }).join("")}</div>`;
  }

  function factsTable(p) {
    const c = M.countyOf(p);
    const rows = [];
    for (const f of M.factors) {
      const items = [];
      for (const d of M.core.inds) {
        if (d.factor !== f.id) continue;
        let v = M.rawVal(p, "place", d.id), lvl = "town";
        if (v == null && c) { v = M.rawVal(c, "county", d.id); lvl = "county"; }
        if (v == null) continue;
        items.push(`<tr><td>${esc(d.label)}<span class="lvl">${lvl}</span></td><td>${esc(A.fmt(v, d.unit))}</td></tr>`);
      }
      if (items.length) rows.push(`<tr class="grp"><td colspan="2">${esc(f.label)}</td></tr>` + items.join(""));
    }
    return `<table class="facts"><tbody>${rows.join("")}</tbody></table>`;
  }

  function sourcesLine(p) {
    const r = M.priceOf(p), zm = M.core.zillowMonth;
    const used = new Set(M.core.inds.map((d) => d.source));
    const list = [...used].map((id) => M.core.sources[id]).filter(Boolean)
      .map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>`).join(" · ");
    return `<p class="src">${M.settings.tenure === "buy" ? `Home value: Zillow ZHVI ${esc(zm.home)}` : `Rent: Zillow ZORI ${esc(zm.rent)}`}, ${r.src === "town" ? `land-weighted over the ZIPs covering ${Math.round((r.share || 0) * 100)}% of the town` : r.src === "county" ? "county median (too little ZIP coverage inside the town)" : "not published here"}. Everything else: ${list}. Data built ${esc(M.core.built)}.</p>`;
  }

  function renderReadout() {
    const box = $("#readout");
    if (st.town) {
      const p = st.town, c = M.countyOf(p), r = M.priceOf(p), b = M.budgetOf(p), mine = st.towns.get(p.id) || {};
      const gap = r.v == null ? "" : b === "ok" ? `${money(M.settings.cap - r.v)} under your cap` : `${money(r.v - M.settings.cap)} over your cap`;
      const anchor = st.region ? M.anchorOf(st.region) : null;
      box.innerHTML = `
        <div class="row-btns"><button type="button" class="btn" id="back-region">← ${esc(st.region ? st.region.label : "Back")}</button></div>
        <div class="readout-head"><h2>${esc(p.name)}, ${esc(p.st)}</h2>
          <p class="meta">${esc(c ? c.name : "")} · pop ${p.pop ? p.pop.toLocaleString("en-US") : "—"} · GEOID ${esc(p.id)}${anchor && st.regionTowns.includes(p) ? ` · ${p._d.toFixed(1)} mi from ${esc(anchor.name)}` : ""}</p></div>
        <div class="fitbox"><span class="big num" style="color:${p.s && p.s.ok ? fitColor(Math.max(p.pct ?? 0, 0.35)) : "var(--dim)"}">${p.s && p.s.ok ? fitNum(p.s) : "—"}</span>
          <span class="lab">fit under your weights, of 100</span>
          <span class="rank">${p.rank ? `#${p.rank.toLocaleString("en-US")} of ${M.rankN.toLocaleString("en-US")} towns · top ${Math.max(1, Math.round((100 * p.rank) / M.rankN))}%` : p.s ? `data covers ${Math.round(p.s.cov * 100)}% of your weight, under the 80% floor` : "not enough data to score"}</span></div>
        <div class="row-btns">${pricePill(p)}${M.settings.tenure === "rent" && M.homeOf(p).v != null ? `<span class="pill unk">home ${money(M.homeOf(p).v)}</span>` : ""}<span class="small muted">${esc(gap)}</span></div>
        <section><h3>Your status</h3><div class="status" role="group" aria-label="Status">${STATUSES.map(([k, l]) => `<button type="button" data-s="${k}" aria-pressed="${mine.status === k}">${l}</button>`).join("")}</div></section>
        <section><h3><label for="note">Notes</label></h3><textarea id="note" placeholder="What you saw, who you met, what to check next time">${esc(mine.note || "")}</textarea><p class="note-saved" id="note-saved"></p></section>
        <section><h3>Why it scores this way</h3>${factorBars(p)}</section>
        <section><h3>The numbers</h3>${factsTable(p)}</section>
        ${sourcesLine(p)}`;
      $("#back-region").addEventListener("click", () => { st.town = null; L.rtowns.selectAll("path").classed("sel", false); renderReadout(); });
      box.querySelectorAll(".status button").forEach((btn) => btn.addEventListener("click", () => {
        const cur = (st.towns.get(p.id) || {}).status;
        saveTown(p.id, { status: cur === btn.dataset.s ? null : btn.dataset.s });
      }));
      const saveNote = debounce((v) => saveTown(p.id, { note: v }), 700);
      $("#note").addEventListener("input", (e) => { $("#note-saved").textContent = "Saving…"; saveNote(e.target.value); });
      return;
    }
    if (st.region) {
      const pin = st.region, a = M.anchorOf(pin), ts = st.regionTowns;
      const under = ts.filter((p) => M.budgetOf(p) === "ok").length;
      const isPinned = st.pins.some((p) => p.id === pin.id);
      box.innerHTML = `
        <div class="readout-head"><p class="eyebrow">${pin.kind === "rival" ? "Challenger" : pin.kind === "home" ? "Where you live now" : isPinned ? "Your pick" : "Exploring"}</p>
          <h2>${esc(pin.label)}</h2>
          <p class="meta">${ts.length} towns over 5,000 people within ${pin.radius_mi} mi of ${esc(a.name)} · ${under} within your ${esc(capText())}</p></div>
        <div class="field"><label for="radius" class="eyebrow" style="margin:0">Radius <em class="num">${pin.radius_mi} mi</em></label>
          <input type="range" id="radius" min="5" max="60" step="5" value="${pin.radius_mi}"></div>
        <div class="row-btns">${isPinned ? `<button type="button" class="btn danger" id="unpin">Remove pin</button>` : pin.kind === "home" ? "" : `<button type="button" class="btn primary" id="pin">Pin this area</button>`}<button type="button" class="btn" id="to-us">All US</button></div>
        <section><h3>Towns, best fit first</h3>
        ${ts.length ? `<table class="towns"><thead><tr><th>Fit</th><th>Town</th><th style="text-align:right">${M.settings.tenure === "buy" ? "Home" : "Rent"}</th></tr></thead><tbody>
          ${ts.map((p) => { const s = (st.towns.get(p.id) || {}).status; return `<tr data-town="${esc(p.id)}"><td>${scoreChip(p)}</td><td>${esc(p.name)}<span class="st muted">${p._d.toFixed(0)} mi${s ? " · " + esc(STATUS_LABEL[s]) : ""}</span></td><td class="r">${pricePill(p)}</td></tr>`; }).join("")}
        </tbody></table>` : `<p class="empty">No town over 5,000 people inside this radius. Widen it.</p>`}</section>
        <p class="src">Fit 0-100 is the weighted geometric mean of the factor scores, so one weak factor drags it down hard. Prices are Zillow's typical ${M.settings.tenure === "buy" ? "home value" : "market rent"}, ${esc(M.settings.tenure === "buy" ? M.core.zillowMonth.home : M.core.zillowMonth.rent)}.</p>`;
      box.querySelectorAll("[data-town]").forEach((r) => r.addEventListener("click", () => selectTown(r.dataset.town)));
      $("#to-us").addEventListener("click", goUS);
      $("#radius").addEventListener("change", (e) => {
        const next = { ...pin, radius_mi: +e.target.value };
        if (isPinned) savePin(next);
        openPin(next, { keepTab: true });
      });
      if (isPinned) $("#unpin").addEventListener("click", () => removePin(pin.id));
      else if ($("#pin")) $("#pin").addEventListener("click", () => {
        const id = "p-" + pin.anchor;
        savePin({ id, label: pin.label, anchor: pin.anchor, radius_mi: pin.radius_mi, order: Date.now() % 1e9 });
        st.region = { ...pin, id, kind: "pick" };
        renderReadout();
      });
      return;
    }
    const home = homePlace();
    const rows = st.pins.map((pin) => ({ pin, sm: M.pinSummary(pin) })).filter((x) => x.sm);
    const top = M.challengers[0];
    box.innerHTML = `
      <div class="readout-head"><p class="eyebrow">Overview</p><h2>How your picks stack up</h2>
        <p class="meta">Best town in each area under today's weights, against your ${esc(capText())}.</p></div>
      ${rows.length || top ? `<table class="cmp"><thead><tr><th>Area</th><th class="r">Fit</th><th class="r">${M.settings.tenure === "buy" ? "Home" : "Rent"}</th><th class="r">In budget</th></tr></thead><tbody>
        ${rows.map(({ pin, sm }) => `<tr data-pin="${esc(pin.id)}" style="cursor:pointer"><td>${esc(pin.label)}<br><span class="muted small">${sm.best ? esc(sm.best.name) : "—"}</span></td><td class="r">${sm.best ? fitNum(sm.best.s) : "—"}</td><td class="r">${sm.best ? pricePill(sm.best) : "—"}</td><td class="r">${sm.under}/${sm.towns.length}</td></tr>`).join("")}
        ${top ? `<tr data-rival="${esc(top.town.id)}" style="cursor:pointer"><td><span style="color:var(--rival)">Top challenger</span><br><span class="muted small">${esc(top.town.name)}, ${esc(top.town.st)}</span></td><td class="r">${fitNum(top.town.s)}</td><td class="r">${pricePill(top.town)}</td><td class="r">—</td></tr>` : ""}
        ${home ? `<tr><td>Where you live now<br><span class="muted small">${esc(home.name)}, ${esc(home.st)}</span></td><td class="r">${fitNum(home.s) ?? "—"}</td><td class="r">${pricePill(home)}</td><td class="r">—</td></tr>` : ""}
      </tbody></table>` : ""}
      <section><h3>Reading the map</h3>
        <p class="small muted">Every US county is shaded by how well it fits your weights, brightest is best. Amber pins are the areas you picked, violet pins are the machine's challengers${home ? ", the white diamond is where you live now" : ""}. Click any pin or county to zoom in; every town inside the ring is outlined and scored, and the details panel shows why.</p></section>
      ${rows.length ? `<section><h3>What the data says so far</h3>
        <p class="small muted">${rows.filter((x) => x.sm.best && M.budgetOf(x.sm.best) === "over").length} of your ${rows.length} areas have a best-fitting town over your budget. Switch the map to price colors and the ZIP layer when zoomed in to find the pockets that are not.</p></section>` : ""}`;
    box.querySelectorAll("[data-pin]").forEach((r) => r.addEventListener("click", () => openPin(st.pins.find((p) => p.id === r.dataset.pin))));
    box.querySelectorAll("[data-rival]").forEach((r) => r.addEventListener("click", () => openRival(r.dataset.rival)));
  }

  // ------------------------------------------------------------------ saving
  function setSync(text, warn) { $("#sync").innerHTML = `<b class="${warn ? "local" : ""}">●</b> ${esc(text)}`; }
  const saveSettings = debounce(async () => {
    try { await st.store.saveSettings(M.settings); setSync(st.store.label, st.store.kind === "local"); }
    catch (e) { setSync(`Could not save (${e.message || e.code || "error"})`, true); }
  }, 600);
  async function savePin(pin) {
    st.pins = st.pins.filter((p) => p.id !== pin.id).concat([pin]);
    drawPins(); renderPlaces();
    try { await st.store.savePin(pin); } catch (e) { setSync(`Could not save pin (${e.message || "error"})`, true); }
  }
  async function removePin(id) {
    st.pins = st.pins.filter((p) => p.id !== id);
    drawPins();
    try { await st.store.removePin(id); } catch (e) { setSync(`Could not remove pin (${e.message || "error"})`, true); }
    goUS();
  }
  async function saveTown(id, patch) {
    const cur = { ...(st.towns.get(id) || {}), ...patch };
    if (!cur.status && !cur.note) st.towns.delete(id); else st.towns.set(id, cur);
    const say = (t) => { const n = $("#note-saved"); if (n) n.textContent = t; };
    try { await st.store.saveTown(id, cur); say(st.store.kind === "local" ? "Saved on this device" : "Saved"); }
    catch (e) { say(`Not saved: ${e.message || "error"}`); }
    if (patch.status !== undefined) {
      document.querySelectorAll("#readout .status button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.s === cur.status)));
      renderPlaces();
    }
  }

  // ------------------------------------------------------------------ rescoring
  function rescore() {
    M.compute();
    makeScales();
    paintUS();
    drawPins();
    if (st.region) {
      st.regionTowns.sort((a, b) => (b.s ? b.s.score : -1) - (a.s ? a.s.score : -1));
      paintRegion();
      drawLabels();
    }
    renderLegend();
    renderPlaces();
    const focusInReadout = document.activeElement && document.activeElement.closest && document.activeElement.closest("#readout");
    if (!focusInReadout) renderReadout();
    if (!st.region) hudUS();
  }
  let raf = 0;
  function rescoreSoon() { cancelAnimationFrame(raf); raf = requestAnimationFrame(rescore); }

  // ------------------------------------------------------------------ chrome
  function mobileTab(m) {
    if (!window.matchMedia("(max-width: 1100px)").matches) {
      if (m === "weights" || m === "places") leftTab(m);
      return;
    }
    document.body.classList.remove("m-places", "m-detail", "m-weights");
    document.body.classList.add("m-" + m);
    document.querySelectorAll(".mtabs button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.m === m)));
    if (m === "weights" || m === "places") leftTab(m);
  }
  function leftTab(t) {
    $("#tab-places").hidden = t !== "places";
    $("#tab-weights").hidden = t !== "weights";
    document.querySelectorAll(".left .tabs button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tab === t)));
  }
  function runSearch(q) {
    const ul = $("#search-results");
    const hits = M.search(q);
    if (q.trim().length < 2) { ul.hidden = true; return; }
    ul.innerHTML = hits.length ? hits.map((h) => `<li><button type="button" data-id="${esc(h.id)}" data-kind="${h.kind}"><span>${esc(h.label)}</span><small>${h.kind} · ${h.pop.toLocaleString("en-US")}</small></button></li>`).join("")
      : `<li class="muted small" style="padding:8px 10px">No town over 5,000 people or county by that name.</li>`;
    ul.hidden = false;
    ul.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      ul.hidden = true; $("#search").value = "";
      if (b.dataset.kind === "county") openCounty(b.dataset.id);
      else { const p = M.places.get(b.dataset.id); openPin({ id: "t-" + p.id, label: `${p.name}, ${p.st}`, anchor: p.id, radius_mi: 20, kind: "temp" }); }
    }));
  }
  function wireChrome() {
    document.querySelectorAll(".mtabs button").forEach((b) => b.addEventListener("click", () => mobileTab(b.dataset.m)));
    document.querySelectorAll(".left .tabs button").forEach((b) => b.addEventListener("click", () => leftTab(b.dataset.tab)));
    document.querySelectorAll("[data-color]").forEach((b) => b.addEventListener("click", () => {
      st.colorBy = b.dataset.color;
      document.querySelectorAll("[data-color]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      paintRegion(); renderLegend();
    }));
    $("#btn-zips").addEventListener("click", (e) => {
      st.showZips = !st.showZips;
      e.currentTarget.setAttribute("aria-pressed", String(st.showZips));
      L.rzips.attr("display", st.showZips ? null : "none");
      paintRegion(); renderLegend();
    });
    $("#btn-us").addEventListener("click", goUS);
    const s = $("#search");
    s.addEventListener("input", debounce((e) => runSearch(e.target.value), 120));
    s.addEventListener("keydown", (e) => { if (e.key === "Escape") { $("#search-results").hidden = true; s.blur(); } });
    document.addEventListener("click", (e) => { if (!e.target.closest(".search")) $("#search-results").hidden = true; });
    let lastW = 0;
    window.addEventListener("resize", debounce(() => {
      const { w } = scopeSize();
      if (Math.abs(w - lastW) < 2) return;
      lastW = w;
      fitProjection();
      drawUS(); drawPins();
      if (st.region) { const r = st.region; clearRegion(); openPin(r, { instant: true, keepTab: true }); } else zoomHome(0);
    }, 200));
    document.body.classList.add("m-places");
  }

  // ------------------------------------------------------------------ public API
  return {
    async start(us) {
      usStates = us.states.map((f) => decodeFeature(f, us.q));
      usCounties = us.counties.map((f) => decodeFeature(f, us.q));
      wireChrome();
      fitProjection();
      st.ready = true;
    },
    // Replace everything shown: settings, pins and notes, from a store or the wizard.
    show({ settings, pins, towns }) {
      if (settings) M.settings = settings;
      st.pins = (pins || []).slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
      st.towns = new Map(Object.entries(towns || {}));
      M.compute();
      makeScales();
      drawUS();
      drawPins();
      renderWeights();
      renderLegend();
      renderPlaces();
      if (st.region) { const r = st.region; clearRegion(); openPin(r, { instant: true, keepTab: true }); }
      else { renderReadout(); hudUS(); }
      setSync(st.store.label, st.store.kind === "local");
    },
    setStore(store) { st.store = store; setSync(store.label, store.kind === "local"); },
    get store() { return st.store; },
    setSync,
    goUS,
  };
}
