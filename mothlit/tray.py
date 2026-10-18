"""Ícone na bandeja do sistema com ações rápidas (pystray).

O pystray roda numa thread própria (seguro no Windows). As ações que usam a rede
rodam em outra thread, para o menu da bandeja nunca travar.
"""

import ctypes
import logging
import sys
import threading
from typing import Callable

import pystray

from .ui import marca

log = logging.getLogger(__name__)


class _IconeNitido(pystray.Icon):
    """pystray.Icon que entrega ao Windows o ícone no tamanho exato da bandeja.

    O pystray carrega o ícone no tamanho padrão (32 px) e o Windows reduz para a bandeja
    (16 px a 100%), o que deixa a mariposa menor e borrada. Aqui carregamos do nosso .ico
    multi-tamanho o quadro do tamanho certo (SM_CXSMICON, que já considera o zoom da tela).
    Se algo falhar, cai no comportamento normal do pystray.
    """

    def __init__(self, *args, ico=None, **kwargs):
        self._ico = ico
        super().__init__(*args, **kwargs)

    def _assert_icon_handle(self):
        if self._icon_handle:
            return
        if self._ico and sys.platform == "win32":
            try:
                from pystray._util import win32

                lado = ctypes.windll.user32.GetSystemMetrics(49)  # SM_CXSMICON
                handle = win32.LoadImage(None, str(self._ico), win32.IMAGE_ICON, lado, lado, win32.LR_LOADFROMFILE)
                if handle:
                    self._icon_handle = handle
                    return
            except Exception:
                log.debug("Ícone nítido indisponível; usando o padrão do pystray", exc_info=True)
        super()._assert_icon_handle()


class Bandeja:
    def __init__(self, api, ao_abrir: Callable[[], None], ao_sair: Callable[[], None],
                 ao_alterar: Callable[[], None] | None = None, ao_clicar: Callable[[], None] | None = None):
        """`api` é a mesma `ui.app.Api` usada pela janela; `ao_alterar` avisa a janela para reler o estado.

        `ao_clicar`: clique esquerdo no ícone (o mini painel). Sem ele, o clique abre o app completo.
        """
        self._api = api
        self._ao_abrir = ao_abrir
        self._ao_clicar = ao_clicar or ao_abrir
        self._ao_sair = ao_sair
        self._ao_alterar = ao_alterar
        try:
            ico = marca.ico_bandeja()
        except Exception:  # o ícone nítido é cosmético: nunca pode impedir o app de abrir
            log.exception("Não consegui gerar o ícone da bandeja; usando o padrão")
            ico = None
        self._icone = _IconeNitido(
            "mothlit",
            marca.imagem_bandeja(64),
            "Mothlit",
            ico=ico,
            menu=pystray.Menu(
                # item padrão = clique esquerdo; invisível no menu do botão direito
                pystray.MenuItem("Controles rápidos", self._clicar, default=True, visible=False),
                pystray.MenuItem("Abrir Mothlit", self._abrir),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(lambda _: self._rotulo("luz"), lambda: self._acao("luz")),
                pystray.MenuItem(lambda _: self._rotulo("ar"), lambda: self._acao("ar")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Sair", self._sair),
            ),
        )

    def iniciar(self) -> None:
        threading.Thread(target=self._icone.run, name="bandeja", daemon=True).start()

    def parar(self) -> None:
        try:
            self._icone.stop()
        except Exception:
            log.debug("Bandeja já parada", exc_info=True)

    def atualizar_menu(self) -> None:
        """Recalcula os textos dinâmicos (chamar quando o estado dos aparelhos mudar)."""
        try:
            self._icone.update_menu()
        except Exception:
            log.debug("Não consegui atualizar o menu da bandeja", exc_info=True)

    # --- menu ---

    def _rotulo(self, qual: str) -> str:
        nome = "luz" if qual == "luz" else "ar"
        ligado = self._api.ultimo_ligado(qual)
        if ligado is None:
            return f"Ligar/desligar {nome}"
        return f"Desligar {nome}" if ligado else f"Ligar {nome}"

    def _abrir(self) -> None:
        self._ao_abrir()

    def _clicar(self) -> None:
        self._ao_clicar()

    def _sair(self) -> None:
        self.parar()
        self._ao_sair()

    def _acao(self, qual: str) -> None:
        threading.Thread(target=self._alternar, args=(qual,), name=f"bandeja-{qual}", daemon=True).start()

    def _alternar(self, qual: str) -> None:
        r = self._api.alternar_luz() if qual == "luz" else self._api.alternar_ar()
        if r["ok"]:
            nome = "Lâmpada" if qual == "luz" else "Ar-condicionado"
            genero = "a" if qual == "luz" else "o"
            self._avisar(f"{nome} {'ligad' if r['dados'] else 'desligad'}{genero}.")
        else:
            self._avisar(r.get("erro") or "Falha ao falar com o aparelho.")
        self.atualizar_menu()
        if self._ao_alterar:
            self._ao_alterar()

    def _avisar(self, mensagem: str) -> None:
        if self._icone.HAS_NOTIFICATION:
            try:
                self._icone.notify(mensagem, "Mothlit")
            except Exception:
                log.debug("Notificação falhou", exc_info=True)
