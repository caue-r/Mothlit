"use strict";
/* Mothlit: código compartilhado entre a janela completa (app.js) e o mini painel da bandeja (flyout.js). */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ---------------------------------------------------------------- ícones (traço, 24x24)

const ICONES = {
  energia: '<path d="M12 3v8"/><path d="M6.6 6.6a8 8 0 1 0 10.8 0"/>',
  ajustes: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  menos: '<path d="M6 12h12"/>',
  mais: '<path d="M12 6v12M6 12h12"/>',
  fechar: '<path d="M7 7l10 10M17 7 7 17"/>',
  atualizar: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/>',
  seta: '<path d="m7 10 5 5 5-5"/>',
  sol: '<circle cx="12" cy="12" r="3.5"/><path d="M12 3v1.8M12 19.2V21M3 12h1.8M19.2 12H21M5.6 5.6l1.3 1.3M17.1 17.1l1.3 1.3M5.6 18.4l1.3-1.3M17.1 6.9l1.3-1.3"/>',
  lua: '<path d="M19.5 14.2A7.5 7.5 0 0 1 9.8 4.5a7.5 7.5 0 1 0 9.7 9.7Z"/>',
  floco: '<path d="M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9"/><path d="m9.5 4.5 2.5 2 2.5-2M9.5 19.5l2.5-2 2.5 2"/>',
  gota: '<path d="M12 3.5s5.5 6 5.5 10.2a5.5 5.5 0 0 1-11 0C6.5 9.5 12 3.5 12 3.5Z"/>',
  vento: '<path d="M3 9h10.5a2.5 2.5 0 1 0-2.5-2.5M3 15h14.5a2.5 2.5 0 1 1-2.5 2.5M3 12h7"/>',
  auto: '<path d="m6 19 6-14 6 14M8.3 14h7.4"/>',
  oscilar: '<path d="M4 9h14l-3-3M20 15H6l3 3"/>',
  expandir: '<path d="M14 4h6v6M10 20H4v-6M20 4l-6.5 6.5M4 20l6.5-6.5"/>',
  direita: '<path d="m10 7 5 5-5 5"/>',
  lampada: '<path d="M9.5 18h5M10.5 21h3"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.2h5c0-.9.4-1.7 1.1-2.2A6 6 0 0 0 12 3Z"/>',
  ventilador: '<circle cx="12" cy="12" r="1.6"/>' +
    [0, 120, 240].map(a => `<path transform="rotate(${a} 12 12)" d="M12 10.4c-.4-3.4.6-6.4 3-6.4 2.6 0 2.8 3.6-1.6 6.8"/>`).join(""),
};

function svg(nome) {
  return `<svg class="icone" viewBox="0 0 24 24" aria-hidden="true">${ICONES[nome] || ""}</svg>`;
}

function pintarIcones(raiz = document) {
  $$("[data-icone]", raiz).forEach(el => { el.innerHTML = svg(el.dataset.icone); });
}

// ---------------------------------------------------------------- ponte com o Python

let marcarPronta;
const apiPronta = new Promise(r => { marcarPronta = r; });
window.addEventListener("pywebviewready", () => marcarPronta());

async function chamar(metodo, ...args) {
  await apiPronta;
  try {
    return await window.pywebview.api[metodo](...args);
  } catch (e) {
    return { ok: false, configurado: true, erro: "Erro inesperado: " + (e && e.message ? e.message : e) };
  }
}

const hora = () => new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

// ---------------------------------------------------------------- animação de valores

const animacoes = new Map();
const easeOut = t => 1 - Math.pow(1 - t, 3);

function animar(chave, de, para, ms, aplicar) {
  cancelAnimationFrame(animacoes.get(chave));
  if (Math.abs(para - de) < 1e-6) { aplicar(para); return; }
  const inicio = performance.now();
  const quadro = agora => {
    const t = Math.min(1, (agora - inicio) / ms);
    aplicar(de + (para - de) * easeOut(t));
    if (t < 1) animacoes.set(chave, requestAnimationFrame(quadro));
    else animacoes.delete(chave);
  };
  animacoes.set(chave, requestAnimationFrame(quadro));
}

function progresso(input) {
  const p = ((input.value - input.min) / (input.max - input.min)) * 100;
  input.style.setProperty("--p", `${p}%`);
}

function deslizar(input, valor, ms = 380) {
  animar(input.id, Number(input.value), valor, ms, v => { input.value = v; progresso(input); });
}

function prepararSlider(input) {
  input.step = "any";  // movimento contínuo; arredondamos no código
  input.addEventListener("input", () => { cancelAnimationFrame(animacoes.get(input.id)); progresso(input); });
  progresso(input);
}

function hsvParaRgb(h, s, v) {
  const i = Math.floor(h * 6), f = h * 6 - i;
  const p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
  const [r, g, b] = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][((i % 6) + 6) % 6];
  return [r, g, b].map(c => Math.round(c * 255));
}

function corDoBranco(temp) {
  // 0 = branco quente (~2700 K), 100 = branco frio (~6500 K)
  const t = Math.min(100, Math.max(0, temp ?? 50)) / 100;
  const quente = [255, 190, 120], frio = [205, 225, 255];
  return quente.map((q, i) => Math.round(q + (frio[i] - q) * t));
}
