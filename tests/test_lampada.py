from unittest.mock import MagicMock

import pytest
import tinytuya

from mothlit.devices import ErroDispositivo, Lampada

# Status real do painel Ekaza (tipo B, protocolo 3.5)
STATUS_BRANCO = {
    "dps": {
        "20": True,
        "21": "white",
        "22": 500,
        "23": 342,
        "24": "000003e803e8",
        "25": "000e0d0000000000000000c80000",
        "26": 0,
        "34": True,
    }
}


def bulb_falso(status=STATUS_BRANCO):
    """BulbDevice real (sem rede) com status() mockado, para testar a detecção de verdade."""
    bulb = tinytuya.BulbDevice("id", "127.0.0.1", "0123456789abcdef", version=3.5)
    bulb.status = MagicMock(return_value=status)
    for metodo in ("turn_on", "turn_off", "set_brightness_percentage", "set_colourtemp_percentage", "set_colour"):
        setattr(bulb, metodo, MagicMock(return_value={"dps": {}}))
    return bulb


def test_estado_modo_branco():
    estado = Lampada("id", "ip", "key", 3.5, bulb=bulb_falso()).estado()
    assert estado.ligada is True
    assert estado.modo == "white"
    assert estado.brilho == 50
    assert estado.temperatura_cor == 34
    assert estado.cor_rgb == (255, 0, 0)
    assert estado.suporta_cor and estado.suporta_temperatura


def test_estado_modo_colorido_usa_v_do_hsv_como_brilho():
    status = {"dps": {**STATUS_BRANCO["dps"], "21": "colour", "24": "007803e801f4"}}  # h=120 s=1000 v=500
    estado = Lampada("id", "ip", "key", 3.5, bulb=bulb_falso(status)).estado()
    assert estado.modo == "colour"
    assert estado.brilho == 50
    assert estado.cor_rgb[1] > estado.cor_rgb[0]


def test_comandos_repassam_para_tinytuya():
    bulb = bulb_falso()
    lampada = Lampada("id", "ip", "key", 3.5, bulb=bulb)
    lampada.ligar()
    lampada.desligar()
    lampada.definir_brilho(0)  # 0 % desligaria; o mínimo é 1 %
    lampada.definir_temperatura_cor(150)
    lampada.definir_cor(300, -5, 10)
    bulb.turn_on.assert_called_once()
    bulb.turn_off.assert_called_once()
    bulb.set_brightness_percentage.assert_called_with(1)
    bulb.set_colourtemp_percentage.assert_called_with(100)
    bulb.set_colour.assert_called_with(255, 0, 10)


def test_erro_de_rede_vira_mensagem_amigavel():
    bulb = bulb_falso({"Error": "Network Error: Device Unreachable", "Err": "905", "Payload": None})
    with pytest.raises(ErroDispositivo, match="inacessível"):
        Lampada("id", "ip", "key", 3.5, bulb=bulb).estado()


def test_chave_ou_versao_errada():
    bulb = bulb_falso()
    bulb.turn_on.return_value = {"Error": "Check device key or version", "Err": "914", "Payload": None}
    with pytest.raises(ErroDispositivo, match="local_key"):
        Lampada("id", "ip", "key", 3.5, bulb=bulb).ligar()


def test_excecao_de_socket_vira_erro_dispositivo():
    bulb = bulb_falso()
    bulb.turn_off.side_effect = OSError("boom")
    with pytest.raises(ErroDispositivo):
        Lampada("id", "ip", "key", 3.5, bulb=bulb).desligar()
