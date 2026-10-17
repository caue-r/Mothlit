"use strict";
/* Mothlit: interface. Fala com o Python via pywebview.api (cada chamada roda numa thread no Python). */

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
  ventilador: '<circle cx="12" cy="12" r="1.6"/>' +
    [0, 120, 240].map(a => `<path transform="rotate(${a} 12 12)" d="M12 10.4c-.4-3.4.6-6.4 3-6.4 2.6 0 2.8 3.6-1.6 6.8"/>`).join(""),
};

function svg(nome) {
  return `<svg class="icone" viewBox="0 0 24 24" aria-hidden="true">${ICONES[nome] || ""}</svg>`;
}

function pintarIcones(raiz = document) {
  $$("[data-icone]", raiz).forEach(el => { el.innerHTML = svg(el.dataset.icone); });
}

// ---------------------------------------------------------------- nomes exibidos

const NOMES = {
  modo: { auto: "Auto", cool: "Resfriar", dry: "Desumidificar", wind: "Ventilar", fan: "Ventilar", heat: "Aquecer" },
  ventilador: { auto: "Auto", low: "Baixa", medium: "Média", high: "Alta", turbo: "Turbo" },
  opcional: { off: "Desligado", sleep: "Dormir", quiet: "Silencioso", speed: "Rápido", windFree: "WindFree",
    windFreeSleep: "WindFree noturno", energySaving: "Econômico", smart: "Inteligente", comfort: "Conforto" },
  oscilacao: { fixed: "Fixa", vertical: "Vertical", horizontal: "Horizontal", all: "Todas", off: "Desligada", swing: "Vai e vem" },
};
const ICONE_MODO = { auto: "auto", cool: "floco", dry: "gota", wind: "vento", fan: "vento", heat: "sol" };
const nome = (campo, valor) => (NOMES[campo] && NOMES[campo][valor]) || valor || "–";

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

// ---------------------------------------------------------------- estado e sincronização

const RELER_MS = { ar: 2500, luz: 800 };   // a SmartThings demora a refletir o comando
const JANELA_INTERACAO_MS = 4000;           // não deixa uma leitura "desfazer" o que o usuário acabou de mexer
const estado = { ar: null, luz: null };
const ultimaInteracao = { ar: 0, luz: 0 };

let ocupados = 0;
function ocupar(delta) {
  ocupados = Math.max(0, ocupados + delta);
  $("#btn-atualizar").classList.toggle("girando", ocupados > 0);
}

async function ler(qual) {
  ocupar(+1);
  const r = await chamar(qual === "ar" ? "estado_ar" : "estado_luz");
  ocupar(-1);
  if (!r.ok) return falhou(qual, r);
  if (Date.now() - ultimaInteracao[qual] < JANELA_INTERACAO_MS) return;
  estado[qual] = r.dados;
  qual === "ar" ? aplicarAr(r.dados) : aplicarLuz(r.dados);
  status(`Atualizado às ${hora()}`, "sutil");
}

function atualizarTudo() {
  ler("ar");
  ler("luz");
}

function interagiu(qual) {
  ultimaInteracao[qual] = Date.now();
  return ultimaInteracao[qual];
}

async function comando(qual, metodo, args, descricao) {
  const marca = interagiu(qual);
  const r = await chamar(metodo, ...args);
  if (!r.ok) {
    falhou(qual, r);
    ultimaInteracao[qual] = 0;
    setTimeout(() => ler(qual), 400);  // volta a interface para o estado real
    return;
  }
  status(descricao);
  setTimeout(() => {
    if (ultimaInteracao[qual] === marca) ultimaInteracao[qual] = 0;
    ler(qual);
  }, RELER_MS[qual]);
}

function falhou(qual, r) {
  const configurado = r.configurado !== false;
  situacao(qual, configurado ? "Sem conexão" : "Não configurado", configurado);
  status(r.erro || "Falha desconhecida.", "erro");
}

function situacao(qual, texto, erro = false) {
  const el = $(qual === "ar" ? "#ar-situacao" : "#luz-situacao");
  el.textContent = texto;
  el.classList.toggle("erro", erro);
}

// ---------------------------------------------------------------- barra de status

let erroVisivelAte = 0;
let temporizadorStatus;
function status(mensagem, tipo = "") {
  if (tipo === "sutil" && Date.now() < erroVisivelAte) return;  // rotina não esconde erro recente
  erroVisivelAte = tipo === "erro" ? Date.now() + 8000 : 0;
  const el = $("#status");
  el.classList.add("sumindo");
  clearTimeout(temporizadorStatus);
  temporizadorStatus = setTimeout(() => {
    el.textContent = tipo === "erro" ? `${hora()} · ${mensagem}` : mensagem;
    el.className = "status " + (tipo === "erro" ? "erro" : tipo === "sutil" ? "" : "novo");
    if (tipo !== "erro") temporizadorStatus = setTimeout(() => el.classList.remove("novo"), 1800);
  }, 150);
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

// ---------------------------------------------------------------- abas e páginas

function abas(nav, aoTrocar) {
  const botoes = $$("button", nav);
  botoes.forEach((botao, i) => botao.addEventListener("click", () => {
    if (botao.classList.contains("ativa")) return;
    botoes.forEach(b => b.classList.toggle("ativa", b === botao));
    nav.dataset.pos = i;
    aoTrocar(botao.dataset.alvo, i);
  }));
}

function mostrar(paginas, indice) {
  paginas.forEach((p, j) => {
    p.classList.toggle("ativa", j === indice);
    p.classList.toggle("antes", j < indice);  // páginas à esquerda saem para a esquerda
  });
}

// ---------------------------------------------------------------- ar-condicionado

const ar = {
  card: $("#card-ar"),
  slider: $("#ar-slider"),
  alvoExibido: null,
  passo: 1,
};

function montarVento() {
  const n = 13;
  let html = "";
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    const x = 62 + t * 176;
    const abre = (t - 0.5) * 80;
    html += `<path d="M${x} 80 C ${x + abre * 0.15} 105, ${x + abre * 0.6} 135, ${x + abre} 166"
              style="animation-delay:${(-i * 0.13).toFixed(2)}s"/>`;
  }
  $("#ar-vento").innerHTML = html;
}

const formatar = v => (Number.isInteger(v) ? String(v) : v.toFixed(1));

function mostrarAlvo(valor, animado = true) {
  const el = $("#ar-alvo");
  const de = ar.alvoExibido ?? valor;
  ar.alvoExibido = valor;
  $("#ar-visor").textContent = formatar(valor);
  if (!animado) { el.textContent = formatar(valor); return; }
  animar("ar-alvo", de, valor, 420, v => { el.textContent = formatar(Math.round(v / ar.passo) * ar.passo); });
}

function aplicarAr(d) {
  $("#ar-nome").textContent = d.nome || "Ar-condicionado";
  situacao("ar", d.ligado ? "Ligado" : "Desligado");
  ar.card.classList.toggle("ligado", d.ligado);
  ar.card.classList.toggle("desligado", !d.ligado);
  $("#ar-energia").classList.toggle("ligada", d.ligado);

  const [min, max, passo] = d.faixa;
  ar.passo = passo || 1;
  ar.slider.min = min;
  ar.slider.max = max;
  $("#ar-min").textContent = `${formatar(min)}°`;
  $("#ar-max").textContent = `${formatar(max)}°`;
  if (d.alvo != null) {
    mostrarAlvo(d.alvo);
    deslizar(ar.slider, d.alvo);
  }
  $("#ar-ambiente").textContent = d.ambiente != null ? `${formatar(d.ambiente)} °C` : "– °C";

  definirBloco("modo", d.modos, d.modo, ICONE_MODO[d.modo] || "floco");
  definirBloco("ventilador", d.ventiladores, d.ventilador);
  definirBloco("opcional", d.opcionais, d.opcional);
  definirBloco("oscilacao", d.oscilacoes, d.oscilacao);
}

function definirBloco(campo, opcoes, atual, icone) {
  const bloco = $(`.bloco[data-campo="${campo}"]`);
  bloco.opcoes = opcoes || [];
  bloco.atual = atual;
  bloco.classList.toggle("indisponivel", bloco.opcoes.length === 0);
  bloco.classList.toggle("unico", bloco.opcoes.length === 1);
  if (icone && bloco.dataset.iconeAtual !== icone) {
    bloco.dataset.iconeAtual = icone;
    $(".bloco-icone", bloco).innerHTML = svg(icone);
  }
  trocarTexto(bloco, bloco.opcoes.length ? nome(campo, atual) : "Indisponível");
}

function trocarTexto(bloco, texto) {
  const el = $(".bloco-valor", bloco);
  if (el.textContent === texto) return;
  bloco.classList.add("trocando");
  setTimeout(() => { el.textContent = texto; bloco.classList.remove("trocando"); }, 140);
}

const COMANDO_BLOCO = {
  modo: ["ar_modo", "Modo"],
  ventilador: ["ar_ventilador", "Ventilação"],
  opcional: ["ar_opcional", "Modo extra"],
  oscilacao: ["ar_oscilacao", "Oscilação"],
};

function escolherNoBloco(bloco, valor) {
  const campo = bloco.dataset.campo;
  const [metodo, rotulo] = COMANDO_BLOCO[campo];
  bloco.atual = valor;
  trocarTexto(bloco, nome(campo, valor));
  if (campo === "modo") definirBloco("modo", bloco.opcoes, valor, ICONE_MODO[valor] || "floco");
  comando("ar", metodo, [valor], `${rotulo}: ${nome(campo, valor)}`);
}

let enviarAlvo;
function alvoAlterado(valor, imediato) {
  interagiu("ar");
  const [min, max] = [Number(ar.slider.min), Number(ar.slider.max)];
  valor = Math.min(max, Math.max(min, Math.round(valor / ar.passo) * ar.passo));
  mostrarAlvo(valor);
  clearTimeout(enviarAlvo);
  enviarAlvo = setTimeout(
    () => comando("ar", "ar_temperatura", [valor], `Temperatura alvo em ${formatar(valor)} °C`),
    imediato ? 0 : 700,  // cliques seguidos em −/+ viram um único comando
  );
  return valor;
}

function iniciarAr() {
  montarVento();
  prepararSlider(ar.slider);
  ar.slider.addEventListener("input", () => {
    interagiu("ar");
    mostrarAlvo(Math.round(Number(ar.slider.value) / ar.passo) * ar.passo, false);
  });
  ar.slider.addEventListener("change", () => {
    const v = alvoAlterado(Number(ar.slider.value), true);
    deslizar(ar.slider, v, 200);  // encaixa no passo
  });
  for (const [id, direcao] of [["#ar-menos", -1], ["#ar-mais", +1]]) {
    $(id).addEventListener("click", () => {
      const base = ar.alvoExibido ?? Number(ar.slider.value);
      const v = alvoAlterado(base + direcao * ar.passo, false);
      deslizar(ar.slider, v, 260);
    });
  }
  $("#ar-energia").addEventListener("click", () => {
    if (!estado.ar) return;
    const ligar = !estado.ar.ligado;
    estado.ar.ligado = ligar;
    ar.card.classList.toggle("ligado", ligar);
    ar.card.classList.toggle("desligado", !ligar);
    $("#ar-energia").classList.toggle("ligada", ligar);
    situacao("ar", ligar ? "Ligando…" : "Desligando…");
    comando("ar", "ar_ligar", [ligar], ligar ? "Ar-condicionado ligado" : "Ar-condicionado desligado");
  });
  $$(".bloco").forEach(bloco => bloco.addEventListener("click", e => { e.stopPropagation(); abrirMenu(bloco); }));
}

// ---------------------------------------------------------------- menu dos blocos

let blocoAberto = null;

function abrirMenu(bloco) {
  const menu = $("#menu");
  if (blocoAberto === bloco) return fecharMenu();
  fecharMenu();
  if (!bloco.opcoes || bloco.opcoes.length < 2) return;
  const campo = bloco.dataset.campo;
  menu.innerHTML = bloco.opcoes
    .map(v => `<button data-valor="${v}" class="${v === bloco.atual ? "atual" : ""}">${nome(campo, v)}</button>`)
    .join("");
  const r = bloco.getBoundingClientRect();
  const largura = Math.max(150, r.width);
  menu.style.left = `${Math.min(r.left, window.innerWidth - largura - 12)}px`;
  menu.style.top = `${r.bottom + 6}px`;
  menu.style.minWidth = `${largura}px`;
  $$("button", menu).forEach(b => b.addEventListener("click", ev => {
    ev.stopPropagation();
    fecharMenu();
    if (b.dataset.valor !== bloco.atual) escolherNoBloco(bloco, b.dataset.valor);
  }));
  // se não couber embaixo, abre para cima
  requestAnimationFrame(() => {
    const altura = menu.offsetHeight;
    if (r.bottom + 6 + altura > window.innerHeight - 8) {
      menu.style.top = `${r.top - altura - 6}px`;
      menu.style.transformOrigin = "bottom left";
    } else {
      menu.style.transformOrigin = "top left";
    }
    menu.classList.add("aberto");
  });
  bloco.classList.add("aberto");
  blocoAberto = bloco;
}

function fecharMenu() {
  $("#menu").classList.remove("aberto");
  if (blocoAberto) blocoAberto.classList.remove("aberto");
  blocoAberto = null;
}

// ---------------------------------------------------------------- lâmpada

const luz = {
  quarto: $("#quarto"),
  brilho: $("#luz-brilho"),
  temp: $("#luz-temp"),
  disco: $("#disco"),
  marca: $("#disco-marca"),
};

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

function desenharQuarto() {
  const d = estado.luz;
  if (!d) return;
  const rgb = d.modo === "colour" && d.hsv ? hsvParaRgb(d.hsv[0], d.hsv[1], 1) : corDoBranco(d.temperatura);
  luz.quarto.style.setProperty("--luz", `rgb(${rgb.join(",")})`);
  luz.quarto.style.setProperty("--int", d.ligada ? (0.25 + 0.75 * d.brilho / 100).toFixed(3) : 0);
  luz.quarto.classList.toggle("apagado", !d.ligada);
}

function posicionarMarca(h, s, suave) {
  const raio = luz.disco.clientWidth / 2;
  const angulo = h * 2 * Math.PI;
  luz.marca.classList.toggle("suave", suave);
  luz.marca.style.left = `${raio + Math.sin(angulo) * s * raio}px`;
  luz.marca.style.top = `${raio - Math.cos(angulo) * s * raio}px`;
  luz.marca.style.background = `rgb(${hsvParaRgb(h, s, 1).join(",")})`;
}

function aplicarLuz(d) {
  $("#luz-nome").textContent = d.nome || "Lâmpada";
  situacao("luz", d.ligada ? `Ligada · ${d.modo === "colour" ? "Colorida" : "Branca"}` : "Desligada");
  $("#luz-energia").classList.toggle("ligada", d.ligada);
  deslizar(luz.brilho, Math.max(1, d.brilho));
  $("#luz-brilho-valor").textContent = `${d.brilho}%`;
  if (d.temperatura != null) deslizar(luz.temp, d.temperatura);
  if (d.hsv) posicionarMarca(d.hsv[0], d.hsv[1], true);
  $("#abas-luz").style.display = d.suportaCor && d.suportaTemperatura ? "" : "none";
  if (!d.suportaCor && d.suportaTemperatura) mostrar($$(".subpagina"), 1);
  desenharQuarto();
}

function iniciarLuz() {
  prepararSlider(luz.brilho);
  prepararSlider(luz.temp);
  posicionarMarca(0, 0, false);

  $("#luz-energia").addEventListener("click", () => {
    if (!estado.luz) return;
    const ligar = !estado.luz.ligada;
    estado.luz.ligada = ligar;
    $("#luz-energia").classList.toggle("ligada", ligar);
    desenharQuarto();
    comando("luz", "luz_ligar", [ligar], ligar ? "Lâmpada ligada" : "Lâmpada desligada");
  });

  // brilho: vale para o modo branco e para o colorido
  luz.brilho.addEventListener("input", () => {
    interagiu("luz");
    const v = Math.round(Number(luz.brilho.value));
    $("#luz-brilho-valor").textContent = `${v}%`;
    if (estado.luz) { estado.luz.brilho = v; estado.luz.ligada = true; desenharQuarto(); }
  });
  luz.brilho.addEventListener("change", () => {
    const v = Math.round(Number(luz.brilho.value));
    const d = estado.luz;
    if (d && d.modo === "colour" && d.hsv) {
      // no modo colorido o brilho é o V do HSV: mantém a cor e muda só a intensidade
      comando("luz", "luz_hsv", [d.hsv[0], d.hsv[1], v / 100], `Brilho em ${v}%`);
    } else {
      comando("luz", "luz_brilho", [v], `Brilho em ${v}%`);
    }
  });

  // disco de cores
  const lerDisco = e => {
    const r = luz.disco.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
    const h = ((Math.atan2(dx, -dy) / (2 * Math.PI)) + 1) % 1;
    const s = Math.min(1, Math.hypot(dx, dy) / (r.width / 2));
    return [h, s];
  };
  const previaCor = ([h, s]) => {
    posicionarMarca(h, s, false);
    if (estado.luz) {
      estado.luz.modo = "colour";
      estado.luz.ligada = true;
      estado.luz.hsv = [h, s, Number(luz.brilho.value) / 100];
      desenharQuarto();
    }
  };
  luz.disco.addEventListener("pointerdown", e => {
    interagiu("luz");
    luz.disco.setPointerCapture(e.pointerId);
    luz.disco.classList.add("arrastando");
    previaCor(lerDisco(e));
  });
  luz.disco.addEventListener("pointermove", e => {
    if (!luz.disco.classList.contains("arrastando")) return;
    interagiu("luz");
    previaCor(lerDisco(e));
  });
  luz.disco.addEventListener("pointerup", e => {
    if (!luz.disco.classList.contains("arrastando")) return;
    luz.disco.classList.remove("arrastando");
    const [h, s] = lerDisco(e);
    comando("luz", "luz_hsv", [h, s, Number(luz.brilho.value) / 100], "Cor alterada");
  });

  // branco
  const previaBranco = v => {
    if (!estado.luz) return;
    estado.luz.temperatura = v;
    estado.luz.modo = "white";
    estado.luz.ligada = true;
    desenharQuarto();
  };
  luz.temp.addEventListener("input", () => { interagiu("luz"); previaBranco(Math.round(Number(luz.temp.value))); });
  luz.temp.addEventListener("change", () => {
    const v = Math.round(Number(luz.temp.value));
    comando("luz", "luz_temperatura", [v], "Temperatura de cor ajustada");
  });
  $$(".presets button").forEach(b => b.addEventListener("click", () => {
    const v = Number(b.dataset.temp);
    interagiu("luz");
    deslizar(luz.temp, v, 320);
    previaBranco(v);
    comando("luz", "luz_temperatura", [v], `Branco ${b.textContent.toLowerCase()}`);
  }));
}

// ---------------------------------------------------------------- janela

const app = $("#app");

function sair(depois) {
  fecharMenu();
  app.classList.remove("visivel");
  app.classList.add("saindo");
  setTimeout(depois, 170);
}

window.aoRestaurar = () => {
  app.classList.remove("saindo");
  requestAnimationFrame(() => app.classList.add("visivel"));
};

async function abrirConfiguracoes() {
  const r = await chamar("configuracoes");
  if (r.ok) {
    const d = r.dados;
    $("#folha-dados").innerHTML = [
      ["Lâmpada", `${d.lampadaIp} · protocolo ${d.lampadaVersao}`],
      ["Ar-condicionado", d.arId],
      ["Arquivo .env", d.env],
      ["Segredos", "Gerenciador de Credenciais do Windows (mothlit)"],
    ].map(([t, v]) => `<dt>${t}</dt><dd>${v}</dd>`).join("");
  }
  $("#folha-fundo").classList.add("aberta");
}

function iniciarJanela() {
  $("#btn-min").addEventListener("click", () => sair(() => chamar("minimizar")));
  $("#btn-fechar").addEventListener("click", () => sair(() => chamar("fechar")));
  $("#btn-atualizar").addEventListener("click", () => { status("Atualizando…", "sutil"); atualizarTudo(); });
  $("#btn-config").addEventListener("click", abrirConfiguracoes);
  $("#folha-fechar").addEventListener("click", () => $("#folha-fundo").classList.remove("aberta"));
  $("#folha-fundo").addEventListener("click", e => {
    if (e.target.id === "folha-fundo") $("#folha-fundo").classList.remove("aberta");
  });
  document.addEventListener("click", fecharMenu);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { fecharMenu(); $("#folha-fundo").classList.remove("aberta"); }
    if (e.key === "F5") { e.preventDefault(); atualizarTudo(); }
  });
  document.addEventListener("contextmenu", e => e.preventDefault());

  abas($("#abas"), (_, i) => { fecharMenu(); mostrar($$(".pagina"), i); });
  abas($("#abas-luz"), (_, i) => mostrar($$(".subpagina"), i));
}

document.addEventListener("DOMContentLoaded", () => {
  pintarIcones();
  iniciarJanela();
  iniciarAr();
  iniciarLuz();
  requestAnimationFrame(() => app.classList.add("visivel"));
  status("Conectando…", "sutil");
  atualizarTudo();
});
