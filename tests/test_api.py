"""A ponte com o JavaScript: sempre responde dicts simples, nunca deixa exceção escapar."""

from unittest.mock import MagicMock

from mothlit.devices import ErroDispositivo, EstadoAr, EstadoLampada
from mothlit.ui.app import Api


def estado_ar():
    return EstadoAr(
        ligado=True, temperatura_alvo=24.0, faixa_alvo=(16.0, 30.0, 1.0), temperatura_ambiente=25.0,
        modo="cool", modos=["auto", "cool"], ventilador="auto", ventiladores=["auto", "low"],
        capabilities={"switch"}, oscilacao="fixed", oscilacoes=["fixed", "all"], modo_opcional="off",
        modos_opcionais=["off", "sleep"], rotulo="Ar condicionado Quarto",
    )


def estado_luz():
    return EstadoLampada(ligada=True, modo="colour", brilho=40, temperatura_cor=30, cor_rgb=(255, 0, 0),
                         suporta_temperatura=True, suporta_cor=True, cor_hsv=(0.0, 1.0, 0.4))


def test_estado_ar_vira_dict_serializavel():
    ar = MagicMock()
    ar.estado.return_value = estado_ar()
    r = Api(ar=ar).estado_ar()
    assert r["ok"] is True
    assert r["dados"]["nome"] == "Ar condicionado Quarto"
    assert r["dados"]["faixa"] == [16.0, 30.0, 1.0]
    assert r["dados"]["opcionais"] == ["off", "sleep"]
    assert "capabilities" not in r["dados"]  # set não é serializável em JSON


def test_estado_luz_vira_dict():
    luz = MagicMock()
    luz.nome = "Quarto"
    luz.estado.return_value = estado_luz()
    r = Api(lampada=luz).estado_luz()
    assert r["dados"] == {
        "nome": "Quarto", "ligada": True, "modo": "colour", "brilho": 40, "temperatura": 30,
        "hsv": [0.0, 1.0, 0.4], "suportaCor": True, "suportaTemperatura": True,
    }


def test_comandos_chegam_aos_adaptadores():
    ar, luz = MagicMock(), MagicMock()
    api = Api(lampada=luz, ar=ar)
    api.ar_ligar(False)
    api.ar_temperatura(23)
    api.ar_modo("dry")
    api.ar_oscilacao("all")
    api.luz_ligar(True)
    api.luz_brilho(55.4)
    api.luz_hsv(0.5, 0.8, 0.3)
    ar.desligar.assert_called_once()
    ar.definir_temperatura.assert_called_with(23.0)
    ar.definir_modo.assert_called_with("dry")
    ar.definir_oscilacao.assert_called_with("all")
    luz.ligar.assert_called_once()
    luz.definir_brilho.assert_called_with(55)
    luz.definir_hsv.assert_called_with(0.5, 0.8, 0.3)


def test_erro_do_aparelho_vira_mensagem():
    luz = MagicMock()
    luz.ligar.side_effect = ErroDispositivo("Lâmpada inacessível.")
    assert Api(lampada=luz).luz_ligar(True) == {"ok": False, "configurado": True, "erro": "Lâmpada inacessível."}


def test_erro_inesperado_nao_escapa():
    ar = MagicMock()
    ar.estado.side_effect = KeyError("x")
    r = Api(ar=ar).estado_ar()
    assert r["ok"] is False and r["erro"].startswith("Erro inesperado")


def test_alternar_le_estado_e_inverte():
    luz = MagicMock()
    luz.nome = "Quarto"
    luz.estado.return_value = estado_luz()  # ligada
    api = Api(lampada=luz)
    r = api.alternar_luz()
    assert r["ok"] is True and r["dados"] is False
    luz.desligar.assert_called_once()
    assert api.ultimo_ligado("luz") is False


def test_alternar_com_erro_nao_envia_comando():
    ar = MagicMock()
    ar.estado.side_effect = ErroDispositivo("Sem internet.")
    r = Api(ar=ar).alternar_ar()
    assert r == {"ok": False, "configurado": True, "erro": "Sem internet."}
    ar.ligar.assert_not_called()
    ar.desligar.assert_not_called()


def test_mudanca_de_estado_avisa_a_bandeja():
    ar = MagicMock()
    ar.estado.return_value = estado_ar()  # ligado
    api = Api(ar=ar)
    avisos = []
    api._ao_mudar = lambda: avisos.append(api.ultimo_ligado("ar"))
    assert api.ultimo_ligado("ar") is None
    api.estado_ar()
    api.estado_ar()  # mesmo estado: não avisa de novo
    api.ar_ligar(False)
    assert avisos == [True, False]


def test_aparelho_nao_configurado():
    r = Api(erro_ar="Ar-condicionado não configurado.").estado_ar()
    assert r == {"ok": False, "configurado": False, "erro": "Ar-condicionado não configurado."}
