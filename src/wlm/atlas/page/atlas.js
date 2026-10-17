/* Wilinski Atlas — the map over the Location Machine's evidence.

   Data: data/core.json (every county and town: factor scores, raw values, rents), geo/us.json
   (national outlines) and geo/<ST>.json (a state's counties, towns and rent-bearing ZIPs,
   fetched when a region in that state is opened). Nothing here invents a number: scores
   are recombined from the engine's factor values by AtlasScore.combine, and every figure
   on screen is a value from core.json with its source named.

   Shared state lives in the `db` capability when the viewer has it:
     settings/joint   {weights: {factor: points}, ceiling, budgetOnly}
     pins/<id>        {label, anchor, radius_mi, kind, order}
     towns/<placeId>  {status, note}
   Without it the page still works, saving to this browser only, and says so. */
(function () {
  "use strict";
  const A = window.AtlasScore;
  const MI_PER_DEG = 69.05;
  const STATUSES = [
    ["want", "Want to visit"], ["visited", "Visited"], ["favorite", "Favorite"], ["ruled-out", "Ruled out"],
  ];
  const STATUS_LABEL = Object.fromEntries(STATUSES);
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const S = {
    core: null, factors: [], weights: [], defaults: [], ceiling: 2000, budgetOnly: true,
    counties: new Map(), places: new Map(), ind: new Map(), rawIdx: { county: new Map(), place: new Map() },
    rankN: 0, countyRankN: 0, challengers: [], pins: [], pinsFromStore: false, towns: new Map(),
    region: null, regionTowns: [], town: null, colorBy: "fit", showZips: false,
    geo: new Map(), k: 1, db: null, storeOk: false, ready: false,
  };

  // ------------------------------------------------------------------ helpers
  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cleanName = (n) => String(n)
    .replace(/ (metropolitan|metro|consolidated|unified) government \(balance\)$/i, "")
    .replace(/ \(balance\)$/, "")
    .replace(/ (city|town|village|borough|CDP|municipality|plantation)$/, "");
  const fitNum = (s) => (s ? Math.round(s.score * 100) : null);
  function miles(lat1, lon1, lat2, lon2) {
    const r = Math.PI / 180, dLat = (lat2 - lat1) * r, dLon = (lon2 - lon1) * r;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dLon / 2) ** 2;
    return 2 * 3958.76 * Math.asin(Math.sqrt(a));
  }
  function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
  const lsGet = (k) => { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } };
  const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private window */ } };
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  // ------------------------------------------------------------------ data
  function rawVal(obj, level, id) {
    const i = S.rawIdx[level].get(id);
    return i === undefined ? null : obj.raw[i];
  }
  function rentOf(p) {
    if (p.rent != null) return { v: p.rent, src: "town", share: p.rentShare };
    const c = S.counties.get(p.county);
    const v = c ? rawVal(c, "county", "cost_rent_median_zori") : null;
    return { v: v, src: v == null ? null : "county" };
  }
  function budgetOf(p) {
    const r = rentOf(p);
    if (r.v == null) return "unk";
    return r.v <= S.ceiling ? "ok" : "over";
  }
  function rentPill(p) {
    const r = rentOf(p), b = budgetOf(p);
    const txt = r.v == null ? "rent n/a" : "$" + Math.round(r.v).toLocaleString("en-US") + (r.src === "county" ? " cty" : "");
    return `<span class="pill ${b}" title="${b === "unk" ? "No Zillow rent for this town or county" : (r.src === "county" ? "County median (no ZIP coverage for this town)" : "Typical market rent, ZIPs covering this town")}">${esc(txt)}</span>`;
  }

  function loadCore(core) {
    S.core = core;
    S.factors = core.factors;
    S.defaults = core.factors.map((f) => f.default_weight);
    S.weights = S.defaults.slice();
    S.ceiling = core.budget.rent_ceiling_usd || 2000;
    core.inds.forEach((d) => S.ind.set(d.id, d));
    core.counties.raw.forEach((id, i) => S.rawIdx.county.set(id, i));
    core.places.raw.forEach((id, i) => S.rawIdx.place.set(id, i));
    for (const r of core.counties.rows) {
      const [id, name, st, lat, lon, pop, f, raw] = r;
      S.counties.set(id, { id, name, st, lat, lon, pop, f, raw, places: [], level: "county" });
    }
    for (const r of core.places.rows) {
      const [id, name, st, county, lat, lon, pop, f, raw, rent, rentShare, home, homeShare] = r;
      const p = { id, name: cleanName(name), full: name, st, county, lat, lon, pop, f, raw, rent, rentShare, home, homeShare, level: "place" };
      S.places.set(id, p);
      const c = S.counties.get(county);
      if (c) c.places.push(p);
    }
  }

  function computeScores() {
    const { eps, minCov } = S.core;
    const home = S.core.home;
    for (const c of S.counties.values()) c.s = A.combine(c.f, S.weights, eps, minCov);
    for (const p of S.places.values()) p.s = A.combine(p.f, S.weights, eps, minCov);
    const ok = (o) => o.s && o.s.ok;
    const towns = [...S.places.values()].filter((p) => ok(p) && p.id !== home.place).sort((a, b) => b.s.score - a.s.score);
    towns.forEach((p, i) => { p.rank = i + 1; });
    S.rankN = towns.length;
    for (const p of S.places.values()) if (!ok(p) || p.id === home.place) p.rank = null;
    const hp = S.places.get(home.place);
    if (hp && ok(hp)) hp.rank = 1 + towns.filter((t) => t.s.score > hp.s.score).length;
    const cs = [...S.counties.values()].filter(ok).sort((a, b) => b.s.score - a.s.score);
    cs.forEach((c, i) => { c.pct = 1 - i / Math.max(1, cs.length - 1); });
    S.countyRankN = cs.length;
    for (const p of S.places.values()) p.pct = p.rank ? 1 - (p.rank - 1) / Math.max(1, S.rankN - 1) : null;

    // Challengers: engine.two_stage in miniature — the best counties that contain a town,
    // each shown through its best town (under the rent cap when that switch is on).
    S.challengers = [];
    for (const c of cs) {
      if (c.id === home.county || !c.places.length) continue;
      const inside = c.places.filter(ok).sort((a, b) => b.s.score - a.s.score);
      const pick = S.budgetOnly ? inside.find((p) => budgetOf(p) !== "over") : inside[0];
      if (!pick) continue;
      S.challengers.push({ county: c, town: pick });
      if (S.challengers.length >= S.core.challengers) break;
    }
  }

  function townsNear(lat, lon, r) {
    const out = [];
    for (const p of S.places.values()) {
      if (Math.abs(p.lat - lat) > r / MI_PER_DEG + 0.1) continue;
      const d = miles(lat, lon, p.lat, p.lon);
      if (d <= r) out.push(Object.assign(p, { _d: d }));
    }
    return out.sort((a, b) => (b.s ? b.s.score : -1) - (a.s ? a.s.score : -1));
  }

  function pinSummary(pin) {
    const a = anchorOf(pin);
    if (!a) return null;
    const ts = townsNear(a.lat, a.lon, pin.radius_mi).filter((p) => p.s && p.s.ok);
    const best = ts[0] || null;
    const bestOk = ts.find((p) => budgetOf(p) === "ok") || null;
    return { anchor: a, towns: ts, best, bestOk, under: ts.filter((p) => budgetOf(p) === "ok").length };
  }
  const anchorOf = (pin) => S.places.get(pin.anchor) || S.counties.get(pin.anchor) || null;

  // ------------------------------------------------------------------ colour
  let fitRamp, rentScale;
  function makeScales() {
    fitRamp = d3.interpolateRgbBasis([css("--fit0"), css("--fit1"), css("--fit2"), css("--fit3"), css("--fit4")]);
    const ok = css("--ok"), over = css("--over");
    rentScale = d3.scaleLinear().domain([S.ceiling * 0.55, S.ceiling * 0.95, S.ceiling * 1.05, S.ceiling * 1.7])
      .range([ok, d3.interpolateRgb(ok, "#d9f2e6")(0.45), d3.interpolateRgb(over, "#ffe1e4")(0.45), over]).clamp(true);
  }
  const fitColor = (pct) => (pct == null ? "#1a2232" : fitRamp(pct));
  function townFill(p) {
    if (S.colorBy === "rent") { const r = rentOf(p).v; return r == null ? "#1a2232" : rentScale(r); }
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
    S.k = e.transform.k;
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
    L.us.selectAll("path").attr("fill", (d) => { const c = S.counties.get(d.id); return fitColor(c ? c.pct : null); });
  }
  function countyTip(d) {
    const c = S.counties.get(d.id);
    if (!c) return "";
    const rent = rawVal(c, "county", "cost_rent_median_zori");
    return `<b>${esc(c.name)}, ${esc(c.st)}</b>fit ${c.s && c.s.ok ? fitNum(c.s) : "—"} · rent ${rent == null ? "n/a" : "$" + Math.round(rent).toLocaleString("en-US")}<br>${c.places.length} town${c.places.length === 1 ? "" : "s"} over 5,000 · click to explore`;
  }

  function project(lat, lon) { return projection([lon, lat]); }

  function drawPins() {
    const items = [];
    const home = S.places.get(S.core.home.place);
    if (home) items.push({ key: "home", kind: "home", lat: home.lat, lon: home.lon, label: "Home · " + home.name, act: () => openPin({ id: "home", label: "Harrisburg (home)", anchor: home.id, radius_mi: 20, kind: "home" }) });
    S.challengers.forEach((c, i) => items.push({
      key: "rv" + c.county.id, kind: "rival", lat: c.town.lat, lon: c.town.lon, label: (i + 1) + " · " + c.town.name,
      act: () => openPin({ id: "rv-" + c.town.id, label: c.town.name + ", " + c.town.st, anchor: c.town.id, radius_mi: 20, kind: "rival" }),
    }));
    S.pins.forEach((p) => { const a = anchorOf(p); if (a) items.push({ key: "pin" + p.id, kind: p.kind === "pick" ? "pick" : "mine", lat: a.lat, lon: a.lon, label: p.label, act: () => openPin(p) }); });
    const { w } = scopeSize();
    for (const it of items) {
      const xy = project(it.lat, it.lon);
      it.x = xy ? xy[0] : null; it.y = xy ? xy[1] : null;
      it.flip = xy != null && xy[0] > w - 130; // label to the left near the east edge
    }
    const g = L.pins.selectAll("g.pin").data(items.filter((d) => d.x != null), (d) => d.key).join((enter) => {
      const e = enter.append("g").attr("class", (d) => "pin " + d.kind).attr("tabindex", 0).attr("role", "button");
      e.append("circle").attr("class", "halo").attr("r", 9);
      e.append("circle").attr("class", "core");
      e.append("text").attr("x", 11).attr("y", 4);
      return e;
    });
    g.attr("class", (d) => "pin " + d.kind + (d.flip ? " flip" : "")).attr("aria-label", (d) => d.label);
    g.select("text").attr("x", (d) => (d.flip ? -11 : 11));
    g.select(".core").attr("r", (d) => (d.kind === "home" ? 4.5 : d.kind === "rival" ? 5 : 6.5))
      .attr("transform", (d) => (d.kind === "home" ? "rotate(45)" : null));
    g.select("text").text((d) => d.label);
    g.on("click", (e, d) => { e.stopPropagation(); d.act(); })
      .on("keydown", (e, d) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); d.act(); } });
    rescale();
  }

  function rescale() {
    const k = S.k;
    L.pins.selectAll("g.pin").attr("transform", (d) => `translate(${d.x},${d.y}) scale(${1 / k})`)
      .select("text").attr("display", (d) => {
        // Zoomed in, the region's own pin would sit on its anchor town's label; the HUD names it.
        if (S.region && d.lat === (anchorOf(S.region) || {}).lat && d.lon === (anchorOf(S.region) || {}).lon) return "none";
        return d.kind === "rival" && k < 2.2 && !S.region ? "none" : null;
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

  function loadState(st) {
    if (!S.geo.has(st)) {
      S.geo.set(st, fetch(`geo/${st}.json`).then((r) => {
        if (!r.ok) throw new Error(`geo/${st}.json: ${r.status}`);
        return r.json();
      }).then((j) => ({
        counties: j.counties.map((f) => decodeFeature(f, j.q)),
        towns: j.towns.map((f) => decodeFeature(f, j.q)),
        zips: j.zips.map((f) => decodeFeature(f, j.q)),
      })).catch((e) => { S.geo.delete(st); throw e; }));
    }
    return S.geo.get(st);
  }

  async function openPin(pin, opts) {
    opts = opts || {};
    const a = anchorOf(pin);
    if (!a) return;
    S.region = pin;
    S.town = null;
    S.regionTowns = townsNear(a.lat, a.lon, pin.radius_mi);
    document.body.classList.add("zoomed");
    $("#scope").classList.add("zoomed");
    $("#btn-us").hidden = false;
    $("#hud-mode").innerHTML = `Region <b>${esc(pin.label)}</b> · radius ${pin.radius_mi} mi · ${S.regionTowns.length} towns`;
    zoomToBox(a.lat, a.lon, pin.radius_mi * 1.08, opts.instant ? 0 : 1300);
    rescale();
    renderReadout();
    renderPlaces();
    if (!opts.keepTab) mobileTab("detail");
    const sts = new Set(S.regionTowns.map((p) => p.st));
    sts.add(a.st);
    const box = [a.lon - (pin.radius_mi * 1.7) / (MI_PER_DEG * Math.cos(a.lat * Math.PI / 180)), a.lat - (pin.radius_mi * 1.7) / MI_PER_DEG,
      a.lon + (pin.radius_mi * 1.7) / (MI_PER_DEG * Math.cos(a.lat * Math.PI / 180)), a.lat + (pin.radius_mi * 1.7) / MI_PER_DEG];
    // Neighbouring states whose counties reach into the box, so a ring on a state line is complete.
    for (const c of S.counties.values()) if (c.lat > box[1] - 0.5 && c.lat < box[3] + 0.5 && c.lon > box[0] - 0.5 && c.lon < box[2] + 0.5) sts.add(c.st);
    let layers;
    try {
      layers = await Promise.all([...sts].map(loadState));
    } catch (e) {
      $("#hud-mode").innerHTML += ` · <b>outlines failed to load</b>`;
      return;
    }
    if (S.region !== pin) return;
    drawRegion(pin, a, box, layers);
  }

  function drawRegion(pin, a, box, layers) {
    const inR = new Set(S.regionTowns.map((p) => p.id));
    const pick = (key) => layers.flatMap((l) => l[key]).filter((f) => intersects(f.bbox, box));
    L.rcounties.selectAll("path").data(pick("counties"), (d) => d.id).join("path").attr("class", "rc").attr("d", path);
    L.rzips.selectAll("path").data(pick("zips").filter((f) => f.r != null), (d) => d.id).join("path").attr("class", "rz").attr("d", path)
      .attr("fill", (d) => rentScale(d.r)).attr("fill-opacity", 0.55);
    L.rzips.attr("display", S.showZips ? null : "none");
    const towns = pick("towns").filter((f) => S.places.has(f.id));
    L.rtowns.selectAll("path").data(towns, (d) => d.id).join("path")
      .attr("d", path)
      .attr("class", (d) => "rt" + (inR.has(d.id) ? "" : " out") + (S.town && S.town.id === d.id ? " sel" : ""))
      .on("mousemove", (e, d) => showTip(e, townTip(S.places.get(d.id))))
      .on("mouseleave", hideTip)
      .on("click", (e, d) => { e.stopPropagation(); selectTown(d.id); });
    paintRegion();
    const circle = d3.geoCircle().center([a.lon, a.lat]).radius(pin.radius_mi / MI_PER_DEG)();
    L.ring.selectAll("path").data([circle]).join("path").attr("class", "ring").attr("d", path);
    drawLabels();
  }
  function paintRegion() {
    L.rtowns.selectAll("path").attr("fill", (d) => townFill(S.places.get(d.id)))
      .attr("fill-opacity", S.showZips ? 0.25 : 0.9);
  }
  function drawLabels() {
    const top = S.regionTowns.filter((p) => p.s && p.s.ok).slice(0, 9);
    const a = S.region ? anchorOf(S.region) : null;
    if (a && a.level === "place" && !top.includes(a)) top.push(a);
    const items = top.map((p) => { const xy = project(p.lat, p.lon); return xy && { p, x: xy[0], y: xy[1], key: p.id }; }).filter(Boolean);
    const g = L.labels.selectAll("g.lbl").data(items, (d) => d.key).join((enter) => {
      const e = enter.append("g").attr("class", "lbl");
      e.append("text").attr("text-anchor", "middle").attr("y", 4);
      return e;
    });
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
    const r = rentOf(p);
    return `<b>${esc(p.name)}, ${esc(p.st)}</b>fit ${p.s && p.s.ok ? fitNum(p.s) : "—"}${p.rank ? " · #" + p.rank.toLocaleString("en-US") : ""} · rent ${r.v == null ? "n/a" : "$" + Math.round(r.v).toLocaleString("en-US")}${r.src === "county" ? " (county)" : ""}<br>pop ${p.pop ? p.pop.toLocaleString("en-US") : "—"}${S.towns.get(p.id) && S.towns.get(p.id).status ? " · " + STATUS_LABEL[S.towns.get(p.id).status] : ""}`;
  }

  function goUS() {
    S.region = null; S.town = null; S.regionTowns = [];
    clearRegion();
    document.body.classList.remove("zoomed");
    $("#scope").classList.remove("zoomed");
    $("#btn-us").hidden = true;
    $("#hud-mode").innerHTML = `Continental US · <b>${S.countyRankN.toLocaleString("en-US")}</b> counties scored`;
    zoomHome(1000);
    renderReadout();
    renderPlaces();
  }

  function openCounty(id) {
    const c = S.counties.get(id);
    if (!c) return;
    const towns = c.places.filter((p) => p.s && p.s.ok).sort((a, b) => b.s.score - a.s.score);
    const anchor = towns[0] || c;
    openPin({ id: "cty-" + id, label: c.name + ", " + c.st, anchor: anchor.id, radius_mi: 20, kind: "temp" });
  }

  function selectTown(id) {
    const p = S.places.get(id);
    if (!p) return;
    S.town = p;
    L.rtowns.selectAll("path").classed("sel", (d) => d.id === id);
    if (!S.region) { openPin({ id: "t-" + id, label: p.name + ", " + p.st, anchor: id, radius_mi: 15, kind: "temp" }).then(() => { S.town = p; L.rtowns.selectAll("path").classed("sel", (d) => d.id === id); renderReadout(); }); return; }
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
    const rent = S.colorBy === "rent" && S.region;
    const stops = d3.range(0, 1.0001, 0.1).map((t) => fitColor(t)).join(",");
    const rstops = d3.range(0, 1.0001, 0.1).map((t) => rentScale(S.ceiling * (0.55 + t * 1.15))).join(",");
    $("#legend").innerHTML = rent || S.showZips && S.region
      ? `<div>Rent vs your $${S.ceiling.toLocaleString("en-US")} cap</div><div class="ramp" style="background:linear-gradient(90deg,${rstops})"></div>
         <div class="ramp-l"><span>$${Math.round(S.ceiling * 0.55).toLocaleString("en-US")}</span><span>cap</span><span>$${Math.round(S.ceiling * 1.7).toLocaleString("en-US")}+</span></div>`
      : `<div>Fit under your weights (national rank)</div><div class="ramp" style="background:linear-gradient(90deg,${stops})"></div>
         <div class="ramp-l"><span>bottom</span><span>median</span><span>top</span></div>
         <div class="legend-keys"><span><i style="background:var(--pick)"></i>your picks</span><span><i style="background:var(--rival)"></i>challengers</span><span><i style="background:var(--home);border-radius:1px"></i>home</span></div>`;
  }

  // ------------------------------------------------------------------ panels
  function scoreChip(o) {
    if (!o || !o.s || !o.s.ok) return `<span class="chip" style="background:#2a3446;color:var(--dim)">—</span>`;
    return `<span class="chip" style="background:${fitColor(o.pct)}">${fitNum(o.s)}</span>`;
  }

  function renderPlaces() {
    const home = S.places.get(S.core.home.place);
    const cards = (list) => list.join("") || "";
    const pinCards = S.pins.map((pin) => {
      const sm = pinSummary(pin);
      if (!sm) return "";
      const b = sm.best;
      const kind = pin.kind === "pick" ? "pick" : "mine";
      return `<button type="button" class="card" data-pin="${esc(pin.id)}" aria-current="${!!(S.region && S.region.id === pin.id)}">
        <span class="dot ${kind}"></span><span class="t">${esc(pin.label)}</span><span class="score num">${b ? fitNum(b.s) : "—"}</span>
        <span class="s">best ${b ? esc(b.name) : "—"} ${b ? rentPill(b) : ""}<br>${sm.under} of ${sm.towns.length} towns under $${S.ceiling.toLocaleString("en-US")}${sm.bestOk && sm.bestOk !== b ? ` · best under cap: ${esc(sm.bestOk.name)} ${fitNum(sm.bestOk.s)}` : ""}</span></button>`;
    });
    const rivals = S.challengers.map((c, i) => `<button type="button" class="card" data-rival="${esc(c.town.id)}" aria-current="${!!(S.region && S.region.anchor === c.town.id)}">
        <span class="dot rival"></span><span class="t">${i + 1}. ${esc(c.town.name)}, ${esc(c.town.st)}</span><span class="score num">${fitNum(c.town.s)}</span>
        <span class="s">${esc(c.county.name)} ${rentPill(c.town)} · #${c.town.rank.toLocaleString("en-US")} of ${S.rankN.toLocaleString("en-US")}</span></button>`);
    const visits = [...S.towns.entries()].filter(([, v]) => v && v.status).map(([id, v]) => ({ p: S.places.get(id), v })).filter((x) => x.p);
    const order = { favorite: 0, want: 1, visited: 2, "ruled-out": 3 };
    visits.sort((a, b) => order[a.v.status] - order[b.v.status] || (b.p.s ? b.p.s.score : 0) - (a.p.s ? a.p.s.score : 0));
    $("#tab-places").innerHTML = `
      <section><h3 class="eyebrow">Your picks <em>${S.pins.length} areas</em></h3>
        <div class="cards">${cards(pinCards) || `<p class="empty">No areas pinned. Search for a town above, or click any county on the map, then pin it.</p>`}</div></section>
      <section><h3 class="eyebrow">Challengers <em>machine picks, live</em></h3>
        <p class="small muted" style="margin-bottom:10px">The best-fitting counties in America under your current weights${S.budgetOnly ? `, each shown through its best town under $${S.ceiling.toLocaleString("en-US")} rent` : ""}. Visit one of these for every two of yours.</p>
        <div class="cards">${cards(rivals) || `<p class="empty">No county clears the coverage floor under these weights.</p>`}</div></section>
      <section><h3 class="eyebrow">Visit list <em>${visits.length} towns</em></h3>
        ${visits.length ? `<table class="towns"><tbody>${visits.map((x) => `<tr data-town="${esc(x.p.id)}"><td>${scoreChip(x.p)}</td><td>${esc(x.p.name)}, ${esc(x.p.st)}<span class="st muted">${esc(STATUS_LABEL[x.v.status])}</span></td><td class="r">${rentPill(x.p)}</td></tr>`).join("")}</tbody></table>`
          : `<p class="empty">Mark towns as Want to visit, Visited, Favorite or Ruled out from the details panel. They collect here.</p>`}</section>
      ${home ? `<section><h3 class="eyebrow">Home baseline</h3><button type="button" class="card" data-home="1"><span class="dot home"></span><span class="t">${esc(home.name)}, ${esc(home.st)}</span><span class="score num">${fitNum(home.s) ?? "—"}</span>
        <span class="s">Where you live now, scored the same way. Anything worth moving to should beat it. ${rentPill(home)}</span></button></section>` : ""}`;
    $("#tab-places").querySelectorAll("[data-pin]").forEach((b) => b.addEventListener("click", () => openPin(S.pins.find((p) => p.id === b.dataset.pin))));
    $("#tab-places").querySelectorAll("[data-rival]").forEach((b) => b.addEventListener("click", () => {
      const t = S.places.get(b.dataset.rival);
      openPin({ id: "rv-" + t.id, label: t.name + ", " + t.st, anchor: t.id, radius_mi: 20, kind: "rival" });
    }));
    $("#tab-places").querySelectorAll("[data-town]").forEach((r) => r.addEventListener("click", () => selectTown(r.dataset.town)));
    const hb = $("#tab-places").querySelector("[data-home]");
    if (hb) hb.addEventListener("click", () => openPin({ id: "home", label: "Harrisburg (home)", anchor: S.core.home.place, radius_mi: 20, kind: "home" }));
  }

  function renderWeights() {
    const total = S.weights.reduce((a, b) => a + b, 0);
    $("#tab-weights").innerHTML = `
      <section><h3 class="eyebrow">Joint weights <em>${S.storeOk ? "shared" : "this browser"}</em></h3>
        <p class="small muted">Set these together. Points are relative: what matters is each factor's share of the total. Every score on the map updates as you move them.</p></section>
      <div class="total"><span>total points</span><b class="num">${total}</b></div>
      <div class="weights">${S.factors.map((f, i) => `
        <div class="w-row${S.weights[i] ? "" : " zero"}">
          <label for="w-${f.id}">${esc(f.label)}</label><output id="o-${f.id}" for="w-${f.id}">${S.weights[i]}<span class="muted"> · ${total ? Math.round(100 * S.weights[i] / total) : 0}%</span></output>
          <input type="range" id="w-${f.id}" min="0" max="30" step="1" value="${S.weights[i]}" data-i="${i}">
          <p>${esc(f.blurb)}</p>
        </div>`).join("")}</div>
      <div class="field"><label for="ceiling" class="eyebrow" style="margin:0">Rent cap, per month</label>
        <input type="number" id="ceiling" min="500" max="10000" step="50" value="${S.ceiling}"></div>
      <label class="check"><input type="checkbox" id="budget-only" ${S.budgetOnly ? "checked" : ""}> Challengers must have a town under the rent cap</label>
      <div class="row-btns"><button type="button" class="btn" id="w-reset">Reset to starting point</button></div>
      <p class="small muted">Starting point (from your answers on 2026-10-15): no kids, so schools start at 0; income is portable, so local jobs start at 0. Climate scores against a placeholder band of 40-62°F winters until you tell us your real one.</p>`;
    $("#tab-weights").querySelectorAll("input[type=range]").forEach((inp) => inp.addEventListener("input", () => {
      S.weights[+inp.dataset.i] = +inp.value;
      const t = S.weights.reduce((a, b) => a + b, 0);
      S.factors.forEach((f, i) => { const o = $("#o-" + f.id); if (o) o.innerHTML = `${S.weights[i]}<span class="muted"> · ${t ? Math.round(100 * S.weights[i] / t) : 0}%</span>`; o && o.parentElement.classList.toggle("zero", !S.weights[i]); });
      $("#tab-weights .total b").textContent = t;
      rescoreSoon();
      saveSettings();
    }));
    $("#ceiling").addEventListener("change", (e) => {
      const v = Math.round(+e.target.value);
      if (v >= 500 && v <= 10000) { S.ceiling = v; makeScales(); rescore(); saveSettings(); }
    });
    $("#budget-only").addEventListener("change", (e) => { S.budgetOnly = e.target.checked; rescore(); saveSettings(); });
    $("#w-reset").addEventListener("click", () => { S.weights = S.defaults.slice(); renderWeights(); rescore(); saveSettings(); });
  }

  function factorBars(p) {
    const total = S.weights.reduce((a, b) => a + b, 0) || 1;
    const order = S.factors.map((f, i) => i).sort((a, b) => S.weights[b] - S.weights[a]);
    return `<div class="bars">${order.map((i) => {
      const v = p.f[i], w = S.weights[i];
      return `<div class="bar-row${w ? "" : " off"}" title="${esc(S.factors[i].blurb)}"><span>${esc(S.factors[i].label)} <span class="muted num small">${Math.round(100 * w / total)}%</span></span>
        <span class="track"><i style="width:${v == null ? 0 : Math.max(2, v * 100)}%;background:${v == null ? "transparent" : fitColor(v)}"></i></span>
        <span class="v">${v == null ? "n/a" : Math.round(v * 100)}</span></div>`;
    }).join("")}</div>`;
  }

  function factsTable(p) {
    const c = S.counties.get(p.county);
    const rows = [];
    S.factors.forEach((f, fi) => {
      const items = [];
      for (const d of S.core.inds) {
        if (d.factor !== f.id) continue;
        let v = rawVal(p, "place", d.id), lvl = "town";
        if (v == null && c) { v = rawVal(c, "county", d.id); lvl = "county"; }
        if (v == null) continue;
        items.push(`<tr><td>${esc(d.label)}<span class="lvl">${lvl}</span></td><td>${esc(A.fmt(v, d.unit))}</td></tr>`);
      }
      if (items.length) rows.push(`<tr class="grp"><td colspan="2">${esc(f.label)}</td></tr>` + items.join(""));
    });
    return `<table class="facts"><tbody>${rows.join("")}</tbody></table>`;
  }

  function sourcesLine(p) {
    const used = new Set(S.core.inds.map((d) => d.source));
    const r = rentOf(p);
    const zm = S.core.zillowMonth;
    const list = [...used].map((id) => S.core.sources[id]).filter(Boolean)
      .map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>`).join(" · ");
    return `<p class="src">Rent: Zillow ZORI ${esc(zm.rent)}, ${r.src === "town" ? `land-weighted over the ZIPs covering ${Math.round((r.share || 0) * 100)}% of the town` : r.src === "county" ? "county median (too little ZIP coverage inside the town)" : "not published here"}. Home value: Zillow ZHVI ${esc(zm.home)}. Everything else: ${list}. Built ${esc(S.core.built)}.</p>`;
  }

  function renderReadout() {
    const box = $("#readout");
    if (S.town) {
      const p = S.town, c = S.counties.get(p.county), r = rentOf(p), b = budgetOf(p), mine = S.towns.get(p.id) || {};
      const gap = r.v == null ? "" : b === "ok" ? `$${Math.round(S.ceiling - r.v).toLocaleString("en-US")} under your cap` : `$${Math.round(r.v - S.ceiling).toLocaleString("en-US")} over your cap`;
      box.innerHTML = `
        <div class="row-btns"><button type="button" class="btn" id="back-region">← ${esc(S.region ? S.region.label : "Back")}</button></div>
        <div class="readout-head"><h2>${esc(p.name)}, ${esc(p.st)}</h2>
          <p class="meta">${esc(c ? c.name : "")} · pop ${p.pop ? p.pop.toLocaleString("en-US") : "—"} · GEOID ${esc(p.id)}${S.region && p._d != null && S.regionTowns.includes(p) ? ` · ${p._d.toFixed(1)} mi from ${esc(cleanName(anchorOf(S.region).name))}` : ""}</p></div>
        <div class="fitbox"><span class="big num" style="color:${p.s && p.s.ok ? fitColor(Math.max(p.pct, 0.35)) : "var(--dim)"}">${p.s && p.s.ok ? fitNum(p.s) : "—"}</span>
          <span class="lab">fit under your weights</span>
          <span class="rank">${p.rank ? `#${p.rank.toLocaleString("en-US")} of ${S.rankN.toLocaleString("en-US")} towns · top ${Math.max(1, Math.round(100 * p.rank / S.rankN))}%` : p.s ? `data covers ${Math.round(p.s.cov * 100)}% of your weight, under the 80% floor` : "not enough data to score"}</span></div>
        <div class="row-btns">${rentPill(p)}${p.home != null ? `<span class="pill unk">home $${Math.round(p.home / 1000).toLocaleString("en-US")}k</span>` : ""}<span class="small muted">${esc(gap)}</span></div>
        <section><h3>Your status</h3><div class="status" role="group" aria-label="Status">${STATUSES.map(([k, l]) => `<button type="button" data-s="${k}" aria-pressed="${mine.status === k}">${l}</button>`).join("")}</div></section>
        <section><h3><label for="note">Notes</label></h3><textarea id="note" placeholder="What you saw, who you met, what to check next time">${esc(mine.note || "")}</textarea><p class="note-saved" id="note-saved"></p></section>
        <section><h3>Why it scores this way</h3>${factorBars(p)}</section>
        <section><h3>The numbers</h3>${factsTable(p)}</section>
        ${sourcesLine(p)}`;
      $("#back-region").addEventListener("click", () => { S.town = null; L.rtowns.selectAll("path").classed("sel", false); renderReadout(); });
      box.querySelectorAll(".status button").forEach((btn) => btn.addEventListener("click", () => {
        const cur = (S.towns.get(p.id) || {}).status;
        saveTown(p.id, { status: cur === btn.dataset.s ? null : btn.dataset.s });
      }));
      const saveNote = debounce((v) => saveTown(p.id, { note: v }), 700);
      $("#note").addEventListener("input", (e) => { $("#note-saved").textContent = "Saving…"; saveNote(e.target.value); });
      return;
    }
    if (S.region) {
      const pin = S.region, a = anchorOf(pin);
      const ts = S.regionTowns;
      const under = ts.filter((p) => budgetOf(p) === "ok").length;
      const isPinned = S.pins.some((p) => p.id === pin.id);
      box.innerHTML = `
        <div class="readout-head"><p class="eyebrow">${pin.kind === "rival" ? "Challenger" : pin.kind === "home" ? "Home baseline" : isPinned ? "Your pick" : "Exploring"}</p>
          <h2>${esc(pin.label)}</h2>
          <p class="meta">${ts.length} towns over 5,000 people within ${pin.radius_mi} mi of ${esc(a.level === "place" ? a.name : a.name)} · ${under} under $${S.ceiling.toLocaleString("en-US")} rent</p></div>
        <div class="field"><label for="radius" class="eyebrow" style="margin:0">Radius <em class="num">${pin.radius_mi} mi</em></label>
          <input type="range" id="radius" min="5" max="60" step="5" value="${pin.radius_mi}" style="accent-color:var(--signal)"></div>
        <div class="row-btns">${isPinned ? `<button type="button" class="btn danger" id="unpin">Remove pin</button>` : `<button type="button" class="btn primary" id="pin">Pin this area</button>`}<button type="button" class="btn" id="to-us">All US</button></div>
        <section><h3>Towns, best fit first</h3>
        ${ts.length ? `<table class="towns"><thead><tr><th>Fit</th><th>Town</th><th style="text-align:right">Rent</th></tr></thead><tbody>
          ${ts.map((p) => { const st = (S.towns.get(p.id) || {}).status; return `<tr data-town="${esc(p.id)}"><td>${scoreChip(p)}</td><td>${esc(p.name)}<span class="st muted">${p._d.toFixed(0)} mi${st ? " · " + esc(STATUS_LABEL[st]) : ""}</span></td><td class="r">${rentPill(p)}</td></tr>`; }).join("")}
        </tbody></table>` : `<p class="empty">No town over 5,000 people inside this radius. Widen it.</p>`}</section>
        <p class="src">Fit 0-100 is the weighted geometric mean of the factor scores (one weak factor drags it down hard). Rent is Zillow's typical market rent, ${esc(S.core.zillowMonth.rent)}.</p>`;
      box.querySelectorAll("[data-town]").forEach((r) => r.addEventListener("click", () => selectTown(r.dataset.town)));
      $("#to-us").addEventListener("click", goUS);
      $("#radius").addEventListener("change", (e) => {
        const r = +e.target.value;
        const next = Object.assign({}, pin, { radius_mi: r });
        if (isPinned) savePin(next);
        openPin(next, { keepTab: true });
      });
      if (isPinned) $("#unpin").addEventListener("click", () => removePin(pin.id));
      else $("#pin").addEventListener("click", () => {
        const id = "p-" + pin.anchor;
        savePin({ id, label: pin.label, anchor: pin.anchor, radius_mi: pin.radius_mi, kind: "mine", order: Date.now() });
        S.region = Object.assign({}, pin, { id, kind: "mine" });
        renderReadout();
      });
      return;
    }
    // Overview: summary before detail.
    const home = S.places.get(S.core.home.place);
    const rows = S.pins.map((pin) => ({ pin, sm: pinSummary(pin) })).filter((x) => x.sm);
    const top = S.challengers[0];
    box.innerHTML = `
      <div class="readout-head"><p class="eyebrow">Overview</p><h2>How your picks stack up</h2>
        <p class="meta">Best town in each area under today's weights, against the rent cap of $${S.ceiling.toLocaleString("en-US")}/mo.</p></div>
      <table class="cmp"><thead><tr><th>Area</th><th class="r">Fit</th><th class="r">Rent</th><th class="r">Under cap</th></tr></thead><tbody>
        ${rows.map(({ pin, sm }) => `<tr data-pin="${esc(pin.id)}" style="cursor:pointer"><td>${esc(pin.label)}<br><span class="muted small">${sm.best ? esc(sm.best.name) : "—"}</span></td><td class="r">${sm.best ? fitNum(sm.best.s) : "—"}</td><td class="r">${sm.best ? rentPill(sm.best) : "—"}</td><td class="r">${sm.under}/${sm.towns.length}</td></tr>`).join("")}
        ${top ? `<tr data-rival="${esc(top.town.id)}" style="cursor:pointer"><td><span style="color:var(--rival)">Top challenger</span><br><span class="muted small">${esc(top.town.name)}, ${esc(top.town.st)}</span></td><td class="r">${fitNum(top.town.s)}</td><td class="r">${rentPill(top.town)}</td><td class="r">—</td></tr>` : ""}
        ${home ? `<tr><td>Home<br><span class="muted small">${esc(home.name)}, ${esc(home.st)}</span></td><td class="r">${fitNum(home.s) ?? "—"}</td><td class="r">${rentPill(home)}</td><td class="r">—</td></tr>` : ""}
      </tbody></table>
      <section><h3>Reading the map</h3>
        <p class="small muted">Every US county is shaded by how well it fits the weights you set together, brightest is best. Amber pins are the areas you picked, violet pins are the machine's challengers, the white diamond is home. Click any pin or county to zoom in; every town inside the ring is outlined and scored, and the details panel shows why.</p></section>
      <section><h3>What the data says so far</h3>
        <p class="small muted">${rows.filter((x) => x.sm.best && budgetOf(x.sm.best) === "over").length} of your ${rows.length} picked areas have a best-fitting town over the rent cap. Use the Rent color and ZIP rents layer when zoomed in to find the pockets that are not.</p></section>`;
    box.querySelectorAll("[data-pin]").forEach((r) => r.addEventListener("click", () => openPin(S.pins.find((p) => p.id === r.dataset.pin))));
    box.querySelectorAll("[data-rival]").forEach((r) => r.addEventListener("click", () => {
      const t = S.places.get(r.dataset.rival);
      openPin({ id: "rv-" + t.id, label: t.name + ", " + t.st, anchor: t.id, radius_mi: 20, kind: "rival" });
    }));
  }

  // ------------------------------------------------------------------ rescoring
  function rescore() {
    computeScores();
    makeScales();
    paintUS();
    drawPins();
    if (S.region) {
      S.regionTowns.sort((a, b) => (b.s ? b.s.score : -1) - (a.s ? a.s.score : -1));
      paintRegion();
      drawLabels();
    }
    renderLegend();
    renderPlaces();
    if (!document.activeElement || !document.activeElement.closest || !document.activeElement.closest("#readout")) renderReadout();
    $("#hud-mode").innerHTML = S.region ? $("#hud-mode").innerHTML : `Continental US · <b>${S.countyRankN.toLocaleString("en-US")}</b> counties scored`;
  }
  let raf = 0;
  function rescoreSoon() { cancelAnimationFrame(raf); raf = requestAnimationFrame(rescore); }

  // ------------------------------------------------------------------ store
  function setSync(text, local) { $("#sync").innerHTML = `<b class="${local ? "local" : ""}">●</b> ${esc(text)}`; }

  const saveSettings = debounce(async () => {
    const body = { weights: Object.fromEntries(S.factors.map((f, i) => [f.id, S.weights[i]])), ceiling: S.ceiling, budgetOnly: S.budgetOnly, updatedAt: new Date().toISOString() };
    if (S.db) {
      try { await S.db.doc("settings/joint").set(body); setSync("Saved for both of you"); } catch (e) { setSync("Could not save weights (" + (e && e.code || "error") + ")", true); }
    } else { lsSet("atlas.settings", body); setSync("Saved on this device only", true); }
  }, 600);

  function applySettings(body) {
    if (!body) return;
    if (body.weights) S.weights = S.factors.map((f, i) => (typeof body.weights[f.id] === "number" ? Math.max(0, Math.min(30, body.weights[f.id])) : S.defaults[i]));
    if (typeof body.ceiling === "number" && body.ceiling >= 500 && body.ceiling <= 10000) S.ceiling = body.ceiling;
    if (typeof body.budgetOnly === "boolean") S.budgetOnly = body.budgetOnly;
  }

  function fallbackPins() {
    return S.core.wishlist.map((w, i) => ({ id: w.id, label: w.label, anchor: w.anchor, radius_mi: w.radius_mi, kind: "pick", order: i }));
  }
  function validPin(d, id) {
    return d && typeof d.anchor === "string" && (S.places.has(d.anchor) || S.counties.has(d.anchor))
      ? { id, label: String(d.label || "").slice(0, 80) || id, anchor: d.anchor, radius_mi: Math.max(5, Math.min(60, +d.radius_mi || 20)), kind: d.kind === "pick" ? "pick" : "mine", order: +d.order || 0 }
      : null;
  }
  async function ensureSeeded() {
    if (S.pinsFromStore || !S.db) return;
    await Promise.all(fallbackPins().map((p) => S.db.doc("pins/" + p.id).set(p)));
    S.pinsFromStore = true;
  }
  async function savePin(pin) {
    if (S.db) {
      try { await ensureSeeded(); await S.db.doc("pins/" + pin.id).set(pin); setSync("Pin saved for both of you"); } catch (e) { setSync("Could not save pin", true); }
    } else {
      S.pins = S.pins.filter((p) => p.id !== pin.id).concat([pin]);
      lsSet("atlas.pins", S.pins);
      drawPins(); renderPlaces();
    }
  }
  async function removePin(id) {
    if (S.db) {
      try { await ensureSeeded(); await S.db.doc("pins/" + id).delete(); } catch (e) { setSync("Could not remove pin", true); }
    } else {
      S.pins = S.pins.filter((p) => p.id !== id);
      lsSet("atlas.pins", S.pins);
      drawPins(); renderPlaces();
    }
    goUS();
  }
  async function saveTown(id, patch) {
    const cur = Object.assign({}, S.towns.get(id) || {}, patch, { updatedAt: new Date().toISOString() });
    if (!cur.status && !cur.note) cur.status = null;
    S.towns.set(id, cur);
    if (S.db) {
      try {
        if (!cur.status && !cur.note) await S.db.doc("towns/" + id).delete();
        else await S.db.doc("towns/" + id).set({ status: cur.status || null, note: String(cur.note || "").slice(0, 4000), updatedAt: cur.updatedAt });
        const ns = $("#note-saved"); if (ns) ns.textContent = "Saved for both of you";
      } catch (e) { const ns = $("#note-saved"); if (ns) ns.textContent = "Not saved: " + (e && e.code || "error"); }
    } else {
      lsSet("atlas.towns", Object.fromEntries(S.towns));
      const ns = $("#note-saved"); if (ns) ns.textContent = "Saved on this device only";
    }
    if (patch.status !== undefined) {
      document.querySelectorAll("#readout .status button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.s === cur.status)));
      renderPlaces();
    }
  }

  async function connectStore() {
    let db = null;
    try { db = window.claude && window.claude.use ? await window.claude.use("db") : null; } catch (e) { db = null; }
    if (!db) {
      applySettings(lsGet("atlas.settings"));
      const pins = lsGet("atlas.pins");
      S.pins = Array.isArray(pins) ? pins.map((p) => validPin(p, p.id)).filter(Boolean) : fallbackPins();
      const towns = lsGet("atlas.towns");
      if (towns && typeof towns === "object") for (const [k, v] of Object.entries(towns)) if (S.places.has(k)) S.towns.set(k, v);
      setSync("Saved on this device only", true);
      return;
    }
    S.db = db; S.storeOk = true;
    S.pins = fallbackPins();
    setSync("Shared with both of you");
    db.doc("settings/joint").onSnapshot((snap) => {
      if (!snap.exists || snap.metadata.hasPendingWrites) return;
      const active = document.activeElement && document.activeElement.closest && document.activeElement.closest("#tab-weights");
      applySettings(snap.data());
      if (!S.ready) return;
      makeScales();
      if (!active) renderWeights();
      rescore();
    }, (e) => setSync("Live sync stopped (" + e.code + ")", true));
    db.collection("pins").onSnapshot((snap) => {
      S.pinsFromStore = !snap.empty;
      S.pins = snap.empty ? fallbackPins() : snap.docs.map((d) => validPin(d.data(), d.id)).filter(Boolean).sort((a, b) => a.order - b.order);
      if (!S.ready) return;
      drawPins(); renderPlaces();
      if (!S.region && !S.town) renderReadout();
    }, (e) => setSync("Live sync stopped (" + e.code + ")", true));
    db.collection("towns").onSnapshot((snap) => {
      S.towns.clear();
      for (const d of snap.docs) if (S.places.has(d.id)) S.towns.set(d.id, d.data());
      if (!S.ready) return;
      renderPlaces();
      const editing = document.activeElement && document.activeElement.id === "note";
      if (S.town && !editing) renderReadout();
    }, (e) => setSync("Live sync stopped (" + e.code + ")", true));
  }

  // ------------------------------------------------------------------ search
  let searchIndex = [];
  function buildSearch() {
    searchIndex = [...S.places.values()].map((p) => ({ id: p.id, kind: "town", label: p.name + ", " + p.st, key: (p.name + " " + p.st).toLowerCase(), pop: p.pop || 0 }))
      .concat([...S.counties.values()].map((c) => ({ id: c.id, kind: "county", label: c.name + ", " + c.st, key: (c.name + " " + c.st).toLowerCase(), pop: c.pop || 0 })));
  }
  function runSearch(q) {
    q = q.trim().toLowerCase();
    const ul = $("#search-results");
    if (q.length < 2) { ul.hidden = true; return; }
    const hits = searchIndex.filter((x) => x.key.includes(q))
      .sort((a, b) => (b.key.startsWith(q) - a.key.startsWith(q)) || b.pop - a.pop).slice(0, 8);
    ul.innerHTML = hits.length ? hits.map((h) => `<li><button type="button" data-id="${esc(h.id)}" data-kind="${h.kind}"><span>${esc(h.label)}</span><small>${h.kind} · ${h.pop.toLocaleString("en-US")}</small></button></li>`).join("")
      : `<li class="muted small" style="padding:8px 10px">No town over 5,000 people or county by that name.</li>`;
    ul.hidden = false;
    ul.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      ul.hidden = true; $("#search").value = "";
      if (b.dataset.kind === "county") openCounty(b.dataset.id);
      else { const p = S.places.get(b.dataset.id); openPin({ id: "t-" + p.id, label: p.name + ", " + p.st, anchor: p.id, radius_mi: 20, kind: "temp" }); }
    }));
  }

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
  function wireChrome() {
    document.querySelectorAll(".mtabs button").forEach((b) => b.addEventListener("click", () => mobileTab(b.dataset.m)));
    document.querySelectorAll(".left .tabs button").forEach((b) => b.addEventListener("click", () => leftTab(b.dataset.tab)));
    document.querySelectorAll("[data-color]").forEach((b) => b.addEventListener("click", () => {
      S.colorBy = b.dataset.color;
      document.querySelectorAll("[data-color]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      paintRegion(); renderLegend();
    }));
    $("#btn-zips").addEventListener("click", (e) => {
      S.showZips = !S.showZips;
      e.currentTarget.setAttribute("aria-pressed", String(S.showZips));
      L.rzips.attr("display", S.showZips ? null : "none");
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
      if (S.region) { const r = S.region; clearRegion(); openPin(r, { instant: true, keepTab: true }); } else zoomHome(0);
    }, 200));
    document.body.classList.add("m-places");
  }

  // ------------------------------------------------------------------ boot
  async function boot() {
    const [core, us] = await Promise.all([
      fetch("data/core.json").then((r) => { if (!r.ok) throw new Error("data/core.json " + r.status); return r.json(); }),
      fetch("geo/us.json").then((r) => { if (!r.ok) throw new Error("geo/us.json " + r.status); return r.json(); }),
    ]);
    loadCore(core);
    usStates = us.states.map((f) => decodeFeature(f, us.q));
    usCounties = us.counties.map((f) => decodeFeature(f, us.q));
    wireChrome();
    await connectStore();
    computeScores();
    makeScales();
    fitProjection();
    drawUS();
    drawPins();
    buildSearch();
    renderWeights();
    renderLegend();
    renderPlaces();
    renderReadout();
    $("#hud-mode").innerHTML = `Continental US · <b>${S.countyRankN.toLocaleString("en-US")}</b> counties scored`;
    S.ready = true;
    $("#loading").hidden = true;
  }
  boot().catch((e) => {
    $("#loading").textContent = "Could not load the map data: " + e.message;
  });
})();
