import pytest

from mothlit.setup import extrair_codigo


def test_endereco_completo_do_redirect():
    assert extrair_codigo("https://httpbin.org/get?code=Ab12Cd&state=xyz", "xyz") == "Ab12Cd"


def test_json_da_pagina_do_httpbin():
    json_httpbin = '{\n  "args": {\n    "code": "Q9w8E7", \n    "state": "xyz"\n  }, \n  "headers": {}\n}'
    assert extrair_codigo(json_httpbin) == "Q9w8E7"


def test_so_o_codigo():
    assert extrair_codigo("  Z1y2X3 \n") == "Z1y2X3"


def test_state_diferente_e_recusado():
    with pytest.raises(ValueError, match="state diferente"):
        extrair_codigo("https://httpbin.org/get?code=Ab12Cd&state=outro", "xyz")


def test_usuario_negou_acesso():
    with pytest.raises(ValueError, match="access_denied"):
        extrair_codigo("https://httpbin.org/get?error=access_denied&state=xyz", "xyz")


@pytest.mark.parametrize("texto", ["", "https://httpbin.org/get", "isso tem espaço"])
def test_sem_codigo(texto):
    with pytest.raises(ValueError):
        extrair_codigo(texto)
