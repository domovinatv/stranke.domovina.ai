"""Fill parties.brand_color for parties that have a logo but no Wikidata P465.

Dominant-color heuristic over the web PNG (data/logos/{slug}.png):
  - sample non-transparent, non-near-white, non-near-black pixels
  - quantize to a small palette and take the most frequent cluster
  - skip low-saturation results (grey logos get no color rather than mud)

Idempotent: only fills rows where brand_color IS NULL.
"""
from __future__ import annotations

import colorsys
import logging
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import connect  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("brand_colors")

LOGO_DIR = ROOT / "data" / "logos"


def dominant_color(path: Path) -> str | None:
    with Image.open(path) as im:
        img = im.convert("RGBA")
    img.thumbnail((128, 128))
    pixels = [
        (r, g, b)
        for r, g, b, a in img.getdata()
        if a > 128
        and not (r > 235 and g > 235 and b > 235)   # near-white
        and not (r < 25 and g < 25 and b < 25)      # near-black
    ]
    if len(pixels) < 50:
        return None
    sample = Image.new("RGB", (len(pixels), 1))
    sample.putdata(pixels)
    quant = sample.quantize(colors=8, method=Image.Quantize.FASTOCTREE)
    palette = quant.getpalette()
    counts = sorted(quant.getcolors(), reverse=True)
    for count, idx in counts:
        r, g, b = palette[idx * 3: idx * 3 + 3]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s >= 0.25 and v >= 0.25:
            return f"#{r:02X}{g:02X}{b:02X}"
    return None


def run() -> None:
    with connect() as conn:
        rows = conn.execute(
            "SELECT slug FROM parties WHERE brand_color IS NULL"
        ).fetchall()
        n = 0
        for r in rows:
            p = LOGO_DIR / f"{r['slug']}.png"
            if not p.exists():
                continue
            color = dominant_color(p)
            if color:
                conn.execute(
                    "UPDATE parties SET brand_color = ? WHERE slug = ?",
                    (color, r["slug"]),
                )
                n += 1
                log.info("%s -> %s", r["slug"], color)
        conn.commit()
        total = conn.execute(
            "SELECT COUNT(*) FROM parties WHERE brand_color IS NOT NULL"
        ).fetchone()[0]
        log.info("filled %d; parties with brand_color now: %d", n, total)


if __name__ == "__main__":
    run()
