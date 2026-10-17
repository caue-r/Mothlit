"""Peças compartilhadas pelos painéis."""

import time
from typing import Callable

import customtkinter as ctk

from . import tema
from .widgets import BotaoIcone
from .worker import Worker

# Depois que o usuário mexe num controle, ignoramos atualizações de estado por
# alguns segundos para o controle não "pular de volta" antes do aparelho reagir.
JANELA_INTERACAO_S = 4.0


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
    """Card do aparelho (nome, situação, botão de energia) + lógica comum de leitura/comando."""

    def __init__(self, master, nome: str, worker: Worker, mostrar_status: Callable[..., None]):
        super().__init__(master, fg_color="transparent")
        self.worker = worker
        self.mostrar_status = mostrar_status
        self.dispositivo = None
        self.online = False
        self._ultima_interacao = 0.0

        self.card = ctk.CTkFrame(self, fg_color=tema.CARD, corner_radius=18, border_width=1,
                                 border_color=tema.CARD_BORDA)
        self.card.pack(fill="x")

        cabecalho = ctk.CTkFrame(self.card, fg_color="transparent")
        cabecalho.pack(fill="x", padx=18, pady=(16, 4))
        textos = ctk.CTkFrame(cabecalho, fg_color="transparent")
        textos.pack(side="left", fill="x", expand=True)
        self.rotulo_nome = ctk.CTkLabel(textos, text=nome, font=tema.fonte(15, "bold"), text_color=tema.TEXTO,
                                        anchor="w", height=20)
        self.rotulo_nome.pack(fill="x")
        self.rotulo_situacao = ctk.CTkLabel(textos, text="Conectando…", font=tema.fonte(12),
                                            text_color=tema.TEXTO_SUAVE, anchor="w", height=16)
        self.rotulo_situacao.pack(fill="x")
        self.botao_energia = BotaoIcone(cabecalho, tema.ICONE_ENERGIA, self._energia, tamanho=44, tamanho_icone=18)
        self.botao_energia.pack(side="right")

    # --- ciclo de vida ---

    def definir_dispositivo(self, dispositivo, erro: str | None = None) -> None:
        self.dispositivo = dispositivo
        if dispositivo is not None:
            self.rotulo_nome.configure(text=dispositivo.nome)
        else:
            self.definir_situacao("Não configurado", tema.TEXTO_SUAVE)
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
            self.mostrar_status(descricao)
            self.after(reler_apos_ms, self.atualizar)

        self.worker.executar(funcao, ok, self._falhou)

    def registrar_interacao(self) -> None:
        self._ultima_interacao = time.monotonic()

    def definir_situacao(self, texto: str, cor: str = tema.TEXTO_SUAVE) -> None:
        self.rotulo_situacao.configure(text=texto, text_color=cor)

    def _estado_recebido(self, estado) -> None:
        self.online = True
        self.habilitar(True)
        self.mostrar_status(f"Atualizado às {time.strftime('%H:%M')}", sutil=True)
        if time.monotonic() - self._ultima_interacao >= JANELA_INTERACAO_S:
            self.aplicar_estado(estado)

    def _falhou(self, mensagem: str) -> None:
        self.online = False
        self.definir_situacao("● Sem conexão", tema.ERRO)
        self.mostrar_status(mensagem, erro=True)

    # --- implementados pelos painéis ---

    def _energia(self) -> None:
        raise NotImplementedError

    def aplicar_estado(self, estado) -> None:
        raise NotImplementedError

    def habilitar(self, ativo: bool) -> None:
        raise NotImplementedError
