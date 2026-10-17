"""Configuração: valores não sensíveis no .env, segredos no keyring.

O .env é procurado primeiro na pasta atual (útil no desenvolvimento) e depois
em %APPDATA%\\Mothlit\\.env, que é onde o `setup` grava.
"""

import json
import logging
import os
import sys
import threading
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

import keyring
import keyring.errors
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


# --- log em arquivo (o .exe não tem console) ---


def configurar_log() -> Path:
    """Log em %APPDATA%\\Mothlit\\mothlit.log, com rotação (até ~3 MB). Erros não tratados também vão para lá."""
    caminho = pasta_config() / "mothlit.log"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    arquivo = RotatingFileHandler(caminho, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.handlers[:] = [arquivo]
    raiz.setLevel(logging.INFO)
    # bibliotecas falantes (o tinytuya em DEBUG chega a registrar chaves de sessão)
    for nome in ("httpx", "httpcore", "tinytuya", "urllib3", "pywebview", "PIL"):
        logging.getLogger(nome).setLevel(logging.WARNING)

    def registrar(tipo, valor, rastro, thread=None):
        logging.getLogger("mothlit").critical("Erro não tratado%s", f" na thread {thread}" if thread else "",
                                              exc_info=(tipo, valor, rastro))

    sys.excepthook = registrar
    threading.excepthook = lambda a: registrar(a.exc_type, a.exc_value, a.exc_traceback, a.thread.name)
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


SEGREDO_SMARTTHINGS_OAUTH = "smartthings_oauth"

# O Gerenciador de Credenciais do Windows aceita até 2560 bytes por segredo (UTF-16: ~1280
# caracteres). Valores maiores (tokens OAuth podem ser longos) são gravados em pedaços.
_PEDACO = 1000


def salvar_segredo_json(nome: str, dados: dict) -> None:
    texto = json.dumps(dados, separators=(",", ":"))
    pedacos = [texto[i : i + _PEDACO] for i in range(0, len(texto), _PEDACO)] or [""]
    antigos = int(ler_segredo(f"{nome}#n") or 0)
    for i, pedaco in enumerate(pedacos):
        salvar_segredo(f"{nome}#{i}", pedaco)
    salvar_segredo(f"{nome}#n", str(len(pedacos)))  # por último: só "vale" depois de tudo gravado
    for i in range(len(pedacos), antigos):
        apagar_segredo(f"{nome}#{i}")


def ler_segredo_json(nome: str) -> dict | None:
    total = ler_segredo(f"{nome}#n")
    if not total:
        return None
    partes = [ler_segredo(f"{nome}#{i}") for i in range(int(total))]
    if any(p is None for p in partes):
        return None
    try:
        return json.loads("".join(partes))
    except ValueError:
        return None


def apagar_segredo_json(nome: str) -> None:
    total = int(ler_segredo(f"{nome}#n") or 0)
    apagar_segredo(f"{nome}#n")
    for i in range(total):
        apagar_segredo(f"{nome}#{i}")


def apagar_segredo(nome: str) -> None:
    try:
        keyring.delete_password(SERVICO_KEYRING, nome)
    except keyring.errors.PasswordDeleteError:
        pass


def ler_segredo(nome: str) -> str | None:
    return keyring.get_password(SERVICO_KEYRING, nome)


def salvar_segredo(nome: str, valor: str) -> None:
    keyring.set_password(SERVICO_KEYRING, nome, valor)
