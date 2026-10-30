"use strict";
/* Mothlit: code shared by the full window (app.js) and the tray quick panel (flyout.js). */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ---------------------------------------------------------------- icons (stroke, 24x24)

const ICONS = {
  power: '<path d="M12 3v8"/><path d="M6.6 6.6a8 8 0 1 0 10.8 0"/>',
  settings: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  minus: '<path d="M6 12h12"/>',
  plus: '<path d="M12 6v12M6 12h12"/>',
  close: '<path d="M7 7l10 10M17 7 7 17"/>',
  refresh: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/>',
  chevron: '<path d="m7 10 5 5 5-5"/>',
  sun: '<circle cx="12" cy="12" r="3.5"/><path d="M12 3v1.8M12 19.2V21M3 12h1.8M19.2 12H21M5.6 5.6l1.3 1.3M17.1 17.1l1.3 1.3M5.6 18.4l1.3-1.3M17.1 6.9l1.3-1.3"/>',
  moon: '<path d="M19.5 14.2A7.5 7.5 0 0 1 9.8 4.5a7.5 7.5 0 1 0 9.7 9.7Z"/>',
  snowflake: '<path d="M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9"/><path d="m9.5 4.5 2.5 2 2.5-2M9.5 19.5l2.5-2 2.5 2"/>',
  drop: '<path d="M12 3.5s5.5 6 5.5 10.2a5.5 5.5 0 0 1-11 0C6.5 9.5 12 3.5 12 3.5Z"/>',
  wind: '<path d="M3 9h10.5a2.5 2.5 0 1 0-2.5-2.5M3 15h14.5a2.5 2.5 0 1 1-2.5 2.5M3 12h7"/>',
  auto: '<path d="m6 19 6-14 6 14M8.3 14h7.4"/>',
  swing: '<path d="M4 9h14l-3-3M20 15H6l3 3"/>',
  expand: '<path d="M14 4h6v6M10 20H4v-6M20 4l-6.5 6.5M4 20l6.5-6.5"/>',
  right: '<path d="m10 7 5 5-5 5"/>',
  bulb: '<path d="M9.5 18h5M10.5 21h3"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.2h5c0-.9.4-1.7 1.1-2.2A6 6 0 0 0 12 3Z"/>',
  fan: '<circle cx="12" cy="12" r="1.6"/>' +
    [0, 120, 240].map(a => `<path transform="rotate(${a} 12 12)" d="M12 10.4c-.4-3.4.6-6.4 3-6.4 2.6 0 2.8 3.6-1.6 6.8"/>`).join(""),
};

function svg(name) {
  return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

function paintIcons(root = document) {
  $$("[data-icon]", root).forEach(el => { el.innerHTML = svg(el.dataset.icon); });
}

// ---------------------------------------------------------------- bridge to Python

let markReady;
const apiReady = new Promise(r => { markReady = r; });
window.addEventListener("pywebviewready", () => markReady());

async function call(method, ...args) {
  await apiReady;
  try {
    return await window.pywebview.api[method](...args);
  } catch (e) {
    return { ok: false, configured: true, error: "Unexpected error: " + (e && e.message ? e.message : e) };
  }
}

const clock = () => new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });

// ---------------------------------------------------------------- value animation

const animations = new Map();
const easeOut = t => 1 - Math.pow(1 - t, 3);

function animate(key, from, to, ms, apply) {
  cancelAnimationFrame(animations.get(key));
  if (Math.abs(to - from) < 1e-6) { apply(to); return; }
  const start = performance.now();
  const frame = now => {
    const t = Math.min(1, (now - start) / ms);
    apply(from + (to - from) * easeOut(t));
    if (t < 1) animations.set(key, requestAnimationFrame(frame));
    else animations.delete(key);
  };
  animations.set(key, requestAnimationFrame(frame));
}

function updateFill(input) {
  const p = ((input.value - input.min) / (input.max - input.min)) * 100;
  input.style.setProperty("--p", `${p}%`);
}

function slide(input, value, ms = 380) {
  animate(input.id, Number(input.value), value, ms, v => { input.value = v; updateFill(input); });
}

function prepareSlider(input) {
  input.step = "any";  // continuous movement; we round in the code
  input.addEventListener("input", () => { cancelAnimationFrame(animations.get(input.id)); updateFill(input); });
  updateFill(input);
}

function hsvToRgb(h, s, v) {
  const i = Math.floor(h * 6), f = h * 6 - i;
  const p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
  const [r, g, b] = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][((i % 6) + 6) % 6];
  return [r, g, b].map(c => Math.round(c * 255));
}

function whiteColor(temp) {
  // 0 = warm white (~2700 K), 100 = cool white (~6500 K)
  const t = Math.min(100, Math.max(0, temp ?? 50)) / 100;
  const warm = [255, 190, 120], cool = [205, 225, 255];
  return warm.map((w, i) => Math.round(w + (cool[i] - w) * t));
}
