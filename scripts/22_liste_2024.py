"""Kompas stranaka scope: 2024 parliamentary lists that won seats → party_ids.

Reads the izbori.domovina.ai mirror of the DIP archive (election
`parlament-2024`, read-only), the catalog (data/stranke.db, read-only) and the
current Sabor MPs (data/financiranje/zastupnici.json), and writes
data/kompas/liste_2024.json:

  liste                   coalitions as voters saw them: constituency variants
                          grouped by lead party (see src/kompas/liste.py), with
                          seats per izborna jedinica, every ballot variant and
                          every member mapped to party_id
  manjine                 the 8 minority seats (XII), proposer mapped the same way
                          (grupe birača have party_id null, vrsta "grupa-biraca")
  zastupnici_izvan_lista  parties with sitting MPs that were on none of the above
                          (post-election splits: DOMiNO, Drito, …)
  nezavisni_zastupnici    sitting MPs without a party (Sabor "NZ")
  stranke                 every party_id in scope, deduplicated
  mandati                 seat arithmetic, asserted: lists + minorities = 151

Name matching is src/party_match.py, the same rules as
scripts/08_crosscheck_parlament.py, but without the 'dip-parlament-2024'
aliases that 08 writes from these very ballot names — so `match` says what
evidence the mapping rests on (exact | alias | fuzzy:<score> | none).

Idempotent: the file is rewritten only when its content (minus
izvor.generated_at) changes.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import DB_PATH, connect  # noqa: E402
from src.kompas.liste import ALIAS_SOURCE_SELF, ELECTION, build, read_rows, unmatched  # noqa: E402
from src.party_match import load_catalog  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("liste_2024")

# Sister repo next to this one, or its archive on the external disk.
IZBORI_CANDIDATES = [
    ROOT.parent / "izbori.domovina.ai" / "data" / "izbori.sqlite",
    Path("/Volumes/DOMOVINA2TB/git/domovinatv/izbori.domovina.ai/data/izbori.sqlite"),
]
DEFAULT_IZBORI_DB = next((p for p in IZBORI_CANDIDATES if p.exists()), IZBORI_CANDIDATES[-1])
DEFAULT_OUT = ROOT / "data" / "kompas" / "liste_2024.json"
ZASTUPNICI = ROOT / "data" / "financiranje" / "zastupnici.json"

TOTAL_SEATS = 151  # 140 (I–X) + 3 (XI diaspora) + 8 (XII minorities)


def dump(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--izbori-db", type=Path, default=DEFAULT_IZBORI_DB)
    ap.add_argument("--stranke-db", type=Path, default=DB_PATH)
    ap.add_argument("--zastupnici", type=Path, default=ZASTUPNICI)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--ukupno-mandata", type=int, default=TOTAL_SEATS,
                    help="expected seat total (lists + minorities); tests use a small fixture")
    args = ap.parse_args()

    if not args.izbori_db.exists():
        sys.exit(f"izbori DB not found: {args.izbori_db} — mount DOMOVINA2TB or pass --izbori-db")

    izb = sqlite3.connect(f"file:{args.izbori_db}?mode=ro", uri=True)
    rows = read_rows(izb, ELECTION)
    izb.close()
    log.info("%s: %d rh/zup list rows", ELECTION, len(rows))

    with connect(args.stranke_db) as conn:
        catalog = load_catalog(conn, exclude_alias_sources=[ALIAS_SOURCE_SELF])
    log.info("catalog: %d parties", len(catalog))

    zast = json.loads(args.zastupnici.read_text(encoding="utf-8"))
    out = build(rows, catalog, zast["mps"])

    seats = out["mandati"]
    if seats["liste"] != seats["liste_rh_razina"]:
        sys.exit(f"winning lists hold {seats['liste']} seats, RH-level rows {seats['liste_rh_razina']}")
    if seats["ukupno"] != args.ukupno_mandata:
        sys.exit(f"seat total {seats['ukupno']} != {args.ukupno_mandata}")
    if out["zastupnici_bez_kataloga"]:
        log.warning("MP parties not in catalog: %s",
                    sorted({z["stranka"] for z in out["zastupnici_bez_kataloga"]}))

    out["izvor"] = {
        "izbori": "izbori.domovina.ai/data/izbori.sqlite (DIP arhiva)",
        "election": ELECTION,
        "katalog": "data/stranke.db",
        "zastupnici": "data/financiranje/zastupnici.json",
        "zastupnici_izvor": zast.get("source"),
        "zastupnici_fetched_at": zast.get("fetched_at"),
        "broj_zastupnika": len(zast["mps"]),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }

    if args.out.exists():
        try:
            old = json.loads(args.out.read_text(encoding="utf-8"))
            gen = old.get("izvor", {}).get("generated_at")
            if gen:
                cand = json.loads(dump(out))
                cand["izvor"]["generated_at"] = gen
                if cand == old:
                    log.info("unchanged: %s", args.out)
                    out["izvor"]["generated_at"] = gen
        except (json.JSONDecodeError, AttributeError):
            pass
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(dump(out), encoding="utf-8")

    log.info("lists: %d, seats %d + minorities %d = %d", len(out["liste"]),
             seats["liste"], seats["manjine"], seats["ukupno"])
    for l in out["liste"]:
        log.info("  %-45s %3d seats, %d variant(s), %d members", l["list_id"],
                 l["mandati"], len(l["varijante"]), len(l["clanice"]))
    for g in out["manjine"]:
        log.info("  %-45s %3d seats", g["manjine_id"], g["mandati"])
    for e in out["zastupnici_izvan_lista"]:
        log.info("  MPs outside lists: %s (%d)", e["slug"], e["broj_zastupnika"])
    for where, name, vrsta in unmatched(out):
        log.info("  UNMATCHED [%s] %s (%s)", where, name, vrsta)
    log.info("parties in scope: %d; wrote %s", len(out["stranke"]), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
