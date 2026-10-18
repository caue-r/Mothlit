"use strict";
/* Mothlit: janela completa. Usa comum.js (ícones, ponte com o Python, sliders). */

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

// ---------------------------------------------------------------- estado e sincronização

const RELER_MS = { ar: 2500, luz: 800 };   // a SmartThings demora a refletir o comando
const JANELA_INTERACAO_MS = 4000;           // não deixa uma leitura "desfazer" o que o usuário acabou de mexer
const ATUALIZAR_A_CADA_MS = 30000;
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

// Chamado pelo Python ao abrir pelo mini painel ("›" de um aparelho).
window.selecionarAba = alvo => {
  const botao = $(`#abas button[data-alvo="${alvo}"]`);
  if (botao) botao.click();
};

// Chamado pelo Python quando a janela volta (bandeja ou barra de tarefas): fade-in e dados frescos.
window.aoRestaurar = () => {
  app.classList.remove("saindo");
  // se saiu pelo – ou ×, está transparente: faz o fade-in; se já está visível, não pisca
  if (!app.classList.contains("visivel")) setTimeout(() => app.classList.add("visivel"), 30);
  atualizarTudo();
};

function mostrarConfiguracoes(d) {
  $("#folha-dados").innerHTML = [
    ["Lâmpada", `${d.lampadaIp} · protocolo ${d.lampadaVersao}`],
    ["Ar-condicionado", d.arId],
    ["Arquivo .env", d.env],
  ].map(([t, v]) => `<dt>${t}</dt><dd>${v}</dd>`).join("");

  const st = d.smartthings || {};
  let acesso;
  if (st.tipo === "oauth") {
    const validade = st.expiraEm
      ? new Date(st.expiraEm * 1000).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
      : "–";
    acesso = `OAuth · renova sozinho<small>Token atual válido até ${validade}; a autorização dura enquanto o Mothlit rodar ao menos a cada 30 dias.</small>`;
  } else if (st.tipo === "pat") {
    acesso = "Token pessoal (PAT)<small>Tokens novos expiram em 24 h. Para não precisar trocar, rode o setup com OAuth.</small>";
  } else {
    acesso = "Não configurado<small>Rode o setup ou cole um token pessoal abaixo.</small>";
  }
  $("#acesso-st").innerHTML = acesso;
}

async function abrirConfiguracoes() {
  const r = await chamar("configuracoes");
  if (r.ok) mostrarConfiguracoes(r.dados);
  await carregarPreferencias();
  $("#folha-fundo").classList.add("aberta");
}

function iniciarTrocaDeToken() {
  $("#form-token").addEventListener("submit", async e => {
    e.preventDefault();
    const campo = $("#novo-token"), botao = $("#salvar-token");
    if (!campo.value.trim()) return campo.focus();
    botao.disabled = true;
    botao.textContent = "Validando…";
    const r = await chamar("trocar_token_smartthings", campo.value);
    botao.disabled = false;
    botao.textContent = "Salvar";
    if (r.ok) {
      campo.value = "";
      mostrarConfiguracoes(r.dados);
      status("Token da SmartThings salvo");
      ler("ar");
    } else {
      status(r.erro || "Não consegui salvar o token.", "erro");
    }
  });
}

// ---------------------------------------------------------------- preferências

function aplicarPreferencias(p) {
  $("#pref-iniciar").setAttribute("aria-checked", String(p.iniciarComSistema));
  $("#pref-iniciar").disabled = !p.iniciarSuportado;
  $("#pref-bandeja").setAttribute("aria-checked", String(p.fecharParaBandeja));
  $("#btn-fechar").title = p.fecharParaBandeja ? "Fechar (fica na bandeja)" : "Fechar";
}

async function carregarPreferencias() {
  const r = await chamar("preferencias");
  if (r.ok) aplicarPreferencias(r.dados);
}

function iniciarPreferencias() {
  $$(".chave").forEach(chave => chave.addEventListener("click", async () => {
    const novo = chave.getAttribute("aria-checked") !== "true";
    chave.setAttribute("aria-checked", String(novo));  // resposta imediata; o Python confirma
    chave.classList.add("salvando");
    const r = await chamar("definir_preferencia", chave.dataset.pref, novo);
    chave.classList.remove("salvando");
    if (r.ok) {
      aplicarPreferencias(r.dados);
      status("Preferência salva");
    } else {
      chave.setAttribute("aria-checked", String(!novo));
      status(r.erro || "Não consegui salvar a preferência.", "erro");
    }
  }));
  carregarPreferencias();
}

function iniciarJanela() {
  // vai para a bandeja; depois de escondida, a interface volta ao normal (invisível ao usuário)
  $("#btn-min").addEventListener("click", () => sair(async () => {
    await chamar("minimizar");
    app.classList.remove("saindo");  // fica transparente até aoRestaurar() fazer o fade-in
  }));
  $("#btn-fechar").addEventListener("click", () => sair(async () => {
    const r = await chamar("fechar");
    if (r && r.dados === "bandeja") app.classList.remove("saindo");  // idem ao –
  }));
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
  iniciarPreferencias();
  iniciarTrocaDeToken();
  requestAnimationFrame(() => app.classList.add("visivel"));
  status("Conectando…", "sutil");
  atualizarTudo();
  setInterval(() => { if (ocupados === 0) atualizarTudo(); }, ATUALIZAR_A_CADA_MS);
});
