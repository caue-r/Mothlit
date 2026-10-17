"""Executa chamadas de rede fora da thread do Tk e devolve o resultado nela.

O Tk não é thread-safe: as threads só colocam o resultado numa fila, e a
thread da UI esvazia essa fila periodicamente com `after()`.
"""

import queue
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from ..config import ErroConfiguracao
from ..devices import ErroDispositivo

INTERVALO_MS = 50


class Worker:
    def __init__(self, raiz, max_threads: int = 4):
        self._raiz = raiz
        self._pool = ThreadPoolExecutor(max_workers=max_threads, thread_name_prefix="mothlit")
        self._fila: queue.Queue[Callable[[], Any]] = queue.Queue()
        self._ativo = True
        self._raiz.after(INTERVALO_MS, self._processar)

    def executar(
        self,
        funcao: Callable[[], Any],
        ao_concluir: Callable[[Any], Any] | None = None,
        ao_falhar: Callable[[str], Any] | None = None,
    ) -> None:
        """Roda `funcao` numa thread; os callbacks rodam na thread da UI."""

        def tarefa():
            try:
                resultado = funcao()
            except (ErroDispositivo, ErroConfiguracao) as e:
                mensagem = str(e)
            except Exception as e:  # nunca deixa a UI sem resposta
                mensagem = f"Erro inesperado: {e}"
            else:
                if ao_concluir:
                    self._fila.put(lambda: ao_concluir(resultado))
                return
            if ao_falhar:
                self._fila.put(lambda: ao_falhar(mensagem))

        self._pool.submit(tarefa)

    def encerrar(self) -> None:
        self._ativo = False
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _processar(self) -> None:
        while True:
            try:
                callback = self._fila.get_nowait()
            except queue.Empty:
                break
            callback()
        if self._ativo:
            self._raiz.after(INTERVALO_MS, self._processar)
