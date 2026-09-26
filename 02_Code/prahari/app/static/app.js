const $ = (id) => document.getElementById(id);
let me = null;
let map, trackMap, trackLayer, mapLegend;
const tiles = new Map();
let ws;
let camFilter = "";
let booted = false;
const MAX_TILES = 4;

// Latest server state, shared by the overview, tabs and charts.
const state = { health: null, cameras: [], camRows: [], alerts: [], detections: [], gaps: null, watchlist: [] };
const seenAlerts = new Set();

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function icon(name, cls) {
  const px = cls === "lg" ? 22 : 16;
  return "<svg class='ic" + (cls ? " " + cls : "") + "' width='" + px + "' height='" + px + "' fill='none' stroke='currentColor' stroke-width='1.8' aria-hidden='true'><use href='#i-" + name + "'/></svg>";
}

async function api(path, opts = {}) {
  // Marks the request as the web UI, so the server uses the session cookie only.
  const headers = Object.assign({ "X-Prahari-Client": "web" }, opts.headers || {});
  if (opts.json) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
  }
  const res = await fetch(path, Object.assign({ credentials: "include" }, opts, { headers }));
  return res;
}

// Parse a response into {ok, data, error}. Never throws on a non-JSON body.
async function readJson(res) {
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (res.ok) return { ok: true, data };
  let detail = data && data.detail;
  if (Array.isArray(detail)) detail = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  return { ok: false, data, error: (detail || res.statusText || "Request failed") + " (HTTP " + res.status + ")" };
}

function toast(msg, kind) {
  const box = $("toasts");
  if (!box) return;
  const el = document.createElement("div");
  el.className = "toast" + (kind ? " " + kind : "");
  el.setAttribute("role", kind === "err" || kind === "crit" ? "alert" : "status");
  el.innerHTML = icon(kind === "err" || kind === "crit" ? "alert" : "check") + "<span>" + msg + "</span>";
  box.appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 320); }, kind === "crit" ? 6500 : 3800);
}

function loadingHtml(text) {
  return "<div class='loading'><span class='spinner' aria-hidden='true'></span><span>" + esc(text) + "</span></div>";
}

function errorHtml(text) {
  return "<div class='state-box error' role='alert'>" + icon("alert") + "<span>" + esc(text) + "</span></div>";
}

async function withBusy(btn, fn) {
  if (btn) btn.disabled = true;
  try { return await fn(); } finally { if (btn) btn.disabled = false; }
}

// ---------- Session ----------

function showApp() {
  $("login-card").classList.add("hidden");
  $("app").classList.remove("hidden");
  if (me && $("whoami")) $("whoami").textContent = me.username + (me.role ? " · " + me.role : "");
  tickClock();
}

async function login() {
  $("login-err").textContent = "";
  const btn = $("login-btn");
  await withBusy(btn, async () => {
    btn.textContent = "Signing in…";
    let res;
    try {
      res = await api("/api/login", { method: "POST", json: { username: $("user").value, password: $("pass").value } });
    } catch (e) {
      $("login-err").textContent = "Server unreachable. Check that PRAHARI is running.";
      btn.textContent = "Log in";
      return;
    }
    btn.textContent = "Log in";
    if (!res.ok) {
      $("login-err").textContent = "Login failed";
      $("pass").select();
      return;
    }
    me = await res.json();
    showApp();
    await boot();
  });
}

async function logout() {
  const btn = $("logout-btn");
  if (btn) btn.disabled = true;
  try {
    await api("/api/logout", { method: "POST" });
  } catch (e) {
    // Even if the server is unreachable, leave the app: the cookie expires on its own.
  }
  // Back to a clean URL so the next sign-in starts on Operations, not the last tab.
  location.replace("/");
}

async function boot() {
  if (booted) return;
  booted = true;
  initMap();
  await refreshHealth();
  await Promise.all([loadCameras(), loadAlerts(), loadWatchlist(), loadDetections()]);
  await loadTrack();
  await loadGaps();
  connectWs();
  renderOverview();
  setInterval(refreshHealth, 8000);
  setInterval(loadAlerts, 5000);
  setInterval(loadDetections, 15000);
  setInterval(tickClock, 1000);
  const fromHash = (location.hash || "").slice(1);
  if (fromHash && $("panel-" + fromHash)) selectTab(fromHash);
}

function tickClock() {
  const now = new Date();
  const t = now.toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" });
  if ($("clock")) $("clock").textContent = t + " IST";
  const d = now.toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata" });
  document.querySelectorAll(".osd-time").forEach((el) => { el.textContent = d + " " + t; });
}

async function refreshHealth() {
  let data;
  try {
    const res = await fetch("/api/health");
    data = await res.json();
  } catch (e) {
    if ($("health-line")) $("health-line").innerHTML = "<span><i class='led warn'></i>server unreachable</span>";
    return;
  }
  state.health = data;
  const host = data.sentinel_host_configured ? "Sentinel host set" : "sample cameras";
  const wsOk = ws && ws.readyState === 1;
  if ($("health-line")) {
    $("health-line").innerHTML =
      "<span><i class='led " + (data.status === "ok" ? "ok" : "warn") + "'></i>" + esc(data.status) + "</span>" +
      "<span>" + data.cameras + " cameras</span>" +
      "<span>" + data.detections + " detections</span>" +
      "<span>WS " + (wsOk ? "connected" : "polling") + "</span>" +
      "<span>" + esc(host) + "</span>";
  }
  if ($("footer-health")) {
    $("footer-health").textContent = data.cameras + " cameras · " + data.detections + " detections · WS " + (wsOk ? "connected" : "polling");
  }
  if ($("banner") && data.sentinel_host_configured) {
    $("banner").textContent = "sync from cameras.json. Live catalogue cameras have no coordinates.";
  }
  renderOverview();
}

// ---------- Maps ----------

function color(health) {
  if (health === "live") return "#17784a";
  if (health === "degraded") return getComputedStyle(document.documentElement).getPropertyValue("--high").trim();
  if (health === "offline") return "#8a4038";
  return "#6b7280";
}

// OSM tiles, desaturated in CSS so health-coloured pins carry the colour.
function baseLayer(target) {
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: "&copy; OpenStreetMap contributors",
  }).addTo(target);
}

function initMap() {
  if (map) return;
  map = L.map("map", { zoomControl: true }).setView([22.5, 72.0], 7);
  baseLayer(map);
  trackMap = L.map("track-map").setView([22.5, 72.5], 7);
  baseLayer(trackMap);
  mapLegend = L.control({ position: "bottomleft" });
  mapLegend.onAdd = () => {
    const div = L.DomUtil.create("div", "map-legend");
    div.id = "map-legend";
    return div;
  };
  mapLegend.addTo(map);
  map.on("popupopen", (ev) => {
    const btn = ev.popup._contentNode.querySelector("[data-open]");
    if (btn) btn.onclick = () => openTile(btn.getAttribute("data-open"));
  });
}

function healthPill(h) {
  const k = h || "unknown";
  return "<span class='pill " + esc(k) + "'><span class='dot " + esc(k) + "'></span>" + esc(k) + "</span>";
}

function camMatches(c, q) {
  if (!q) return true;
  return [c.camera_id, c.department, c.location, c.codec, c.ownership, c.health].join(" ").toLowerCase().includes(q);
}

async function loadCameras(department) {
  if (department !== undefined) camFilter = department;
  const q = camFilter ? "?department=" + encodeURIComponent(camFilter) : "";
  let res;
  try { res = await api("/api/cameras" + q); } catch (e) { return; }
  if (!res.ok) {
    $("cam-table").innerHTML = "<tbody><tr class='empty-row'><td>Could not load cameras (HTTP " + res.status + ")</td></tr></tbody>";
    return;
  }
  const rows = await res.json();
  if (!camFilter) state.cameras = rows;
  state.camRows = rows;
  if (map._markers) map._markers.forEach((m) => map.removeLayer(m));
  map._markers = [];
  const pinned = [];
  rows.forEach((c) => {
    if (c.lat === 0 && c.lon === 0) return;
    const m = L.circleMarker([c.lat, c.lon], { radius: 8, color: "#ffffff", weight: 2, fillColor: color(c.health), fillOpacity: 0.95 });
    m.bindTooltip(esc(c.camera_id) + " · " + esc(c.location || ""), { direction: "top", offset: [0, -6] });
    m.bindPopup(
      "<div class='pop-id'>" + esc(c.camera_id) + "</div>" +
      "<div class='pop-meta'>" + esc(c.department) + " · " + esc(c.location) +
      "<br>" + esc(c.ownership) + " · " + esc(c.codec) + (c.width ? " · " + esc(c.width) + "×" + esc(c.height) : "") +
      "<br>" + healthPill(c.health) + "</div>" +
      "<button class='primary btn-sm' data-open='" + esc(c.camera_id) + "'>Open</button>"
    );
    m.addTo(map);
    map._markers.push(m);
    pinned.push(c);
  });
  if (pinned.length && !map._fitted) {
    map._fitted = true;
    map.fitBounds(pinned.map((c) => [c.lat, c.lon]), { padding: [40, 40], maxZoom: 9 });
  }
  const counts = { live: 0, degraded: 0, offline: 0, unknown: 0 };
  pinned.forEach((c) => { counts[counts[c.health] === undefined ? "unknown" : c.health] += 1; });
  if ($("map-legend")) {
    $("map-legend").innerHTML = ["live", "degraded", "offline", "unknown"].map((k) =>
      "<div><span class='dot " + k + "'></span>" + k + " <span class='id'>" + counts[k] + "</span></div>").join("") +
      "<div class='hint'>" + pinned.length + " of " + rows.length + " mapped</div>";
  }
  renderCamTable(rows);
  const depts = [...new Set((state.cameras.length ? state.cameras : rows).map((c) => c.department))];
  const perDept = {};
  (state.cameras.length ? state.cameras : rows).forEach((c) => { perDept[c.department] = (perDept[c.department] || 0) + 1; });
  $("filters").innerHTML = ["All"].concat(depts).map((d) => {
    const on = (d === "All" && !camFilter) || d === camFilter ? " on" : "";
    const n = d === "All" ? (state.cameras.length || rows.length) : perDept[d];
    return "<span class='chip" + on + "' role='button' tabindex='0' data-d='" + esc(d) + "'>" + esc(d) + " <span class='n'>" + n + "</span></span>";
  }).join("");
  $("filters").onclick = (e) => {
    const chip = e.target.closest("[data-d]");
    if (chip) loadCameras(chip.getAttribute("data-d") === "All" ? "" : chip.getAttribute("data-d"));
  };
  $("filters").onkeydown = (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.getAttribute("data-d")) { e.preventDefault(); e.target.click(); }
  };
  if ($("count-cameras")) $("count-cameras").textContent = state.cameras.length || rows.length;
  renderOverview();
  renderCharts();
}

function renderCamTable(rows) {
  const q = ($("cam-search") && $("cam-search").value || "").trim().toLowerCase();
  const shown = rows.filter((c) => camMatches(c, q));
  const table = $("cam-table");
  const body = shown.length ? shown.map((c) => {
    const res = c.width ? c.width + "×" + c.height : "";
    return "<tr><td class='id'>" + esc(c.camera_id) + "</td><td>" + esc(c.department) + "</td><td>" + esc(c.location) +
      "</td><td><span class='pill " + (c.ownership === "Gov" ? "navy" : "neutral") + "'>" + esc(c.ownership || "") + "</span></td>" +
      "<td>" + healthPill(c.health) + "</td><td class='id'>" + esc(c.codec) + "</td><td class='id'>" + esc(res) +
      "</td><td class='num'>" + (c.retention_days !== undefined ? esc(c.retention_days) + " d" : "") +
      "</td><td class='num'><button class='btn-sm' data-open='" + esc(c.camera_id) + "'>" + icon("camera") + "Open</button></td></tr>";
  }).join("") : "<tr class='empty-row'><td colspan='9'>No cameras match this filter.</td></tr>";
  table.innerHTML = "<caption>Live catalogue cameras have no coordinates. Open them from this table.</caption>" +
    "<thead><tr><th>id</th><th>dept</th><th>location</th><th>ownership</th><th>health</th><th>codec</th><th>resolution</th><th class='num'>retention</th><th></th></tr></thead><tbody>" +
    body + "</tbody>";
  table.onclick = (e) => {
    const btn = e.target.closest && e.target.closest("[data-open]");
    if (btn) openTile(btn.getAttribute("data-open"), true);
  };
}

// ---------- Video wall ----------

function syncSlots() {
  const wall = $("wall");
  wall.querySelectorAll(".slot").forEach((s) => s.remove());
  for (let i = tiles.size; i < MAX_TILES; i++) {
    const s = document.createElement("div");
    s.className = "slot";
    s.innerHTML = icon("camera") + "<span>SLOT " + (i + 1) + " · NO SIGNAL</span>";
    wall.appendChild(s);
  }
  if ($("wall-count")) {
    $("wall-count").textContent = tiles.size + " / " + MAX_TILES;
    $("wall-count").className = "pill " + (tiles.size ? "live" : "neutral");
  }
}

async function openTile(cameraId, jump) {
  $("tile-err").textContent = "";
  if (jump) selectTab("operations");
  if (tiles.has(cameraId)) {
    tiles.get(cameraId).scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }
  const camRes = await api("/api/cameras/" + encodeURIComponent(cameraId));
  if (!camRes.ok) {
    $("tile-err").textContent = "Camera " + cameraId + " could not be opened (HTTP " + camRes.status + ").";
    return;
  }
  const cam = await camRes.json();
  if (cam.playback && cam.playback.kind === "unavailable") {
    $("tile-empty").textContent = cam.playback.reason || "Drop own_feed.mp4 into 03_Data/recordings";
    return;
  }
  const sess = await api("/api/sessions", { method: "POST", json: { camera_id: cameraId } });
  if (sess.status === 429) {
    $("tile-err").textContent = "Fifth live session rejected. Close a tile first.";
    return;
  }
  const token = cam.playback.token;
  const url = "/api/stream/" + encodeURIComponent(cameraId) + "?token=" + encodeURIComponent(token);
  const wrap = document.createElement("div");
  wrap.className = "tile";
  wrap.innerHTML = "<p><span class='rec'>LIVE</span><span class='tile-name'>" + esc(cameraId) + "</span> <button data-x title='Close tile'>Close</button></p>" +
    "<video controls playsinline muted autoplay></video>" +
    "<span class='osd'>" + esc(cam.location || cam.department || "") + " · <span class='osd-time'></span></span>";
  const video = wrap.querySelector("video");
  if (cam.playback && cam.playback.kind === "hls" && window.Hls && window.Hls.isSupported()) {
    const hls = new window.Hls({ enableWorker: true, startPosition: -1 });
    hls.loadSource(url);
    hls.attachMedia(video);
    hls.on(window.Hls.Events.ERROR, (_e, d) => {
      if (d && d.fatal) $("tile-err").textContent = cameraId + ": stream error (" + (d.details || d.type) + ").";
    });
    wrap._hls = hls;
  } else {
    video.src = url;
  }
  video.onerror = () => { $("tile-err").textContent = cameraId + ": the stream could not be played."; };
  wrap.querySelector("[data-x]").onclick = async () => {
    if (wrap._hls) wrap._hls.destroy();
    await api("/api/sessions/" + encodeURIComponent(cameraId), { method: "DELETE" });
    wrap.remove();
    tiles.delete(cameraId);
    syncSlots();
  };
  const firstSlot = $("wall").querySelector(".slot");
  $("wall").insertBefore(wrap, firstSlot);
  tiles.set(cameraId, wrap);
  $("tile-empty").textContent = "";
  syncSlots();
  tickClock();
}

// ---------- Plates ----------

function normPlate(s) {
  return String(s || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

// Indices where a space belongs when an Indian plate is written out:
// state code | district | series | number.
function plateGroups(p) {
  const m = /^([A-Z]{2})(\d{1,2})([A-Z]{0,3})(\d{1,4})$/.exec(p);
  if (!m) return new Set();
  const cuts = new Set();
  let i = m[1].length; cuts.add(i);
  i += m[2].length; if (m[3]) { cuts.add(i); i += m[3].length; }
  cuts.add(i);
  return cuts;
}

// Render a plate. `diffAgainst` marks characters that differ from the raw OCR,
// so a corrected character is visible rather than silently fixed.
function plateHtml(text, opts = {}) {
  const cls = "plate" + (opts.lg ? " lg" : "") + (opts.variant ? " " + opts.variant : "");
  if (!text) return "<span class='" + cls + " none'><span class='chars'>" + esc(opts.empty || "none") + "</span></span>";
  const raw = opts.raw ? String(text) : normPlate(text);
  const cuts = opts.raw ? new Set() : plateGroups(raw);
  const ref = opts.diffAgainst ? normPlate(opts.diffAgainst) : "";
  const diff = ref && ref.length === raw.length;
  let chars = "";
  for (let i = 0; i < raw.length; i++) {
    if (cuts.has(i) && i > 0) chars += "<span class='gap'></span>";
    const fixed = diff && ref[i] !== raw[i];
    chars += fixed ? "<span class='fix' title='Corrected from " + esc(ref[i]) + "'>" + esc(raw[i]) + "</span>" : esc(raw[i]);
  }
  const ind = opts.variant === "raw" ? "" : "<span class='ind' aria-hidden='true'>IND</span>";
  return "<span class='" + cls + "'" + (opts.title ? " title='" + esc(opts.title) + "'" : "") + ">" + ind + "<span class='chars'>" + chars + "</span></span>";
}

function meterHtml(conf) {
  if (conf === undefined || conf === null || conf === "") return "<span class='muted'>–</span>";
  const v = Math.max(0, Math.min(1, Number(conf)));
  const band = v >= 0.7 ? "" : (v >= 0.35 ? " warn" : " bad");
  return "<span class='meter" + band + "' title='Confidence " + v.toFixed(2) + "'><span class='bar'><i style='width:" + (v * 100).toFixed(0) + "%'></i></span><span class='v'>" + v.toFixed(2) + "</span></span>";
}

function statusPill(status, label) {
  const map = { verified: "ok", low_confidence: "warn", unverified: "warn", no_text: "neutral" };
  const ic = status === "verified" ? icon("check") : (status === "no_text" ? "" : icon("alert"));
  return "<span class='pill " + (map[status] || "neutral") + "'>" + ic + esc(label || status || "-") + "</span>";
}

function sourceLabel(src) {
  if (src === "operator_confirm") return "Operator confirm";
  if (src === "anpr") return "ANPR";
  if (src === "seed") return "Seed record";
  return src || "";
}

// ---------- Track ----------

function fmtTs(ts, withDate) {
  const t = Date.parse(ts);
  if (!t) return esc(ts || "");
  const d = new Date(t);
  const time = d.toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  if (!withDate) return time;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "Asia/Kolkata" }) + " " + time;
}

function spanLabel(a, b) {
  const ms = Date.parse(b) - Date.parse(a);
  if (!(ms >= 0)) return "–";
  const h = Math.floor(ms / 3600000);
  const m = Math.round((ms % 3600000) / 60000);
  if (h >= 48) return Math.round(h / 24) + " days";
  return (h ? h + " h " : "") + m + " min";
}

async function loadTrack(plate) {
  plate = normPlate(plate || $("plate-search").value) || "GJ01AB1234";
  $("plate-search").value = plate;
  $("track-summary").innerHTML = "<div class='ts-item skeleton' style='height:58px'></div>".repeat(4);
  let res;
  try { res = await api("/api/track/" + encodeURIComponent(plate)); } catch (e) { res = null; }
  if (!res || !res.ok) {
    $("track-summary").innerHTML = "";
    $("track-meta").innerHTML = errorHtml("Could not reconstruct " + plate + (res ? " (HTTP " + res.status + ")" : "") + ".");
    return;
  }
  const data = await res.json();
  $("csv-link").href = "/api/track/" + encodeURIComponent(plate) + "/report.csv";
  $("track-meta").textContent = data.count + " points · " + (data.category || "") +
    (data.flags.length ? " · flags: " + data.flags.map((f) => f.note).join("; ") : "");
  const pts = data.points || [];
  const cams = new Set(pts.map((p) => p.camera_id));
  $("track-summary").innerHTML = pts.length ?
    "<div class='ts-item'><span class='label'>Registration</span>" + plateHtml(data.plate || plate) +
      (data.category ? " <span class='pill crit'>" + esc(data.category) + "</span>" : "") + "</div>" +
    "<div class='ts-item'><span class='label'>Sightings</span><span class='value'>" + data.count + "</span> <span class='muted'>at " + cams.size + " cameras</span></div>" +
    "<div class='ts-item'><span class='label'>First seen</span><span class='value'>" + fmtTs(pts[0].ts, true) + "</span><div class='hint'>" + esc(pts[0].location || pts[0].camera_id) + "</div></div>" +
    "<div class='ts-item'><span class='label'>Last seen</span><span class='value'>" + fmtTs(pts[pts.length - 1].ts, true) + "</span><div class='hint'>" + esc(pts[pts.length - 1].location || pts[pts.length - 1].camera_id) + " · span " + spanLabel(pts[0].ts, pts[pts.length - 1].ts) + "</div></div>"
    : "<div class='ts-item' style='grid-column:1/-1'><span class='label'>No sightings</span><span>" + esc(plate) + " has not been detected on any registered camera.</span></div>";
  if (trackLayer) trackMap.removeLayer(trackLayer);
  const located = pts.map((p, i) => ({ p, i })).filter((x) => x.p.lat && x.p.lon);
  const latlngs = located.map((x) => [x.p.lat, x.p.lon]);
  trackLayer = L.layerGroup();
  if (latlngs.length) {
    L.polyline(latlngs, { color: "#14223f", weight: 3, opacity: 0.85, dashArray: "6 6" }).addTo(trackLayer);
    located.forEach((x, k) => {
      const cls = k === 0 ? " first" : (k === located.length - 1 ? " last" : "");
      const pin = L.divIcon({ className: "", html: "<div class='track-pin" + cls + "'>" + (x.i + 1) + "</div>", iconSize: [26, 26], iconAnchor: [13, 13] });
      L.marker([x.p.lat, x.p.lon], { icon: pin })
        .bindPopup("<div class='pop-id'>" + (x.i + 1) + ". " + esc(x.p.location) + "</div><div class='pop-meta'>" + esc(x.p.camera_id) + "<br>" + fmtTs(x.p.ts, true) + "</div>")
        .addTo(trackLayer);
    });
    trackMap.fitBounds(latlngs, { padding: [30, 30] });
  }
  trackLayer.addTo(trackMap);
  $("track-table").innerHTML = "<thead><tr><th>#</th><th>ts</th><th>camera</th><th>location</th></tr></thead><tbody>" +
    (pts.length ? pts.map((p, i) => "<tr><td class='id'>" + (i + 1) + "</td><td class='id' title='" + esc(p.ts) + "'>" + fmtTs(p.ts, true) + "</td><td class='id'>" + esc(p.camera_id) + "</td><td>" + esc(p.location) + "</td></tr>").join("")
      : "<tr class='empty-row'><td colspan='4'>No sightings for this plate.</td></tr>") +
    "</tbody>";
}

// ---------- Alerts ----------

function ageLabel(ts) {
  if (!ts) return "";
  const t = Date.parse(ts);
  if (!t) return "";
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return Math.round(s) + "s";
  if (s < 3600) return Math.round(s / 60) + "m";
  if (s < 86400 * 2) return Math.round(s / 3600) + "h";
  return Math.round(s / 86400) + "d";
}

function alertTitle(a) {
  if (a.entity_type === "intrusion" || a.category === "INTRUSION") return { html: "<strong>INTRUSION @ " + esc(a.camera_id) + "</strong>", text: "INTRUSION @ " + a.camera_id };
  if (a.entity_type === "person") {
    const t = a.entity_id || a.plate || "person";
    return { html: icon("user") + " <strong>" + esc(t) + "</strong>", text: t };
  }
  return { html: plateHtml(a.plate), text: a.plate };
}

async function loadAlerts() {
  let openRes, pendingRes;
  try {
    openRes = await api("/api/alerts?status=open");
    pendingRes = await api("/api/alerts?status=pending_review");
  } catch (e) { return; }
  if (!openRes.ok) return;
  const rows = await openRes.json();
  if (pendingRes.ok) rows.push(...await pendingRes.json());
  const rank = { CRITICAL: 0, HIGH: 1, LOW: 2 };
  rows.sort((a, b) => ((rank[a.priority] ?? 9) - (rank[b.priority] ?? 9)) || (Date.parse(b.ts) - Date.parse(a.ts)));
  const firstLoad = !state.alertsLoaded;
  const fresh = new Set();
  rows.forEach((a) => {
    if (!seenAlerts.has(a.alert_id)) {
      if (!firstLoad) fresh.add(a.alert_id);
      seenAlerts.add(a.alert_id);
    }
  });
  state.alerts = rows;
  state.alertsLoaded = true;
  if (!firstLoad) {
    rows.filter((a) => fresh.has(a.alert_id)).slice(0, 3).forEach((a) => {
      toast("<strong>" + esc(a.priority) + "</strong> · " + esc(alertTitle(a).text) + " at " + esc(a.camera_id) + (a.category ? " · " + esc(a.category) : ""), a.priority === "CRITICAL" ? "crit" : "");
    });
  }
  const crit = rows.filter((a) => a.priority === "CRITICAL").length;
  const pending = rows.filter((a) => a.status === "pending_review").length;
  if ($("count-alerts")) {
    $("count-alerts").textContent = rows.length || "";
    $("count-alerts").className = "count" + (crit ? " crit" : "");
  }
  if ($("alert-summary")) {
    $("alert-summary").innerHTML = rows.length ?
      "<span class='pill crit'>" + crit + " critical</span>" +
      "<span class='pill warn'>" + rows.filter((a) => a.priority === "HIGH").length + " high</span>" +
      (pending ? "<span class='pill neutral'>" + pending + " pending review</span>" : "") +
      "<span class='pill neutral'>" + rows.length + " open</span>" : "<span class='pill ok'>" + icon("check") + "All clear</span>";
  }
  $("alert-empty").style.display = rows.length ? "none" : "flex";
  $("alert-list").innerHTML = rows.length ? "<table class='alert-table'><thead><tr><th>PRI</th><th>entity</th><th>category</th><th>camera</th><th>age</th><th class='num'>count</th><th></th></tr></thead><tbody>" +
    rows.map((a) => {
      const review = a.status === "pending_review" ? "<span class='review'>pending_review</span>" : "";
      const n = Number(a.counter) || 1;
      return "<tr class='alert-row " + esc(a.priority) + (fresh.has(a.alert_id) ? " fresh" : "") + "'><td class='pri'><span class='pri-badge " + esc(a.priority) + "'>" + esc(a.priority) + "</span>" + review +
        "</td><td>" + alertTitle(a).html + "</td><td>" + (a.category ? "<span class='pill " + (a.priority === "CRITICAL" ? "crit" : "neutral") + "'>" + esc(a.category) + "</span>" : "") +
        "</td><td class='id'>" + esc(a.camera_id) + "</td><td class='id' title='" + esc(a.ts) + "'>" + ageLabel(a.ts) +
        "</td><td class='num'><span class='counter" + (n > 1 ? " multi" : "") + "'>×" + esc(a.counter) + "</span></td><td class='num'><button class='btn-sm' data-ack='" + esc(a.alert_id) + "'>" + icon("check") + "Ack</button></td></tr>";
    }).join("") + "</tbody></table>" : "";
  $("alert-list").onclick = async (e) => {
    const btn = e.target.closest && e.target.closest("[data-ack]");
    if (!btn) return;
    const id = btn.getAttribute("data-ack");
    btn.disabled = true;
    const res = await api("/api/alerts/" + id + "/ack", { method: "POST" });
    if (res.ok) toast("Alert acknowledged. Audit row written.");
    else toast("Acknowledge failed (HTTP " + res.status + ")", "err");
    loadAlerts();
  };
  renderOverview();
}

function connectWs() {
  try {
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/alerts");
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "alert") { loadAlerts(); loadDetections(); }
    };
    ws.onopen = refreshHealth;
    ws.onclose = refreshHealth;
  } catch (e) {
    ws = null;
  }
}

// ---------- Detections ----------

async function loadDetections() {
  let res;
  try { res = await api("/api/detections"); } catch (e) { return; }
  if (!res.ok) return;
  const rows = await res.json();
  rows.sort((a, b) => (Date.parse(b.ts) || 0) - (Date.parse(a.ts) || 0));
  state.detections = rows;
  renderDetections();
  renderOverview();
  renderEntityCounts();
}

function detIdent(d) {
  return d.plate || d.face_id || d.object_class || d.entity_id || "";
}

function renderDetections() {
  if (!$("det-table")) return;
  const q = ($("det-search") && $("det-search").value || "").trim().toLowerCase();
  const rows = state.detections.filter((d) => !q ||
    [detIdent(d), d.plate_raw, d.camera_id, sourceLabel(d.source), d.entity_type, d.category].join(" ").toLowerCase().includes(q));
  const shown = rows.slice(0, 150);
  $("det-table").innerHTML = "<thead><tr><th>time</th><th>type</th><th>verified / id</th><th>raw OCR</th><th>source</th><th>camera</th><th>confidence</th><th>crop</th></tr></thead><tbody>" +
    (shown.length ? shown.map((d) => {
      const isPlate = (d.entity_type || "vehicle") === "vehicle" && d.plate;
      const ident = isPlate ? plateHtml(d.plate, { diffAgainst: d.plate_raw }) : "<span class='id'>" + esc(detIdent(d)) + "</span>";
      const crop = d.crop_uri ? "<a href='" + esc(d.crop_uri) + "' target='_blank' rel='noopener'><img class='thumb' loading='lazy' src='" + esc(d.crop_uri) + "' alt='crop'></a>" : "<span class='muted'>–</span>";
      const enhanced = d.is_ai_reconstructed ? " <span class='pill warn' title='AI-reconstructed crop'>AI</span>" : "";
      return "<tr><td class='id' title='" + esc(d.ts) + "'>" + fmtTs(d.ts, true) + "</td><td>" + esc(d.entity_type || "vehicle") +
        "</td><td>" + ident + (d.category ? " <span class='pill crit'>" + esc(d.category) + "</span>" : "") +
        "</td><td class='id muted'>" + esc(d.plate_raw || "") + "</td><td><span class='src'>" + esc(sourceLabel(d.source)) +
        "</span></td><td class='id'>" + esc(d.camera_id) + "</td><td>" + meterHtml(d.confidence) + "</td><td>" + crop + enhanced + "</td></tr>";
    }).join("") : "<tr class='empty-row'><td colspan='8'>" + (q ? "No detections match this filter." : "No detections recorded yet.") + "</td></tr>") +
    "</tbody>" + (rows.length > shown.length ? "<caption>Showing the newest " + shown.length + " of " + rows.length + " detections.</caption>" : "");
}

// ---------- Overview ----------

function kpiHtml(o) {
  return "<div class='kpi " + (o.tone || "") + "'><span class='label'>" + icon(o.icon) + esc(o.label) + "</span>" +
    "<span class='value'>" + o.value + "</span>" + (o.seg || "") + "<span class='foot'>" + o.foot + "</span></div>";
}

function renderOverview() {
  if (!$("kpis") || !state.health) return;
  const cams = state.cameras;
  const h = { live: 0, degraded: 0, offline: 0, unknown: 0 };
  cams.forEach((c) => { h[h[c.health] === undefined ? "unknown" : c.health] += 1; });
  const total = cams.length || state.health.cameras || 0;
  const seg = total ? "<span class='seg' aria-hidden='true'>" + ["live", "degraded", "offline", "unknown"].map((k) =>
    h[k] ? "<i style='width:" + (h[k] / total * 100) + "%;background:" + color(k) + "'></i>" : "").join("") + "</span>" : "";
  const crit = state.alerts.filter((a) => a.priority === "CRITICAL").length;
  const plates = state.detections.filter((d) => d.plate).length;
  const anpr = state.detections.filter((d) => d.source === "anpr").length;
  const gaps = state.gaps;
  const gapN = gaps ? (gaps.offline || []).length + (gaps.missing_coords || []).length + (gaps.private_without_consent || []).length : null;
  $("kpis").innerHTML = [
    kpiHtml({ icon: "camera", label: "Cameras registered", value: total, seg, foot: h.live + " live · " + h.degraded + " degraded · " + h.offline + " offline · " + h.unknown + " unknown" }),
    kpiHtml({ icon: "scan", label: "Detections", value: state.health.detections, foot: plates + " plate reads · " + anpr + " automatic ANPR" }),
    kpiHtml({ icon: "bell", label: "Open alerts", value: state.alerts.length, tone: crit ? "crit" : "good", foot: crit ? crit + " critical awaiting acknowledgement" : "No critical alerts" }),
    kpiHtml({ icon: "list", label: "Watchlist entries", value: state.health.watchlist ?? state.watchlist.length, foot: "VAHAN / eGujCop-style cases" }),
    kpiHtml({ icon: "alert", label: "Coverage gaps", value: gapN === null ? "–" : gapN, tone: gapN ? "warn" : "", foot: gaps ? (gaps.offline || []).length + " offline · " + (gaps.missing_coords || []).length + " unmapped" : "Loading gap report" }),
  ].join("");

  const opsAlerts = state.alerts.slice(0, 4);
  $("ops-alerts").innerHTML = opsAlerts.length ? opsAlerts.map((a) =>
    "<div class='feed-row'><span class='pri-badge " + esc(a.priority) + "'>" + esc(a.priority) + "</span>" +
    "<div><div>" + alertTitle(a).html + "</div><div class='meta'>" + esc(a.category || "") + " · " + esc(a.camera_id) + "</div></div>" +
    "<div class='right'>" + ageLabel(a.ts) + " ago<br><span class='counter" + ((Number(a.counter) || 1) > 1 ? " multi" : "") + "'>×" + esc(a.counter) + "</span></div></div>").join("")
    : "<p class='empty-state'>" + icon("check", "lg") + "<span>No open alerts</span></p>";

  const reads = state.detections.filter((d) => d.plate).slice(0, 5);
  $("ops-reads").innerHTML = reads.length ? reads.map((d) =>
    "<div class='feed-row'>" + plateHtml(d.plate, { diffAgainst: d.plate_raw }) +
    "<div class='meta'>" + esc(sourceLabel(d.source)) + " · " + esc(d.camera_id) + "</div>" +
    "<div class='right'>" + meterHtml(d.confidence) + "<br>" + fmtTs(d.ts, true) + "</div></div>").join("")
    : "<p class='empty-state'>" + icon("scan", "lg") + "<span>No plate reads yet. Run ANPR this still on Onboard.</span></p>";
}

// ---------- Watchlist ----------

async function loadWatchlist() {
  let res;
  try { res = await api("/api/watchlist"); } catch (e) { return; }
  if (!res.ok) return;
  const rows = await res.json();
  state.watchlist = rows;
  $("wl-table").innerHTML = "<thead><tr><th>id</th><th>type</th><th>plate</th><th>name</th><th>gallery</th><th>category</th><th>priority</th><th>source</th></tr></thead><tbody>" +
    (rows.length ? rows.map((w) => "<tr><td class='id'>" + esc(w.source_case_id) + "</td><td>" + (w.entity_type === "person" ? icon("user") : icon("car")) + " " + esc(w.entity_type || "") +
      "</td><td>" + (w.plate ? plateHtml(w.plate) : "") +
      "</td><td>" + esc(w.name || "") + "</td><td class='id'>" + esc(w.gallery_id || "") + "</td><td>" + (w.category ? "<span class='pill " + (w.priority === "CRITICAL" ? "crit" : "neutral") + "'>" + esc(w.category) + "</span>" : "") +
      "</td><td><span class='pri-badge " + esc(w.priority) + "'>" + esc(w.priority) + "</span></td><td class='src'>" + esc(w.source || "") + "</td></tr>").join("")
      : "<tr class='empty-row'><td colspan='8'>Watchlist is empty.</td></tr>") +
    "</tbody>";
}

// ---------- Analytics & gaps ----------

async function loadGaps() {
  let res;
  try { res = await api("/api/gap-report"); } catch (e) { return; }
  if (!res.ok) {
    $("gap-out").textContent = "Gap report unavailable (HTTP " + res.status + ")";
    return;
  }
  const gaps = await res.json();
  state.gaps = gaps;
  $("gap-out").textContent = JSON.stringify(gaps, null, 2);
  const shortRet = (gaps.short_retention || []);
  $("gap-kpis").innerHTML = [
    kpiHtml({ icon: "camera", label: "Cameras in census", value: gaps.total ?? state.cameras.length, foot: Object.keys(gaps.counts_by_department || {}).length + " departments" }),
    kpiHtml({ icon: "alert", label: "Offline", value: (gaps.offline || []).length, tone: (gaps.offline || []).length ? "crit" : "good", foot: (gaps.offline || []).slice(0, 2).join(", ") || "None" }),
    kpiHtml({ icon: "clock", label: "Short retention", value: shortRet.length, tone: shortRet.length ? "warn" : "", foot: "Under 15 days of recording" }),
    kpiHtml({ icon: "pin", label: "No coordinates", value: (gaps.missing_coords || []).length, tone: (gaps.missing_coords || []).length ? "warn" : "", foot: "Not placeable on the map" }),
    kpiHtml({ icon: "shield", label: "Private, no consent", value: (gaps.private_without_consent || []).length, tone: (gaps.private_without_consent || []).length ? "crit" : "good", foot: "Must not be viewed" }),
  ].join("");
  const gapRows = [];
  (gaps.offline || []).forEach((c) => gapRows.push([c, "<span class='pill offline'>offline</span>", "No signal from device"]));
  (gaps.private_without_consent || []).forEach((c) => gapRows.push([typeof c === "string" ? c : c.camera_id, "<span class='pill crit'>no consent</span>", "Private camera without recorded consent"]));
  shortRet.forEach((c) => gapRows.push([c.camera_id, "<span class='pill warn'>retention</span>", c.retention_days ? c.retention_days + " days retained" : "Retention not declared"]));
  (gaps.missing_coords || []).forEach((c) => gapRows.push([c, "<span class='pill neutral'>unmapped</span>", "Missing latitude / longitude"]));
  $("gap-table").innerHTML = "<thead><tr><th>camera</th><th>gap</th><th>detail</th></tr></thead><tbody>" +
    (gapRows.length ? gapRows.map((r) => "<tr><td class='id'>" + esc(r[0]) + "</td><td>" + r[1] + "</td><td>" + esc(r[2]) + "</td></tr>").join("")
      : "<tr class='empty-row'><td colspan='3'>No coverage gaps.</td></tr>") + "</tbody>";
  renderCharts();
  renderEntityCounts();
  renderOverview();
}

function barsHtml(entries, klass) {
  if (!entries.length) return "<p class='empty'>No data yet.</p>";
  const max = Math.max(...entries.map((e) => e[1]), 1);
  return entries.map((e) =>
    "<div class='bar-row' title='" + esc(e[0]) + ": " + e[1] + "'><span class='name'>" + esc(e[0]) + "</span>" +
    "<span class='track'><i class='" + (klass ? klass(e[0]) : "") + "' style='width:" + (e[1] / max * 100).toFixed(1) + "%'></i></span>" +
    "<span class='val'>" + e[1] + "</span></div>").join("");
}

function renderCharts() {
  if (!$("chart-dept")) return;
  const byDept = (state.gaps && state.gaps.counts_by_department) || state.cameras.reduce((acc, c) => { acc[c.department] = (acc[c.department] || 0) + 1; return acc; }, {});
  $("chart-dept").innerHTML = barsHtml(Object.entries(byDept).sort((a, b) => b[1] - a[1]));
  const h = { live: 0, degraded: 0, offline: 0, unknown: 0 };
  state.cameras.forEach((c) => { h[h[c.health] === undefined ? "unknown" : c.health] += 1; });
  $("chart-health").innerHTML = barsHtml(Object.entries(h), (k) => k);
}

function renderEntityCounts() {
  if (!$("entity-counts")) return;
  const counts = {};
  state.detections.forEach((r) => {
    const k = r.entity_type || "vehicle";
    counts[k] = (counts[k] || 0) + 1;
  });
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const body = entries.map(([k, n]) => "<tr><td>" + esc(k) + "</td><td class='num'>" + n + "</td></tr>").join("");
  $("entity-counts").innerHTML = "<div class='bars'>" + barsHtml(entries) + "</div>" +
    "<details><summary>Table view</summary><table><thead><tr><th>entity_type</th><th class='num'>n</th></tr></thead><tbody>" + body + "</tbody></table></details>";
}

// ---------- Recognition results ----------

function mediaHtml(previewUrl, cropUri) {
  const parts = [];
  if (previewUrl) parts.push("<figure><img src='" + previewUrl + "' alt='Submitted still'><figcaption>Submitted still</figcaption></figure>");
  if (cropUri) parts.push("<figure><img src='" + esc(cropUri) + "' alt='Plate crop'><figcaption>Detection crop</figcaption></figure>");
  return parts.length ? "<div class='result-media'>" + parts.join("") + "</div>" : "";
}

function alertBannerHtml(alerts) {
  const list = (alerts || []).filter(Boolean);
  if (!list.length) return "";
  return list.map((a) => "<div class='state-box alert' role='alert'>" + icon("bell") + "<span><strong>Watchlist hit · " + esc(a.priority || "") + "</strong> · " +
    esc(alertTitle(a).text) + (a.category ? " · " + esc(a.category) : "") + " at " + esc(a.camera_id) + ". Alert raised.</span></div>").join("");
}

function renderResult(el, payload, previewUrl) {
  if (!el) return;
  if (payload.gallery_id && payload.n_images !== undefined) {
    el.innerHTML = "<div class='state-box success'>" + icon("check") + "<span>Enrolled " + esc(payload.n_images) + " image(s) into gallery " +
      esc(payload.gallery_id) + ".</span></div><details><summary>raw</summary><pre>" + esc(JSON.stringify(payload, null, 2)) + "</pre></details>";
    return;
  }
  const reading = plateReading(payload);
  const events = payload.events || (payload.event ? [payload.event] : []);
  const alerts = payload.alerts || (payload.alert ? [payload.alert] : []);
  const raw = "<details><summary>raw</summary><pre>" + esc(JSON.stringify(payload, null, 2)) + "</pre></details>";
  const cropUri = (events.find((e) => e.crop_uri) || {}).crop_uri;
  const media = mediaHtml(previewUrl, cropUri);
  if (!events.length) {
    const note = payload.inserted === false ? "No plate accepted." : "No events.";
    const body = "<div class='state-box note'>" + icon("alert") + "<span>" + note +
      (payload.inserted === false && reading ? " The reading below is kept as evidence and was not written as a detection." : "") + "</span></div>" + reading;
    el.innerHTML = (media ? "<div class='result-layout'>" + media + "<div class='reading-card'>" + body + "</div></div>" : body) + raw;
    return;
  }
  const list = "<div class='events'>" + events.map((e) => {
    const src = sourceLabel(e.source);
    const ident = e.plate || e.face_id || e.object_class || e.entity_id || "";
    const kind = e.entity_type === "person" ? "user" : (e.entity_type === "vehicle" || e.plate ? "car" : "grid");
    const title = e.plate ? plateHtml(e.plate, { diffAgainst: e.plate_raw }) : "<span class='id'>" + esc(ident) + "</span>";
    const sub = [esc(e.entity_type || ""), esc(src), e.plate_raw ? "raw OCR <span class='id'>" + esc(e.plate_raw) + "</span>" : "", e.camera_id ? "<span class='id'>" + esc(e.camera_id) + "</span>" : ""].filter(Boolean).join(" · ");
    return "<div class='event'><span class='kind'>" + icon(kind) + "</span><div><div class='ttl'>" + title +
      (e.category ? "<span class='pill crit'>" + esc(e.category) + "</span>" : "") + "</div><div class='sub'>" + sub + "</div></div>" + meterHtml(e.confidence) + "</div>";
  }).join("") + "</div>";
  const summary = "<div class='reading-head'><strong>" + events.length + " event" + (events.length === 1 ? "" : "s") + " recorded</strong>" +
    "<span class='pill ok'>" + icon("check") + "written to detections</span></div>";
  const body = alertBannerHtml(alerts) + (reading || "") + (reading ? "" : summary + list);
  const tail = reading ? "<details><summary>Stored event</summary>" + list + "</details>" : "";
  el.innerHTML = (media ? "<div class='result-layout'>" + media + "<div class='reading-card'>" + body + tail + "</div></div>" : body + tail) + raw;
}

// Show what OCR saw next to what the system accepted. "Nothing found" and
// "found text we rejected" look identical without this, which is how a foreign
// plate reads as an OCR failure.
function plateReading(payload) {
  if (payload.plate_raw === undefined && !payload.validation) return "";
  const raw = payload.plate_raw || "";
  const candidate = payload.plate_candidate || "";
  const accepted = payload.plate || (payload.event && payload.event.plate) || "";
  const conf = payload.confidence;
  const status = payload.status || "";

  // What OCR produced comes first and is always shown. Confidence describes it;
  // it does not decide whether it appears.
  const head = "<div class='reading-head'>" + statusPill(status, payload.status_label || status) +
    "<span class='field' style='flex-direction:row;align-items:center;gap:8px'>OCR confidence " +
    (conf !== undefined && conf !== null ? meterHtml(conf) : "<span class='muted'>–</span>") + "</span></div>";

  const plates = ["<figure><figcaption>Raw OCR</figcaption>" +
    (raw ? plateHtml(raw, { lg: true, variant: "raw", raw: true }) : plateHtml("", { lg: true, empty: "nothing read" })) + "</figure>"];
  if (candidate && candidate !== accepted) {
    plates.push("<span class='step'><span class='arrow' aria-hidden='true'>→</span><figure><figcaption>Reads as · not accepted</figcaption>" +
      plateHtml(candidate, { lg: true, variant: "candidate", diffAgainst: raw }) + "</figure></span>");
  }
  plates.push("<span class='step'><span class='arrow' aria-hidden='true'>→</span><figure><figcaption>Verified plate</figcaption>" +
    (accepted ? plateHtml(accepted, { lg: true, diffAgainst: raw, title: "Verified plate" }) : plateHtml("", { lg: true, empty: "none" })) + "</figure></span>");

  const detail = [];
  if (payload.validation) detail.push("<dt>Detail</dt><dd>" + esc(payload.validation) + "</dd>");
  detail.push("<dt>Status</dt><dd>" + esc(payload.status_label || status || "-") + "</dd>");
  const corrected = payload.plate_corrected ?
    "<div class='state-box note'>" + icon("alert") + "<span>Characters were corrected to fit the plate format. " +
    "Treat as weaker evidence. Corrected characters are underlined.</span></div>" : "";
  return "<div class='reading-card'>" + head + "<div class='plates'>" + plates.join("") + "</div>" +
    "<dl class='reading-detail'>" + detail.join("") + "</dl>" + corrected + "</div>";
}

// ---------- Tabs ----------

function selectTab(name) {
  const btn = document.querySelector(".tab[data-tab='" + name + "']");
  if (!btn) return;
  document.querySelectorAll(".tab").forEach((b) => {
    b.classList.remove("on");
    b.setAttribute("aria-selected", "false");
  });
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("on"));
  btn.classList.add("on");
  btn.setAttribute("aria-selected", "true");
  $("panel-" + name).classList.add("on");
  if (history.replaceState) history.replaceState(null, "", "#" + name);
  if (name === "operations" && map) setTimeout(() => map.invalidateSize(), 100);
  if (name === "track" && trackMap) setTimeout(() => trackMap.invalidateSize(), 100);
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => selectTab(btn.dataset.tab));
});
document.addEventListener("click", (e) => {
  const go = e.target.closest && e.target.closest("[data-goto]");
  if (go) selectTab(go.getAttribute("data-goto"));
});

// ---------- Wiring ----------

$("login-form").onsubmit = (e) => { e.preventDefault(); login(); };
$("logout-btn").onclick = logout;
$("cam-search").oninput = () => renderCamTable(state.camRows);
$("det-search").oninput = renderDetections;
$("track-form").onsubmit = (e) => {
  e.preventDefault();
  withBusy(e.submitter, () => loadTrack($("plate-search").value));
};
if ($("predict-btn")) {
  $("predict-btn").onclick = async () => {
    const plate = normPlate($("plate-search").value) || "GJ01AB1234";
    const out = $("predict-out");
    $("predict-box").open = true;
    out.innerHTML = loadingHtml("Ranking likely next cameras…");
    const r = await readJson(await api("/api/predict/" + encodeURIComponent(plate)));
    if (!r.ok) { out.innerHTML = errorHtml(r.error); return; }
    const preds = (r.data && r.data.predictions) || [];
    out.innerHTML = (preds.length ? preds.map((p) =>
      "<div class='predict-row'><span class='id'>" + esc(p.camera_id) + "</span><span class='hint'>" + esc(p.note || "") + "</span>" + meterHtml(p.probability) + "</div>").join("")
      : "<p class='empty'>No prediction available.</p>") +
      "<p class='hint'>" + esc(r.data.note || "") + (r.data.method ? " Method: " + esc(r.data.method) + "." : "") + "</p>";
  };
}
$("onboard-form").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.consent = fd.get("consent") === "on";
  body.lat = parseFloat(body.lat); body.lon = parseFloat(body.lon);
  await withBusy(e.submitter, async () => {
    const r = await readJson(await api("/api/cameras", { method: "POST", json: body }));
    if (r.ok) toast("Camera " + esc(body.camera_id) + " added to the registry.");
    else toast("Add camera failed: " + esc(r.error), "err");
  });
  loadCameras();
  loadGaps();
};
$("csv-file").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  const r = await readJson(await api("/api/cameras/import", { method: "POST", body: fd }));
  if (r.ok) toast("CSV imported: " + esc(file.name));
  else toast("CSV import failed: " + esc(r.error), "err");
  loadCameras();
  loadGaps();
};

function previewOf(file) {
  try { return URL.createObjectURL(file); } catch (e) { return ""; }
}

async function runAnpr(file) {
  if (!file) return;
  const out = $("anpr-out");
  out.innerHTML = loadingHtml("Reading plate… the first read after start-up loads the models and can take ~20 s.");
  const fd = new FormData();
  fd.append("file", file);
  fd.append("camera_id", $("anpr-cam").value);
  let r;
  try {
    r = await readJson(await api("/api/ingest/frame", { method: "POST", body: fd }));
  } catch (err) {
    out.innerHTML = errorHtml("Server unreachable. The plate was not read.");
    return;
  }
  if (!r.ok) { out.innerHTML = errorHtml("ANPR failed: " + r.error); return; }
  renderResult(out, r.data, previewOf(file));
  if (r.data && r.data.alert) toast("<strong>Watchlist hit</strong> · " + esc(r.data.alert.plate || "") + " · " + esc(r.data.alert.category || ""), "crit");
  loadAlerts();
  loadDetections();
  refreshHealth();
}

async function runAnalyse(file) {
  if (!file) return;
  const out = $("analyse-out");
  out.innerHTML = loadingHtml("Analysing still for plates, objects and permitted faces…");
  const fd = new FormData();
  fd.append("file", file);
  fd.append("camera_id", $("analyse-cam").value);
  fd.append("engines", $("analyse-cam").value.indexOf("cam") === 0 ? "anpr,objects" : "anpr,objects,faces");
  let r;
  try {
    r = await readJson(await api("/api/ingest/analyse", { method: "POST", body: fd }));
  } catch (err) {
    out.innerHTML = errorHtml("Server unreachable. The still was not analysed.");
    return;
  }
  if (!r.ok) { out.innerHTML = errorHtml("Analysis failed: " + r.error); return; }
  renderResult(out, r.data, previewOf(file));
  loadAlerts();
  loadGaps();
  loadDetections();
  refreshHealth();
}

$("anpr-file").onchange = (e) => runAnpr(e.target.files[0]);
$("analyse-file").onchange = (e) => runAnalyse(e.target.files[0]);

// Drag and drop onto the recognition drop zones.
document.querySelectorAll("[data-drop]").forEach((zone) => {
  const input = $(zone.getAttribute("data-drop"));
  ["dragenter", "dragover"].forEach((t) => zone.addEventListener(t, (e) => { e.preventDefault(); zone.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => zone.addEventListener(t, () => zone.classList.remove("over")));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    if (input.id === "anpr-file") runAnpr(file); else runAnalyse(file);
  });
});

$("confirm-form").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await withBusy(e.submitter, async () => {
    const r = await readJson(await api("/api/ingest/confirm", { method: "POST", json: { camera_id: fd.get("camera_id"), plate: fd.get("plate") } }));
    if (r.ok) toast("Operator confirm recorded: " + esc(normPlate(fd.get("plate"))) + " at " + esc(fd.get("camera_id")) + ".");
    else toast("Confirm plate failed: " + esc(r.error), "err");
  });
  loadAlerts();
  loadTrack();
  loadDetections();
  refreshHealth();
};
$("confirm-face-form").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await withBusy(e.submitter, async () => {
    const r = await readJson(await api("/api/ingest/confirm-face", { method: "POST", json: { camera_id: fd.get("camera_id"), gallery_id: fd.get("gallery_id") } }));
    if (r.ok) toast("Face confirm recorded for gallery " + esc(fd.get("gallery_id")) + ".");
    else toast("Confirm face failed: " + esc(r.error), "err");
  });
  loadAlerts();
  loadDetections();
};
$("wl-form").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await withBusy(e.submitter, async () => {
    const r = await readJson(await api("/api/watchlist", { method: "POST", json: Object.fromEntries(fd.entries()) }));
    if (r.ok) toast("Watchlist entry " + esc(fd.get("source_case_id")) + " saved.");
    else toast("Save failed: " + esc(r.error), "err");
  });
  loadWatchlist();
};
if ($("enroll-person-form")) {
  $("enroll-person-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const out = $("enroll-out");
    out.innerHTML = loadingHtml("Enrolling photo…");
    await withBusy(e.submitter, async () => {
      const r = await readJson(await api("/api/faces/enroll", { method: "POST", body: fd }));
      if (!r.ok) { out.innerHTML = errorHtml("Enroll failed: " + r.error); return; }
      renderResult(out, r.data);
    });
    loadWatchlist();
  };
}

document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) && !$("app").classList.contains("hidden")) {
    e.preventDefault();
    selectTab("track");
    $("plate-search").focus();
    $("plate-search").select();
  }
});

syncSlots();
api("/api/me").then((r) => {
  if (r.ok) { r.json().then((u) => { me = u; showApp(); boot(); }); }
}).catch(() => {});
