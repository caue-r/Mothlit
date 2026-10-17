"""Iniciar com o Windows, usando um winreg falso (não toca no registro real)."""

import sys

import pytest

from mothlit import inicializacao


class ChaveFalsa:
    def __init__(self, valores):
        self.valores = valores

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class WinregFalso:
    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self):
        self.valores = {}

    def OpenKey(self, raiz, caminho):
        return ChaveFalsa(self.valores)

    CreateKey = OpenKey

    def QueryValueEx(self, chave, nome):
        if nome not in chave.valores:
            raise FileNotFoundError(nome)
        return chave.valores[nome], self.REG_SZ

    def SetValueEx(self, chave, nome, _reservado, _tipo, valor):
        chave.valores[nome] = valor

    def DeleteValue(self, chave, nome):
        if nome not in chave.valores:
            raise FileNotFoundError(nome)
        del chave.valores[nome]


@pytest.fixture
def registro(monkeypatch):
    falso = WinregFalso()
    monkeypatch.setattr(inicializacao, "winreg", falso)
    return falso


def test_liga_e_desliga(registro):
    assert inicializacao.ativo() is False
    inicializacao.definir(True)
    assert inicializacao.ativo() is True
    assert registro.valores["Mothlit"].endswith("-m mothlit --bandeja")
    inicializacao.definir(False)
    assert inicializacao.ativo() is False
    inicializacao.definir(False)  # desligar de novo não quebra


def test_comando_usa_pythonw_sem_console():
    assert "pythonw.exe" in inicializacao.comando().lower()


def test_comando_do_executavel(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\Mothlit\Mothlit.exe")
    assert inicializacao.comando() == r'"C:\Apps\Mothlit\Mothlit.exe" --bandeja'


def test_fora_do_windows(monkeypatch):
    monkeypatch.setattr(inicializacao, "winreg", None)
    assert inicializacao.suportado() is False
    assert inicializacao.ativo() is False
    with pytest.raises(OSError):
        inicializacao.definir(True)
