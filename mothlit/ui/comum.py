"""Peças compartilhadas pelos painéis."""

import time
from typing import Callable

import customtkinter as ctk

from .worker import Worker

COR_OK = "#3ecf6e"
COR_ERRO = "#e5534b"
COR_NEUTRA = "#8b949e"

# Depois que o usuário mexe num controle, ignoramos atualizações de estado por
# alguns segundos para o controle não "pular de volta" antes do aparelho reagir.
JANELA_INTERACAO_S = 4.0


class Indicador(ctk.CTkLabel):
    """Bolinha colorida + texto de conexão."""

    def __init__(self, master):
        super().__init__(master, text="", anchor="e")
        self.definir("carregando")

    def definir(self, situacao: str) -> None:
        texto, cor = {
            "conectado": ("● Conectado", COR_OK),
            "erro": ("● Sem conexão", COR_ERRO),
            "carregando": ("● Conectando…", COR_NEUTRA),
            "nao_configurado": ("● Não configurado", COR_NEUTRA),
        }[situacao]
        self.configure(text=texto, text_color=cor)


class Atrasador:
    """Agrupa eventos rápidos (arrastar slider, cliques em −/+) num único envio."""

    def __init__(self, widget, atraso_ms: int, acao: Callable[[], None]):
        self._widget = widget
        self._atraso = atraso_ms
        self._acao = acao
        self._agendado = None

    def disparar(self) -> None:
        if self._agendado:
            self._widget.after_cancel(self._agendado)
        self._agendado = self._widget.after(self._atraso, self._executar)

    def _executar(self) -> None:
        self._agendado = None
        self._acao()


class PainelBase(ctk.CTkFrame):
    """Moldura com título, indicador e a lógica comum de leitura/comando."""

    def __init__(self, master, titulo: str, worker: Worker, mostrar_status: Callable[..., None]):
        super().__init__(master, corner_radius=12)
        self.worker = worker
        self.mostrar_status = mostrar_status
        self.dispositivo = None
        self._ultima_interacao = 0.0

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(topo, text=titulo, font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        self.indicador = Indicador(topo)
        self.indicador.pack(side="right")

        self.corpo = ctk.CTkFrame(self, fg_color="transparent")
        self.corpo.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    def definir_dispositivo(self, dispositivo, erro: str | None = None) -> None:
        self.dispositivo = dispositivo
        if dispositivo is None:
            self.indicador.definir("nao_configurado")
            self.habilitar(False)
            if erro:
                self.mostrar_status(erro, erro=True)

    def atualizar(self) -> None:
        if self.dispositivo is None:
            return
        self.worker.executar(self.dispositivo.estado, self._estado_recebido, self._falhou)

    def comando(self, funcao: Callable[[], object], descricao: str, reler_apos_ms: int = 800) -> None:
        """Envia um comando em segundo plano e relê o estado depois."""
        if self.dispositivo is None:
            return
        self.registrar_interacao()
        marca = self._ultima_interacao

        def ok(_):
            # Comando confirmado: se o usuário não mexeu de novo, a releitura pode ser aplicada.
            if self._ultima_interacao == marca:
                self._ultima_interacao = 0.0
            self.indicador.definir("conectado")
            self.mostrar_status(descricao)
            self.after(reler_apos_ms, self.atualizar)

        self.worker.executar(funcao, ok, self._falhou)

    def registrar_interacao(self) -> None:
        self._ultima_interacao = time.monotonic()

    def _estado_recebido(self, estado) -> None:
        self.indicador.definir("conectado")
        self.habilitar(True)
        if time.monotonic() - self._ultima_interacao >= JANELA_INTERACAO_S:
            self.aplicar_estado(estado)

    def _falhou(self, mensagem: str) -> None:
        self.indicador.definir("erro")
        self.mostrar_status(mensagem, erro=True)

    # implementados pelos painéis
    def aplicar_estado(self, estado) -> None:
        raise NotImplementedError

    def habilitar(self, ativo: bool) -> None:
        raise NotImplementedError
