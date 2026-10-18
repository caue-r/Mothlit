from unittest.mock import MagicMock

from mothlit.tray import Bandeja


def bandeja(api):
    b = Bandeja(api, ao_abrir=MagicMock(), ao_sair=MagicMock(), ao_alterar=MagicMock())
    b._icone = MagicMock(HAS_NOTIFICATION=True)  # não cria o ícone de verdade
    return b


def test_rotulos_seguem_o_ultimo_estado():
    api = MagicMock()
    api.ultimo_ligado.side_effect = {"luz": True, "ar": None}.get
    b = bandeja(api)
    assert b._rotulo("luz") == "Desligar luz"
    assert b._rotulo("ar") == "Ligar/desligar ar"


def test_alternar_avisa_e_pede_releitura():
    api = MagicMock()
    api.alternar_ar.return_value = {"ok": True, "dados": True}
    b = bandeja(api)
    b._alternar("ar")
    b._icone.notify.assert_called_with("Ar-condicionado ligado.", "Mothlit")
    b._icone.update_menu.assert_called_once()
    b._ao_alterar.assert_called_once()


def test_erro_vira_notificacao():
    api = MagicMock()
    api.alternar_luz.return_value = {"ok": False, "erro": "Lâmpada inacessível."}
    b = bandeja(api)
    b._alternar("luz")
    b._icone.notify.assert_called_with("Lâmpada inacessível.", "Mothlit")


def test_clique_esquerdo_abre_o_mini_painel():
    abrir, clicar = MagicMock(), MagicMock()
    b = Bandeja(MagicMock(), ao_abrir=abrir, ao_sair=MagicMock(), ao_clicar=clicar)
    b._clicar()
    clicar.assert_called_once()
    abrir.assert_not_called()
    b._abrir()  # "Abrir Mothlit" no menu do botão direito continua abrindo o app completo
    abrir.assert_called_once()


def test_sem_mini_painel_o_clique_abre_o_app():
    abrir = MagicMock()
    b = Bandeja(MagicMock(), ao_abrir=abrir, ao_sair=MagicMock())
    b._clicar()
    abrir.assert_called_once()


def test_sair_para_icone_e_fecha_janela():
    b = bandeja(MagicMock())
    b._sair()
    b._icone.stop.assert_called_once()
    b._ao_sair.assert_called_once()
