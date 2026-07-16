"""Ingest the NSK "Funkcije u političkim strankama" XML -> party_functions.

Each RECORD: Funkcija (predsjednik, zastupnik u Hrvatskom saboru, ...),
NositeljFunkcije ("Prezime, Ime"), Mandat "[YYYY-MM-DD / YYYY-MM-DD]" where an
unknown end reads "GGGG-mm-dd" (= ongoing -> NULL), NazivStranke.

Party matching reuses the same key strategy as 02_enrich_imenik.
Idempotent: INSERT OR IGNORE on (party_id, function, holder, mandate_start).
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import httpx
from lxml import etree
from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import add_function, connect  # noqa: E402
from src.normalize import norm_key  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
import importlib  # noqa: E402

_imenik = importlib.import_module("02_enrich_imenik")
name_keys = _imenik.name_keys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("enrich_funkcije")

RAW = ROOT / "data" / "raw" / "imenik" / "funkcije-u-strankama.xml"
URL = (
    "https://data.gov.hr/ckan/dataset/b8ecbf48-21bd-4eb9-bda0-0282687ed0e3/"
    "resource/9a6f0a90-58c6-4767-af5c-c7e6fc3a026c/download/funkcije-u-strankama.xml"
)

_MANDATE_RE = re.compile(r"\[\s*([0-9-]+|GGGG-mm-dd)\s*/\s*([0-9-]+|GGGG-mm-dd)\s*\]")


def fetch() -> bytes:
    if RAW.exists():
        log.info("cache hit %s", RAW)
        return RAW.read_bytes()
    log.info("GET %s", URL)
    r = httpx.get(URL, timeout=60, follow_redirects=True)
    r.raise_for_status()
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_bytes(r.content)
    return r.content


def parse_mandate(s: str | None) -> tuple[str | None, str | None]:
    if not s:
        return None, None
    m = _MANDATE_RE.search(s)
    if not m:
        return None, None
    start, end = m.group(1), m.group(2)
    return (
        None if start.startswith("GGGG") else start,
        None if end.startswith("GGGG") else end,
    )


def holder_name(s: str) -> str:
    """"Prezime, Ime" -> "Ime Prezime"."""
    parts = [p.strip() for p in s.split(",", 1)]
    if len(parts) == 2:
        return f"{parts[1]} {parts[0]}"
    return s.strip()


def run() -> None:
    content = fetch()
    root = etree.fromstring(content)

    with connect() as conn:
        # Rebuild from scratch each run — matching heuristics may change and
        # INSERT OR IGNORE alone would strand rows under a stale party_id.
        conn.execute("DELETE FROM party_functions WHERE source = 'nsk-funkcije'")
        rows = conn.execute("SELECT id, canonical_name FROM parties").fetchall()
        by_key: dict[str, int] = {}
        for r in rows:
            for k in name_keys(r["canonical_name"]):
                by_key.setdefault(k, r["id"])
        fuzz_names = {r["canonical_name"]: r["id"] for r in rows}
        # Cache fuzzy lookups — the XML repeats the same party name many times.
        resolved: dict[str, int | None] = {}

        inserted = unmatched = 0
        for rec in root.findall(".//RECORD"):
            pname = rec.findtext("NazivStranke")
            fn = rec.findtext("Funkcija")
            holder = rec.findtext("NositeljFunkcije")
            if not (pname and fn and holder):
                continue
            if pname not in resolved:
                pid = None
                for k in name_keys(pname):
                    if k in by_key:
                        pid = by_key[k]
                        break
                if pid is None:
                    best = process.extractOne(
                        pname, fuzz_names.keys(), scorer=fuzz.token_sort_ratio,
                        processor=norm_key, score_cutoff=93,
                    )
                    pid = fuzz_names[best[0]] if best else None
                resolved[pname] = pid
            party_id = resolved[pname]
            if party_id is None:
                unmatched += 1
                continue

            start, end = parse_mandate(rec.findtext("Mandat"))
            add_function(
                conn, party_id, fn.strip(), holder_name(holder), start, end, "nsk-funkcije"
            )
            inserted += 1

        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM party_functions").fetchone()[0]
        n_unmatched_parties = sum(1 for v in resolved.values() if v is None)
        log.info(
            "functions processed=%d unmatched-records=%d (distinct unmatched parties=%d); "
            "party_functions total=%d",
            inserted, unmatched, n_unmatched_parties, total,
        )


if __name__ == "__main__":
    run()
