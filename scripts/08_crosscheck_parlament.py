"""Cross-check the catalog against the 2024 parliamentary election results.

Reads the sister repo's mirror of the DIP archive
(izbori.domovina.ai/data/izbori.sqlite, election `parlament-2024`) and:

  1. collects every party named on any list (rezultat_lista.stranke,
     '; '-joined full official names) at RH level, with total votes and
     seats of the lists it appeared on;
  2. matches each against the catalog (canonical_name / short_name /
     aliases, diacritics- and punctuation-insensitive, with a
     "strip trailing ' - ABBR'" fallback and rapidfuzz >= 93);
  3. verifies matched parties are AKTIVAN (a party that ran in 2024 but is
     PRESTANAK in the registry is either a data error or a post-election
     dissolution — flagged either way);
  4. stores the election-ballot name variant as an alias
     (source 'dip-parlament-2024') so FTS finds parties by ballot name;
  5. prints unmatched names — catalog gaps or coalition labels that aren't
     registered parties (e.g. joint platforms).

Read-only towards the izbori DB. Idempotent towards ours.
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import add_alias, connect  # noqa: E402
from src.normalize import norm_key  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("crosscheck")

DEFAULT_IZBORI_DB = (
    ROOT.parent / "izbori.domovina.ai" / "data" / "izbori.sqlite"
)

_ABBR_SUFFIX = re.compile(r"\s*-\s*\"?[A-ZČĆĐŠŽ][A-ZČĆĐŠŽa-zčćđšž !.]{0,30}\"?\s*$")


def name_variants(name: str) -> list[str]:
    """Normalised match keys for a ballot party name, most specific first.

    Ballot names stack suffixes ("AUTOHTONA - HSP - DRAŽEN KELEMINEC -
    A - HSP - Dražen Keleminec"), so the abbr-strip is applied iteratively.
    """
    name = name.strip().strip('"')
    keys = [norm_key(name)]
    current = name
    for _ in range(3):
        stripped = _ABBR_SUFFIX.sub("", current).strip()
        if not stripped or stripped == current:
            break
        keys.append(norm_key(stripped))
        current = stripped
    out: list[str] = []
    for k in keys:
        if k and k not in out:
            out.append(k)
    return out


def collect_election_parties(izbori_db: Path) -> dict[str, dict]:
    """{ballot party name: {votes, seats, lists}} from RH-level parlament-2024."""
    conn = sqlite3.connect(f"file:{izbori_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT l.naziv AS lista, l.stranke, l.glasova, COALESCE(l.mandata, 0) AS mandata
           FROM rezultat r JOIN rezultat_lista l ON l.rezultat_id = r.id
           WHERE r.election = 'parlament-2024' AND r.level = 'rh'
             AND l.stranke IS NOT NULL AND l.stranke != ''"""
    ).fetchall()
    conn.close()

    parties: dict[str, dict] = {}
    for r in rows:
        for raw in r["stranke"].split(";"):
            name = raw.strip()
            if not name:
                continue
            entry = parties.setdefault(
                name, {"votes": 0, "seats": 0, "lists": set()}
            )
            # RH level repeats one row per izborna jedinica list — the same
            # (lista, stranke) pair appears up to 10-12 times; aggregate.
            entry["votes"] += r["glasova"] or 0
            entry["seats"] += r["mandata"]
            entry["lists"].add(r["lista"])
    return parties


def run(izbori_db: Path, write_aliases: bool) -> None:
    if not izbori_db.exists():
        sys.exit(f"izbori DB not found: {izbori_db} — run izbori.domovina.ai mirror first")

    election = collect_election_parties(izbori_db)
    log.info("parlament-2024: %d distinct party names on ballots", len(election))

    with connect() as conn:
        if write_aliases:
            # Rebuild — matching may improve between runs and stale aliases
            # would otherwise stay attached to a wrong party.
            conn.execute(
                "DELETE FROM party_aliases WHERE source = 'dip-parlament-2024'"
            )
        rows = conn.execute(
            """SELECT p.id, p.canonical_name, p.short_name, p.status, p.status_date,
                      COALESCE(GROUP_CONCAT(a.alias, ';'), '') AS aliases
               FROM parties p LEFT JOIN party_aliases a ON a.party_id = p.id
               GROUP BY p.id
               ORDER BY (p.status != 'AKTIVAN'),
                        COALESCE(p.status_date, '9999-12-31') DESC, p.id"""
        ).fetchall()
        # Key priority: exact names before abbr-stripped variants, and (via the
        # ORDER BY above) active parties before defunct ones — so the ballot's
        # "SDP" resolves to today's SDP, not the 1990s SDPH-SDP entity.
        by_key: dict[str, sqlite3.Row] = {}
        for r in rows:
            candidates = [r["canonical_name"], r["short_name"] or ""]
            candidates += [a for a in r["aliases"].split(";") if a]
            for c in candidates:
                if c:
                    by_key.setdefault(norm_key(c), r)
        for r in rows:
            candidates = [r["canonical_name"], r["short_name"] or ""]
            candidates += [a for a in r["aliases"].split(";") if a]
            for c in candidates:
                for k in name_variants(c):
                    by_key.setdefault(k, r)
        fuzz_map = {r["canonical_name"]: r for r in rows}

        matched: list[tuple[str, sqlite3.Row, dict]] = []
        unmatched: list[tuple[str, dict]] = []
        for name, info in sorted(election.items(), key=lambda kv: -kv[1]["votes"]):
            row = None
            for k in name_variants(name):
                if k in by_key:
                    row = by_key[k]
                    break
            if row is None:
                best = process.extractOne(
                    name, fuzz_map.keys(), scorer=fuzz.token_sort_ratio,
                    processor=norm_key, score_cutoff=93,
                )
                if best:
                    row = fuzz_map[best[0]]
            if row is None:
                unmatched.append((name, info))
            else:
                matched.append((name, row, info))
                if write_aliases:
                    add_alias(conn, row["id"], name, "dip-parlament-2024")

        conn.commit()

        print(f"\n=== MATCHED {len(matched)}/{len(election)} ===")
        print(f"{'ballot name':<62} {'catalog':<48} {'status':<9} seats")
        not_active = []
        for name, row, info in matched:
            status = row["status"] or "NEPOZNAT"
            print(f"{name[:60]:<62} {row['canonical_name'][:46]:<48} "
                  f"{status:<9} {info['seats']}")
            if status == "PRESTANAK":
                not_active.append((name, row))

        if not_active:
            ELECTION_DAY = "2024-04-17"
            print(f"\n=== RAN IN 2024 BUT NOT AKTIVAN IN REGISTRY ({len(not_active)}) ===")
            for name, row in not_active:
                sd = row["status_date"] or "?"
                verdict = (
                    "OK: dissolved after the election"
                    if sd > ELECTION_DAY
                    else "SUSPICIOUS: dissolved before the election — check match"
                )
                print(f"  {name}  ->  {row['canonical_name']} "
                      f"[{row['status']} {sd}]  {verdict}")

        if unmatched:
            print(f"\n=== UNMATCHED ({len(unmatched)}) — catalog gap or non-party label ===")
            for name, info in unmatched:
                print(f"  {name}  (votes~{info['votes']}, seats={info['seats']}, "
                      f"lists={len(info['lists'])})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--izbori-db", type=Path, default=DEFAULT_IZBORI_DB)
    ap.add_argument("--no-aliases", action="store_true",
                    help="don't write ballot-name aliases back to the catalog")
    args = ap.parse_args()
    run(args.izbori_db, write_aliases=not args.no_aliases)
