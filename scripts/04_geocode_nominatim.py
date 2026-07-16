"""Geocode party seats via Nominatim (OpenStreetMap).

Same smart-fallback ladder as the klubovi pipeline, adapted to party rows —
per party an ORDERED list of candidate queries from most specific to most
general, stopping at the first hit:

  1. `<address>, <city>, Hrvatska`     (full seat street + city)
  2. `<address>, Hrvatska`
  3. `<ZIP>, Hrvatska`                 (5-digit postal code if present)
  4. `<city>, Hrvatska`

We also request `addressdetails=1` and backfill `parties.county` from the
response (Croatian counties come back as `county`/`state`).

Rate limit: 1.05 req/s per Nominatim usage policy (0 when NOMINATIM_ENDPOINT
points to a local instance). Responses cached under data/raw/nominatim/ keyed
by SHA of the query. Idempotent: skips rows that already have lat/lng.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import connect  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("geocode")

CACHE_DIR = ROOT / "data" / "raw" / "nominatim"
USER_AGENT = "stranke-baza/0.1 (local research; one-shot bulk geocode of HR political parties)"
_BASE = os.environ.get("NOMINATIM_ENDPOINT", "https://nominatim.openstreetmap.org").rstrip("/")
ENDPOINT = f"{_BASE}/search"
_LOCAL = any(h in _BASE for h in ("localhost", "127.0.0.1", "nominatim:"))
_THROTTLE = 0.0 if _LOCAL else 1.05

_ZIP_RE = re.compile(r"\b(\d{5})\b")


def _zip_from(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"(\d)\s+(\d)", r"\1\2", text)
    m = _ZIP_RE.search(cleaned)
    return m.group(1) if m else None


def build_query_candidates(party: dict) -> list[str]:
    out: list[str] = []
    address = (party.get("address") or "").strip()
    city = (party.get("city") or "").strip()
    zip_code = _zip_from(address) or _zip_from(city)

    if address and city:
        out.append(f"{address}, {city}, Hrvatska")
    if address:
        out.append(f"{address}, Hrvatska")
    if zip_code:
        out.append(f"{zip_code}, Hrvatska")
    if city:
        out.append(f"{city}, Hrvatska")

    seen: set[str] = set()
    return [q for q in out if not (q in seen or seen.add(q))]


def cache_path(query: str) -> Path:
    h = hashlib.sha256(query.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.json"


def geocode(client: httpx.Client, query: str) -> dict | None:
    """Return the first Nominatim result dict (with lat/lon/address) or None."""
    cache = cache_path(query)
    if cache.exists():
        data = json.loads(cache.read_text())
    else:
        if _THROTTLE:
            time.sleep(_THROTTLE)
        try:
            r = client.get(
                ENDPOINT,
                params={
                    "q": query,
                    "format": "json",
                    "countrycodes": "hr",
                    "limit": 1,
                    "addressdetails": 1,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
        except httpx.HTTPError as e:
            log.warning("network error for %r: %s", query, e)
            return None
        if r.status_code != 200:
            log.warning("nominatim %d for %r", r.status_code, query)
            return None
        data = r.json()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data, ensure_ascii=False))

    if not data:
        return None
    return data[0]


def _county_from(result: dict) -> str | None:
    addr = result.get("address") or {}
    return addr.get("county") or addr.get("state")


def run() -> None:
    limit_env = os.environ.get("NOMINATIM_LIMIT")
    limit = int(limit_env) if limit_env and limit_env.isdigit() else None

    with connect() as conn:
        rows = conn.execute(
            "SELECT id, slug, canonical_name, city, address FROM parties WHERE lat IS NULL"
        ).fetchall()
        if limit:
            rows = rows[:limit]
        log.info("to geocode: %d parties", len(rows))

        counters = {"ok": 0, "no_query": 0, "no_hit": 0}
        hit_by_level: dict[int, int] = {}
        with httpx.Client(timeout=20) as hx:
            for i, r in enumerate(rows, 1):
                row = dict(r)
                candidates = build_query_candidates(row)
                if not candidates:
                    counters["no_query"] += 1
                    continue

                hit: dict | None = None
                for level, q in enumerate(candidates, 1):
                    hit = geocode(hx, q)
                    if hit:
                        hit_by_level[level] = hit_by_level.get(level, 0) + 1
                        break

                if not hit:
                    counters["no_hit"] += 1
                else:
                    try:
                        lat, lng = float(hit["lat"]), float(hit["lon"])
                    except (KeyError, TypeError, ValueError):
                        counters["no_hit"] += 1
                        continue
                    conn.execute(
                        "UPDATE parties SET lat = ?, lng = ?, "
                        "county = COALESCE(county, ?) WHERE id = ?",
                        (lat, lng, _county_from(hit), row["id"]),
                    )
                    counters["ok"] += 1

                if i % 25 == 0:
                    conn.commit()
                    log.info(
                        "progress %d/%d  ok=%d no_query=%d no_hit=%d  hits-per-level=%s",
                        i, len(rows), counters["ok"], counters["no_query"],
                        counters["no_hit"], hit_by_level,
                    )
            conn.commit()
            log.info("done. counters=%s  hits-per-level=%s", counters, hit_by_level)
            total = conn.execute(
                "SELECT COUNT(*) FROM parties WHERE lat IS NOT NULL"
            ).fetchone()[0]
            log.info("parties with coords now: %d", total)


if __name__ == "__main__":
    run()
