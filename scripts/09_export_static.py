"""Export the SQLite catalog as static JSON for the React PWA frontend.

Writes:
    frontend/public/data/parties.json        — flat array, one row per party
    frontend/public/data/cities.json         — city list with counts
    frontend/public/data/stats.json          — global coverage numbers
    frontend/public/data/parties/<slug>.json — per-party detail (people,
                                               functions timeline, aliases, notes)
    frontend/public/data/manifest.json       — { generated_at, counts, schema_version }

Run:
    uv run python scripts/09_export_static.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import connect  # noqa: E402

OUT_DIR = ROOT / "frontend" / "public" / "data"
LOGO_SRC = ROOT / "data" / "logos"
SIZED_SRC = ROOT / "data" / "logos_sized"
LOGO_TIERS = [192, 256, 512, 1024]

SCHEMA_VERSION = 2

LIST_COLUMNS = [
    "id", "slug", "canonical_name", "short_name", "oib", "reg_number",
    "status", "registered_at", "status_date", "city", "address", "county",
    "founded_place", "founded_date", "website", "email", "phone",
    "phone_kind", "phone_e164", "fb_url", "ig_url", "x_url", "president",
    "wiki_url", "brand_color", "lat", "lng",
]


def _ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "parties").mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _logo_sizes(slug: str) -> list[int]:
    """Size tiers genuinely available on the p.ff.hr CDN (no upscaling)."""
    return [s for s in LOGO_TIERS if (SIZED_SRC / str(s) / f"{slug}.png").exists()]


def export_parties(conn) -> list[dict]:
    rows = conn.execute(
        f"SELECT {', '.join(LIST_COLUMNS)} FROM parties ORDER BY canonical_name"
    ).fetchall()
    parties = []
    for r in rows:
        d = dict(r)
        if (LOGO_SRC / f"{d['slug']}.png").exists():
            d["logo"] = f"{d['slug']}.png"
            sizes = _logo_sizes(d["slug"])
            if sizes:
                d["logo_sizes"] = sizes
        # drop nulls to shrink payload
        parties.append({k: v for k, v in d.items() if v not in (None, "")})
    return parties


def export_cities(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT city AS name, COUNT(*) AS n,
               SUM(CASE WHEN status = 'AKTIVAN' THEN 1 ELSE 0 END) AS active
        FROM parties WHERE city IS NOT NULL
        GROUP BY city ORDER BY n DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def export_stats(conn) -> dict:
    g = dict(conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN status = 'AKTIVAN' THEN 1 ELSE 0 END) AS active,
          SUM(CASE WHEN status = 'PRESTANAK' THEN 1 ELSE 0 END) AS defunct,
          SUM(CASE WHEN lat IS NOT NULL THEN 1 ELSE 0 END) AS with_geo,
          SUM(CASE WHEN phone_kind = 'mobile' THEN 1 ELSE 0 END) AS can_sms,
          SUM(CASE WHEN phone IS NOT NULL THEN 1 ELSE 0 END) AS can_call,
          SUM(CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) AS can_email,
          SUM(CASE WHEN address IS NOT NULL THEN 1 ELSE 0 END) AS can_mail,
          SUM(CASE WHEN
            website IS NOT NULL OR fb_url IS NOT NULL OR ig_url IS NOT NULL
            OR x_url IS NOT NULL THEN 1 ELSE 0 END) AS can_web,
          SUM(CASE WHEN
            phone IS NOT NULL AND email IS NOT NULL AND address IS NOT NULL
            AND (website IS NOT NULL OR fb_url IS NOT NULL OR ig_url IS NOT NULL)
            THEN 1 ELSE 0 END) AS full_contact,
          SUM(CASE WHEN president IS NOT NULL THEN 1 ELSE 0 END) AS with_president,
          SUM(CASE WHEN oib IS NOT NULL THEN 1 ELSE 0 END) AS with_oib,
          SUM(CASE WHEN wiki_url IS NOT NULL THEN 1 ELSE 0 END) AS with_wiki
        FROM parties
        """
    ).fetchone())

    decades = conn.execute(
        """
        SELECT SUBSTR(registered_at, 1, 3) || '0-e' AS decade, COUNT(*) AS n
        FROM parties WHERE registered_at IS NOT NULL
        GROUP BY decade ORDER BY decade
        """
    ).fetchall()

    return {"global": g, "decades": [dict(r) for r in decades]}


def export_party_details(conn, ids: list[int]) -> int:
    n = 0
    for pid in ids:
        p = conn.execute("SELECT * FROM parties WHERE id = ?", (pid,)).fetchone()
        if not p:
            continue
        people = conn.execute(
            """SELECT full_name, role, represents FROM party_people
               WHERE party_id = ?
               ORDER BY (role != 'PREDSJEDNIK'), full_name""",
            (pid,),
        ).fetchall()
        functions = conn.execute(
            """SELECT function, holder, mandate_start, mandate_end
               FROM party_functions WHERE party_id = ?
               ORDER BY function, mandate_start""",
            (pid,),
        ).fetchall()
        aliases = conn.execute(
            "SELECT alias, source FROM party_aliases WHERE party_id = ? ORDER BY alias",
            (pid,),
        ).fetchall()
        payload = {
            "id": pid,
            "slug": p["slug"],
            "notes": p["notes"],
            "seat": p["seat"],
            "book_number": p["book_number"],
            "people": [dict(r) for r in people],
            "functions": [dict(r) for r in functions],
            "aliases": [dict(r) for r in aliases],
        }
        _write_json(OUT_DIR / "parties" / f"{p['slug']}.json", payload)
        n += 1
    return n


def main() -> None:
    _ensure_dirs()
    with connect() as conn:
        parties = export_parties(conn)
        cities = export_cities(conn)
        stats = export_stats(conn)
        details_n = export_party_details(conn, [p["id"] for p in parties])

    _write_json(OUT_DIR / "parties.json", parties)
    _write_json(OUT_DIR / "cities.json", cities)
    _write_json(OUT_DIR / "stats.json", stats)
    _write_json(
        OUT_DIR / "manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "counts": {
                "parties": len(parties),
                "cities": len(cities),
                "party_details": details_n,
            },
        },
    )
    print(f"parties={len(parties)} cities={len(cities)} details={details_n}")


if __name__ == "__main__":
    main()
