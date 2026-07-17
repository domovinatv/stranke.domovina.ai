"""Standardized square PWA icons per party (mirror of klubovi scripts/50 +
politika/novcanik-prototip scripts/render_square_icons.py).

For every AKTIVAN party with a logo (data/logos_sized/1024 or best tier):
  data/export/party_square/{slug}.png            1024x1024 opaque, logo in 70% box
  data/export/party_square/maskable/{slug}.png   56% box (Android adaptive safe zone)

Background heuristic (contrast guard — the politika logoBg lesson): party logos
are mostly colored marks that read best on WHITE; a predominantly light/white
logo (mean opaque luminance > 0.72) would vanish, so it gets the party primary
(from parties-app.json brand) or neutral navy #1D2440 instead.

Run: uv run python scripts/16_render_party_square_icons.py   (after 15)
Upload: scripts/17_upload_party_square.sh
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SIZED = ROOT / "data" / "logos_sized"
APP_JSON = ROOT / "data" / "export" / "parties-app.json"
OUT = ROOT / "data" / "export" / "party_square"

SIZE = 1024
VARIANTS = {"icon": 0.70, "maskable": 0.56}
LIGHT_LOGO_LUM = 0.72
NEUTRAL_DARK = (0x1D, 0x24, 0x40, 255)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("party_square")


def best_logo(slug: str) -> Path | None:
    for tier in ("1024", "512", "256", "192"):
        p = SIZED / tier / f"{slug}.png"
        if p.exists():
            return p
    return None


def mean_luminance(img: Image.Image) -> float:
    acc = n = 0
    for r, g, b, a in img.convert("RGBA").getdata():
        if a >= 128:
            acc += 0.2126 * r + 0.7152 * g + 0.0722 * b
            n += 1
    return (acc / n / 255) if n else 0.0


def hex_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4)) + (255,)


def run() -> None:
    parties = json.loads(APP_JSON.read_text(encoding="utf-8"))
    n_done = n_dark_bg = 0
    for p in parties:
        src = best_logo(p["slug"])
        if not src:
            continue
        logo = Image.open(src).convert("RGBA")
        light = mean_luminance(logo) > LIGHT_LOGO_LUM
        bg = hex_rgb(p["brand"]["primaryHex"]) if (light and p.get("brand")) else (NEUTRAL_DARK if light else (255, 255, 255, 255))
        if light:
            n_dark_bg += 1
        for variant, ratio in VARIANTS.items():
            box = round(SIZE * ratio)
            ic = logo.copy()
            ic.thumbnail((box, box), Image.LANCZOS)
            canvas = Image.new("RGBA", (SIZE, SIZE), bg)
            canvas.paste(ic, ((SIZE - ic.width) // 2, (SIZE - ic.height) // 2), ic)
            out_dir = OUT if variant == "icon" else OUT / "maskable"
            out_dir.mkdir(parents=True, exist_ok=True)
            canvas.convert("RGB").save(out_dir / f"{p['slug']}.png", "PNG", optimize=True)
        n_done += 1
    log.info("rendered %d parties (%d light logos on colored bg) -> %s", n_done, n_dark_bg, OUT)


if __name__ == "__main__":
    run()
