"""Painel do ar-condicionado: liga/desliga, temperatura alvo, modo e ventilador."""

import customtkinter as ctk

from ..devices import ArCondicionado, EstadoAr
from .comum import Atrasador, PainelBase

NOMES_MODO = {
    "auto": "Auto",
    "cool": "Frio",
    "dry": "Desumidificar",
    "wind": "Ventilar",
    "fan": "Ventilar",
    "heat": "Quente",
}
NOMES_VENTILADOR = {
    "auto": "Auto",
    "low": "Baixa",
    "medium": "Média",
    "high": "Alta",
    "turbo": "Turbo",
}

# A SmartThings demora um pouco para refletir o comando no /status.
RELER_APOS_MS = 2500


class PainelAr(PainelBase):
    dispositivo: ArCondicionado | None

    def __init__(self, master, worker, mostrar_status):
        super().__init__(master, "❄ Ar-condicionado", worker, mostrar_status)
        self._alvo: float | None = None
        self._faixa = (16.0, 30.0, 1.0)
        self._modos: dict[str, str] = {}  # nome exibido -> valor da API
        self._ventiladores: dict[str, str] = {}

        linha = ctk.CTkFrame(self.corpo, fg_color="transparent")
        linha.pack(fill="x", pady=(4, 10))
        self.switch = ctk.CTkSwitch(linha, text="Ligado", command=self._alternar)
        self.switch.pack(side="left")
        self.rotulo_ambiente = ctk.CTkLabel(linha, text="Ambiente: –", text_color="gray")
        self.rotulo_ambiente.pack(side="right")

        # Temperatura alvo
        ctk.CTkLabel(self.corpo, text="Temperatura alvo", anchor="w", height=20).pack(fill="x")
        alvo = ctk.CTkFrame(self.corpo, fg_color="transparent")
        alvo.pack(pady=(4, 12))
        self.botao_menos = ctk.CTkButton(alvo, text="−", width=44, height=44, font=ctk.CTkFont(size=22),
                                         command=lambda: self._ajustar_alvo(-1))
        self.botao_menos.pack(side="left")
        self.rotulo_alvo = ctk.CTkLabel(alvo, text="– °C", width=120, font=ctk.CTkFont(size=34, weight="bold"))
        self.rotulo_alvo.pack(side="left", padx=12)
        self.botao_mais = ctk.CTkButton(alvo, text="+", width=44, height=44, font=ctk.CTkFont(size=22),
                                        command=lambda: self._ajustar_alvo(+1))
        self.botao_mais.pack(side="left")
        self._enviar_alvo = Atrasador(self, 900, self._mandar_alvo)

        # Modo e ventilador (opções vêm do aparelho)
        ctk.CTkLabel(self.corpo, text="Modo", anchor="w", height=20).pack(fill="x")
        self.seletor_modo = ctk.CTkSegmentedButton(self.corpo, values=["–"], command=self._modo_escolhido)
        self.seletor_modo.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(self.corpo, text="Ventilador", anchor="w", height=20).pack(fill="x")
        self.seletor_ventilador = ctk.CTkSegmentedButton(
            self.corpo, values=["–"], command=self._ventilador_escolhido
        )
        self.seletor_ventilador.pack(fill="x", pady=(2, 0))

        self._controles = [self.switch, self.botao_menos, self.botao_mais, self.seletor_modo, self.seletor_ventilador]

    # --- estado vindo do aparelho ---

    def aplicar_estado(self, estado: EstadoAr) -> None:
        self.switch.select() if estado.ligado else self.switch.deselect()
        amb = estado.temperatura_ambiente
        self.rotulo_ambiente.configure(text=f"Ambiente: {amb:g} °C" if amb is not None else "Ambiente: –")

        self._faixa = estado.faixa_alvo
        self._alvo = estado.temperatura_alvo
        self._mostrar_alvo()

        self._modos = {NOMES_MODO.get(m, m): m for m in estado.modos}
        self._atualizar_seletor(self.seletor_modo, self._modos, estado.modo, NOMES_MODO)
        self._ventiladores = {NOMES_VENTILADOR.get(v, v): v for v in estado.ventiladores}
        self._atualizar_seletor(self.seletor_ventilador, self._ventiladores, estado.ventilador, NOMES_VENTILADOR)

    @staticmethod
    def _atualizar_seletor(seletor, opcoes: dict[str, str], atual: str | None, nomes: dict[str, str]) -> None:
        seletor.configure(values=list(opcoes) or ["–"])
        seletor.set(nomes.get(atual, atual) if atual else "")

    def habilitar(self, ativo: bool) -> None:
        for controle in self._controles:
            controle.configure(state="normal" if ativo else "disabled")

    # --- ações do usuário ---

    def _alternar(self) -> None:
        if self.switch.get():
            self.comando(self.dispositivo.ligar, "Ar-condicionado ligado", RELER_APOS_MS)
        else:
            self.comando(self.dispositivo.desligar, "Ar-condicionado desligado", RELER_APOS_MS)

    def _ajustar_alvo(self, direcao: int) -> None:
        if self._alvo is None:
            return
        minimo, maximo, passo = self._faixa
        self._alvo = max(minimo, min(maximo, self._alvo + direcao * passo))
        self.registrar_interacao()
        self._mostrar_alvo()
        self._enviar_alvo.disparar()  # vários cliques seguidos viram um único comando

    def _mostrar_alvo(self) -> None:
        self.rotulo_alvo.configure(text=f"{self._alvo:g} °C" if self._alvo is not None else "– °C")

    def _mandar_alvo(self) -> None:
        valor = self._alvo
        self.comando(lambda: self.dispositivo.definir_temperatura(valor), f"Temperatura alvo em {valor:g} °C",
                     RELER_APOS_MS)

    def _modo_escolhido(self, nome: str) -> None:
        modo = self._modos.get(nome)
        if modo:
            self.comando(lambda: self.dispositivo.definir_modo(modo), f"Modo: {nome}", RELER_APOS_MS)

    def _ventilador_escolhido(self, nome: str) -> None:
        velocidade = self._ventiladores.get(nome)
        if velocidade:
            self.comando(lambda: self.dispositivo.definir_ventilador(velocidade), f"Ventilador: {nome}",
                         RELER_APOS_MS)
