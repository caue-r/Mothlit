"""Onboarding interativo: `python -m mothlit setup`."""

import re
import webbrowser
from getpass import getpass
from urllib.parse import parse_qs, urlparse

import tinytuya

from . import config
from .devices import ErroDispositivo, salvar_credenciais_oauth
from .devices.smartthings import (
    REDIRECT_PADRAO,
    AuthOAuth,
    AuthPAT,
    SmartThingsClient,
    trocar_codigo,
    url_autorizacao,
)

# Categorias Tuya de iluminação (dj = lâmpada, dd = fita, xdd = teto, fwd = ambiente, dc = cordão)
_CATEGORIAS_LUZ = {"dj", "dd", "xdd", "fwd", "dc"}
_REGIOES_TUYA = ["us", "us-e", "eu", "eu-w", "sg", "in", "cn"]


def executar() -> None:
    print("=== Setup do Mothlit ===")
    print(f"Configuração não sensível: {config.caminho_env()}")
    print("Segredos (local_key, tokens): keyring do Windows (Gerenciador de Credenciais)\n")

    if _sim("Configurar a lâmpada (Tuya)?"):
        _setup_lampada()
    if _sim("Configurar o ar-condicionado (SmartThings)?"):
        _setup_ar()
    print("\nPronto. Teste com: uv run python -m mothlit test-lampada  |  uv run python -m mothlit test-ar")


# --- lâmpada ---


def _setup_lampada() -> None:
    print(
        "\nO controle local precisa de: device_id, local_key, IP e versão do protocolo.\n"
        "  1) Automático: informo o Access ID/Secret do seu projeto no Tuya IoT Platform\n"
        "     (iot.tuya.com > Cloud > seu projeto). Busco os dados na nuvem uma única vez\n"
        "     e procuro IP/versão na rede local. O Access Secret NÃO é salvo.\n"
        "  2) Manual: rode `python -m tinytuya wizard` (gera devices.json com id e key)\n"
        "     e `python -m tinytuya scan` (mostra IP e versão), e digite os valores aqui."
    )
    escolha = input("Opção [1/2] (1): ").strip() or "1"
    dados = _lampada_automatico() if escolha == "1" else None
    if dados is None:
        dados = _lampada_manual()

    device_id, local_key, ip, versao, nome = dados
    config.salvar_segredo(config.SEGREDO_LAMPADA_KEY, local_key)
    config.salvar_env({"LAMPADA_ID": device_id, "LAMPADA_IP": ip, "LAMPADA_VERSAO": str(versao),
                       "LAMPADA_NOME": nome or "Lâmpada"})
    print(f"Lâmpada salva: {device_id} em {ip} (protocolo {versao}).")
    print("Dica: reserve esse IP no roteador (DHCP estático) para ele não mudar.")


def _lampada_automatico():
    access_id = input("Access ID: ").strip()
    access_secret = getpass("Access Secret (não aparece): ").strip()
    regiao = input(f"Região {_REGIOES_TUYA} (us): ").strip() or "us"

    nuvem = tinytuya.Cloud(apiRegion=regiao, apiKey=access_id, apiSecret=access_secret, configFile="")
    if getattr(nuvem, "error", None):
        print(f"Falha ao autenticar na Tuya: {nuvem.error}")
        return None
    aparelhos = nuvem.getdevices()
    if not isinstance(aparelhos, list) or not aparelhos:
        print(f"Nenhum aparelho encontrado nessa região ({aparelhos}). Tente outra região ou o modo manual.")
        return None

    luzes = [a for a in aparelhos if a.get("category") in _CATEGORIAS_LUZ] or aparelhos
    escolhido = _escolher(luzes, lambda a: f"{a.get('name')}  [{a.get('id')}]  {a.get('product_name', '')}")

    print("Procurando o aparelho na rede local (até ~20 s)...")
    achados = tinytuya.deviceScan(verbose=False, maxretry=15, byID=True)
    local = achados.get(escolhido["id"], {})
    ip = local.get("ip") or input("Não achei na rede. IP da lâmpada: ").strip()
    versao = local.get("version") or input("Versão do protocolo (ex.: 3.3, 3.5): ").strip()
    return escolhido["id"], escolhido["key"], ip, float(versao), escolhido.get("name") or ""


def _lampada_manual():
    device_id = input("device_id: ").strip()
    local_key = getpass("local_key (não aparece): ").strip()
    ip = input("IP: ").strip()
    versao = float(input("Versão do protocolo (ex.: 3.3, 3.5): ").strip())
    nome = input("Nome para exibir (Lâmpada): ").strip()
    return device_id, local_key, ip, versao, nome


# --- ar-condicionado ---


def _setup_ar() -> None:
    print(
        "\nComo o Mothlit vai acessar a SmartThings?\n"
        "  1) OAuth (recomendado): você autoriza uma vez e o acesso se renova sozinho\n"
        "     (basta o Mothlit rodar ao menos uma vez a cada 30 dias)\n"
        "  2) Token pessoal (PAT): mais simples, mas tokens novos expiram em 24 h"
    )
    escolha = input("Opção [1/2] (1): ").strip() or "1"
    auth = _setup_oauth() if escolha == "1" else _setup_pat()
    if auth is None:
        return

    cliente = SmartThingsClient(auth)
    try:
        aparelhos = cliente.listar_dispositivos()
    except ErroDispositivo as e:
        print(f"Erro: {e}")
        return
    finally:
        cliente.fechar()

    def caps(a):
        return {c["id"] for comp in a.get("components", []) for c in comp.get("capabilities", [])}

    candidatos = [a for a in aparelhos if "airConditionerMode" in caps(a)] or aparelhos
    if not candidatos:
        print("Nenhum aparelho na conta.")
        return
    escolhido = _escolher(candidatos, lambda a: f"{a.get('label') or a.get('name')}  [{a['deviceId']}]")
    config.salvar_env({"SMARTTHINGS_DEVICE_ID": escolhido["deviceId"]})
    print(f"Ar-condicionado salvo: {escolhido.get('label')}.")


def _setup_pat():
    print(
        "\nCrie um Personal Access Token em https://account.smartthings.com/tokens\n"
        "com as permissões de Devices: List, See e Control (r:devices:*, x:devices:*)."
    )
    token = getpass("Token (não aparece): ").strip()
    if not token:
        return None
    config.salvar_segredo(config.SEGREDO_SMARTTHINGS_PAT, token)
    config.apagar_segredo_json(config.SEGREDO_SMARTTHINGS_OAUTH)  # escolheu PAT: OAuth antigo sai de cena
    return AuthPAT(token)


def _setup_oauth():
    print(
        "\nPasso único: criar um app OAuth na sua conta com a SmartThings CLI.\n"
        "  1. Instale a CLI: baixe o smartthings.msi em\n"
        "     https://github.com/SmartThingsCommunity/smartthings-cli/releases\n"
        "  2. Num terminal, rode:  smartthings apps:create\n"
        "     (na primeira vez ele abre o navegador para você entrar na conta Samsung)\n"
        "     - Tipo de app:           OAuth-In App\n"
        "     - Display Name:          Mothlit\n"
        "     - Description:           Controle pelo PC\n"
        "     - Icon Image URL e Target URL: deixe em branco (Enter)\n"
        "     - Escopos:               marque r:devices:* e x:devices:*\n"
        f"     - Redirect URI:          Add Redirect URI -> {REDIRECT_PADRAO}\n"
        "       depois 'Finish editing Redirect URIs' e 'Finish and create OAuth-In SmartApp'\n"
        "  3. Copie o OAuth Client Id e o OAuth Client Secret (o secret só aparece UMA vez)."
    )
    client_id = input("\nOAuth Client Id: ").strip()
    client_secret = getpass("OAuth Client Secret (não aparece): ").strip()
    if not (client_id and client_secret):
        print("Client Id e Client Secret são obrigatórios.")
        return None
    redirect = input(f"Redirect URI ({REDIRECT_PADRAO}): ").strip() or REDIRECT_PADRAO

    url, state = url_autorizacao(client_id, redirect)
    print(
        "\nAbra o endereço abaixo (vou tentar abrir sozinho), entre na conta Samsung e autorize.\n"
        f"\n  {url}\n\n"
        "Depois de autorizar, o navegador vai para uma página do httpbin.\n"
        "Copie o ENDEREÇO completo da barra do navegador (ou só o valor de \"code\") e cole aqui."
    )
    webbrowser.open(url)
    for _ in range(3):
        try:
            codigo = extrair_codigo(input("\nEndereço ou código: "), state)
            credenciais = trocar_codigo(client_id, client_secret, codigo, redirect)
            break
        except ValueError as e:
            print(f"Não entendi: {e}")
        except ErroDispositivo as e:
            print(f"Erro: {e}")
    else:
        return None

    salvar_credenciais_oauth(credenciais)
    print("Autorizado! O acesso será renovado automaticamente.")
    return AuthOAuth(credenciais, salvar=salvar_credenciais_oauth)


def extrair_codigo(texto: str, state_esperado: str | None = None) -> str:
    """Aceita o endereço do redirect, o JSON da página do httpbin ou só o código."""
    texto = texto.strip()
    if not texto:
        raise ValueError("nada foi colado.")
    if texto.startswith("http"):
        parametros = parse_qs(urlparse(texto).query)
        if "error" in parametros:
            raise ValueError(f"a SmartThings recusou a autorização ({parametros['error'][0]}).")
        codigo = (parametros.get("code") or [""])[0]
        state = (parametros.get("state") or [None])[0]
        if state_esperado and state and state != state_esperado:
            raise ValueError("o endereço não é desta autorização (state diferente). Use o link novo.")
    elif "\"code\"" in texto:
        achado = re.search(r'"code"\s*:\s*"([^"]+)"', texto)
        codigo = achado.group(1) if achado else ""
    else:
        codigo = texto
    if not re.fullmatch(r"[A-Za-z0-9._~-]+", codigo or ""):
        raise ValueError("não encontrei o código de autorização.")
    return codigo

# --- utilitários ---


def _escolher(itens: list, rotulo):
    if len(itens) == 1:
        print(f"Encontrado: {rotulo(itens[0])}")
        return itens[0]
    for i, item in enumerate(itens, 1):
        print(f"  {i}) {rotulo(item)}")
    while True:
        resp = input("Número: ").strip()
        if resp.isdigit() and 1 <= int(resp) <= len(itens):
            return itens[int(resp) - 1]


def _sim(pergunta: str) -> bool:
    return input(f"{pergunta} [S/n]: ").strip().lower() not in ("n", "nao", "não")
