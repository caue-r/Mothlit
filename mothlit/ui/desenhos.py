"""Ilustrações desenhadas com Pillow (ar-condicionado, quarto iluminado, roda de cores).

Tudo é renderizado em escala maior e reduzido, para bordas suaves.
"""

import colorsys
import math
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from . import tema

ESCALA = 2


def _rgb(hexa: str) -> tuple[int, int, int]:
    hexa = hexa.lstrip("#")
    return tuple(int(hexa[i : i + 2], 16) for i in (0, 2, 4))


# --- ar-condicionado ---------------------------------------------------------

AR_LARGURA, AR_ALTURA = 340, 190
QUADROS_VENTO = 8


@lru_cache(maxsize=64)
def ar_condicionado(ligado: bool, temperatura: str, quadro: int = 0) -> Image.Image:
    s = ESCALA
    w, h = AR_LARGURA * s, AR_ALTURA * s
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    x0, y0, x1, y1 = 30 * s, 12 * s, (AR_LARGURA - 30) * s, 92 * s

    # sombra
    sombra = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((x0, y0 + 10 * s, x1, y1 + 8 * s), 18 * s, fill=(0, 0, 0, 150))
    img.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(12 * s)))

    # corpo com degradê vertical
    corpo = Image.new("RGBA", (x1 - x0, y1 - y0))
    dc = ImageDraw.Draw(corpo)
    for y in range(y1 - y0):
        t = y / (y1 - y0)
        cor = tuple(int(255 - (255 - c) * t) for c in (214, 222, 230))
        dc.line((0, y, x1 - x0, y), fill=(*cor, 255))
    mascara = Image.new("L", corpo.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, *corpo.size), 18 * s, fill=255)
    img.paste(corpo, (x0, y0), mascara)

    d = ImageDraw.Draw(img)
    # saída de ar
    d.rounded_rectangle((x0 + 14 * s, y1 - 18 * s, x1 - 14 * s, y1 - 9 * s), 4 * s, fill=(28, 36, 46, 255))
    d.rounded_rectangle((x0 + 18 * s, y1 - 16 * s, x1 - 18 * s, y1 - 13 * s), 2 * s, fill=(70, 82, 96, 255))
    # LED de status
    cor_led = _rgb(tema.DESTAQUE) if ligado else (150, 160, 170)
    d.ellipse((x0 + 22 * s, y0 + 22 * s, x0 + 26 * s, y0 + 26 * s), fill=(*cor_led, 255))
    # visor
    if ligado and temperatura:
        f = ImageFont.truetype("seguisb.ttf", 15 * s) if _tem_fonte("seguisb.ttf") else None
        d.text((x1 - 28 * s, y0 + 28 * s), temperatura, font=f, fill=(*_rgb(tema.DESTAQUE), 255), anchor="rm")

    if ligado:
        img.alpha_composite(_vento(w, h, x0, x1, y1, quadro))

    return img.resize((AR_LARGURA, AR_ALTURA), Image.LANCZOS)


def _vento(w, h, x0, x1, y1, quadro):
    """Linhas de ar saindo em leque; `quadro` desloca o brilho para dar movimento."""
    s = ESCALA
    camada = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    n = 15
    altura = 80 * s
    fase = quadro / QUADROS_VENTO
    for i in range(n):
        t = i / (n - 1)
        xs = x0 + 40 * s + t * (x1 - x0 - 80 * s)
        abertura = (t - 0.5) * 70 * s
        pontos = []
        passos = 24
        for k in range(passos):
            u = k / (passos - 1)
            x = xs + abertura * u + math.sin(u * 3 + i) * 3 * s
            y = y1 + 4 * s + u * altura
            pontos.append((x, y, u))
        for k in range(passos - 1):
            u = pontos[k][2]
            onda = 0.5 + 0.5 * math.sin((u - fase) * math.tau * 1.5 + i * 0.7)
            alfa = int(160 * (1 - u) * onda)
            d.line((pontos[k][:2], pontos[k + 1][:2]), fill=(200, 225, 240, alfa), width=max(1, s))
    return camada.filter(ImageFilter.GaussianBlur(0.6 * s))


# --- quarto com o painel de LED ----------------------------------------------

QUARTO_LARGURA, QUARTO_ALTURA = 360, 200


@lru_cache(maxsize=1)
def _quarto_base() -> Image.Image:
    s = ESCALA
    w, h = QUARTO_LARGURA * s, QUARTO_ALTURA * s
    img = Image.new("RGB", (w, h), (34, 44, 54))
    d = ImageDraw.Draw(img)
    # parede do fundo (retângulo central) e superfícies em perspectiva
    fx0, fy0, fx1, fy1 = 95 * s, 60 * s, 265 * s, 160 * s
    d.polygon([(0, 0), (w, 0), (fx1, fy0), (fx0, fy0)], fill=(52, 63, 74))  # teto
    d.polygon([(0, 0), (fx0, fy0), (fx0, fy1), (0, h)], fill=(40, 50, 61))  # parede esquerda
    d.polygon([(w, 0), (fx1, fy0), (fx1, fy1), (w, h)], fill=(44, 55, 66))  # parede direita
    d.polygon([(0, h), (fx0, fy1), (fx1, fy1), (w, h)], fill=(30, 38, 47))  # chão
    d.rectangle((fx0, fy0, fx1, fy1), fill=(58, 70, 82))  # fundo
    # janela com persiana na parede direita
    for k in range(9):
        y = 70 * s + k * 9 * s
        d.line(((300 * s, y + 6 * s), (340 * s, y - 2 * s)), fill=(75, 88, 100), width=3 * s)
    # cama simples
    d.polygon([(120 * s, 150 * s), (240 * s, 150 * s), (262 * s, 178 * s), (98 * s, 178 * s)], fill=(62, 74, 88))
    d.rectangle((98 * s, 178 * s, 262 * s, 186 * s), fill=(48, 58, 70))
    return img


def _painel_teto(d, s, cor):
    # painel quadrado de sobrepor visto em perspectiva no teto
    d.polygon([(150 * s, 26 * s), (210 * s, 26 * s), (222 * s, 42 * s), (138 * s, 42 * s)], fill=cor)


@lru_cache(maxsize=64)
def quarto(ligada: bool, cor: tuple[int, int, int], intensidade: float) -> Image.Image:
    """Quarto escuro; com a lâmpada ligada, o painel e o ambiente recebem a cor da luz."""
    s = ESCALA
    base = _quarto_base().copy()
    if not ligada:
        d = ImageDraw.Draw(base)
        _painel_teto(d, s, (88, 98, 108))
        base = Image.blend(base, Image.new("RGB", base.size, (14, 20, 28)), 0.35)
    else:
        w, h = base.size
        intensidade = max(0.15, min(1.0, intensidade))
        # brilho radial vindo do teto
        glow = Image.radial_gradient("L").resize((int(w * 1.3), int(h * 1.9)))
        glow = ImageChops.invert(glow)
        mascara = Image.new("L", (w, h), 0)
        mascara.paste(glow, (int(w / 2 - glow.width / 2), int(34 * s - glow.height / 2)))
        mascara = mascara.point(lambda v: int(255 * (v / 255) ** 2.2 * 0.95 * intensidade))
        luz = Image.new("RGB", (w, h), cor)
        base = ImageChops.screen(base, Image.composite(luz, Image.new("RGB", (w, h), 0), mascara))
        d = ImageDraw.Draw(base)
        nucleo = tuple(int(c + (255 - c) * 0.55) for c in cor)
        _painel_teto(d, s, nucleo)
        base = base.filter(ImageFilter.SMOOTH)

    mascara = Image.new("L", base.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, *base.size), 14 * s, fill=255)
    final = Image.new("RGBA", base.size, (0, 0, 0, 0))
    final.paste(base, (0, 0), mascara)
    return final.resize((QUARTO_LARGURA, QUARTO_ALTURA), Image.LANCZOS)


def cor_do_branco(temperatura: int) -> tuple[int, int, int]:
    """0 % = branco quente (~2700 K), 100 % = branco frio (~6500 K)."""
    t = max(0, min(100, temperatura)) / 100
    quente, frio = (255, 190, 120), (205, 225, 255)
    return tuple(int(q + (f - q) * t) for q, f in zip(quente, frio))


# --- roda de cores -----------------------------------------------------------


@lru_cache(maxsize=4)
def anel_matiz(diametro: int, espessura: int, fundo: str) -> Image.Image:
    s = ESCALA
    D = diametro * s
    img = Image.new("RGB", (D, D), _rgb(fundo))
    px = img.load()
    c = D / 2
    r_ext, r_int = c, c - espessura * s
    for y in range(D):
        for x in range(D):
            dx, dy = x - c + 0.5, y - c + 0.5
            r = math.hypot(dx, dy)
            if r_int <= r <= r_ext:
                h = (math.degrees(math.atan2(dx, -dy)) % 360) / 360  # 0° no topo, sentido horário
                px[x, y] = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(h, 1, 1))
    mascara = Image.new("L", (D, D), 0)
    md = ImageDraw.Draw(mascara)
    md.ellipse((0, 0, D - 1, D - 1), fill=255)
    md.ellipse((espessura * s, espessura * s, D - espessura * s - 1, D - espessura * s - 1), fill=0)
    final = Image.new("RGB", (D, D), _rgb(fundo))
    final.paste(img, (0, 0), mascara)
    return final.resize((diametro, diametro), Image.LANCZOS)


def quadrado_sv(lado: int, matiz: float) -> Image.Image:
    """Saturação no eixo x (branco → cor) e brilho no eixo y (cima claro → baixo escuro)."""
    cor = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(matiz, 1, 1))
    img = Image.new("RGB", (lado, lado), cor)
    horizontal = Image.linear_gradient("L").rotate(-90).resize((lado, lado))  # esquerda 255 → direita 0
    img = Image.composite(Image.new("RGB", (lado, lado), (255, 255, 255)), img, horizontal)
    vertical = Image.linear_gradient("L").resize((lado, lado))  # topo 0 → base 255
    return Image.composite(Image.new("RGB", (lado, lado), (0, 0, 0)), img, vertical)


def _tem_fonte(nome: str) -> bool:
    try:
        ImageFont.truetype(nome, 10)
        return True
    except OSError:
        return False
