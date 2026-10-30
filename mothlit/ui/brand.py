"""Mothlit icon (moth) built from web/moth.svg.

The SVG only uses absolute M/L/Z commands, so it can be rasterized with Pillow
without extra dependencies. The web interface uses the SVG directly; here we build the .ico
for the window/taskbar and for the tray.
"""

import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .. import config

SVG = Path(__file__).resolve().parent / "web" / "moth.svg"


@lru_cache(maxsize=1)
def _polygons() -> tuple[list[list[tuple[float, float]]], float]:
    text = SVG.read_text(encoding="utf-8")
    side = float(re.search(r'viewBox="0 0 ([\d.]+)', text).group(1))
    path = re.search(r'\sd="([^"]+)"', text).group(1)
    polygons, current = [], []
    for command, numbers in re.findall(r"([MLZ])([^MLZ]*)", path):
        if command == "M" and current:
            polygons.append(current)
            current = []
        if command in "ML":
            values = [float(v) for v in re.findall(r"-?[\d.]+", numbers)]
            current.extend(zip(values[0::2], values[1::2]))
        elif command == "Z" and current:
            polygons.append(current)
            current = []
    if current:
        polygons.append(current)
    return polygons, side


@lru_cache(maxsize=None)
def image(size: int, color: str = "#f4f4f5") -> Image.Image:
    """Moth silhouette, trimmed at the edges and centered in a square."""
    polygons, _ = _polygons()
    scale = 4
    big = size * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    xs = [x for p in polygons for x, _ in p]
    ys = [y for p in polygons for _, y in p]
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    factor = big * 0.92 / max(width, height)
    dx = (big - width * factor) / 2 - min(xs) * factor
    dy = (big - height * factor) / 2 - min(ys) * factor
    for p in polygons:
        d.polygon([(x * factor + dx, y * factor + dy) for x, y in p], fill=color)
    return img.resize((size, size), Image.LANCZOS)


TRAY_SIZES = (16, 20, 24, 32, 40, 48, 64)  # 16 px at 100% scaling; larger on zoomed displays


def tray_image(size: int, color: str = "#f4f4f5") -> Image.Image:
    """Moth for the tray: touching the edges and drawn at the exact size.

    The tray slot is fixed (16x16 at 100%) and the moth is ~2x wider than it is tall,
    so the most it can do is fill the whole width. At small sizes the stroke is slightly
    thickened so the wings do not vanish.
    """
    polygons, _ = _polygons()
    scale = 8
    big = size * scale
    xs = [x for p in polygons for x, _ in p]
    ys = [y for p in polygons for _, y in p]
    factor = big / (max(xs) - min(xs))
    dx = -min(xs) * factor
    dy = (big - (max(ys) - min(ys)) * factor) / 2 - min(ys) * factor
    mask = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(mask)
    for p in polygons:
        d.polygon([(x * factor + dx, y * factor + dy) for x, y in p], fill=255)
    if size <= 24:
        mask = mask.filter(ImageFilter.MaxFilter(3))
    img = Image.new("RGBA", (size, size), color)
    img.putalpha(mask.resize((size, size), Image.LANCZOS))
    return img


# Bump it when the tray drawing changes: the file name changes and the .ico is rebuilt.
# (It cannot compare against this .py's date: in the executable it does not exist as a file.)
TRAY_ICON_VERSION = 2


def tray_ico() -> Path:
    """Multi-size tray .ico (each size drawn natively), in %APPDATA%\\Mothlit."""
    path = config.config_dir() / f"tray-v{TRAY_ICON_VERSION}.ico"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        frames = [tray_image(s) for s in TRAY_SIZES]
        largest = frames[-1]
        largest.save(path, format="ICO", sizes=[(s, s) for s in TRAY_SIZES], append_images=frames[:-1])
    return path


def make_ico(destination: Path) -> Path:
    """Light moth on a dark rounded square, in every size Windows uses."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    base = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    ImageDraw.Draw(base).rounded_rectangle((0, 0, 255, 255), 56, fill="#09090b")
    base.alpha_composite(image(200), (28, 28))
    base.save(destination, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return destination


def ico_file() -> Path:
    """The window/taskbar .ico, built once in %APPDATA%\\Mothlit (and again if the SVG changes)."""
    path = config.config_dir() / "mothlit.ico"
    if not path.exists() or path.stat().st_mtime < SVG.stat().st_mtime:
        make_ico(path)
    return path
