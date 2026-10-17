from mothlit.ui import marca


def test_svg_vira_poligonos():
    poligonos, lado = marca._poligonos()
    assert lado == 512
    assert len(poligonos) == 3  # corpo + dois detalhes das antenas
    assert len(poligonos[0]) > 50


def test_imagem_tem_conteudo_e_tamanho_certo():
    img = marca.imagem(32)
    assert img.size == (32, 32)
    assert img.getbbox() is not None


def test_ico_gerado_na_pasta_de_config(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    caminho = marca.arquivo_ico()
    assert caminho == tmp_path / "Mothlit" / "mothlit.ico"
    assert caminho.stat().st_size > 0
