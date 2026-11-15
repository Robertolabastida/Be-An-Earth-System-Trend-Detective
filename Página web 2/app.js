"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const C = Cesium.Color;
const HOME = Cesium.Cartesian3.fromDegrees(-100, 15, 20000000);
let VARS = [], pick = null, marker = null;
let flying = false, busy = false;

// ---------- Globe ----------
// No Cesium Ion needed: Blue Marble + Black Marble from NASA GIBS, high-resolution Esri imagery when zoomed in.
const viewer = new Cesium.Viewer("cesiumContainer", {
  baseLayer: false, baseLayerPicker: false, geocoder: false, homeButton: false, sceneModePicker: false,
  navigationHelpButton: false, animation: false, timeline: false, fullscreenButton: false,
  infoBox: false, selectionIndicator: false, msaaSamples: 4,
});
const scene = viewer.scene;
viewer.resolutionScale = Math.min(window.devicePixelRatio || 1, 2);   // sharp on retina screens
scene.globe.enableLighting = true;
scene.globe.showGroundAtmosphere = true;
scene.globe.dynamicAtmosphereLighting = true;
scene.globe.maximumScreenSpaceError = 1.1;    // finer tiles (default 2)
scene.globe.tileCacheSize = 400;
scene.globe.baseColor = C.fromCssColorString("#05070f");
scene.skyAtmosphere.show = true;
scene.highDynamicRange = false;
scene.fxaa = true;
viewer.clock.currentTime = Cesium.JulianDate.now();
viewer.clock.shouldAnimate = true;
viewer.camera.setView({ destination: HOME });
viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

function gibs(layer, matrix, ext, date) {
  return new Cesium.WebMapTileServiceImageryProvider({
    url: `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${layer}/default/${date ? date + "/" : ""}${matrix}/{TileMatrix}/{TileRow}/{TileCol}.${ext}`,
    layer, style: "default", format: ext === "png" ? "image/png" : "image/jpeg",
    tileMatrixSetID: matrix, maximumLevel: parseInt(matrix.slice(-1)), tileWidth: 256, tileHeight: 256,
    tilingScheme: new Cesium.WebMercatorTilingScheme(), credit: "NASA GIBS (visual context only, not used for statistics)",
  });
}
const L = viewer.imageryLayers;
const blue = L.addImageryProvider(gibs("BlueMarble_ShadedRelief_Bathymetry", "GoogleMapsCompatible_Level8", "jpeg"));
blue.nightAlpha = 0.12;
const lights = L.addImageryProvider(gibs("VIIRS_Black_Marble", "GoogleMapsCompatible_Level8", "png", "2016-01-01"));
lights.dayAlpha = 0; lights.nightAlpha = 1;          // city lights only on the night side
const detail = L.addImageryProvider(new Cesium.UrlTemplateImageryProvider({
  url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  maximumLevel: 18, credit: "Imagery © Esri, Maxar, Earthstar Geographics (visual context only)",
}));
detail.alpha = 0;                                     // fades in as the camera approaches

// ---------- Constant rotation + level-of-detail blending ----------
window.addEventListener("pointerup", () => (busy = false));
scene.canvas.addEventListener("pointerdown", () => (busy = true));
viewer.clock.onTick.addEventListener(() => {
  const h = viewer.camera.positionCartographic.height;
  if (!pick && !flying && !busy && h > 9e6) viewer.camera.rotate(Cesium.Cartesian3.UNIT_Z, -0.0004);
  detail.alpha = Cesium.Math.clamp((8e6 - h) / 5e6, 0, 1);   // 0 above 8,000 km, 1 below 3,000 km
});

function fly(opts) {
  flying = true;
  const done = () => (flying = false);
  viewer.camera.flyTo({ duration: 2, ...opts, complete: done, cancel: done });
}

// ---------- Map tools (right) ----------
$("zin").onclick = () => viewer.camera.zoomIn(viewer.camera.positionCartographic.height * 0.4);
$("zout").onclick = () => viewer.camera.zoomOut(viewer.camera.positionCartographic.height * 0.6);
$("reset").onclick = () => fly({ destination: HOME, duration: 1.5 });

// ---------- Click on the globe ----------
new Cesium.ScreenSpaceEventHandler(scene.canvas).setInputAction((c) => {
  const cart = viewer.camera.pickEllipsoid(c.position, scene.globe.ellipsoid);
  if (!cart) return;
  const g = Cesium.Cartographic.fromCartesian(cart);
  setPick(Cesium.Math.toDegrees(g.latitude), Cesium.Math.toDegrees(g.longitude));
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

function status(t) { const el = $("status"); el.textContent = t || ""; el.style.display = t ? "block" : "none"; }

// ---------- Selection ----------
let SEL = new Set(), RES = {}, CH = {}, PARAMS = null, gen = 0, flashTimer = null;

function flash(t) { status(t); clearTimeout(flashTimer); flashTimer = setTimeout(() => status(""), 4500); }

// Closing the panel only hides it: the marker and the zoom stay where they are.
function showPanel() { const p = $("panel"); if (p.hidden) { p.hidden = false; p.classList.add("show"); } $("reopen").hidden = true; }
function hidePanel() { $("panel").hidden = true; $("panel").classList.remove("show"); $("reopen").hidden = !pick; }
$("close").onclick = hidePanel;
$("reopen").onclick = showPanel;

// Removing the place name from the search box removes the selection and goes back to the global view.
function clearSelection() {
  const had = !!pick;
  pick = null; PARAMS = null; gen++; RES = {};
  if (marker) { viewer.entities.remove(marker); marker = null; }
  Object.values(CH).forEach((c) => c.destroy()); CH = {};
  $("results").innerHTML = ""; $("sel").textContent = "";
  hidePanel();
  if (had) fly({ destination: HOME, duration: 1.5 });      // the globe resumes rotating
}
$("q").addEventListener("input", () => { if (!$("q").value.trim()) clearSelection(); });

function setPick(lat, lon, o = {}) {
  pick = { lat, lon };
  const label = o.name || `${lat.toFixed(2)}°, ${lon.toFixed(2)}°`;
  $("sel").textContent = label; $("q").value = label;
  if (marker) viewer.entities.remove(marker);
  marker = viewer.entities.add({
    position: Cesium.Cartesian3.fromDegrees(lon, lat),
    point: { pixelSize: 11, color: C.WHITE, outlineColor: C.fromCssColorString("#5DADE2"), outlineWidth: 3, disableDepthTestDistance: Number.POSITIVE_INFINITY },
  });
  if (o.fly) fly({ destination: Cesium.Cartesian3.fromDegrees(lon, lat, 3000000) });
  showPanel();
  if (!o.name) nameFromCoords(lat, lon);
  run();
}

// Clicking the globe: try to show the state/country name instead of raw coordinates.
async function nameFromCoords(lat, lon) {
  try {
    const r = await (await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&zoom=5&lat=${lat}&lon=${lon}`)).json();
    if (!pick || pick.lat !== lat || pick.lon !== lon || !r.address) return;
    const a = r.address, name = [a.state || a.region || a.county, a.country].filter(Boolean).join(", ");
    if (name) { $("sel").textContent = name; $("q").value = name; }
  } catch { /* keep the coordinates */ }
}

// ---------- Place search (OpenStreetMap Nominatim) ----------
$("search").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("q").value.trim(); if (!q) return;
  status("Searching…");
  try {
    const r = await (await fetch("https://nominatim.openstreetmap.org/search?format=json&limit=1&addressdetails=1&q=" + encodeURIComponent(q))).json();
    if (!r.length) { flash(`No place found for "${q}". Try a different name.`); return; }
    status("");
    const p = r[0], lat = parseFloat(p.lat), lon = parseFloat(p.lon);
    const name = [p.name || p.display_name.split(",")[0], p.address && p.address.country].filter((x, i, a) => x && a.indexOf(x) === i).join(", ");
    setPick(lat, lon, { name });
    const [s, n, w, ea] = p.boundingbox.map(Number);
    const span = Math.max(n - s, 0.05, (ea - w) * 0.5);
    fly({ destination: span < 0.2 ? Cesium.Cartesian3.fromDegrees(lon, lat, 60000) : Cesium.Rectangle.fromDegrees(w, s, ea, n) });
  } catch { flash("Place search is unavailable. Click the globe instead."); }
};

// ---------- Variables, divided into sections the user can pick from ----------
const groupOf = (v) => (v.ocean_only ? "Ocean" : "Atmosphere");
const GROUP_NOTE = { Atmosphere: "Air temperature and rainfall at the marked point.", Ocean: "Sea surface conditions. Only works over ocean points." };
fetch("/api/variables").then((r) => r.json()).then((l) => { VARS = l; drawVars(); });

function drawVars() {
  const groups = {};
  VARS.forEach((v) => (groups[groupOf(v)] = groups[groupOf(v)] || []).push(v));
  $("vars").innerHTML = Object.entries(groups).map(([g, list]) => `
    <details class="grp" open>
      <summary><b>${esc(g)}</b><span class="count"></span></summary>
      <p class="note">${esc(GROUP_NOTE[g] || "")}</p>
      ${list.map((v) => `<label class="var" title="${esc(v.explain)} ${esc(v.meaning)}"><input type="checkbox" data-id="${esc(v.id)}">
        <span><b>${esc(v.name)}</b><small>${esc(v.unit)} · since ${v.start} · ${esc(v.source)}</small></span></label>`).join("")}
      <button class="mini" type="button"></button>
    </details>`).join("");
  $("vars").querySelectorAll("input").forEach((i) => (i.onchange = () => { i.checked ? SEL.add(i.dataset.id) : SEL.delete(i.dataset.id); syncVars(); refresh(); }));
  $("vars").querySelectorAll(".mini").forEach((b) => (b.onclick = () => {
    const ids = [...b.closest("details").querySelectorAll("input")].map((i) => i.dataset.id);
    const all = ids.every((id) => SEL.has(id));
    ids.forEach((id) => (all ? SEL.delete(id) : SEL.add(id)));
    syncVars(); refresh();
  }));
  syncVars();
}
function syncVars() {
  $("vars").querySelectorAll("input").forEach((i) => (i.checked = SEL.has(i.dataset.id)));
  $("vars").querySelectorAll("details.grp").forEach((d) => {
    const ins = [...d.querySelectorAll("input")], n = ins.filter((i) => i.checked).length;
    d.querySelector(".count").textContent = `${n} of ${ins.length} selected`;
    d.querySelector(".mini").textContent = n === ins.length ? "Clear this section" : "Select the whole section";
  });
}
$("run").onclick = () => (pick ? run() : flash("Select a location first: click the globe or search for a place."));

// ---------- Demos (real data; text describes the question, results come from the live analysis) ----------
const DEMOS = [
  { t: "Is the Arctic warming?", why: "The Arctic is a sensitive region for climate change.", v: "t2m", lat: 78, lon: 15, a: 1985, b: 2026, n: "Arctic (Svalbard)" },
  { t: "Ocean temperature in the eastern tropical Pacific", why: "Sea temperature shapes El Niño and marine ecosystems.", v: "sst", lat: 0, lon: -120, a: 1985, b: 2026, n: "Eastern tropical Pacific" },
  { t: "Rainfall over the Amazon", why: "Amazon rainfall supports one of Earth's largest forests.", v: "precip", lat: -3.1, lon: -60, a: 1985, b: 2026, n: "Amazon basin" },
];
$("demo-list").innerHTML = DEMOS.map((d, i) => `<button class="demo" data-i="${i}">${esc(d.t)}<small>${esc(d.why)}</small></button>`).join("");
$("demo-list").querySelectorAll(".demo").forEach((b) => (b.onclick = () => {
  const d = DEMOS[+b.dataset.i];
  SEL = new Set([d.v]); syncVars();
  $("y0").value = d.a; $("y1").value = d.b;
  setPick(d.lat, d.lon, { name: d.n, fly: true });
}));

// ---------- Analysis: one collapsible card per selected variable ----------
function run() {                       // new place or period: start over with the selected variables
  if (!pick) return;
  PARAMS = new URLSearchParams({ lat: pick.lat, lon: pick.lon, start: $("y0").value, end: $("y1").value });
  gen++; RES = {};
  Object.values(CH).forEach((c) => c.destroy()); CH = {};
  $("results").innerHTML = "";
  refresh();
}

function refresh() {                   // add cards for newly selected variables, drop the deselected ones
  if (!pick || !PARAMS) return;
  const chosen = VARS.filter((v) => SEL.has(v.id));
  $("hint").hidden = chosen.length > 0;
  [...$("results").children].forEach((el) => {
    const id = el.dataset.id;
    if (!SEL.has(id)) { if (CH[id]) { CH[id].destroy(); delete CH[id]; } delete RES[id]; el.remove(); }
  });
  chosen.forEach((v) => {
    let el = $("res-" + v.id);
    if (!el) {
      el = document.createElement("details");
      el.className = "res"; el.id = "res-" + v.id; el.dataset.id = v.id; el.open = true;
      el.innerHTML = `<summary><b>${esc(v.name)}</b><span class="badge" id="badge-${esc(v.id)}"></span></summary><div class="resbody"></div>`;
    }
    $("results").appendChild(el);      // keeps the order of the variable list
    if (!RES[v.id]) load(v, gen);
  });
}

const body = (id, html) => { const el = $("res-" + id); if (el) el.querySelector(".resbody").innerHTML = html; };
const badge = (id, text, cls) => { const el = $("badge-" + id); if (el) { el.textContent = text; el.className = "badge " + cls; } };

async function load(v, g) {
  RES[v.id] = { loading: true };
  badge(v.id, "Loading…", "");
  body(v.id, `<p class="note">Retrieving ${esc(v.name)} observations for ${pick.lat.toFixed(2)}°, ${pick.lon.toFixed(2)}° …</p>`);
  try {
    const qs = new URLSearchParams(PARAMS); qs.set("var", v.id);
    const r = await fetch("/api/series?" + qs);
    const d = await r.json();
    if (g !== gen || !SEL.has(v.id)) return;
    if (!r.ok) throw new Error(d.error || "Request failed.");
    RES[v.id] = d; renderCard(v.id);
  } catch (e) {
    if (g !== gen || !SEL.has(v.id)) return;
    RES[v.id] = { error: e.message };
    badge(v.id, "No data", "err");
    body(v.id, `<p class="err">${esc(e.message)}</p><p class="note">No substitute data are shown. Try another location or period.</p>`);
  }
}

const sg = (x, n = 2) => (x > 0 ? "+" : "") + x.toFixed(n);
const fp = (p) => (p == null ? "n/a" : p < 0.001 ? "< 0.001" : p.toFixed(3));

function renderCard(id) {
  const d = RES[id], s = d.stats, v = d.variable, u = esc(v.unit);
  const up = s.direction === "increasing";
  const verdict = s.significant
    ? `${esc(v.name)} shows a statistically significant ${s.direction} trend here.`
    : `The evidence is insufficient to establish a statistically significant trend. This does not prove that nothing is changing.`;
  badge(id, s.significant ? "Significant" : "Not significant", s.significant ? "sig" : "");
  body(id, `
    <p class="verdict ${up ? "up" : "down"}">${verdict}</p>
    ${d.notes.map((n) => `<p class="note">${esc(n)}</p>`).join("")}
    <p class="note"><b>Observed:</b> ${s.n_months} monthly values, ${s.first[0]}-${String(s.first[1]).padStart(2, "0")} to ${s.last[0]}-${String(s.last[1]).padStart(2, "0")}.
      Data type: ${esc(v.kind)}.</p>
    <label class="note">View <select id="view-${id}">
      <option value="anom">Seasonal anomalies + trends</option><option value="raw">Original monthly series</option>
      <option value="ann">Annual mean anomalies</option></select></label>
    <div class="chart-box"><canvas id="chart-${id}" aria-label="Time series chart" role="img"></canvas></div>
    <h2>Statistical estimates</h2>
    <dl>
      <dt title="Robust estimate: median of all pairwise slopes (Sen, 1968).">Sen's slope per decade</dt><dd>${sg(s.sen_per_decade, 3)} ${u}</dd>
      <dt title="Sen's slope multiplied by the length of the record.">Total change (Sen)</dt><dd>${sg(s.sen_total_change, 2)} ${u}</dd>
      <dt title="Least-squares slope on seasonal anomalies.">Linear slope per decade</dt><dd>${sg(s.ols_slope_per_decade, 3)} ${u}</dd>
      <dt title="95% interval, widened for autocorrelation (AR(1) effective sample size).">95% CI (linear, /decade)</dt><dd>${sg(s.ols_ci_per_decade[0], 3)} to ${sg(s.ols_ci_per_decade[1], 3)}</dd>
      <dt title="Share of anomaly variance explained by a straight line.">R²</dt><dd>${s.r2.toFixed(3)}</dd>
      <dt title="Mann-Kendall test on annual means; annual means reduce autocorrelation. Main significance decision.">p (Mann-Kendall, annual)</dt><dd>${fp(s.annual_mk_p)}</dd>
      <dt title="Hirsch et al. (1982): one test per calendar month. Does not correct for autocorrelation, so it can be too optimistic.">p (seasonal Mann-Kendall)</dt><dd>${fp(s.seasonal_mk_p)}</dd>
      <dt title="Adjusted for lag-1 autocorrelation of residuals.">p (linear, adjusted)</dt><dd>${fp(s.ols_p)}</dd>
      <dt title="How strongly one month's residual predicts the next.">Lag-1 autocorrelation</dt><dd>${s.lag1_autocorr.toFixed(2)}</dd>
    </dl>
    <p class="note"><b>Interpretation:</b> ${esc(v.meaning)} Statistical significance does not by itself imply practical or scientific importance.</p>
    <p class="sources"><b>Source:</b> ${esc(v.source)} · ${esc(v.dataset)} · ${esc(v.resolution)}.<br><b>Limits:</b> ${esc(v.limits)}</p>`);
  $("view-" + id).onchange = () => draw(id);
  draw(id);
}

function draw(id) {
  const d = RES[id], v = d.variable, mode = $("view-" + id).value;
  const pts = (t, y) => t.map((x, i) => ({ x, y: y[i] }));
  const line = (label, data, color, w = 2) => ({ type: "line", label, data: data.map(([x, y]) => ({ x, y })), borderColor: color, borderWidth: w, pointRadius: 0 });
  let ds;
  if (mode === "raw") ds = [{ type: "scatter", label: "Monthly values", data: pts(d.t, d.values), backgroundColor: "#4fd1ff", pointRadius: 1.5 }];
  else if (mode === "ann") ds = [{ type: "scatter", label: "Annual mean anomaly", data: d.annual.map(([x, y]) => ({ x, y })), backgroundColor: "#6ee7a8", pointRadius: 4 }, line("Sen trend", d.trend_sen, "#ff9a4d", 3)];
  else ds = [{ type: "scatter", label: "Monthly anomaly", data: pts(d.t, d.anomalies), backgroundColor: "rgba(200,220,255,.6)", pointRadius: 1.5 }, line("Linear trend", d.trend_ols, "#4fd1ff", 2), line("Sen's slope", d.trend_sen, "#ff9a4d", 3)];
  if (CH[id]) CH[id].destroy();
  const tick = { color: "#c3d3f0" }, grid = { color: "rgba(195,211,240,.16)" };
  CH[id] = new Chart($("chart-" + id), {
    data: { datasets: ds },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        x: { type: "linear", ticks: { ...tick, callback: (x) => Math.round(x) }, grid, title: { display: true, text: "Year", color: "#c3d3f0" } },
        y: { ticks: tick, grid, title: { display: true, text: (mode === "raw" ? "" : "Anomaly, ") + v.unit, color: "#c3d3f0" } },
      },
      plugins: {
        legend: { labels: { color: "#e9f0ff" } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y.toFixed(3)} ${v.unit} (${c.parsed.x.toFixed(2)})` } },
      },
    },
  });
}