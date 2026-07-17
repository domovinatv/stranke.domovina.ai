"""Kratki wallet alias stranke za wildcard `{alias}.ff.hr` (ff-edge dispatcher).

Načelo (potvrdio vlasnik projekta): stranka koja drži vlastitu `<label>.hr`
domenu (polje `website` u registru) legitimno "posjeduje" taj label — pa ga
dobiva i kao kratki wallet subdomain (hdz.hr → hdz.ff.hr, sdp.hr → sdp.ff.hr).

ZAMKA: `website` je mjestimično zagađen medijskim portalima (nacional.hr,
dulist.hr, radiosamobor.hr…) iz enrichmenta — slijepo preslikavanje domene
dalo bi krive/squatterske aliase. Zato label vrijedi SAMO ako je izvedivo
povezan s imenom stranke:
  a) label == normalizirana kratica (short_name), ili
  b) normalizirana kratica (≥3 znaka) sadržana u labelu (strankadomino ⊃ domino), ili
  c) label sadržan u normaliziranom nazivu/slugu (suverenisti ⊂ hrvatski-suverenisti), ili
  d) normalizirani slug (≥4 znaka) sadržan u labelu (mosthrvatska ⊃ most).

`build_alias_map(parties)` je deterministična funkcija nad CIJELIM skupom
AKTIVNIH stranaka: ispušta duplikate (isti label za 2 stranke), labele jednake
tuđem punom slugu i redundantne (label == vlastiti slug). Kolizije s klupskim
labelima na *.ff.hr provjerava guard u scripts/15 (faila cijeli export).

Dijele je scripts/09 (static export za frontend link) i scripts/15 (export za
ff-edge worker) — ISTI ulaz ⇒ ISTI aliasi, nema divergencije katalog↔worker.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

_WEBSITE_RE = re.compile(r"https?://(?:www\.)?([a-z0-9-]{3,63})\.hr/?$")

# Klupski katalog na ISTOJ *.ff.hr zoni (ss repo) — klubovi imaju prednost pa se
# derivirani alias u koliziji s klupskim labelom ISPUŠTA (npr. `split` je NK
# Split, ne "Split je naš"). Puni slugovi stranaka se i dalje HARD-guardaju u
# scripts/15 (kolizija puna imena = stop svijeta, alias = samo nice-to-have).
DEFAULT_CLUBS_JSON = Path("/Users/ms/git/ss/ss-novcanik-prototip/worker/clubs-app.json")
CLUB_CURATED_ALIASES = {"lom", "luk", "croz", "moks", "nkw"}


def load_club_labels(clubs_json: Path = DEFAULT_CLUBS_JSON) -> set[str]:
    """Svi klupski labeli na *.ff.hr. OBAVEZAN ulaz — bez njega bi 09 i 15
    mogli derivirati različite aliase (divergencija katalog↔worker)."""
    if not clubs_json.exists():
        raise FileNotFoundError(f"clubs-app.json nije nađen: {clubs_json}")
    labels = {c["slug"] for c in json.loads(clubs_json.read_text(encoding="utf-8"))}
    return labels | CLUB_CURATED_ALIASES


def _norm(s: str | None) -> str:
    """Lowercase, bez dijakritika i ne-alfanumerika (Možemo! → mozemo)."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # hrvatski specijalci koje NFKD ne rastavlja
    s = s.replace("đ", "dj").replace("Đ", "dj")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _candidate_label(website: str | None) -> str | None:
    if not website:
        return None
    m = _WEBSITE_RE.match(website.strip().lower())
    return m.group(1) if m else None


def _related(label: str, slug: str, canonical: str | None, short: str | None) -> bool:
    nl = _norm(label)
    ns = _norm(short)
    nslug = _norm(slug)
    ncanon = _norm(canonical)
    if ns and nl == ns:
        return True  # a) label == kratica
    if ns and len(ns) >= 3 and ns in nl:
        return True  # b) kratica u labelu
    if nl and (nl in ncanon or nl in nslug):
        return True  # c) label u nazivu/slugu
    if len(nslug) >= 4 and nslug in nl:
        return True  # d) slug u labelu
    return False


def build_alias_map(parties: list[dict], clubs_json: Path = DEFAULT_CLUBS_JSON) -> dict[str, str]:
    """slug → alias, nad skupom AKTIVNIH stranaka (dictovi sa slug,
    canonical_name, short_name, website). Deterministično; v. modul docstring."""
    club_labels = load_club_labels(clubs_json)
    slugs = {p["slug"] for p in parties}
    candidates: dict[str, list[str]] = {}
    for p in parties:
        label = _candidate_label(p.get("website"))
        if not label or label == p["slug"]:
            continue  # nema weba / label == vlastiti slug (redundantno)
        if label in slugs:
            continue  # label je tuđi (ili vlastiti) puni slug — ne diramo
        if label in club_labels:
            continue  # klub drži label na *.ff.hr (klubovi = prvi na zoni)
        if not _related(label, p["slug"], p.get("canonical_name"), p.get("short_name")):
            continue  # zagađeni website (portal) — odbaci
        candidates.setdefault(label, []).append(p["slug"])
    return {v[0]: k for k, v in candidates.items() if len(v) == 1}
