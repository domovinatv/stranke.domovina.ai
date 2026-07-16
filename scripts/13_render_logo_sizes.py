"""Render the CDN size ladder (192/256/512/1024) from data/logos_orig/.

Policy identical to klubovi scripts/47:
  - SVG sources render every tier (rsvg-convert, keep aspect ratio)
  - raster sources render only tiers <= native max dimension (no upscaling)
  - all outputs 256-color quantized PNGs

Also writes data/logos_index.json — per slug: {logo, original, svg, sizes[],
brand_color} — uploaded to the CDN root as index.json.
"""
from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import connect  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("render_sizes")

LOGO_DIR = ROOT / "data" / "logos"
ORIG_DIR = ROOT / "data" / "logos_orig"
SIZED_DIR = ROOT / "data" / "logos_sized"
TIERS = [192, 256, 512, 1024]


def quantized(img: Image.Image) -> Image.Image:
    return img.convert("RGBA").quantize(colors=256, method=Image.Quantize.FASTOCTREE)


def render_svg(path: Path, width: int) -> Image.Image | None:
    try:
        out = subprocess.run(
            ["rsvg-convert", "-w", str(width), "--keep-aspect-ratio", str(path)],
            capture_output=True, check=True,
        ).stdout
        img = Image.open(io.BytesIO(out))
        img.load()
        return img
    except Exception as e:
        log.warning("svg render failed %s: %s", path.name, e)
        return None


def run() -> None:
    for t in TIERS:
        (SIZED_DIR / str(t)).mkdir(parents=True, exist_ok=True)

    index: dict[str, dict] = {}
    with connect() as conn:
        colors = {
            r["slug"]: r["brand_color"]
            for r in conn.execute(
                "SELECT slug, brand_color FROM parties WHERE brand_color IS NOT NULL"
            )
        }

    n_rendered = 0
    for orig in sorted(ORIG_DIR.iterdir()):
        if orig.suffix not in (".svg", ".png", ".jpg", ".gif", ".webp"):
            continue
        slug = orig.stem
        is_svg = orig.suffix == ".svg"
        sizes: list[int] = []

        if is_svg:
            for t in TIERS:
                img = render_svg(orig, t)
                if img:
                    quantized(img).save(SIZED_DIR / str(t) / f"{slug}.png",
                                        "PNG", optimize=True)
                    sizes.append(t)
        else:
            with Image.open(orig) as im:
                im.load()
                native = max(im.size)
                for t in TIERS:
                    if t > native:
                        continue
                    scaled = im.convert("RGBA").copy()
                    scaled.thumbnail((t, t), Image.LANCZOS)
                    quantized(scaled).save(SIZED_DIR / str(t) / f"{slug}.png",
                                           "PNG", optimize=True)
                    sizes.append(t)

        entry: dict = {"logo": f"logos/{slug}.png", "original": f"originals/{orig.name}"}
        if is_svg:
            entry["svg"] = True
        if sizes:
            entry["sizes"] = sizes
        if colors.get(slug):
            entry["brand_color"] = colors[slug]
        index[slug] = entry
        n_rendered += 1

    (ROOT / "data" / "logos_index.json").write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    per_tier = {t: len(list((SIZED_DIR / str(t)).glob("*.png"))) for t in TIERS}
    log.info("rendered %d parties; per-tier=%s", n_rendered, per_tier)


if __name__ == "__main__":
    run()
