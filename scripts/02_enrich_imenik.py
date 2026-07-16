"""Enrich parties from the NSK "Imenik političkih stranaka" XML (data.gov.hr).

Each RECORD carries:
* NazivStranke        — party name (mixed case, often "Name - ABBR")
* Napomena (multi)    — "Mjesto osnivanja: X", "Razdoblje djelovanja: date/",
                        "PROMJENA NAZIVA n: ..." history notes
* UporabiZa (multi)   — abbreviations, former and English names -> aliases

Matched to the registry rows by a diacritics/case/punctuation-insensitive
name key, with a "strip trailing ' - ABBR'" fallback and a conservative
rapidfuzz pass (>= 93) as last resort. Idempotent: only fills empty fields,
aliases are INSERT OR IGNORE.
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

from src.db import add_alias, connect  # noqa: E402
from src.normalize import norm_key  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("enrich_imenik")

RAW = ROOT / "data" / "raw" / "imenik" / "imenik-stranaka.xml"
URL = (
    "https://data.gov.hr/ckan/dataset/31046f26-ee38-4078-a133-653e4579c11f/"
    "resource/c35c8056-ad16-49cb-b936-51a6003bc0bf/download/imenik-stranaka.xml"
)

_ABBR_SUFFIX = re.compile(r"\s*-\s*[A-ZČĆĐŠŽ]{2,15}\s*$")
_PLACE_RE = re.compile(r"Mjesto osnivanja:\s*(.+)")
_PERIOD_RE = re.compile(r"Razdoblje djelovanja:\s*([0-9-]+)\s*/")


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


def name_keys(name: str) -> list[str]:
    """Match keys for a party name, most specific first."""
    keys = [norm_key(name)]
    stripped = _ABBR_SUFFIX.sub("", name).strip()
    if stripped and stripped != name:
        keys.append(norm_key(stripped))
    return keys


def run() -> None:
    content = fetch()
    root = etree.fromstring(content)

    with connect() as conn:
        rows = conn.execute(
            "SELECT id, canonical_name, short_name, founded_place FROM parties"
        ).fetchall()
        by_key: dict[str, int] = {}
        for r in rows:
            for k in name_keys(r["canonical_name"]):
                by_key.setdefault(k, r["id"])
        fuzz_names = {r["canonical_name"]: r["id"] for r in rows}

        matched = unmatched = fuzzy = 0
        for rec in root.findall(".//RECORD"):
            name = rec.findtext("NazivStranke")
            if not name:
                continue  # group-level records
            party_id = None
            for k in name_keys(name):
                if k in by_key:
                    party_id = by_key[k]
                    break
            if party_id is None:
                best = process.extractOne(
                    name, fuzz_names.keys(), scorer=fuzz.token_sort_ratio,
                    processor=norm_key, score_cutoff=93,
                )
                if best:
                    party_id = fuzz_names[best[0]]
                    fuzzy += 1
            if party_id is None:
                unmatched += 1
                log.debug("no match for imenik record %r", name)
                continue
            matched += 1

            founded_place = founded_date = None
            history: list[str] = []
            for nap in rec.findall("Napomena"):
                text = (nap.text or "").strip()
                if m := _PLACE_RE.match(text):
                    founded_place = m.group(1).strip()
                elif m := _PERIOD_RE.match(text):
                    founded_date = m.group(1).strip()
                elif text.startswith("PROMJENA NAZIVA"):
                    history.append(text)

            conn.execute(
                """UPDATE parties SET
                     founded_place = COALESCE(founded_place, ?),
                     founded_date  = COALESCE(founded_date, ?),
                     notes = CASE
                       WHEN ? != '' AND (notes IS NULL OR notes = '') THEN ?
                       ELSE notes END,
                     updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (founded_place, founded_date, "\n".join(history), "\n".join(history), party_id),
            )
            for uz in rec.findall("UporabiZa"):
                alias = (uz.text or "").strip()
                if alias:
                    add_alias(conn, party_id, alias, "nsk-imenik")

        conn.commit()
        log.info(
            "imenik: matched=%d (fuzzy=%d) unmatched=%d", matched, fuzzy, unmatched
        )
        stats = conn.execute(
            "SELECT COUNT(founded_place), COUNT(founded_date) FROM parties"
        ).fetchone()
        log.info("founded_place=%d founded_date=%d", stats[0], stats[1])


if __name__ == "__main__":
    run()
