import threading
import time

from mothlit.devices import ErroDispositivo
from mothlit.ui.worker import Worker


class RaizFalsa:
    """Imita o `after()` do Tk: guarda callbacks para rodarmos à mão."""

    def __init__(self):
        self.agendados = []
        self.thread_ui = threading.get_ident()

    def after(self, _ms, callback):
        self.agendados.append(callback)

    def rodar_ate(self, condicao, limite_s=2.0):
        fim = time.monotonic() + limite_s
        while not condicao() and time.monotonic() < fim:
            pendentes, self.agendados = self.agendados, []
            for cb in pendentes:
                cb()
            time.sleep(0.01)


def test_resultado_volta_na_thread_da_ui():
    raiz = RaizFalsa()
    worker = Worker(raiz)
    recebido = {}

    def ao_concluir(valor):
        recebido["valor"] = valor
        recebido["thread"] = threading.get_ident()

    worker.executar(lambda: threading.get_ident(), ao_concluir)
    raiz.rodar_ate(lambda: "valor" in recebido)
    assert recebido["thread"] == raiz.thread_ui
    assert recebido["valor"] != raiz.thread_ui  # a função rodou em outra thread
    worker.encerrar()


def test_erro_vira_mensagem():
    raiz = RaizFalsa()
    worker = Worker(raiz)
    erros = []

    def falha():
        raise ErroDispositivo("Lâmpada inacessível.")

    worker.executar(falha, ao_falhar=erros.append)
    worker.executar(lambda: 1 / 0, ao_falhar=erros.append)
    raiz.rodar_ate(lambda: len(erros) == 2)
    assert "Lâmpada inacessível." in erros
    assert any(e.startswith("Erro inesperado") for e in erros)
    worker.encerrar()
