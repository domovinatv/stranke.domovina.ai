"""Firecrawl contact backfill over the parties table.

Usage:
    uv run python scripts/06_backfill.py --unprocessed          # all without a run
    uv run python scripts/06_backfill.py --unprocessed --limit 20
    uv run python scripts/06_backfill.py --slug hdz             # single party
    uv run python scripts/06_backfill.py --all-active           # every AKTIVAN

Requires FIRECRAWL_API_KEYS in .env (comma-separated; auto-rotates on 402).
Stops gracefully when every key is out of credits.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backfill import backfill_party  # noqa: E402
from src.db import connect  # noqa: E402
from src.firecrawl import FirecrawlClient, InsufficientCreditsError  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill")


def main() -> None:
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--unprocessed", action="store_true",
                       help="active parties without any backfill run yet")
    group.add_argument("--all-active", action="store_true",
                       help="every AKTIVAN party regardless of previous runs")
    group.add_argument("--slug", help="single party by slug")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    with connect() as conn:
        if args.slug:
            rows = conn.execute(
                "SELECT * FROM parties WHERE slug = ?", (args.slug,)
            ).fetchall()
        elif args.all_active:
            rows = conn.execute(
                "SELECT * FROM parties WHERE status = 'AKTIVAN' ORDER BY canonical_name"
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT p.* FROM parties p
                   LEFT JOIN backfill_runs r ON r.party_id = p.id
                   WHERE p.status = 'AKTIVAN' AND r.run_id IS NULL
                   ORDER BY p.canonical_name"""
            ).fetchall()
        if args.limit:
            rows = rows[: args.limit]
        log.info("parties to backfill: %d", len(rows))
        if not rows:
            return

        stats: dict[str, int] = {}
        with FirecrawlClient() as client:
            for i, row in enumerate(rows, 1):
                try:
                    result = backfill_party(conn, client, dict(row))
                except InsufficientCreditsError:
                    log.warning("all Firecrawl keys out of credits — stopping")
                    break
                stats[result["status"]] = stats.get(result["status"], 0) + 1
                log.info(
                    "[%d/%d] %s -> %s %s",
                    i, len(rows), result["name"], result["status"],
                    result.get("fields") or "",
                )
                conn.commit()
            conn.commit()
        log.info("done. statuses=%s credits_used~%d", stats, client.credits_used)


if __name__ == "__main__":
    main()
