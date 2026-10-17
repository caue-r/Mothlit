import pytest

from mothlit import config
from mothlit.devices import criar_ar, criar_lampada


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    for var in ("LAMPADA_ID", "LAMPADA_IP", "LAMPADA_VERSAO", "SMARTTHINGS_DEVICE_ID"):
        monkeypatch.delenv(var, raising=False)
    cofre = {}
    monkeypatch.setattr(config.keyring, "get_password", lambda s, n: cofre.get((s, n)))
    monkeypatch.setattr(config.keyring, "set_password", lambda s, n, v: cofre.__setitem__((s, n), v))
    return cofre


def test_salvar_env_mescla_valores(ambiente):
    config.salvar_env({"LAMPADA_ID": "a", "LAMPADA_IP": "1.2.3.4"})
    caminho = config.salvar_env({"LAMPADA_IP": "5.6.7.8"})
    assert caminho.read_text(encoding="utf-8") == "LAMPADA_ID=a\nLAMPADA_IP=5.6.7.8\n"


def test_segredos_vao_para_o_keyring(ambiente):
    config.salvar_segredo(config.SEGREDO_LAMPADA_KEY, "segredo")
    assert ambiente == {("mothlit", "lampada_local_key"): "segredo"}
    assert config.ler_segredo(config.SEGREDO_LAMPADA_KEY) == "segredo"


def test_preferencias_padrao_e_salvas(ambiente):
    assert config.ler_preferencias() == {"fechar_para_bandeja": False}
    config.salvar_preferencia("fechar_para_bandeja", True)
    assert config.ler_preferencias() == {"fechar_para_bandeja": True}


def test_preferencias_corrompidas_voltam_ao_padrao(ambiente):
    config.caminho_preferencias().parent.mkdir(parents=True, exist_ok=True)
    config.caminho_preferencias().write_text("{isso não é json", encoding="utf-8")
    assert config.ler_preferencias() == {"fechar_para_bandeja": False}


def test_preferencia_desconhecida(ambiente):
    with pytest.raises(config.ErroConfiguracao):
        config.salvar_preferencia("tema", "claro")


def test_fabricas_exigem_setup(ambiente):
    with pytest.raises(config.ErroConfiguracao, match="setup"):
        criar_lampada()
    with pytest.raises(config.ErroConfiguracao, match="setup"):
        criar_ar()


def test_fabrica_lampada_usa_env_e_keyring(ambiente):
    cfg = config.Config("id1", "192.168.1.34", 3.5, "")
    config.salvar_segredo(config.SEGREDO_LAMPADA_KEY, "0123456789abcdef")
    assert criar_lampada(cfg).nome == "Lâmpada"
