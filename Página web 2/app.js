"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const HOME = Cesium.Cartesian3.fromDegrees(-100, 15, 20000000);
let VARS = [], varId = "t2m", pick = null, marker = null, chart = null, last = null, explored = false;

// ---------- Globe (no Cesium Ion: imagery from NASA GIBS, stars from the built-in skybox) ----------
const viewer = new Cesium.Viewer("cesiumContainer", {
  baseLayer: false, baseLayerPicker: false, geocoder: false, homeButton: false, sceneModePicker: false,
  navigationHelpButton: false, animation: false, timeline: false, fullscreenButton: false,
  infoBox: false, selectionIndicator: false,
});
const scene = viewer.scene;
scene.globe.enableLighting = true;            // day/night terminator from the Sun position
scene.globe.showGroundAtmosphere = true;
scene.skyAtmosphere.show = true;
scene.highDynamicRange = false;
scene.globe.maximumScreenSpaceError = 1.5;
scene.globe.nightFadeOutDistance = 5e7;
viewer.clock.currentTime = Cesium.JulianDate.now();   // lighting follows the real current time
viewer.clock.shouldAnimate = true;
viewer.camera.setView({ destination: HOME });
viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

viewer.imageryLayers.addImageryProvider(new Cesium.WebMapTileServiceImageryProvider({
  url: "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{TileMatrix}/{TileRow}/{TileCol}.jpeg",
  layer: "BlueMarble_ShadedRelief_Bathymetry", style: "default", format: "image/jpeg",
  tileMatrixSetID: "GoogleMapsCompatible_Level8", maximumLevel: 8, tileWidth: 256, tileHeight: 256,
  tilingScheme: new Cesium.WebMercatorTilingScheme(), credit: "NASA GIBS (visual context only, not used for statistics)",
}));

// slow idle spin until the user starts exploring
const spin = () => { if (!explored) viewer.camera.rotate(Cesium.Cartesian3.UNIT_Z, -0.0006); };
viewer.clock.onTick.addEventListener(spin);

function enter() {
  if (explored) return;
  explored = true;
  $("intro").classList.add("gone");
  $("panel").hidden = false; $("panel").classList.add("show"); $("map-tools").hidden = false;
  viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(-100, 20, 14000000), duration: 2 });
}
$("explore").onclick = enter;
$("zin").onclick = () => viewer.camera.zoomIn(viewer.camera.positionCartographic.height * 0.4);
$("zout").onclick = () => viewer.camera.zoomOut(viewer.camera.positionCartographic.height * 0.6);
$("reset").onclick = () => viewer.camera.flyTo({ destination: HOME, duration: 1.5 });

new Cesium.ScreenSpaceEventHandler(scene.canvas).setInputAction((c) => {
  const cart = viewer.camera.pickEllipsoid(c.position, scene.globe.ellipsoid);
  if (!cart) return;
  enter();
  const g = Cesium.Cartographic.fromCartesian(cart);
  setPick(Cesium.Math.toDegrees(g.latitude), Cesium.Math.toDegrees(g.longitude));
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

function setPick(lat, lon, fly) {
  pick = { lat, lon };
  if (marker) viewer.entities.remove(marker);
  marker = viewer.entities.add({
    position: Cesium.Cartesian3.fromDegrees(lon, lat),
    point: { pixelSize: 11, color: Cesium.Color.WHITE, outlineColor: Cesium.Color.fromCssColorString("#4fd1ff"), outlineWidth: 3 },
  });
  if (fly) viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(lon, lat, 3000000), duration: 2 });
  run();
}

// ---------- Place search (OpenStreetMap Nominatim) ----------
$("search").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("q").value.trim(); if (!q) return;
  try {
    const r = await (await fetch("https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" + encodeURIComponent(q))).json();
    if (!r.length) { $("out").innerHTML = `<p class="err">No place found for "${esc(q)}". Try a different name.</p>`; return; }
    setPick(parseFloat(r[0].lat), parseFloat(r[0].lon), true);
  } catch { $("out").innerHTML = `<p class="err">Place search is unavailable. Click the globe instead.</p>`; }
};

// ---------- Variables ----------
const cur = () => VARS.find((v) => v.id === varId);
fetch("/api/variables").then((r) => r.json()).then((l) => { VARS = l; drawVars(); });
function drawVars() {
  $("vars").innerHTML = VARS.map((v) => `
    <button class="var" role="radio" aria-checked="${v.id === varId}" data-id="${v.id}" title="${esc(v.explain)} ${esc(v.meaning)}">
      <b>${esc(v.name)}</b><small>${esc(v.unit)} · since ${v.start} · ${esc(v.source)}</small></button>`).join("");
  $("vars").querySelectorAll(".var").forEach((b) => (b.onclick = () => { varId = b.dataset.id; drawVars(); if (pick) run(); }));
}
$("run").onclick = () => pick ? run() : ($("out").innerHTML = `<p class="note">Select a location first: click the globe or search for a place.</p>`);

// ---------- Demos (real data; text describes the question, results come from the live analysis) ----------
const DEMOS = [
  { t: "Is the Arctic warming?", why: "The Arctic is a sensitive region for climate change.", v: "t2m", lat: 78, lon: 15, a: 1985, b: 2026 },
  { t: "Ocean temperature in the eastern tropical Pacific", why: "Sea temperature shapes El Niño and marine ecosystems.", v: "sst", lat: 0, lon: -120, a: 1985, b: 2026 },
  { t: "Rainfall over the Amazon", why: "Amazon rainfall supports one of Earth's largest forests.", v: "precip", lat: -3.1, lon: -60, a: 1985, b: 2026 },
];
$("demo-list").innerHTML = DEMOS.map((d, i) => `<button class="demo" data-i="${i}">${esc(d.t)}<small>${esc(d.why)}</small></button>`).join("");
$("demo-list").querySelectorAll(".demo").forEach((b) => (b.onclick = () => {
  const d = DEMOS[+b.dataset.i];
  varId = d.v; $("y0").value = d.a; $("y1").value = d.b; drawVars(); setPick(d.lat, d.lon, true);
}));

// ---------- Analysis ----------
async function run() {
  const v = cur(); if (!v || !pick) return;
  $("out").innerHTML = `<p class="note">Retrieving ${esc(v.name)} observations for ${pick.lat.toFixed(2)}°, ${pick.lon.toFixed(2)}° …</p>`;
  const qs = new URLSearchParams({ var: v.id, lat: pick.lat, lon: pick.lon, start: $("y0").value, end: $("y1").value });
  try {
    const r = await fetch("/api/series?" + qs);
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "Request failed.");
    last = d; render();
  } catch (e) {
    $("out").innerHTML = `<p class="err">${esc(e.message)}</p><p class="note">No substitute data are shown. Try another location or period.</p>`;
  }
}

const sg = (x, n = 2) => (x > 0 ? "+" : "") + x.toFixed(n);
const fp = (p) => (p == null ? "n/a" : p < 0.001 ? "< 0.001" : p.toFixed(3));

function render() {
  const d = last, s = d.stats, v = d.variable, u = esc(v.unit);
  const up = s.direction === "increasing";
  const verdict = s.significant
    ? `${esc(v.name)} shows a statistically significant ${s.direction} trend here.`
    : `The evidence is insufficient to establish a statistically significant trend. This does not prove that nothing is changing.`;
  $("out").innerHTML = `
    <p class="verdict ${up ? "up" : "down"}">${verdict}</p>
    <span class="badge ${s.significant ? "sig" : ""}">${s.significant ? "Significant at 0.05" : "Not significant at 0.05"}</span>
    ${d.notes.map((n) => `<p class="note">${esc(n)}</p>`).join("")}
    <p class="note"><b>Observed:</b> ${s.n_months} monthly values, ${s.first[0]}-${String(s.first[1]).padStart(2, "0")} to ${s.last[0]}-${String(s.last[1]).padStart(2, "0")}.
      Data type: ${esc(v.kind)}.</p>
    <label class="note">View <select id="view">
      <option value="anom">Seasonal anomalies + trends</option><option value="raw">Original monthly series</option>
      <option value="ann">Annual mean anomalies</option></select></label>
    <div class="chart-box"><canvas id="chart" aria-label="Time series chart" role="img"></canvas></div>
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
    <p class="sources"><b>Source:</b> ${esc(v.source)} · ${esc(v.dataset)} · ${esc(v.resolution)}.<br><b>Limits:</b> ${esc(v.limits)}</p>`;
  $("view").onchange = draw; draw();
}

function draw() {
  const d = last, v = d.variable, mode = $("view").value;
  const pts = (t, y) => t.map((x, i) => ({ x, y: y[i] }));
  const line = (label, data, color, w = 2) => ({ type: "line", label, data: data.map(([x, y]) => ({ x, y })), borderColor: color, borderWidth: w, pointRadius: 0 });
  let ds;
  if (mode === "raw") ds = [{ type: "scatter", label: "Monthly values", data: pts(d.t, d.values), backgroundColor: "#4fd1ff", pointRadius: 1.5 }];
  else if (mode === "ann") ds = [{ type: "scatter", label: "Annual mean anomaly", data: d.annual.map(([x, y]) => ({ x, y })), backgroundColor: "#6ee7a8", pointRadius: 4 }, line("Sen trend", d.trend_sen, "#ff9a4d", 3)];
  else ds = [{ type: "scatter", label: "Monthly anomaly", data: pts(d.t, d.anomalies), backgroundColor: "rgba(200,220,255,.6)", pointRadius: 1.5 }, line("Linear trend", d.trend_ols, "#4fd1ff", 2), line("Sen's slope", d.trend_sen, "#ff9a4d", 3)];
  if (chart) chart.destroy();
  const tick = { color: "#9fb0d4" }, grid = { color: "rgba(120,170,255,.12)" };
  chart = new Chart($("chart"), {
    data: { datasets: ds },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        x: { type: "linear", ticks: { ...tick, callback: (x) => Math.round(x) }, grid, title: { display: true, text: "Year", color: "#9fb0d4" } },
        y: { ticks: tick, grid, title: { display: true, text: (mode === "raw" ? "" : "Anomaly, ") + v.unit, color: "#9fb0d4" } },
      },
      plugins: {
        legend: { labels: { color: "#e9f0ff" } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y.toFixed(3)} ${v.unit} (${c.parsed.x.toFixed(2)})` } },
      },
    },
  });
}