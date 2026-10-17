"""Ponto de entrada: `python -m mothlit [setup | test-lampada | test-ar]`. Sem argumento abre a UI."""

import argparse
import sys
import time

from . import config
from .devices import ErroDispositivo, criar_ar, criar_lampada


def test_lampada() -> None:
    lampada = criar_lampada()
    print("Lendo estado da lâmpada...")
    inicial = lampada.estado()
    print(f"  {inicial}")

    passos = [
        ("Ligando", lampada.ligar),
        ("Brilho 20 %", lambda: lampada.definir_brilho(20)),
        ("Brilho 100 %", lambda: lampada.definir_brilho(100)),
    ]
    if inicial.suporta_temperatura:
        passos += [
            ("Branco quente", lambda: lampada.definir_temperatura_cor(0)),
            ("Branco frio", lambda: lampada.definir_temperatura_cor(100)),
        ]
    if inicial.suporta_cor:
        passos += [
            ("Vermelho", lambda: lampada.definir_cor(255, 0, 0)),
            ("Verde", lambda: lampada.definir_cor(0, 255, 0)),
            ("Azul", lambda: lampada.definir_cor(0, 0, 255)),
        ]
    for nome, acao in passos:
        print(f"- {nome}")
        acao()
        time.sleep(2)
    print(f"  Estado agora: {lampada.estado()}")

    print("- Restaurando o estado inicial")
    if inicial.suporta_temperatura and inicial.temperatura_cor is not None:
        lampada.definir_temperatura_cor(inicial.temperatura_cor)
    lampada.definir_brilho(max(inicial.brilho, 1))
    if not inicial.ligada:
        lampada.desligar()
    print("OK")


def test_ar() -> None:
    ar = criar_ar()
    print("Capabilities declaradas:")
    print("  " + ", ".join(sorted(ar.capabilities())))
    estado = ar.estado()
    print("\nEstado atual:")
    print(f"  Ligado: {estado.ligado}")
    print(f"  Temperatura ambiente: {estado.temperatura_ambiente} °C")
    print(f"  Temperatura alvo: {estado.temperatura_alvo} °C (faixa {estado.faixa_alvo})")
    print(f"  Modo: {estado.modo}  (disponíveis: {estado.modos})")
    print(f"  Ventilador: {estado.ventilador}  (disponíveis: {estado.ventiladores})")

    resp = input("\nTestar comandos? Liga, sobe 1 °C, volta a temperatura e restaura on/off. [s/N]: ")
    if resp.strip().lower() not in ("s", "sim"):
        return
    alvo = estado.temperatura_alvo or 24
    if not estado.ligado:
        print("- Ligando")
        ar.ligar()
        time.sleep(3)
    print(f"- Temperatura alvo {alvo + 1:g} °C")
    ar.definir_temperatura(alvo + 1)
    time.sleep(3)
    print(f"  Lido: {ar.estado().temperatura_alvo} °C")
    print(f"- Voltando para {alvo:g} °C")
    ar.definir_temperatura(alvo)
    if not estado.ligado:
        time.sleep(2)
        print("- Desligando")
        ar.desligar()
    print("OK")


def main() -> int:
    parser = argparse.ArgumentParser(prog="mothlit", description="Controle da lâmpada e do ar-condicionado.")
    parser.add_argument("comando", nargs="?", choices=["setup", "test-lampada", "test-ar"])
    parser.add_argument("--bandeja", action="store_true", help="abre escondido na bandeja (usado ao iniciar com o Windows)")
    args = parser.parse_args()

    try:
        if args.comando == "setup":
            from . import setup

            setup.executar()
        elif args.comando == "test-lampada":
            test_lampada()
        elif args.comando == "test-ar":
            test_ar()
        else:
            from .ui.app import executar

            config.configurar_log()
            executar(na_bandeja=args.bandeja)
    except (ErroDispositivo, config.ErroConfiguracao) as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
