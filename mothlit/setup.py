"""Onboarding interativo: `python -m mothlit setup`."""

from getpass import getpass

import tinytuya

from . import config
from .devices import ErroDispositivo
from .devices.smartthings import AuthPAT, SmartThingsClient

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
    print("\nPronto. Teste com: python -m mothlit test-lampada  |  python -m mothlit test-ar")


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

    device_id, local_key, ip, versao = dados
    config.salvar_segredo(config.SEGREDO_LAMPADA_KEY, local_key)
    config.salvar_env({"LAMPADA_ID": device_id, "LAMPADA_IP": ip, "LAMPADA_VERSAO": str(versao)})
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
    return escolhido["id"], escolhido["key"], ip, float(versao)


def _lampada_manual():
    device_id = input("device_id: ").strip()
    local_key = getpass("local_key (não aparece): ").strip()
    ip = input("IP: ").strip()
    versao = float(input("Versão do protocolo (ex.: 3.3, 3.5): ").strip())
    return device_id, local_key, ip, versao


# --- ar-condicionado ---


def _setup_ar() -> None:
    print(
        "\nCrie um Personal Access Token em https://account.smartthings.com/tokens\n"
        "com as permissões de Devices: List, See e Control (r:devices:*, x:devices:*).\n"
        "Atenção: PATs novos valem só 24 h. Veja no README como usar OAuth."
    )
    token = getpass("Token (não aparece): ").strip()
    cliente = SmartThingsClient(AuthPAT(token))
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

    config.salvar_segredo(config.SEGREDO_SMARTTHINGS_PAT, token)
    config.salvar_env({"SMARTTHINGS_DEVICE_ID": escolhido["deviceId"]})
    print(f"Ar-condicionado salvo: {escolhido.get('label')}.")


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
