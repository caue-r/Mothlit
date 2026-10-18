"""Janela do Mothlit com pywebview (WebView2 no Windows).

A interface é HTML/CSS/JS em `web/`. O JavaScript chama os métodos públicos de
`Api` (`pywebview.api.<metodo>()`); o pywebview executa cada chamada numa thread
separada, então a rede nunca trava a interface. Toda resposta é um dict simples:
`{"ok": True, "dados": ...}` ou `{"ok": False, "erro": "mensagem amigável"}`.
"""

import ctypes
import json
import logging
import threading
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable

import webview

from .. import config, inicializacao
from ..config import ErroConfiguracao
from ..devices import (
    ArCondicionado,
    ErroDispositivo,
    EstadoAr,
    EstadoLampada,
    Lampada,
    criar_ar,
    criar_auth_smartthings,
    criar_lampada,
)
from ..devices.smartthings import AuthPAT, SmartThingsClient
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
        self._saindo = False
        self._painel = None  # mini painel da bandeja (ui.flyout.PainelRapido)
        self._abrir_completo: Callable[[str | None], None] | None = None
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
        auth = criar_auth_smartthings()
        return {"ok": True, "dados": {
            "lampadaIp": cfg.lampada_ip or "–",
            "lampadaVersao": cfg.lampada_versao,
            "arId": cfg.ar_device_id or "–",
            "env": str(config.caminho_env()),
            "smartthings": {
                "tipo": getattr(auth, "tipo", None),
                "expiraEm": getattr(auth, "expira_em", None),  # só no OAuth (epoch em segundos)
            },
        }}

    def trocar_token_smartthings(self, token: str):
        """Plano B: cola um token pessoal (PAT) novo. Valida na SmartThings antes de salvar."""
        token = (token or "").strip()
        if not token:
            return {"ok": False, "erro": "Cole o token antes de salvar."}
        cfg = config.carregar()
        cliente = SmartThingsClient(AuthPAT(token))
        try:
            if cfg.ar_device_id:
                cliente.dispositivo(cfg.ar_device_id)
            else:
                cliente.listar_dispositivos()
        except ErroDispositivo as e:
            return {"ok": False, "erro": f"Token não aceito: {e}"}
        finally:
            cliente.fechar()
        config.salvar_segredo(config.SEGREDO_SMARTTHINGS_PAT, token)
        config.apagar_segredo_json(config.SEGREDO_SMARTTHINGS_OAUTH)  # passa a usar o PAT
        self._ar, self._erro_ar = _criar(criar_ar)
        return self.configuracoes()

    def minimizar(self):
        """Vai para a bandeja: some da tela e da barra de tarefas."""
        if self._janela:
            self._janela.hide()

    def fechar(self):
        """Botão ×: vai para a bandeja ou encerra, conforme a preferência."""
        if config.ler_preferencias()["fechar_para_bandeja"]:
            self.minimizar()
            return {"ok": True, "dados": "bandeja"}
        self.sair()
        return {"ok": True, "dados": "saiu"}

    def esconder_flyout(self):
        """O mini painel perdeu o foco (ou Esc)."""
        if self._painel:
            self._painel.esconder()

    def abrir_completo(self, aba: str | None = None):
        """Botão de expandir / setas do mini painel: abre a janela completa, opcionalmente numa aba."""
        self.esconder_flyout()
        if self._abrir_completo:
            self._abrir_completo(aba)

    def sair(self):
        """Encerra de verdade (menu da bandeja), ignorando a preferência de fechar para a bandeja."""
        self._saindo = True
        if self._janela:
            self._janela.destroy()

    def preferencias(self):
        prefs = config.ler_preferencias()
        return {"ok": True, "dados": {
            "iniciarComSistema": inicializacao.ativo(),
            "iniciarSuportado": inicializacao.suportado(),
            "fecharParaBandeja": bool(prefs["fechar_para_bandeja"]),
        }}

    def definir_preferencia(self, nome: str, valor: bool):
        try:
            if nome == "iniciarComSistema":
                inicializacao.definir(bool(valor))
            elif nome == "fecharParaBandeja":
                config.salvar_preferencia("fechar_para_bandeja", bool(valor))
            else:
                return {"ok": False, "erro": f"Preferência desconhecida: {nome}"}
        except OSError as e:
            return {"ok": False, "erro": f"Não consegui salvar a preferência: {e}"}
        return self.preferencias()

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
_MUTEX = "Local\\Mothlit.InstanciaUnica"
_EVENTO_MOSTRAR = "Local\\Mothlit.Mostrar"
_EVENTO_SAIR = "Local\\Mothlit.Sair"  # o instalador pede para o app sair antes de atualizar
_handles = []  # mutex e evento vivem enquanto o processo existir


def _kernel32():
    k = ctypes.windll.kernel32
    for funcao in (k.CreateMutexW, k.CreateEventW, k.OpenEventW):
        funcao.restype = wintypes.HANDLE
    k.SetEvent.argtypes = [wintypes.HANDLE]
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k


def _ja_aberto(trazer_janela: bool = True) -> bool:
    """Instância única. Se o Mothlit já estiver rodando, pede para ele aparecer e devolve True.

    O pedido vai por um evento nomeado do Windows (não por FindWindow), porque a janela
    de quem iniciou escondido na bandeja ainda nem existe para o sistema.
    """
    if sys.platform != "win32":
        return False
    k = _kernel32()
    _handles.append(k.CreateMutexW(None, False, _MUTEX))
    if k.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return False
    if trazer_janela:
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY: deixa a outra instância vir para a frente
        evento = k.OpenEventW(0x0002, False, _EVENTO_MOSTRAR)  # EVENT_MODIFY_STATE
        if evento:
            k.SetEvent(evento)
            k.CloseHandle(evento)
    return True


def _atender_evento(nome: str, acao: Callable[[], None], descricao: str) -> None:
    """Thread que espera um evento nomeado do Windows (outra instância, ou o instalador) e executa `acao`."""
    if sys.platform != "win32":
        return
    k = _kernel32()
    evento = k.CreateEventW(None, False, False, nome)  # auto-reset
    _handles.append(evento)

    def esperar():
        while k.WaitForSingleObject(evento, 0xFFFFFFFF) == 0:  # INFINITE / WAIT_OBJECT_0
            log.info("Pedido recebido: %s", descricao)
            try:
                acao()
            except Exception:
                log.exception("Falha ao atender o pedido: %s", descricao)

    threading.Thread(target=esperar, name=f"evento-{descricao}", daemon=True).start()

def executar(na_bandeja: bool = False) -> None:
    """Abre a janela. `na_bandeja`: começa escondida (usado ao iniciar com o Windows)."""
    from ..tray import Bandeja
    from .flyout import PainelRapido

    if _ja_aberto(trazer_janela=not na_bandeja):
        return
    debug = bool(os.environ.get("MOTHLIT_DEBUG"))
    import keyring

    from .. import __version__

    log.info("Mothlit %s iniciando (executável: %s, bandeja: %s, keyring: %s)", __version__,
             getattr(sys, "frozen", False), na_bandeja, type(keyring.get_keyring()).__name__)
    api = Api.da_configuracao()
    log.info("Lâmpada: %s | Ar: %s (%s)", "ok" if api._lampada else api._erro_lampada,
             "ok" if api._ar else api._erro_ar, getattr(criar_auth_smartthings(), "tipo", None))
    janela = webview.create_window(
        TITULO, url=str(WEB / "index.html"), js_api=api, width=LARGURA, height=ALTURA,
        resizable=False, frameless=True, easy_drag=False, background_color=FUNDO, hidden=na_bandeja,
    )
    api._janela = janela

    def mostrar() -> None:
        janela.show()
        janela.restore()
        _cantos_arredondados(janela)
        try:
            ctypes.windll.user32.SetForegroundWindow(janela.native.Handle.ToInt32())
        except Exception:
            pass
        janela.evaluate_js("window.aoRestaurar && aoRestaurar()")  # fade-in e dados frescos

    def ao_fechar():
        # Alt+F4 também respeita "minimizar na bandeja ao fechar"; "Sair" na bandeja não.
        if not api._saindo and config.ler_preferencias()["fechar_para_bandeja"]:
            janela.hide()
            return False
        return True

    painel = PainelRapido(api, FUNDO)
    api._painel = painel

    def abrir_completo(aba: str | None = None) -> None:
        mostrar()
        if aba in ("clima", "luz"):
            janela.evaluate_js(f"window.selecionarAba && selecionarAba({json.dumps(aba)})")

    api._abrir_completo = abrir_completo

    bandeja = Bandeja(
        api,
        ao_abrir=mostrar,
        ao_clicar=painel.alternar,
        ao_sair=api.sair,
        ao_alterar=lambda: janela.evaluate_js("window.atualizarTudo && atualizarTudo()"),
    )
    api._ao_mudar = bandeja.atualizar_menu

    janela.events.closing += ao_fechar
    _atender_evento(_EVENTO_MOSTRAR, mostrar, "mostrar a janela")
    _atender_evento(_EVENTO_SAIR, api.sair, "sair para atualizar")
    janela.events.shown += lambda: _cantos_arredondados(janela)
    janela.events.loaded += lambda: log.info("Interface carregada")
    janela.events.restored += lambda: janela.evaluate_js("window.aoRestaurar && aoRestaurar()")
    janela.events.closed += bandeja.parar
    janela.events.closed += painel.destruir  # sem isso o webview.start não retorna
    bandeja.iniciar()
    webview.start(debug=debug, icon=str(marca.arquivo_ico()))