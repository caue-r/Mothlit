"""Mini painel da bandeja: abrir/fechar, sem abrir janelas de verdade."""

from unittest.mock import MagicMock

from mothlit.ui import flyout
from mothlit.ui.flyout import PainelRapido


class Relogio:
    def __init__(self):
        self.agora = 100.0

    def __call__(self):
        return self.agora


def painel(monkeypatch):
    relogio = Relogio()
    monkeypatch.setattr(flyout.time, "monotonic", relogio)
    monkeypatch.setattr(flyout, "posicao", lambda l, a: (10, 20))
    p = PainelRapido.__new__(PainelRapido)  # sem criar a janela do pywebview
    p.janela = MagicMock()
    p.janela.native = None  # sem formulário nativo: as chamadas reais ao Windows são puladas
    p.visivel = False
    p._escondido_em = 0.0
    p._nativo_configurado = True
    return p, relogio


def test_clique_abre_e_clique_de_novo_fecha(monkeypatch):
    p, _ = painel(monkeypatch)
    p.alternar()
    assert p.visivel
    p.janela.show.assert_called_once()
    p.janela.move.assert_called_with(10, 20)
    p.janela.evaluate_js.assert_called_with("window.aoMostrar && aoMostrar()")
    p.alternar()
    assert not p.visivel
    p.janela.hide.assert_called_once()


def test_clique_no_icone_que_fechou_o_painel_nao_reabre(monkeypatch):
    p, relogio = painel(monkeypatch)
    p.alternar()
    p.esconder()  # perdeu o foco porque o usuário clicou no ícone da bandeja...
    relogio.agora += 0.05
    p.alternar()  # ...e o clique chega logo depois: deve continuar fechado
    assert not p.visivel
    relogio.agora += 1
    p.alternar()  # um clique de verdade, mais tarde, abre
    assert p.visivel


def test_esconder_duas_vezes_nao_duplica(monkeypatch):
    p, _ = painel(monkeypatch)
    p.alternar()
    p.esconder()
    p.esconder()  # JS blur + Deactivate do Windows chegam juntos
    p.janela.hide.assert_called_once()


def test_moldura_e_posicao_dao_numeros_inteiros():
    largura, altura = flyout._moldura()
    x, y = flyout.posicao(flyout.LARGURA, flyout.ALTURA)
    assert all(isinstance(v, int) for v in (largura, altura, x, y))
    assert largura >= 0 and altura >= 0
