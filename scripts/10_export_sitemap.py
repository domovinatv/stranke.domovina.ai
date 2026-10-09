"""Generate sitemap.xml + robots.txt into frontend/public/ from the SQLite catalog.

Run after 09_export_static.py — frontend/public/data/parties.json must exist.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PUBLIC = ROOT / "frontend" / "public"
SITE = "https://stranke.domovina.ai"


def main() -> None:
    parties = json.loads((PUBLIC / "data" / "parties.json").read_text())
    cities = json.loads((PUBLIC / "data" / "cities.json").read_text())

    today = datetime.now(timezone.utc).date().isoformat()
    urls: list[tuple[str, str, str]] = [
        ("/", "1.0", "weekly"),
        ("/karta", "0.9", "weekly"),
        ("/financiranje", "0.9", "monthly"),
        ("/statistika", "0.8", "monthly"),
        ("/o-projektu", "0.5", "yearly"),
    ]
    for p in parties:
        urls.append((f"/stranka/{p['slug']}", "0.7", "monthly"))
    for c in cities:
        urls.append((f"/grad/{quote(c['name'])}", "0.6", "monthly"))

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, prio, freq in urls:
        parts.append(
            "<url>"
            f"<loc>{SITE}{escape(path)}</loc>"
            f"<lastmod>{today}</lastmod>"
            f"<changefreq>{freq}</changefreq>"
            f"<priority>{prio}</priority>"
            "</url>"
        )
    parts.append("</urlset>")

    (PUBLIC / "sitemap.xml").write_text("\n".join(parts), encoding="utf-8")
    (PUBLIC / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\nSitemap: " + SITE + "/sitemap.xml\n",
        encoding="utf-8",
    )
    print(f"sitemap_urls={len(urls)}")


if __name__ == "__main__":
    main()
