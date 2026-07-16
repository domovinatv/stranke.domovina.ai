"""Ingest the official Registar političkih stranaka RH (data.gov.hr).

Two JSON resources from dataset `registar-politickih-stranaka-republike-hrvatske`:

* Stranke — one row per party: OIB, NAZIV, SBT_ID, STATUS (AKTIVAN|PRESTANAK),
  SJEDISTE ("Grad, Ulica bb"), BROJ_KNJIGE, DATUM_UPISA, DATUM_STATUSA,
  SKRACENI_NAZIV, REGISTARSKI_BROJ.
* Osobe — persons authorised to represent the party, keyed by SBT_ID:
  IME, PREZIME, SVOJSTVO ('PREDSJEDNIK', ...), ZASTUPA, PREDSTAVLJA.

Raw responses are cached under data/raw/registar/ so reruns are offline.
Idempotent: upserts by slug, aliases/persons INSERT OR IGNORE.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import add_alias, add_person, connect, init_db, upsert_party  # noqa: E402
from src.normalize import slugify  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest_registar")

RAW_DIR = ROOT / "data" / "raw" / "registar"

_DATASET = "https://data.gov.hr/ckan/dataset/197ea086-e03b-42d1-b3c1-0496c85faf1e/resource"
URLS = {
    "stranke.json": f"{_DATASET}/1a766609-e55d-4c13-ad0c-7bd409496d34/download/data.json",
    "osobe.json": f"{_DATASET}/5dd77a90-f54e-4f66-85e0-74333285879c/download/data.json",
}


def fetch(name: str) -> list[dict]:
    path = RAW_DIR / name
    if path.exists():
        log.info("cache hit %s", path)
        return json.loads(path.read_text())
    url = URLS[name]
    log.info("GET %s", url)
    r = httpx.get(url, timeout=60, follow_redirects=True)
    r.raise_for_status()
    data = r.json()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False))
    return data


def person_name(p: dict) -> str:
    return " ".join(f"{p['IME'].title()} {p['PREZIME'].title()}".split())


def parse_seat(seat: str | None) -> tuple[str | None, str | None]:
    """"Zadar, Medulićeva 2" -> ("Zadar", "Medulićeva 2")."""
    if not seat:
        return None, None
    parts = [p.strip() for p in seat.split(",")]
    city = parts[0] or None
    address = ", ".join(p for p in parts[1:] if p) or None
    return city, address


def iso_date(v: str | None) -> str | None:
    if not v:
        return None
    return v.split("T")[0]


def run() -> None:
    init_db()
    stranke = fetch("stranke.json")
    osobe = fetch("osobe.json")

    people_by_sbt: dict[int, list[dict]] = {}
    for p in osobe:
        people_by_sbt.setdefault(p["SBT_ID"], []).append(p)

    with connect() as conn:
        # Rebuild people from scratch — name formatting may change between
        # runs and INSERT OR IGNORE alone would strand stale variants.
        conn.execute("DELETE FROM party_people WHERE source = 'registar-osobe'")
        n_parties = n_people = 0
        seen_slugs: dict[str, int] = {}
        for row in stranke:
            name = (row.get("NAZIV") or "").strip()
            if not name:
                continue
            sbt_id = row["SBT_ID"]
            slug = slugify(name)
            # Two distinct registry entries can normalise to the same slug
            # (e.g. a defunct party re-founded under the same name) —
            # disambiguate with the registry ID.
            if slug in seen_slugs and seen_slugs[slug] != sbt_id:
                slug = f"{slug}-{sbt_id}"
            seen_slugs[slug] = sbt_id

            city, address = parse_seat(row.get("SJEDISTE"))
            persons = people_by_sbt.get(sbt_id, [])
            president = next(
                (
                    person_name(p)
                    for p in persons
                    if (p.get("SVOJSTVO") or "").upper() == "PREDSJEDNIK"
                ),
                None,
            )

            party_id = upsert_party(
                conn,
                slug=slug,
                canonical_name=name,
                short_name=row.get("SKRACENI_NAZIV"),
                oib=row.get("OIB"),
                sbt_id=sbt_id,
                reg_number=row.get("REGISTARSKI_BROJ"),
                book_number=row.get("BROJ_KNJIGE"),
                status=row.get("STATUS"),
                registered_at=iso_date(row.get("DATUM_UPISA")),
                status_date=iso_date(row.get("DATUM_STATUSA")),
                seat=row.get("SJEDISTE"),
                city=city,
                address=address,
                president=president,
            )
            n_parties += 1

            if row.get("SKRACENI_NAZIV"):
                add_alias(conn, party_id, row["SKRACENI_NAZIV"].strip(), "registar-skraceni")
            for p in persons:
                full_name = person_name(p)
                add_person(
                    conn,
                    party_id,
                    full_name,
                    role=(p.get("SVOJSTVO") or "").strip() or None,
                    represents=(p.get("PREDSTAVLJA") or "").upper() == "DA",
                    source="registar-osobe",
                )
                n_people += 1

        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM parties").fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM parties WHERE status='AKTIVAN'"
        ).fetchone()[0]
        log.info(
            "upserted %d parties (%d people rows); DB now: %d parties, %d active",
            n_parties, n_people, total, active,
        )


if __name__ == "__main__":
    run()
