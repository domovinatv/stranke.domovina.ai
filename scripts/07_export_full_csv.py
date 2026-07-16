"""Read-only export of the full parties table to a dated CSV on the Desktop."""
from __future__ import annotations

import csv
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import connect  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("export_csv")

COLUMNS = [
    "slug", "canonical_name", "short_name", "oib", "reg_number", "status",
    "registered_at", "status_date", "seat", "city", "address", "county",
    "founded_place", "founded_date", "president", "website", "email",
    "phone", "phone_kind", "phone_e164", "fb_url", "ig_url", "x_url",
    "wiki_url", "lat", "lng",
]


def run() -> None:
    out = Path.home() / "Desktop" / f"hrvatske-politicke-stranke-{date.today().isoformat()}.csv"
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM parties ORDER BY status, canonical_name"
        ).fetchall()
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows([tuple(r) for r in rows])
    log.info("wrote %d rows -> %s", len(rows), out)


if __name__ == "__main__":
    run()
