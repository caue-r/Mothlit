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


def test_bandeja_ocupa_a_largura_inteira():
    for tamanho in (16, 24, 32):
        esquerda, _, direita, _ = marca.imagem_bandeja(tamanho).getbbox()
        assert (esquerda, direita) == (0, tamanho)  # encostada nas bordas: o máximo que cabe


def test_ico_da_bandeja_tem_todos_os_tamanhos(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setenv("APPDATA", str(tmp_path))
    ico = Image.open(marca.ico_bandeja())
    assert sorted(ico.info["sizes"]) == [(t, t) for t in marca.TAMANHOS_BANDEJA]


def test_ico_da_bandeja_funciona_no_executavel(tmp_path, monkeypatch):
    # No .exe do PyInstaller os módulos não existem como arquivo: não pode depender de __file__.
    monkeypatch.setenv("APPDATA", str(tmp_path))
    marca.ico_bandeja()  # 1ª abertura cria o .ico; o bug aparecia da 2ª em diante
    monkeypatch.setattr(marca, "__file__", str(tmp_path / "_internal" / "nao_existe" / "marca.pyc"))
    assert marca.ico_bandeja().exists()


def test_ico_gerado_na_pasta_de_config(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    caminho = marca.arquivo_ico()
    assert caminho == tmp_path / "Mothlit" / "mothlit.ico"
    assert caminho.stat().st_size > 0
