"use strict";
/* Mothlit: mini painel da bandeja (só o essencial). Usa comum.js. */

const RELER_MS = { ar: 2500, luz: 800 };
const JANELA_INTERACAO_MS = 4000;
const estado = { ar: null, luz: null };
const ultimaInteracao = { ar: 0, luz: 0 };
const painel = $("#painel");
const brilho = $("#fly-brilho");

const formatar = v => (Number.isInteger(v) ? String(v) : v.toFixed(1));

// ---------------------------------------------------------------- leitura e comandos

async function ler(qual) {
  const r = await chamar(qual === "ar" ? "estado_ar" : "estado_luz");
  const secao = $(qual === "ar" ? "#fly-ar" : "#fly-luz");
  if (!r.ok) {
    secao.classList.add("offline");
    situacao(qual, r.configurado === false ? "Não configurado" : "Sem conexão", r.configurado !== false);
    return;
  }
  secao.classList.remove("offline");
  if (Date.now() - ultimaInteracao[qual] < JANELA_INTERACAO_MS) return;
  estado[qual] = r.dados;
  qual === "ar" ? aplicarAr(r.dados) : aplicarLuz(r.dados);
}

async function comando(qual, metodo, args) {
  ultimaInteracao[qual] = Date.now();
  const marca = ultimaInteracao[qual];
  const r = await chamar(metodo, ...args);
  if (!r.ok) {
    situacao(qual, r.erro || "Falha ao enviar o comando.", true);
    ultimaInteracao[qual] = 0;
    setTimeout(() => ler(qual), 400);
    return;
  }
  setTimeout(() => {
    if (ultimaInteracao[qual] === marca) ultimaInteracao[qual] = 0;
    ler(qual);
  }, RELER_MS[qual]);
}

function situacao(qual, texto, erro = false) {
  const el = $(qual === "ar" ? "#fly-ar-sit" : "#fly-luz-sit");
  el.textContent = texto;
  el.title = texto;
  el.classList.toggle("erro", erro);
}

// ---------------------------------------------------------------- lâmpada

function corDaLuz(d) {
  const rgb = d.modo === "colour" && d.hsv ? hsvParaRgb(d.hsv[0], d.hsv[1], 1) : corDoBranco(d.temperatura);
  return `rgb(${rgb.join(",")})`;
}

function aplicarLuz(d) {
  $("#fly-luz-nome").textContent = d.nome || "Lâmpada";
  situacao("luz", d.ligada ? `Ligada · ${d.modo === "colour" ? "colorida" : "branca"}` : "Desligada");
  $("#fly-luz").classList.toggle("desligado", !d.ligada);
  $("#fly-luz").style.setProperty("--cor-luz", corDaLuz(d));
  $("#fly-luz-energia").classList.toggle("ligada", d.ligada);
  deslizar(brilho, Math.max(1, d.brilho));
  $("#fly-brilho-valor").textContent = `${d.brilho}%`;
}

function iniciarLuz() {
  prepararSlider(brilho);
  $("#fly-luz-energia").addEventListener("click", () => {
    if (!estado.luz) return;
    const ligar = !estado.luz.ligada;
    estado.luz.ligada = ligar;
    aplicarLuz(estado.luz);
    comando("luz", "luz_ligar", [ligar]);
  });
  brilho.addEventListener("input", () => {
    ultimaInteracao.luz = Date.now();
    $("#fly-brilho-valor").textContent = `${Math.round(Number(brilho.value))}%`;
  });
  brilho.addEventListener("change", () => {
    const v = Math.round(Number(brilho.value));
    const d = estado.luz;
    if (d) { d.brilho = v; d.ligada = true; aplicarLuz(d); }
    if (d && d.modo === "colour" && d.hsv) {
      comando("luz", "luz_hsv", [d.hsv[0], d.hsv[1], v / 100]);  // mantém a cor, muda a intensidade
    } else {
      comando("luz", "luz_brilho", [v]);
    }
  });
}

// ---------------------------------------------------------------- ar-condicionado

let alvoExibido = null;
let passo = 1;
let faixa = [16, 30];

function mostrarAlvo(valor) {
  const el = $("#fly-alvo");
  const de = alvoExibido ?? valor;
  alvoExibido = valor;
  animar("fly-alvo", de, valor, 360, v => { el.textContent = formatar(Math.round(v / passo) * passo); });
}

function aplicarAr(d) {
  $("#fly-ar-nome").textContent = d.nome || "Ar-condicionado";
  const ambiente = d.ambiente != null ? ` · ${formatar(d.ambiente)} °C no ambiente` : "";
  situacao("ar", (d.ligado ? "Ligado" : "Desligado") + ambiente);
  $("#fly-ar").classList.toggle("desligado", !d.ligado);
  $("#fly-ar-energia").classList.toggle("ligada", d.ligado);
  passo = d.faixa[2] || 1;
  faixa = [d.faixa[0], d.faixa[1]];
  if (d.alvo != null) mostrarAlvo(d.alvo);
}

let enviarAlvo;
function iniciarAr() {
  $("#fly-ar-energia").addEventListener("click", () => {
    if (!estado.ar) return;
    const ligar = !estado.ar.ligado;
    estado.ar.ligado = ligar;
    aplicarAr(estado.ar);
    situacao("ar", ligar ? "Ligando…" : "Desligando…");
    comando("ar", "ar_ligar", [ligar]);
  });
  for (const [id, direcao] of [["#fly-menos", -1], ["#fly-mais", +1]]) {
    $(id).addEventListener("click", () => {
      if (alvoExibido == null) return;
      ultimaInteracao.ar = Date.now();
      const v = Math.min(faixa[1], Math.max(faixa[0], alvoExibido + direcao * passo));
      mostrarAlvo(v);
      clearTimeout(enviarAlvo);
      enviarAlvo = setTimeout(() => comando("ar", "ar_temperatura", [v]), 700);  // cliques seguidos = 1 comando
    });
  }
}

// ---------------------------------------------------------------- painel

// O Python chama ao mostrar o painel: entra deslizando e relê os aparelhos.
window.aoMostrar = () => {
  painel.classList.remove("visivel");
  void painel.offsetWidth;
  requestAnimationFrame(() => painel.classList.add("visivel"));
  ler("ar");
  ler("luz");
};

// Some ao perder o foco (clicar fora), como os painéis da bandeja do Windows.
function esconder() {
  painel.classList.remove("visivel");
  chamar("esconder_flyout");
}

document.addEventListener("DOMContentLoaded", () => {
  pintarIcones();
  iniciarLuz();
  iniciarAr();
  $("#fly-expandir").addEventListener("click", () => chamar("abrir_completo", null));
  $$(".fly-abrir").forEach(b => b.addEventListener("click", () => chamar("abrir_completo", b.dataset.aba)));
  window.addEventListener("blur", esconder);
  document.addEventListener("keydown", e => { if (e.key === "Escape") esconder(); });
  document.addEventListener("contextmenu", e => e.preventDefault());
});
