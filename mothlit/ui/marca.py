"""Ícone do Mothlit (mariposa) a partir de web/moth.svg.

O SVG usa só comandos M/L/Z absolutos, então dá para rasterizar com Pillow
sem dependências extras. A interface web usa o SVG direto; aqui geramos o .ico
da janela/barra de tarefas (e da bandeja, na Fase 3).
"""

import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

from .. import config

SVG = Path(__file__).resolve().parent / "web" / "moth.svg"


@lru_cache(maxsize=1)
def _poligonos() -> tuple[list[list[tuple[float, float]]], float]:
    texto = SVG.read_text(encoding="utf-8")
    lado = float(re.search(r'viewBox="0 0 ([\d.]+)', texto).group(1))
    caminho = re.search(r'\sd="([^"]+)"', texto).group(1)
    poligonos, atual = [], []
    for comando, numeros in re.findall(r"([MLZ])([^MLZ]*)", caminho):
        if comando == "M" and atual:
            poligonos.append(atual)
            atual = []
        if comando in "ML":
            valores = [float(v) for v in re.findall(r"-?[\d.]+", numeros)]
            atual.extend(zip(valores[0::2], valores[1::2]))
        elif comando == "Z" and atual:
            poligonos.append(atual)
            atual = []
    if atual:
        poligonos.append(atual)
    return poligonos, lado


@lru_cache(maxsize=None)
def imagem(tamanho: int, cor: str = "#f4f4f5") -> Image.Image:
    """Silhueta da mariposa, recortada nas bordas e centralizada num quadrado."""
    poligonos, _ = _poligonos()
    escala = 4
    grande = tamanho * escala
    img = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    xs = [x for p in poligonos for x, _ in p]
    ys = [y for p in poligonos for _, y in p]
    largura, altura = max(xs) - min(xs), max(ys) - min(ys)
    fator = grande * 0.92 / max(largura, altura)
    dx = (grande - largura * fator) / 2 - min(xs) * fator
    dy = (grande - altura * fator) / 2 - min(ys) * fator
    for p in poligonos:
        d.polygon([(x * fator + dx, y * fator + dy) for x, y in p], fill=cor)
    return img.resize((tamanho, tamanho), Image.LANCZOS)


def arquivo_ico() -> Path:
    """Gera (uma vez) o .ico usado na barra de tarefas e na bandeja."""
    caminho = config.pasta_config() / "mothlit.ico"
    if not caminho.exists() or caminho.stat().st_mtime < SVG.stat().st_mtime:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        base = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        fundo = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        ImageDraw.Draw(fundo).rounded_rectangle((0, 0, 255, 255), 56, fill="#09090b")
        base.alpha_composite(fundo)
        base.alpha_composite(imagem(200), (28, 28))
        base.save(caminho, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return caminho
