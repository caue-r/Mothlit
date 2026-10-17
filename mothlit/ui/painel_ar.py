"""Painel do ar-condicionado: ilustração animada, temperatura alvo, modo, ventilação, extras."""

from functools import lru_cache

import customtkinter as ctk

from ..devices import ArCondicionado, EstadoAr
from . import desenhos, tema
from .comum import Atrasador, PainelBase
from .widgets import Bloco, BotaoIcone

NOMES_MODO = {"auto": "Auto", "cool": "Resfriar", "dry": "Desumidificar", "wind": "Ventilar", "fan": "Ventilar",
              "heat": "Aquecer"}
ICONES_MODO = {"auto": tema.ICONE_AUTO, "cool": tema.ICONE_FLOCO, "dry": tema.ICONE_GOTA,
               "wind": tema.ICONE_VENTILADOR, "fan": tema.ICONE_VENTILADOR, "heat": tema.ICONE_SOL}
NOMES_VENTILADOR = {"auto": "Auto", "low": "Baixa", "medium": "Média", "high": "Alta", "turbo": "Turbo"}
NOMES_OPCIONAL = {"off": "Desligado", "sleep": "Dormir", "quiet": "Silencioso", "speed": "Rápido",
                  "windFree": "WindFree", "windFreeSleep": "WindFree noturno", "energySaving": "Econômico",
                  "smart": "Inteligente", "comfort": "Conforto"}
NOMES_OSCILACAO = {"fixed": "Fixa", "vertical": "Vertical", "horizontal": "Horizontal", "all": "Todas",
                   "off": "Desligada", "swing": "Vai e vem"}

# A SmartThings demora um pouco para refletir o comando no /status.
RELER_APOS_MS = 2500
QUADRO_MS = 110
ILUSTRACAO = (300, 168)


@lru_cache(maxsize=64)
def _imagem_ar(ligado: bool, temperatura: str, quadro: int) -> ctk.CTkImage:
    img = desenhos.ar_condicionado(ligado, temperatura, quadro)
    return ctk.CTkImage(light_image=img, dark_image=img, size=ILUSTRACAO)


def _opcoes(valores: list[str], nomes: dict[str, str]) -> dict[str, str]:
    return {nomes.get(v, v): v for v in valores}


class PainelAr(PainelBase):
    dispositivo: ArCondicionado | None

    def __init__(self, master, worker, mostrar_status):
        super().__init__(master, "Ar-condicionado", worker, mostrar_status)
        self._ligado = False
        self._alvo: float | None = None
        self._faixa = (16.0, 30.0, 1.0)
        self._quadro = 0

        self.ilustracao = ctk.CTkLabel(self.card, text="", image=_imagem_ar(False, "", 0))
        self.ilustracao.pack(pady=(6, 0))

        # Temperatura alvo e ambiente
        linha = ctk.CTkFrame(self.card, fg_color="transparent")
        linha.pack(fill="x", padx=20)
        alvo = ctk.CTkFrame(linha, fg_color="transparent")
        alvo.pack(side="left")
        self.rotulo_alvo = ctk.CTkLabel(alvo, text="–", font=tema.fonte_display(54), text_color=tema.TEXTO,
                                        height=60)
        self.rotulo_alvo.pack(side="left")
        ctk.CTkLabel(alvo, text="°C", font=tema.fonte(15), text_color=tema.TEXTO_SUAVE).pack(
            side="left", anchor="s", padx=(4, 0), pady=(0, 6))
        ambiente = ctk.CTkFrame(linha, fg_color="transparent")
        ambiente.pack(side="right")
        ctk.CTkLabel(ambiente, text="NO AMBIENTE", font=tema.fonte(10, "bold"), text_color=tema.TEXTO_SUAVE,
                     height=14, anchor="e").pack(fill="x")
        self.rotulo_ambiente = ctk.CTkLabel(ambiente, text="– °C", font=tema.fonte(20), text_color=tema.TEXTO,
                                            anchor="e")
        self.rotulo_ambiente.pack(fill="x")

        # Slider com − e +
        controle = ctk.CTkFrame(self.card, fg_color="transparent")
        controle.pack(fill="x", padx=16, pady=(8, 0))
        self.botao_menos = BotaoIcone(controle, tema.ICONE_MENOS, lambda: self._passo(-1), tamanho=34,
                                      tamanho_icone=12)
        self.botao_menos.pack(side="left")
        self.botao_mais = BotaoIcone(controle, tema.ICONE_MAIS, lambda: self._passo(+1), tamanho=34,
                                     tamanho_icone=12)
        self.botao_mais.pack(side="right")
        self.slider = ctk.CTkSlider(controle, from_=16, to=30, number_of_steps=14, height=18,
                                    progress_color=tema.DESTAQUE, button_color=tema.DESTAQUE,
                                    button_hover_color=tema.DESTAQUE_HOVER, fg_color=tema.TRILHO,
                                    command=self._slider_movido)
        self.slider.pack(side="left", fill="x", expand=True, padx=10)
        limites = ctk.CTkFrame(self.card, fg_color="transparent")
        limites.pack(fill="x", padx=62)
        self.rotulo_min = ctk.CTkLabel(limites, text="16°", font=tema.fonte(10), text_color=tema.TEXTO_SUAVE, height=14)
        self.rotulo_min.pack(side="left")
        self.rotulo_max = ctk.CTkLabel(limites, text="30°", font=tema.fonte(10), text_color=tema.TEXTO_SUAVE, height=14)
        self.rotulo_max.pack(side="right")
        self._enviar_alvo = Atrasador(self, 900, self._mandar_alvo)

        # Blocos de modo, ventilação e extras
        grade = ctk.CTkFrame(self.card, fg_color="transparent")
        grade.pack(fill="x", padx=16, pady=(12, 0))
        self.bloco_modo = Bloco(grade, tema.ICONE_FLOCO, "Modo", self._modo_escolhido)
        self.bloco_ventilador = Bloco(grade, tema.ICONE_VENTILADOR, "Ventilação", self._ventilador_escolhido)
        self.bloco_opcional = Bloco(grade, tema.ICONE_LUA, "Dormir", self._opcional_escolhido)
        self.bloco_oscilacao = Bloco(grade, tema.ICONE_OSCILAR, "Oscilação", self._oscilacao_escolhida)
        self._blocos = [self.bloco_modo, self.bloco_ventilador, self.bloco_opcional, self.bloco_oscilacao]
        for i, bloco in enumerate(self._blocos):
            bloco.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0 if i == 3 else 4))
            grade.grid_columnconfigure(i, weight=1, uniform="bloco")

        self.dica = ctk.CTkLabel(self.card, text="", font=tema.fonte(11), text_color=tema.TEXTO_SUAVE, anchor="w",
                                 height=18)
        self.dica.pack(fill="x", padx=20, pady=(10, 14))

        self._animar()

    # --- estado vindo do aparelho ---

    def aplicar_estado(self, e: EstadoAr) -> None:
        self._ligado = e.ligado
        if e.rotulo:
            self.rotulo_nome.configure(text=e.rotulo)
        self.definir_situacao("Ligado" if e.ligado else "Desligado")
        self.botao_energia.destacar(e.ligado)

        self.rotulo_ambiente.configure(
            text=f"{e.temperatura_ambiente:g} °C" if e.temperatura_ambiente is not None else "– °C")
        minimo, maximo, passo = e.faixa_alvo
        if (minimo, maximo, passo) != self._faixa:
            self._faixa = (minimo, maximo, passo)
            self.slider.configure(from_=minimo, to=maximo, number_of_steps=max(1, round((maximo - minimo) / passo)))
            self.rotulo_min.configure(text=f"{minimo:g}°")
            self.rotulo_max.configure(text=f"{maximo:g}°")
        self._alvo = e.temperatura_alvo
        self._mostrar_alvo()

        self.bloco_modo.definir(_opcoes(e.modos, NOMES_MODO), NOMES_MODO.get(e.modo, e.modo),
                                ICONES_MODO.get(e.modo, tema.ICONE_FLOCO))
        self.bloco_ventilador.definir(_opcoes(e.ventiladores, NOMES_VENTILADOR),
                                      NOMES_VENTILADOR.get(e.ventilador, e.ventilador))
        self.bloco_opcional.definir(_opcoes(e.modos_opcionais, NOMES_OPCIONAL),
                                    NOMES_OPCIONAL.get(e.modo_opcional, e.modo_opcional))
        self.bloco_oscilacao.definir(_opcoes(e.oscilacoes, NOMES_OSCILACAO),
                                     NOMES_OSCILACAO.get(e.oscilacao, e.oscilacao))
        self._habilitar_ajustes(e.ligado)

    def habilitar(self, ativo: bool) -> None:
        self.botao_energia.configure(state="normal" if ativo else "disabled")
        self._habilitar_ajustes(ativo and self._ligado)

    def _habilitar_ajustes(self, ativo: bool) -> None:
        estado = "normal" if ativo else "disabled"
        for w in (self.slider, self.botao_menos, self.botao_mais):
            w.configure(state=estado)
        self.slider.configure(progress_color=tema.DESTAQUE if ativo else tema.TEXTO_APAGADO)
        self.rotulo_alvo.configure(text_color=tema.TEXTO if ativo else tema.TEXTO_SUAVE)
        for bloco in self._blocos:
            bloco.habilitar(ativo)
        self.dica.configure(text="" if ativo else "Ligue o aparelho para ajustar temperatura e ventilação.")

    # --- animação do fluxo de ar ---

    def _animar(self) -> None:
        if self._ligado:
            self._quadro = (self._quadro + 1) % desenhos.QUADROS_VENTO
        temperatura = f"{self._alvo:g}" if self._alvo is not None else ""
        self.ilustracao.configure(image=_imagem_ar(self._ligado, temperatura, self._quadro if self._ligado else 0))
        self.after(QUADRO_MS, self._animar)

    # --- ações do usuário ---

    def _energia(self) -> None:
        if self._ligado:
            self.comando(self.dispositivo.desligar, "Ar-condicionado desligado", RELER_APOS_MS)
        else:
            self.comando(self.dispositivo.ligar, "Ar-condicionado ligado", RELER_APOS_MS)
        # resposta visual imediata; a releitura confirma depois
        self._ligado = not self._ligado
        self.botao_energia.destacar(self._ligado)
        self.definir_situacao("Ligando…" if self._ligado else "Desligando…")

    def _passo(self, direcao: int) -> None:
        if self._alvo is None:
            return
        minimo, maximo, passo = self._faixa
        self._alvo = max(minimo, min(maximo, self._alvo + direcao * passo))
        self.registrar_interacao()
        self._mostrar_alvo()
        self._enviar_alvo.disparar()  # vários cliques seguidos viram um único comando

    def _slider_movido(self, valor: float) -> None:
        self._alvo = round(valor / self._faixa[2]) * self._faixa[2]
        self.registrar_interacao()
        self.rotulo_alvo.configure(text=f"{self._alvo:g}")
        self._enviar_alvo.disparar()

    def _mostrar_alvo(self) -> None:
        self.rotulo_alvo.configure(text=f"{self._alvo:g}" if self._alvo is not None else "–")
        if self._alvo is not None:
            self.slider.set(self._alvo)

    def _mandar_alvo(self) -> None:
        valor = self._alvo
        self.comando(lambda: self.dispositivo.definir_temperatura(valor), f"Temperatura alvo em {valor:g} °C",
                     RELER_APOS_MS)

    def _modo_escolhido(self, modo: str) -> None:
        self.comando(lambda: self.dispositivo.definir_modo(modo), f"Modo: {NOMES_MODO.get(modo, modo)}",
                     RELER_APOS_MS)

    def _ventilador_escolhido(self, velocidade: str) -> None:
        self.comando(lambda: self.dispositivo.definir_ventilador(velocidade),
                     f"Ventilação: {NOMES_VENTILADOR.get(velocidade, velocidade)}", RELER_APOS_MS)

    def _opcional_escolhido(self, modo: str) -> None:
        self.comando(lambda: self.dispositivo.definir_modo_opcional(modo),
                     f"Modo extra: {NOMES_OPCIONAL.get(modo, modo)}", RELER_APOS_MS)

    def _oscilacao_escolhida(self, modo: str) -> None:
        self.comando(lambda: self.dispositivo.definir_oscilacao(modo),
                     f"Oscilação: {NOMES_OSCILACAO.get(modo, modo)}", RELER_APOS_MS)
