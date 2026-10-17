"""Ícone na bandeja do sistema com ações rápidas (pystray).

O pystray roda numa thread própria (seguro no Windows). As ações que usam a rede
rodam em outra thread, para o menu da bandeja nunca travar.
"""

import logging
import threading
from typing import Callable

import pystray

from .ui import marca

log = logging.getLogger(__name__)


class Bandeja:
    def __init__(self, api, ao_abrir: Callable[[], None], ao_sair: Callable[[], None],
                 ao_alterar: Callable[[], None] | None = None):
        """`api` é a mesma `ui.app.Api` usada pela janela; `ao_alterar` avisa a janela para reler o estado."""
        self._api = api
        self._ao_abrir = ao_abrir
        self._ao_sair = ao_sair
        self._ao_alterar = ao_alterar
        self._icone = pystray.Icon(
            "mothlit",
            marca.imagem(64),
            "Mothlit",
            menu=pystray.Menu(
                pystray.MenuItem("Abrir Mothlit", self._abrir, default=True),
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
