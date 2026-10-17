"""Janela do Mothlit com pywebview (WebView2 no Windows).

A interface é HTML/CSS/JS em `web/`. O JavaScript chama os métodos públicos de
`Api` (`pywebview.api.<metodo>()`); o pywebview executa cada chamada numa thread
separada, então a rede nunca trava a interface. Toda resposta é um dict simples:
`{"ok": True, "dados": ...}` ou `{"ok": False, "erro": "mensagem amigável"}`.
"""

import ctypes
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

import webview

from .. import config
from ..config import ErroConfiguracao
from ..devices import ArCondicionado, ErroDispositivo, EstadoAr, EstadoLampada, Lampada, criar_ar, criar_lampada
from . import marca

WEB = Path(__file__).resolve().parent / "web"
LARGURA, ALTURA = 420, 760
FUNDO = "#09090b"

log = logging.getLogger(__name__)


def _ar_dict(e: EstadoAr) -> dict[str, Any]:
    return {
        "nome": e.rotulo,
        "ligado": e.ligado,
        "alvo": e.temperatura_alvo,
        "faixa": list(e.faixa_alvo),
        "ambiente": e.temperatura_ambiente,
        "modo": e.modo,
        "modos": e.modos,
        "ventilador": e.ventilador,
        "ventiladores": e.ventiladores,
        "opcional": e.modo_opcional,
        "opcionais": e.modos_opcionais,
        "oscilacao": e.oscilacao,
        "oscilacoes": e.oscilacoes,
    }


def _luz_dict(e: EstadoLampada, nome: str) -> dict[str, Any]:
    return {
        "nome": nome,
        "ligada": e.ligada,
        "modo": e.modo,
        "brilho": e.brilho,
        "temperatura": e.temperatura_cor,
        "hsv": list(e.cor_hsv) if e.cor_hsv else None,
        "suportaCor": e.suporta_cor,
        "suportaTemperatura": e.suporta_temperatura,
    }


def _criar(fabrica):
    try:
        return fabrica(), None
    except ErroConfiguracao as e:
        return None, str(e)


class Api:
    """Métodos chamados pelo JavaScript. Atributos privados (com _) não são expostos."""

    def __init__(self, lampada: Lampada | None = None, ar: ArCondicionado | None = None,
                 erro_lampada: str | None = None, erro_ar: str | None = None):
        self._lampada, self._erro_lampada = lampada, erro_lampada
        self._ar, self._erro_ar = ar, erro_ar
        self._janela = None
        # último liga/desliga conhecido de cada aparelho (usado no menu da bandeja)
        self._ligado: dict[str, bool | None] = {"ar": None, "luz": None}
        self._ao_mudar: Callable[[], None] | None = None

    @classmethod
    def da_configuracao(cls) -> "Api":
        lampada, erro_lampada = _criar(criar_lampada)
        ar, erro_ar = _criar(criar_ar)
        return cls(lampada, ar, erro_lampada, erro_ar)

    # --- ar-condicionado ---

    def estado_ar(self):
        r = self._usar_ar(lambda ar: _ar_dict(ar.estado()))
        if r["ok"]:
            self._lembrar("ar", r["dados"]["ligado"])
        return r

    def ar_ligar(self, ligar: bool):
        r = self._usar_ar(lambda ar: ar.ligar() if ligar else ar.desligar())
        if r["ok"]:
            self._lembrar("ar", bool(ligar))
        return r

    def alternar_ar(self):
        """Lê o estado atual e inverte (usado pela bandeja)."""
        return self._alternar("ar", self.estado_ar, self.ar_ligar)

    def ar_temperatura(self, valor: float):
        return self._usar_ar(lambda ar: ar.definir_temperatura(float(valor)))

    def ar_modo(self, modo: str):
        return self._usar_ar(lambda ar: ar.definir_modo(str(modo)))

    def ar_ventilador(self, velocidade: str):
        return self._usar_ar(lambda ar: ar.definir_ventilador(str(velocidade)))

    def ar_opcional(self, modo: str):
        return self._usar_ar(lambda ar: ar.definir_modo_opcional(str(modo)))

    def ar_oscilacao(self, modo: str):
        return self._usar_ar(lambda ar: ar.definir_oscilacao(str(modo)))

    # --- lâmpada ---

    def estado_luz(self):
        r = self._usar_luz(lambda luz: _luz_dict(luz.estado(), luz.nome))
        if r["ok"]:
            self._lembrar("luz", r["dados"]["ligada"])
        return r

    def luz_ligar(self, ligar: bool):
        r = self._usar_luz(lambda luz: luz.ligar() if ligar else luz.desligar())
        if r["ok"]:
            self._lembrar("luz", bool(ligar))
        return r

    def alternar_luz(self):
        """Lê o estado atual e inverte (usado pela bandeja)."""
        return self._alternar("luz", self.estado_luz, self.luz_ligar)

    def luz_brilho(self, porcentagem: int):
        return self._usar_luz(lambda luz: luz.definir_brilho(round(porcentagem)))

    def luz_temperatura(self, porcentagem: int):
        return self._usar_luz(lambda luz: luz.definir_temperatura_cor(round(porcentagem)))

    def luz_hsv(self, h: float, s: float, v: float):
        return self._usar_luz(lambda luz: luz.definir_hsv(h, s, v))

    def ultimo_ligado(self, qual: str) -> bool | None:
        """Último liga/desliga conhecido ("ar" ou "luz"), sem ir à rede."""
        return self._ligado.get(qual)

    # --- janela e configuração ---

    def configuracoes(self):
        cfg = config.carregar()
        return {"ok": True, "dados": {
            "lampadaIp": cfg.lampada_ip or "–",
            "lampadaVersao": cfg.lampada_versao,
            "arId": cfg.ar_device_id or "–",
            "env": str(config.caminho_env()),
        }}

    def minimizar(self):
        """Vai para a bandeja: some da tela e da barra de tarefas."""
        if self._janela:
            self._janela.hide()

    def fechar(self):
        if self._janela:
            self._janela.destroy()

    # --- internos ---

    def _lembrar(self, qual: str, ligado: bool) -> None:
        if self._ligado[qual] != ligado:
            self._ligado[qual] = ligado
            if self._ao_mudar:
                self._ao_mudar()

    @staticmethod
    def _alternar(qual: str, ler, ligar):
        atual = ler()
        if not atual["ok"]:
            return atual
        chave = "ligado" if qual == "ar" else "ligada"
        novo = not atual["dados"][chave]
        r = ligar(novo)
        return {**r, "dados": novo} if r["ok"] else r

    def _usar_ar(self, acao: Callable[[ArCondicionado], Any]):
        return self._executar(self._ar, self._erro_ar, acao)

    def _usar_luz(self, acao: Callable[[Lampada], Any]):
        return self._executar(self._lampada, self._erro_lampada, acao)

    @staticmethod
    def _executar(dispositivo, erro_config, acao):
        if dispositivo is None:
            return {"ok": False, "configurado": False, "erro": erro_config}
        try:
            return {"ok": True, "dados": acao(dispositivo)}
        except ErroDispositivo as e:
            return {"ok": False, "configurado": True, "erro": str(e)}
        except Exception as e:  # nunca deixa a interface sem resposta
            log.exception("Erro inesperado")
            return {"ok": False, "configurado": True, "erro": f"Erro inesperado: {e}"}


def _cantos_arredondados(janela) -> None:
    """Windows 11: cantos arredondados e borda discreta na janela sem moldura."""
    if sys.platform != "win32":
        return
    try:
        hwnd = janela.native.Handle.ToInt32()
        for atributo, valor in ((33, 2), (34, 0x00272422)):  # CORNER_PREFERENCE=ROUND, BORDER_COLOR (0x00BBGGRR)
            v = ctypes.c_int(valor)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:  # cosmético: sem isso a janela só fica com cantos retos
        log.debug("Não consegui arredondar os cantos", exc_info=True)


TITULO = "Mothlit"
_mutex = None


def _ja_aberto() -> bool:
    """Instância única: se o Mothlit já estiver rodando (talvez escondido na bandeja), traz a janela dele."""
    if sys.platform != "win32":
        return False
    kernel32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
    # o mutex vive enquanto o processo existir; guardamos a referência no módulo
    global _mutex
    _mutex = kernel32.CreateMutexW(None, False, "Local\\Mothlit.InstanciaUnica")
    if kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return False
    hwnd = user32.FindWindowW(None, TITULO)
    if hwnd:
        user32.ShowWindow(hwnd, 5)  # SW_SHOW (a janela pode estar escondida na bandeja)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
    return True


def executar() -> None:
    from ..tray import Bandeja

    if _ja_aberto():
        return
    debug = bool(os.environ.get("MOTHLIT_DEBUG"))
    api = Api.da_configuracao()
    janela = webview.create_window(
        TITULO, url=str(WEB / "index.html"), js_api=api, width=LARGURA, height=ALTURA,
        resizable=False, frameless=True, easy_drag=False, background_color=FUNDO,
    )
    api._janela = janela

    def mostrar() -> None:
        # prepara o fade-in antes de a janela reaparecer
        janela.evaluate_js("window.aoRestaurar && aoRestaurar()")
        janela.show()
        janela.restore()

    bandeja = Bandeja(
        api,
        ao_abrir=mostrar,
        ao_sair=janela.destroy,
        ao_alterar=lambda: janela.evaluate_js("window.atualizarTudo && atualizarTudo()"),
    )
    api._ao_mudar = bandeja.atualizar_menu

    janela.events.shown += lambda: _cantos_arredondados(janela)
    janela.events.restored += lambda: janela.evaluate_js("window.aoRestaurar && aoRestaurar()")
    janela.events.closed += bandeja.parar
    bandeja.iniciar()
    webview.start(debug=debug, icon=str(marca.arquivo_ico()))