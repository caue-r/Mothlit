"use strict";
/* Mothlit: full window. Uses common.js (icons, bridge to Python, sliders). */

// ---------------------------------------------------------------- display names

const NAMES = {
  mode: { auto: "Auto", cool: "Cool", dry: "Dry", wind: "Fan", fan: "Fan", heat: "Heat" },
  fan: { auto: "Auto", low: "Low", medium: "Medium", high: "High", turbo: "Turbo" },
  optional: { off: "Off", sleep: "Sleep", quiet: "Quiet", speed: "Speed", windFree: "WindFree",
    windFreeSleep: "WindFree sleep", energySaving: "Eco", smart: "Smart", comfort: "Comfort" },
  oscillation: { fixed: "Fixed", vertical: "Vertical", horizontal: "Horizontal", all: "All", off: "Off", swing: "Swing" },
};
const MODE_ICON = { auto: "auto", cool: "snowflake", dry: "drop", wind: "wind", fan: "wind", heat: "sun" };
const label = (field, value) => (NAMES[field] && NAMES[field][value]) || value || "–";

// ---------------------------------------------------------------- state and sync

const REREAD_MS = { ac: 2500, light: 800 };   // SmartThings takes a while to reflect the command
const INTERACTION_WINDOW_MS = 4000;           // keeps a read from "undoing" what the user just changed
const REFRESH_EVERY_MS = 30000;
const state = { ac: null, light: null };
const lastInteraction = { ac: 0, light: 0 };

let busy = 0;
function setBusy(delta) {
  busy = Math.max(0, busy + delta);
  $("#btn-refresh").classList.toggle("spinning", busy > 0);
}

async function read(which) {
  setBusy(+1);
  const r = await call(which === "ac" ? "ac_state" : "light_state");
  setBusy(-1);
  if (!r.ok) return failed(which, r);
  if (Date.now() - lastInteraction[which] < INTERACTION_WINDOW_MS) return;
  state[which] = r.data;
  which === "ac" ? applyAc(r.data) : applyLight(r.data);
  showStatus(`Updated at ${clock()}`, "subtle");
}

function refreshAll() {
  read("ac");
  read("light");
}

function touched(which) {
  lastInteraction[which] = Date.now();
  return lastInteraction[which];
}

async function command(which, method, args, description) {
  const mark = touched(which);
  const r = await call(method, ...args);
  if (!r.ok) {
    failed(which, r);
    lastInteraction[which] = 0;
    setTimeout(() => read(which), 400);  // brings the interface back to the real state
    return;
  }
  showStatus(description);
  setTimeout(() => {
    if (lastInteraction[which] === mark) lastInteraction[which] = 0;
    read(which);
  }, REREAD_MS[which]);
}

function failed(which, r) {
  const configured = r.configured !== false;
  setStateText(which, configured ? "No connection" : "Not configured", configured);
  showStatus(r.error || "Unknown failure.", "error");
}

function setStateText(which, text, error = false) {
  const el = $(which === "ac" ? "#ac-state" : "#light-state");
  el.textContent = text;
  el.classList.toggle("error", error);
}

// ---------------------------------------------------------------- status bar

let errorVisibleUntil = 0;
let statusTimer;
function showStatus(message, kind = "") {
  if (kind === "subtle" && Date.now() < errorVisibleUntil) return;  // routine messages do not hide a recent error
  errorVisibleUntil = kind === "error" ? Date.now() + 8000 : 0;
  const el = $("#status");
  el.classList.add("fading");
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => {
    el.textContent = kind === "error" ? `${clock()} · ${message}` : message;
    el.className = "status " + (kind === "error" ? "error" : kind === "subtle" ? "" : "fresh");
    if (kind !== "error") statusTimer = setTimeout(() => el.classList.remove("fresh"), 1800);
  }, 150);
}

// ---------------------------------------------------------------- tabs and pages

function tabs(nav, onChange) {
  const buttons = $$("button", nav);
  buttons.forEach((button, i) => button.addEventListener("click", () => {
    if (button.classList.contains("active")) return;
    buttons.forEach(b => b.classList.toggle("active", b === button));
    nav.dataset.pos = i;
    onChange(button.dataset.target, i);
  }));
}

function showPage(pages, index) {
  pages.forEach((p, j) => {
    p.classList.toggle("active", j === index);
    p.classList.toggle("before", j < index);  // pages to the left leave to the left
  });
}

// ---------------------------------------------------------------- air conditioner

const ac = {
  card: $("#card-ac"),
  slider: $("#ac-slider"),
  shownTarget: null,
  step: 1,
};

function buildAirflow() {
  const n = 13;
  let html = "";
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    const x = 62 + t * 176;
    const spread = (t - 0.5) * 80;
    html += `<path d="M${x} 80 C ${x + spread * 0.15} 105, ${x + spread * 0.6} 135, ${x + spread} 166"
              style="animation-delay:${(-i * 0.13).toFixed(2)}s"/>`;
  }
  $("#ac-airflow").innerHTML = html;
}

const fmt = v => (Number.isInteger(v) ? String(v) : v.toFixed(1));

function showTarget(value, animated = true) {
  const el = $("#ac-target");
  const from = ac.shownTarget ?? value;
  ac.shownTarget = value;
  $("#ac-display").textContent = fmt(value);
  if (!animated) { el.textContent = fmt(value); return; }
  animate("ac-target", from, value, 420, v => { el.textContent = fmt(Math.round(v / ac.step) * ac.step); });
}

function applyAc(d) {
  $("#ac-name").textContent = d.name || "Air conditioner";
  setStateText("ac", d.on ? "On" : "Off");
  ac.card.classList.toggle("on", d.on);
  ac.card.classList.toggle("off", !d.on);
  $("#ac-power").classList.toggle("on", d.on);

  const [min, max, step] = d.range;
  ac.step = step || 1;
  ac.slider.min = min;
  ac.slider.max = max;
  $("#ac-min").textContent = `${fmt(min)}°`;
  $("#ac-max").textContent = `${fmt(max)}°`;
  if (d.target != null) {
    showTarget(d.target);
    slide(ac.slider, d.target);
  }
  $("#ac-room").textContent = d.room != null ? `${fmt(d.room)} °C` : "– °C";

  setTile("mode", d.modes, d.mode, MODE_ICON[d.mode] || "snowflake");
  setTile("fan", d.fans, d.fan);
  setTile("optional", d.optionals, d.optional);
  setTile("oscillation", d.oscillations, d.oscillation);
}

function setTile(field, options, current, icon) {
  const tile = $(`.tile[data-field="${field}"]`);
  tile.options = options || [];
  tile.current = current;
  tile.classList.toggle("unavailable", tile.options.length === 0);
  tile.classList.toggle("single", tile.options.length === 1);
  if (icon && tile.dataset.currentIcon !== icon) {
    tile.dataset.currentIcon = icon;
    $(".tile-icon", tile).innerHTML = svg(icon);
  }
  swapText(tile, tile.options.length ? label(field, current) : "Unavailable");
}

function swapText(tile, text) {
  const el = $(".tile-value", tile);
  if (el.textContent === text) return;
  tile.classList.add("swapping");
  setTimeout(() => { el.textContent = text; tile.classList.remove("swapping"); }, 140);
}

const TILE_COMMAND = {
  mode: ["ac_mode", "Mode"],
  fan: ["ac_fan", "Fan"],
  optional: ["ac_optional", "Extra mode"],
  oscillation: ["ac_oscillation", "Swing"],
};

function chooseInTile(tile, value) {
  const field = tile.dataset.field;
  const [method, title] = TILE_COMMAND[field];
  tile.current = value;
  swapText(tile, label(field, value));
  if (field === "mode") setTile("mode", tile.options, value, MODE_ICON[value] || "snowflake");
  command("ac", method, [value], `${title}: ${label(field, value)}`);
}

let sendTarget;
function targetChanged(value, immediate) {
  touched("ac");
  const [min, max] = [Number(ac.slider.min), Number(ac.slider.max)];
  value = Math.min(max, Math.max(min, Math.round(value / ac.step) * ac.step));
  showTarget(value);
  clearTimeout(sendTarget);
  sendTarget = setTimeout(
    () => command("ac", "ac_temperature", [value], `Target temperature set to ${fmt(value)} °C`),
    immediate ? 0 : 700,  // consecutive −/+ clicks become a single command
  );
  return value;
}

function initAc() {
  buildAirflow();
  prepareSlider(ac.slider);
  ac.slider.addEventListener("input", () => {
    touched("ac");
    showTarget(Math.round(Number(ac.slider.value) / ac.step) * ac.step, false);
  });
  ac.slider.addEventListener("change", () => {
    const v = targetChanged(Number(ac.slider.value), true);
    slide(ac.slider, v, 200);  // snaps to the step
  });
  for (const [id, direction] of [["#ac-minus", -1], ["#ac-plus", +1]]) {
    $(id).addEventListener("click", () => {
      const base = ac.shownTarget ?? Number(ac.slider.value);
      const v = targetChanged(base + direction * ac.step, false);
      slide(ac.slider, v, 260);
    });
  }
  $("#ac-power").addEventListener("click", () => {
    if (!state.ac) return;
    const on = !state.ac.on;
    state.ac.on = on;
    ac.card.classList.toggle("on", on);
    ac.card.classList.toggle("off", !on);
    $("#ac-power").classList.toggle("on", on);
    setStateText("ac", on ? "Turning on…" : "Turning off…");
    command("ac", "ac_power", [on], on ? "Air conditioner on" : "Air conditioner off");
  });
  $$(".tile").forEach(tile => tile.addEventListener("click", e => { e.stopPropagation(); openMenu(tile); }));
}

// ---------------------------------------------------------------- tile menu

let openTile = null;

function openMenu(tile) {
  const menu = $("#menu");
  if (openTile === tile) return closeMenu();
  closeMenu();
  if (!tile.options || tile.options.length < 2) return;
  const field = tile.dataset.field;
  menu.innerHTML = tile.options
    .map(v => `<button data-value="${v}" class="${v === tile.current ? "current" : ""}">${label(field, v)}</button>`)
    .join("");
  const r = tile.getBoundingClientRect();
  const width = Math.max(150, r.width);
  menu.style.left = `${Math.min(r.left, window.innerWidth - width - 12)}px`;
  menu.style.top = `${r.bottom + 6}px`;
  menu.style.minWidth = `${width}px`;
  $$("button", menu).forEach(b => b.addEventListener("click", ev => {
    ev.stopPropagation();
    closeMenu();
    if (b.dataset.value !== tile.current) chooseInTile(tile, b.dataset.value);
  }));
  // if it does not fit below, open upwards
  requestAnimationFrame(() => {
    const height = menu.offsetHeight;
    if (r.bottom + 6 + height > window.innerHeight - 8) {
      menu.style.top = `${r.top - height - 6}px`;
      menu.style.transformOrigin = "bottom left";
    } else {
      menu.style.transformOrigin = "top left";
    }
    menu.classList.add("open");
  });
  tile.classList.add("open");
  openTile = tile;
}

function closeMenu() {
  $("#menu").classList.remove("open");
  if (openTile) openTile.classList.remove("open");
  openTile = null;
}

// ---------------------------------------------------------------- lamp

const light = {
  room: $("#room"),
  brightness: $("#light-brightness"),
  temp: $("#light-temp"),
  wheel: $("#wheel"),
  handle: $("#wheel-handle"),
};

function drawRoom() {
  const d = state.light;
  if (!d) return;
  const rgb = d.mode === "colour" && d.hsv ? hsvToRgb(d.hsv[0], d.hsv[1], 1) : whiteColor(d.temperature);
  light.room.style.setProperty("--light", `rgb(${rgb.join(",")})`);
  light.room.style.setProperty("--intensity", d.on ? (0.25 + 0.75 * d.brightness / 100).toFixed(3) : 0);
  light.room.classList.toggle("dark", !d.on);
}

function placeHandle(h, s, smooth) {
  const radius = light.wheel.clientWidth / 2;
  const angle = h * 2 * Math.PI;
  light.handle.classList.toggle("smooth", smooth);
  light.handle.style.left = `${radius + Math.sin(angle) * s * radius}px`;
  light.handle.style.top = `${radius - Math.cos(angle) * s * radius}px`;
  light.handle.style.background = `rgb(${hsvToRgb(h, s, 1).join(",")})`;
}

function applyLight(d) {
  $("#light-name").textContent = d.name || "Lamp";
  setStateText("light", d.on ? `On · ${d.mode === "colour" ? "Color" : "White"}` : "Off");
  $("#light-power").classList.toggle("on", d.on);
  slide(light.brightness, Math.max(1, d.brightness));
  $("#light-brightness-value").textContent = `${d.brightness}%`;
  if (d.temperature != null) slide(light.temp, d.temperature);
  if (d.hsv) placeHandle(d.hsv[0], d.hsv[1], true);
  $("#light-tabs").style.display = d.supportsColor && d.supportsTemperature ? "" : "none";
  if (!d.supportsColor && d.supportsTemperature) showPage($$(".subpage"), 1);
  drawRoom();
}

function initLight() {
  prepareSlider(light.brightness);
  prepareSlider(light.temp);
  placeHandle(0, 0, false);

  $("#light-power").addEventListener("click", () => {
    if (!state.light) return;
    const on = !state.light.on;
    state.light.on = on;
    $("#light-power").classList.toggle("on", on);
    drawRoom();
    command("light", "light_power", [on], on ? "Lamp on" : "Lamp off");
  });

  // brightness: applies to both white and colour mode
  light.brightness.addEventListener("input", () => {
    touched("light");
    const v = Math.round(Number(light.brightness.value));
    $("#light-brightness-value").textContent = `${v}%`;
    if (state.light) { state.light.brightness = v; state.light.on = true; drawRoom(); }
  });
  light.brightness.addEventListener("change", () => {
    const v = Math.round(Number(light.brightness.value));
    const d = state.light;
    if (d && d.mode === "colour" && d.hsv) {
      // in colour mode the brightness is the V of the HSV: keeps the color and changes only the intensity
      command("light", "light_hsv", [d.hsv[0], d.hsv[1], v / 100], `Brightness at ${v}%`);
    } else {
      command("light", "light_brightness", [v], `Brightness at ${v}%`);
    }
  });

  // color wheel
  const readWheel = e => {
    const r = light.wheel.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
    const h = ((Math.atan2(dx, -dy) / (2 * Math.PI)) + 1) % 1;
    const s = Math.min(1, Math.hypot(dx, dy) / (r.width / 2));
    return [h, s];
  };
  const previewColor = ([h, s]) => {
    placeHandle(h, s, false);
    if (state.light) {
      state.light.mode = "colour";
      state.light.on = true;
      state.light.hsv = [h, s, Number(light.brightness.value) / 100];
      drawRoom();
    }
  };
  light.wheel.addEventListener("pointerdown", e => {
    touched("light");
    light.wheel.setPointerCapture(e.pointerId);
    light.wheel.classList.add("dragging");
    previewColor(readWheel(e));
  });
  light.wheel.addEventListener("pointermove", e => {
    if (!light.wheel.classList.contains("dragging")) return;
    touched("light");
    previewColor(readWheel(e));
  });
  light.wheel.addEventListener("pointerup", e => {
    if (!light.wheel.classList.contains("dragging")) return;
    light.wheel.classList.remove("dragging");
    const [h, s] = readWheel(e);
    command("light", "light_hsv", [h, s, Number(light.brightness.value) / 100], "Color changed");
  });

  // white
  const previewWhite = v => {
    if (!state.light) return;
    state.light.temperature = v;
    state.light.mode = "white";
    state.light.on = true;
    drawRoom();
  };
  light.temp.addEventListener("input", () => { touched("light"); previewWhite(Math.round(Number(light.temp.value))); });
  light.temp.addEventListener("change", () => {
    const v = Math.round(Number(light.temp.value));
    command("light", "light_temperature", [v], "Color temperature adjusted");
  });
  $$(".presets button").forEach(b => b.addEventListener("click", () => {
    const v = Number(b.dataset.temp);
    touched("light");
    slide(light.temp, v, 320);
    previewWhite(v);
    command("light", "light_temperature", [v], `${b.textContent} white`);
  }));
}

// ---------------------------------------------------------------- window

const app = $("#app");

function leave(after) {
  closeMenu();
  app.classList.remove("visible");
  app.classList.add("leaving");
  setTimeout(after, 170);
}

// Called by Python when opening from the quick panel (a device's "›").
window.selectTab = target => {
  const button = $(`#tabs button[data-target="${target}"]`);
  if (button) button.click();
};

// Called by Python when the window comes back (tray or taskbar): fade-in and fresh data.
window.onRestore = () => {
  app.classList.remove("leaving");
  // if it left through – or ×, it is transparent: fade it in; if it is already visible, do not flicker
  if (!app.classList.contains("visible")) setTimeout(() => app.classList.add("visible"), 30);
  refreshAll();
};

function showSettings(d) {
  $("#sheet-data").innerHTML = [
    ["Lamp", `${d.lampIp} · protocol ${d.lampVersion}`],
    ["Air conditioner", d.acId],
    [".env file", d.env],
  ].map(([t, v]) => `<dt>${t}</dt><dd>${v}</dd>`).join("");

  const st = d.smartthings || {};
  let access;
  if (st.kind === "oauth") {
    const validUntil = st.expiresAt
      ? new Date(st.expiresAt * 1000).toLocaleString("en-US", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
      : "–";
    access = `OAuth · renews itself<small>Current token valid until ${validUntil}; the authorization lasts as long as Mothlit runs at least once every 30 days.</small>`;
  } else if (st.kind === "pat") {
    access = "Personal access token (PAT)<small>New tokens expire in 24 h. To stop replacing it, run setup with OAuth.</small>";
  } else {
    access = "Not configured<small>Run setup or paste a personal access token below.</small>";
  }
  $("#st-access").innerHTML = access;
}

async function openSettings() {
  const r = await call("settings");
  if (r.ok) showSettings(r.data);
  await loadPreferences();
  $("#sheet-backdrop").classList.add("open");
}

function initTokenForm() {
  $("#token-form").addEventListener("submit", async e => {
    e.preventDefault();
    const field = $("#new-token"), button = $("#save-token");
    if (!field.value.trim()) return field.focus();
    button.disabled = true;
    button.textContent = "Validating…";
    const r = await call("replace_smartthings_token", field.value);
    button.disabled = false;
    button.textContent = "Save";
    if (r.ok) {
      field.value = "";
      showSettings(r.data);
      showStatus("SmartThings token saved");
      read("ac");
    } else {
      showStatus(r.error || "Could not save the token.", "error");
    }
  });
}

// ---------------------------------------------------------------- preferences

function applyPreferences(p) {
  $("#pref-startup").setAttribute("aria-checked", String(p.launchAtStartup));
  $("#pref-startup").disabled = !p.launchSupported;
  $("#pref-tray").setAttribute("aria-checked", String(p.closeToTray));
  $("#btn-close").title = p.closeToTray ? "Close (stays in the tray)" : "Close";
}

async function loadPreferences() {
  const r = await call("preferences");
  if (r.ok) applyPreferences(r.data);
}

function initPreferences() {
  $$(".switch").forEach(sw => sw.addEventListener("click", async () => {
    const value = sw.getAttribute("aria-checked") !== "true";
    sw.setAttribute("aria-checked", String(value));  // instant feedback; Python confirms
    sw.classList.add("saving");
    const r = await call("set_preference", sw.dataset.pref, value);
    sw.classList.remove("saving");
    if (r.ok) {
      applyPreferences(r.data);
      showStatus("Preference saved");
    } else {
      sw.setAttribute("aria-checked", String(!value));
      showStatus(r.error || "Could not save the preference.", "error");
    }
  }));
  loadPreferences();
}

function initWindow() {
  // goes to the tray; once hidden, the interface goes back to normal (invisible to the user)
  $("#btn-min").addEventListener("click", () => leave(async () => {
    await call("minimize");
    app.classList.remove("leaving");  // stays transparent until onRestore() fades it in
  }));
  $("#btn-close").addEventListener("click", () => leave(async () => {
    const r = await call("close");
    if (r && r.data === "tray") app.classList.remove("leaving");  // same as –
  }));
  $("#btn-refresh").addEventListener("click", () => { showStatus("Refreshing…", "subtle"); refreshAll(); });
  $("#btn-settings").addEventListener("click", openSettings);
  $("#sheet-close").addEventListener("click", () => $("#sheet-backdrop").classList.remove("open"));
  $("#sheet-backdrop").addEventListener("click", e => {
    if (e.target.id === "sheet-backdrop") $("#sheet-backdrop").classList.remove("open");
  });
  document.addEventListener("click", closeMenu);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { closeMenu(); $("#sheet-backdrop").classList.remove("open"); }
    if (e.key === "F5") { e.preventDefault(); refreshAll(); }
  });
  document.addEventListener("contextmenu", e => e.preventDefault());

  tabs($("#tabs"), (_, i) => { closeMenu(); showPage($$(".page"), i); });
  tabs($("#light-tabs"), (_, i) => showPage($$(".subpage"), i));
}

document.addEventListener("DOMContentLoaded", () => {
  paintIcons();
  initWindow();
  initAc();
  initLight();
  initPreferences();
  initTokenForm();
  requestAnimationFrame(() => app.classList.add("visible"));
  showStatus("Connecting…", "subtle");
  refreshAll();
  setInterval(() => { if (busy === 0) refreshAll(); }, REFRESH_EVERY_MS);
});
