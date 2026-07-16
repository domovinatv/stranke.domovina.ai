"""Build the parties_fts virtual table for full-text search.

FTS5 with unicode61 tokenizer and diacritics removal so a query for
"djakovo" also matches "Đakovo", "Sibenik" matches "Šibenik" etc.

Idempotent: drops + recreates the table on each run.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import connect  # noqa: E402
from src.normalize import strip_diacritics  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("build_fts")

FTS_SCHEMA = """
DROP TABLE IF EXISTS parties_fts;
CREATE VIRTUAL TABLE parties_fts USING fts5(
  slug UNINDEXED,
  name,
  short_name,
  city,
  address,
  aliases,
  tokenize = "unicode61 remove_diacritics 2"
);
"""


def run() -> None:
    with connect() as conn:
        conn.executescript(FTS_SCHEMA)
        rows = conn.execute(
            """
            SELECT
              p.slug,
              p.canonical_name,
              COALESCE(p.short_name, '')                AS short_name,
              COALESCE(p.city, '')                      AS city,
              COALESCE(p.address, '')                   AS address,
              COALESCE(GROUP_CONCAT(a.alias, ' '), '')  AS aliases
            FROM parties p
            LEFT JOIN party_aliases a ON a.party_id = p.id
            GROUP BY p.id
            """
        ).fetchall()

        # FTS5's unicode61 tokenizer doesn't decompose Đ/đ (same blind spot as
        # the slug normalizer) — run every field through strip_diacritics.
        def _norm(s: str) -> str:
            return strip_diacritics(s or "").lower()

        conn.executemany(
            "INSERT INTO parties_fts (slug, name, short_name, city, address, aliases) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (r["slug"], _norm(r["canonical_name"]), _norm(r["short_name"]),
                 _norm(r["city"]), _norm(r["address"]), _norm(r["aliases"]))
                for r in rows
            ],
        )
        conn.commit()
        log.info("indexed %d parties into parties_fts", len(rows))


if __name__ == "__main__":
    run()
