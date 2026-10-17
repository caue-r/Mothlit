"""Cores, fontes e ícones da interface."""

from functools import lru_cache
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

# Paleta (azul-marinho escuro com destaque ciano)
FUNDO = "#0b1520"
CARD = "#111e2b"
CARD_BORDA = "#1b2b3b"
BLOCO = "#14222f"
BLOCO_HOVER = "#1a2b3b"
BLOCO_BORDA = "#21334a"
DESTAQUE = "#7fd4f2"
DESTAQUE_HOVER = "#9be0f7"
TEXTO_SOBRE_DESTAQUE = "#08202c"
TEXTO = "#e7eef5"
TEXTO_SUAVE = "#8da2b6"
TEXTO_APAGADO = "#4f6274"
ERRO = "#ff7b72"
OK = "#5fd38d"

_PASTA_FONTES = Path(r"C:\Windows\Fonts")
# Segoe Fluent Icons (Windows 11) ou Segoe MDL2 Assets (Windows 10): mesmos códigos.
_FONTES_ICONE = ["SegoeIcons.ttf", "segmdl2.ttf"]

# Códigos conferidos visualmente na fonte
ICONE_ENERGIA = "\ue7e8"
ICONE_ENGRENAGEM = "\ue713"
ICONE_MINIMIZAR = "\ue921"
ICONE_FECHAR = "\ue8bb"
ICONE_ATUALIZAR = "\ue72c"
ICONE_CASA = "\ue80f"
ICONE_LAMPADA = "\uea80"
ICONE_SETA_BAIXO = "\ue70d"
ICONE_SOL = "\ue706"
ICONE_LUA = "\ue708"
ICONE_GOTA = "\ueb42"
ICONE_OSCILAR = "\ue8ab"
ICONE_AUTO = "\ue895"
ICONE_PALETA = "\ue790"
ICONE_TERMOMETRO = "\ue9ca"
ICONE_MAIS = "\ue710"
ICONE_MENOS = "\ue738"
ICONE_FLOCO = "floco"  # desenhado com a fonte Segoe UI Symbol
ICONE_VENTILADOR = "ventilador"  # desenhado à mão


def fonte(tamanho: int = 13, peso: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI", size=tamanho, weight=peso)


def fonte_display(tamanho: int) -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI Light", size=tamanho)


@lru_cache(maxsize=None)
def _fonte_pil(nome: str, tamanho: int):
    try:
        return ImageFont.truetype(str(_PASTA_FONTES / nome), tamanho)
    except OSError:
        return None


@lru_cache(maxsize=None)
def icone(codigo: str, tamanho: int = 18, cor: str = TEXTO) -> ctk.CTkImage:
    """Renderiza um ícone em 3x e entrega como CTkImage (nítido em telas com escala)."""
    escala = 3
    lado = tamanho * escala
    imagem = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(imagem)

    if codigo == ICONE_VENTILADOR:
        _desenhar_ventilador(imagem, lado, cor)
    else:
        if codigo == ICONE_FLOCO:
            texto, pil = "\u2744", _fonte_pil("seguisym.ttf", int(lado * 0.9))
        else:
            texto = codigo
            pil = next((f for f in (_fonte_pil(n, int(lado * 0.82)) for n in _FONTES_ICONE) if f), None)
        if pil is not None:
            d.text((lado / 2, lado / 2), texto, font=pil, fill=cor, anchor="mm")

    return ctk.CTkImage(light_image=imagem, dark_image=imagem, size=(tamanho, tamanho))


def _desenhar_ventilador(destino: Image.Image, lado: int, cor: str) -> None:
    """Três pás em elipse giradas 120° em volta de um cubo central."""
    c = lado / 2
    largura = max(2, lado // 13)
    pa = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    ImageDraw.Draw(pa).ellipse(
        (c - lado * 0.15, c - lado * 0.46, c + lado * 0.15, c - lado * 0.08), outline=cor, width=largura
    )
    pa = pa.rotate(-18, resample=Image.BICUBIC, center=(c, c))  # leve inclinação, como hélice
    for angulo in (0, 120, 240):
        destino.alpha_composite(pa.rotate(angulo, resample=Image.BICUBIC, center=(c, c)))
    rc = lado * 0.07
    ImageDraw.Draw(destino).ellipse((c - rc, c - rc, c + rc, c + rc), fill=cor)
