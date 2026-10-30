"use strict";
/* Mothlit: tray quick panel (just the essentials). Uses common.js. */

const REREAD_MS = { ac: 2500, light: 800 };
const INTERACTION_WINDOW_MS = 4000;
const state = { ac: null, light: null };
const lastInteraction = { ac: 0, light: 0 };
const panel = $("#panel");
const brightness = $("#fly-brightness");

const fmt = v => (Number.isInteger(v) ? String(v) : v.toFixed(1));

// ---------------------------------------------------------------- reading and commands

async function read(which) {
  const r = await call(which === "ac" ? "ac_state" : "light_state");
  const section = $(which === "ac" ? "#fly-ac" : "#fly-light");
  if (!r.ok) {
    section.classList.add("offline");
    setStateText(which, r.configured === false ? "Not configured" : "No connection", r.configured !== false);
    return;
  }
  section.classList.remove("offline");
  if (Date.now() - lastInteraction[which] < INTERACTION_WINDOW_MS) return;
  state[which] = r.data;
  which === "ac" ? applyAc(r.data) : applyLight(r.data);
}

async function command(which, method, args) {
  lastInteraction[which] = Date.now();
  const mark = lastInteraction[which];
  const r = await call(method, ...args);
  if (!r.ok) {
    setStateText(which, r.error || "Failed to send the command.", true);
    lastInteraction[which] = 0;
    setTimeout(() => read(which), 400);
    return;
  }
  setTimeout(() => {
    if (lastInteraction[which] === mark) lastInteraction[which] = 0;
    read(which);
  }, REREAD_MS[which]);
}

function setStateText(which, text, error = false) {
  const el = $(which === "ac" ? "#fly-ac-state" : "#fly-light-state");
  el.textContent = text;
  el.title = text;
  el.classList.toggle("error", error);
}

// ---------------------------------------------------------------- lamp

function lightColor(d) {
  const rgb = d.mode === "colour" && d.hsv ? hsvToRgb(d.hsv[0], d.hsv[1], 1) : whiteColor(d.temperature);
  return `rgb(${rgb.join(",")})`;
}

function applyLight(d) {
  $("#fly-light-name").textContent = d.name || "Lamp";
  setStateText("light", d.on ? `On · ${d.mode === "colour" ? "color" : "white"}` : "Off");
  $("#fly-light").classList.toggle("off", !d.on);
  $("#fly-light").style.setProperty("--light-color", lightColor(d));
  $("#fly-light-power").classList.toggle("on", d.on);
  slide(brightness, Math.max(1, d.brightness));
  $("#fly-brightness-value").textContent = `${d.brightness}%`;
}

function initLight() {
  prepareSlider(brightness);
  $("#fly-light-power").addEventListener("click", () => {
    if (!state.light) return;
    const on = !state.light.on;
    state.light.on = on;
    applyLight(state.light);
    command("light", "light_power", [on]);
  });
  brightness.addEventListener("input", () => {
    lastInteraction.light = Date.now();
    $("#fly-brightness-value").textContent = `${Math.round(Number(brightness.value))}%`;
  });
  brightness.addEventListener("change", () => {
    const v = Math.round(Number(brightness.value));
    const d = state.light;
    if (d) { d.brightness = v; d.on = true; applyLight(d); }
    if (d && d.mode === "colour" && d.hsv) {
      command("light", "light_hsv", [d.hsv[0], d.hsv[1], v / 100]);  // keeps the color, changes the intensity
    } else {
      command("light", "light_brightness", [v]);
    }
  });
}

// ---------------------------------------------------------------- air conditioner

let shownTarget = null;
let step = 1;
let range = [16, 30];

function showTarget(value) {
  const el = $("#fly-target");
  const from = shownTarget ?? value;
  shownTarget = value;
  animate("fly-target", from, value, 360, v => { el.textContent = fmt(Math.round(v / step) * step); });
}

function applyAc(d) {
  $("#fly-ac-name").textContent = d.name || "Air conditioner";
  const room = d.room != null ? ` · ${fmt(d.room)} °C in the room` : "";
  setStateText("ac", (d.on ? "On" : "Off") + room);
  $("#fly-ac").classList.toggle("off", !d.on);
  $("#fly-ac-power").classList.toggle("on", d.on);
  step = d.range[2] || 1;
  range = [d.range[0], d.range[1]];
  if (d.target != null) showTarget(d.target);
}

let sendTarget;
function initAc() {
  $("#fly-ac-power").addEventListener("click", () => {
    if (!state.ac) return;
    const on = !state.ac.on;
    state.ac.on = on;
    applyAc(state.ac);
    setStateText("ac", on ? "Turning on…" : "Turning off…");
    command("ac", "ac_power", [on]);
  });
  for (const [id, direction] of [["#fly-minus", -1], ["#fly-plus", +1]]) {
    $(id).addEventListener("click", () => {
      if (shownTarget == null) return;
      lastInteraction.ac = Date.now();
      const v = Math.min(range[1], Math.max(range[0], shownTarget + direction * step));
      showTarget(v);
      clearTimeout(sendTarget);
      sendTarget = setTimeout(() => command("ac", "ac_temperature", [v]), 700);  // consecutive clicks = 1 command
    });
  }
}

// ---------------------------------------------------------------- panel

// Python calls this when showing the panel: it slides in and rereads the devices.
window.onShow = () => {
  panel.classList.remove("visible");
  void panel.offsetWidth;
  requestAnimationFrame(() => panel.classList.add("visible"));
  read("ac");
  read("light");
};

// Hides when it loses focus (clicking outside), like the Windows tray panels.
function hidePanel() {
  panel.classList.remove("visible");
  call("hide_flyout");
}

document.addEventListener("DOMContentLoaded", () => {
  paintIcons();
  initLight();
  initAc();
  $("#fly-expand").addEventListener("click", () => call("open_full", null));
  $$(".fly-open").forEach(b => b.addEventListener("click", () => call("open_full", b.dataset.tab)));
  window.addEventListener("blur", hidePanel);
  document.addEventListener("keydown", e => { if (e.key === "Escape") hidePanel(); });
  document.addEventListener("contextmenu", e => e.preventDefault());
});
