"""Mini painel da bandeja: janela pequena, sem moldura, que abre colada na bandeja.

Abre com um clique no ícone da bandeja e some ao perder o foco (clicar fora), como
os painéis rápidos do próprio Windows. Para o app completo, há o botão de expandir.
"""

import ctypes
import logging
import sys
import time
from ctypes import wintypes
from pathlib import Path

import webview

log = logging.getLogger(__name__)

WEB = Path(__file__).resolve().parent / "web"
LARGURA, ALTURA = 340, 264
MARGEM = 12  # distância da barra de tarefas e da borda da tela
# Clicar no ícone da bandeja com o painel aberto: o painel perde o foco (e some) um
# instante antes do clique chegar. Sem esta janela de tempo, ele reabriria na hora.
IGNORAR_CLIQUE_APOS_ESCONDER_S = 0.5


def posicao(largura: int, altura: int) -> tuple[int, int]:
    """Canto da área de trabalho junto à barra de tarefas, em pixels lógicos (os do pywebview)."""
    if sys.platform != "win32":
        return 100, 100
    u = ctypes.windll.user32
    area = wintypes.RECT()
    u.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0)  # SPI_GETWORKAREA (pixels físicos)
    escala = u.GetDpiForSystem() / 96
    largura_tela = u.GetSystemMetrics(0)
    x = area.right / escala - largura - MARGEM
    y = area.bottom / escala - altura - MARGEM
    if area.top > 0:  # barra de tarefas em cima
        y = area.top / escala + MARGEM
    if area.left > 0 and area.right >= largura_tela:  # barra de tarefas à esquerda
        x = area.left / escala + MARGEM
    return int(x), int(y)


def _moldura() -> tuple[int, int]:
    """Quanto a janela sem moldura "perde" do tamanho pedido ao pywebview (pixels lógicos).

    O pywebview dimensiona como se houvesse a moldura padrão do Windows (bordas + barra de
    título) e depois a esconde; o que sobra visível fica menor. Somamos isso de volta.
    """
    if sys.platform != "win32":
        return 0, 0
    u = ctypes.windll.user32
    escala = u.GetDpiForSystem() / 96
    borda_x = u.GetSystemMetrics(32) + u.GetSystemMetrics(92)  # SM_CXSIZEFRAME + SM_CXPADDEDBORDER
    borda_y = u.GetSystemMetrics(33) + u.GetSystemMetrics(92)  # SM_CYSIZEFRAME + SM_CXPADDEDBORDER
    titulo = u.GetSystemMetrics(4)  # SM_CYCAPTION
    return round(2 * borda_x / escala), round((2 * borda_y + titulo) / escala)


class PainelRapido:
    def __init__(self, api, fundo: str):
        x, y = posicao(LARGURA, ALTURA)
        extra_l, extra_a = _moldura()
        # Já nasce na posição certa: no pywebview, move() só roda depois que a janela foi exibida.
        self.janela = webview.create_window(
            "Mothlit · controles rápidos", url=str(WEB / "flyout.html"), js_api=api,
            width=LARGURA + extra_l, height=ALTURA + extra_a, x=x, y=y, resizable=False, frameless=True, easy_drag=False,
            background_color=fundo, hidden=True, on_top=True,
        )
        self.visivel = False
        self._escondido_em = 0.0
        self._nativo_configurado = False

    # --- abrir / fechar ---

    def alternar(self) -> None:
        """Clique no ícone da bandeja."""
        if self.visivel:
            self.esconder()
        elif time.monotonic() - self._escondido_em >= IGNORAR_CLIQUE_APOS_ESCONDER_S:
            self.mostrar()

    def mostrar(self) -> None:
        self._fora_da_barra_de_tarefas()
        self.janela.show()
        self.visivel = True
        self.janela.move(*posicao(LARGURA, ALTURA))  # caso a tela/barra tenha mudado desde a criação
        self._configurar_nativo()
        try:
            ctypes.windll.user32.SetForegroundWindow(self.janela.native.Handle.ToInt32())
        except Exception:
            pass
        self.janela.evaluate_js("window.aoMostrar && aoMostrar()")

    def esconder(self) -> None:
        if not self.visivel:
            return
        self.visivel = False
        self._escondido_em = time.monotonic()
        self.janela.hide()

    def destruir(self) -> None:
        """Fecha o painel junto com o app (senão o webview.start nunca retorna).

        Não usa janela.destroy(): no pywebview ele espera a janela ter sido exibida, e o
        painel pode nunca ter sido aberto. Fecha o formulário nativo, de forma assíncrona.
        """
        try:
            from System import Action

            nativo = self.janela.native
            nativo.BeginInvoke(Action(nativo.Close))
        except Exception:
            log.debug("Painel já fechado", exc_info=True)

    # --- janela nativa (WinForms) ---

    def _fora_da_barra_de_tarefas(self) -> None:
        """WS_EX_TOOLWINDOW: sem botão na barra de tarefas e fora do Alt+Tab, como os painéis do Windows.

        (Não usar ShowInTaskbar do WinForms: ele recria a janela e derruba o WebView2 dentro dela.)
        """
        if sys.platform != "win32":
            return
        try:
            nativo = self.janela.native
            if not nativo.IsHandleCreated:
                return
            u = ctypes.windll.user32
            u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
            hwnd = nativo.Handle.ToInt32()
            estilo = u.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            u.SetWindowLongW(hwnd, -20, (estilo | 0x80) & ~0x40000)  # +TOOLWINDOW, -APPWINDOW
        except Exception:
            log.debug("Não consegui tirar o painel da barra de tarefas", exc_info=True)

    def _configurar_nativo(self) -> None:
        """Uma vez: cantos arredondados e fechar ao perder o foco (Deactivate do formulário)."""
        if self._nativo_configurado:
            return
        try:
            from .app import _cantos_arredondados

            _cantos_arredondados(self.janela)
            self.janela.native.Deactivate += lambda *_: self.esconder()
            self._nativo_configurado = True
        except Exception:
            log.debug("Configuração nativa do painel indisponível", exc_info=True)
