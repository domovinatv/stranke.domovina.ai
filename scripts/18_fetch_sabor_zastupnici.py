"""Snapshot the current Sabor MPs with gender and the list they were elected on.

Sources (official, no auth):
  * https://www.sabor.hr/api/interaktivna-sabornica-new?_format=json —
    the 150 currently seated MPs (name, party abbr, club, minority flag,
    profile URL). Same API izbori.domovina.ai/scripts/fetch_sabor_seating.py
    uses.
  * each MP's profile page on sabor.hr — "Rođen"/"Rođena" (gender),
    "Izabran(a): lista …" (the list the mandate came from, which is what
    state funding follows per ZFPAIP čl. 7), "Stranačka pripadnost",
    "Početak obnašanja zastupničkog mandata", "Izborna jedinica".

Raw HTML is cached in data/raw/sabor/ (rerun with --refresh to re-fetch).
Output: data/financiranje/zastupnici.json (committed — it is the per-person
input of the funding page).
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "sabor"
OUT = ROOT / "data" / "financiranje" / "zastupnici.json"
API = "https://www.sabor.hr/api/interaktivna-sabornica-new?_format=json"
UA = {"User-Agent": "stranke.domovina.ai/0.1 (+https://stranke.domovina.ai)"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sabor")


def page_text(raw: str) -> str:
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", "", raw, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", raw))
    t = re.sub(r"[ \t\xa0]+", " ", t)
    return re.sub(r"\n\s*\n*", "\n", t)


def field(text: str, label: str) -> str | None:
    """Value on the line after a 'Label:' line."""
    m = re.search(rf"^{label}:?\s*\n(.+)$", text, flags=re.M)
    return m.group(1).strip() if m else None


def parse_profile(text: str) -> dict:
    gender = None
    if re.search(r"\bRođena\b", text):
        gender = "F"
    elif re.search(r"\bRođen\b", text):
        gender = "M"
    elected = field(text, r"Izabran[a]?")
    m = re.search(r"^(Izabran[a]?):", text, flags=re.M)
    if gender is None and m:
        gender = "F" if m.group(1) == "Izabrana" else "M"
    start = field(text, "Početak obnašanja zastupničkog mandata")
    return {
        "gender": gender,
        "elected_on": elected,
        "party_full": field(text, "Stranačka pripadnost"),
        "constituency": field(text, "Izborna jedinica"),
        "mandate_start": start.rstrip(".") if start else None,
        # e.g. "… započeo mandat … kao zamjeniku zastupnika Furija Radina"
        "mandate_changes": field(text, "Promjene tijekom zastupničkog mandata"),
    }


def fetch(client: httpx.Client, url: str, path: Path, refresh: bool) -> str:
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8")
    r = client.get(url)
    r.raise_for_status()
    path.write_text(r.text, encoding="utf-8")
    time.sleep(0.3)
    return r.text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch cached pages")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "profiles").mkdir(exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(headers=UA, timeout=30, follow_redirects=True) as client:
        seats = json.loads(fetch(client, API, RAW / "seating.json", args.refresh))
        mps = []
        for s in seats["sjedeca_mjesta"]:
            z = s.get("zastupnik") or {}
            ime = (z.get("ime") or "").strip()
            if "," not in ime:
                continue
            surname, firstname = (p.strip() for p in ime.split(",", 1))
            profile = (z.get("profile") or "").replace("http://", "https://")
            slug = profile.rstrip("/").rsplit("/", 1)[-1]
            text = page_text(fetch(client, profile, RAW / "profiles" / f"{slug}.html", args.refresh))
            info = parse_profile(text)
            # Profile header carries the full name; the API truncates some
            # multi-word surnames ("Ban, Boška" for Boška Ban Vlahek).
            m = re.search(r"^11\. saziv Hrvatskoga sabora.*\n(.+?)\s*$", text, flags=re.M)
            full_name = m.group(1).strip() if m else f"{firstname} {surname}"
            mps.append({
                "id": z.get("id"),
                "slug": slug,
                "name": full_name,
                "seat": s.get("seat"),
                "party": (z.get("stranka") or "").strip(),
                "club": (z.get("klub") or "").strip(),
                "minority": bool(z.get("manjine")),
                "profile": profile,
                "img": (z.get("img") or "").replace("http://", "https://") or None,
                **info,
            })

    missing = [m["name"] for m in mps if not m["gender"]]
    if missing:
        log.error("gender not found for: %s", missing)
        return 1
    f = sum(m["gender"] == "F" for m in mps)
    log.info("%d MPs: %d F / %d M (%.1f%% F)", len(mps), f, len(mps) - f, 100 * f / len(mps))

    OUT.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": API,
        "mps": sorted(mps, key=lambda m: (m["party"], m["name"])),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log.info("wrote %s", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
