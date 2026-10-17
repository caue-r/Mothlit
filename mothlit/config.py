"""Configuração: valores não sensíveis no .env, segredos no keyring.

O .env é procurado primeiro na pasta atual (útil no desenvolvimento) e depois
em %APPDATA%\\Mothlit\\.env, que é onde o `setup` grava.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

import keyring
from dotenv import load_dotenv

SERVICO_KEYRING = "mothlit"

# Nomes das entradas no keyring
SEGREDO_LAMPADA_KEY = "lampada_local_key"
SEGREDO_SMARTTHINGS_PAT = "smartthings_pat"


class ErroConfiguracao(Exception):
    """Configuração ausente ou inválida."""


def pasta_config() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Mothlit"


def caminho_env() -> Path:
    return pasta_config() / ".env"


@dataclass
class Config:
    lampada_id: str
    lampada_ip: str
    lampada_versao: float
    ar_device_id: str
    lampada_nome: str = "Lâmpada"


def carregar() -> Config:
    # load_dotenv não sobrescreve variáveis já definidas: o .env local vence.
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(caminho_env())
    try:
        versao = float(os.environ.get("LAMPADA_VERSAO", "3.3"))
    except ValueError as e:
        raise ErroConfiguracao("LAMPADA_VERSAO inválida no .env (ex.: 3.3, 3.5).") from e
    return Config(
        lampada_id=os.environ.get("LAMPADA_ID", ""),
        lampada_ip=os.environ.get("LAMPADA_IP", ""),
        lampada_versao=versao,
        ar_device_id=os.environ.get("SMARTTHINGS_DEVICE_ID", ""),
        lampada_nome=os.environ.get("LAMPADA_NOME") or "Lâmpada",
    )


def salvar_env(valores: dict[str, str]) -> Path:
    """Mescla `valores` no .env do usuário e devolve o caminho gravado."""
    caminho = caminho_env()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    atuais: dict[str, str] = {}
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                chave, _, valor = linha.partition("=")
                atuais[chave.strip()] = valor.strip()
    atuais.update(valores)
    caminho.write_text("".join(f"{k}={v}\n" for k, v in atuais.items()), encoding="utf-8")
    return caminho


# --- preferências do app (não sensíveis) ---

PREFERENCIAS_PADRAO = {"fechar_para_bandeja": False}


def caminho_preferencias() -> Path:
    return pasta_config() / "preferencias.json"


def ler_preferencias() -> dict:
    """Preferências salvas, completadas com os padrões. Arquivo ausente ou corrompido = padrões."""
    try:
        salvas = json.loads(caminho_preferencias().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        salvas = {}
    return {**PREFERENCIAS_PADRAO, **{k: v for k, v in salvas.items() if k in PREFERENCIAS_PADRAO}}


def salvar_preferencia(nome: str, valor) -> dict:
    if nome not in PREFERENCIAS_PADRAO:
        raise ErroConfiguracao(f"Preferência desconhecida: {nome}")
    preferencias = {**ler_preferencias(), nome: valor}
    caminho = caminho_preferencias()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(preferencias, indent=2), encoding="utf-8")
    return preferencias


def ler_segredo(nome: str) -> str | None:
    return keyring.get_password(SERVICO_KEYRING, nome)


def salvar_segredo(nome: str, valor: str) -> None:
    keyring.set_password(SERVICO_KEYRING, nome, valor)
