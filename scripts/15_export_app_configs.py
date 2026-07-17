"""Export app-ready party configs for the white-label wallet (politika/novcanik-prototip).

Reads data/stranke.db (status='AKTIVAN' only) and emits
data/export/parties-app.json: one compact record per party with identity fields
(name = kratica, shortName, fullName = registered name, town, founded, oib),
a `logo` flag (true iff data/logos_sized/256/{slug}.png exists) and — where a
logo exists and its colors pass sanity checks — a logo-derived brand palette
{primaryHex, accentHex, pageHex}. Color heuristic is a faithful port of
klubovi.domovina.ai scripts/48_export_app_configs.py (median-cut clusters,
saturation floor, ensure-dark for white text, page tint).

COLLISION GUARD: the ff.hr wildcard zone is shared with the football-club
catalog (ss repo worker/clubs-app.json + curated aliases). The export
intersects party slugs (and the curated party aliases hdz/sdp/mozemo/most)
against every club label and FAILS on any overlap — a collision would make
ff-edge dispatch ambiguous. Measured 2026-07-16: zero overlap on all axes.

Run: uv run python scripts/15_export_app_configs.py
     [--clubs-json /path/to/ss-novcanik-prototip/worker/clubs-app.json]
"""
from __future__ import annotations

import argparse
import colorsys
import json
import logging
import sqlite3
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "stranke.db"
LOGO_DIR = ROOT / "data" / "logos_sized" / "256"
OUT_PATH = ROOT / "data" / "export" / "parties-app.json"
DEFAULT_CLUBS_JSON = Path("/Users/ms/git/ss/ss-novcanik-prototip/worker/clubs-app.json")

# Kurirani stranački aliasi (sync s ss repo worker/parties-aliases.ts — NE
# generirati kratice mehanički; 155 kratica bi se sudaralo međusobno i s klubovima).
PARTY_ALIASES = ["hdz", "sdp", "mozemo", "most"]
# Klupski kurirani aliasi + whitelabel slug (sync s ss src/clubs/aliases.ts).
CLUB_ALIASES = ["lom", "luk", "croz", "moks", "nkw"]

ALPHA_MIN = 128
WHITE_MIN = 235
BLACK_MAX = 25
N_CLUSTERS = 8
SAT_MIN = 0.25
HUE_DELTA_MIN = 30.0
LIGHT_DELTA_MIN = 0.25
ACCENT_SHARE_MIN = 0.10
LUM_MAX = 0.6
SHORT_NAME_MAX = 14

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("export_party_app_configs")


# --- color helpers (port of klubovi 48) --------------------------------------

def hex_of(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def hsv_of(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    return colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)


def hsl_of(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    h, l, s = colorsys.rgb_to_hls(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    return h, s, l


def rgb_from_hsl(h: float, s: float, l: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return round(r * 255), round(g * 255), round(b * 255)


def rel_luminance(rgb: tuple[int, int, int]) -> float:
    def ch(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def hue_dist_deg(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    d = abs(hsv_of(a)[0] - hsv_of(b)[0]) * 360
    return min(d, 360 - d)


def ensure_dark(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    if rel_luminance(rgb) < LUM_MAX:
        return rgb
    h, s, _l = hsl_of(rgb)
    l = 0.45
    out = rgb_from_hsl(h, s, l)
    while rel_luminance(out) >= LUM_MAX and l > 0.15:
        l -= 0.05
        out = rgb_from_hsl(h, s, l)
    return out


def logo_clusters(path: Path) -> list[tuple[tuple[int, int, int], float]]:
    img = Image.open(path).convert("RGBA")
    px = [
        (r, g, b)
        for r, g, b, a in img.getdata()
        if a >= ALPHA_MIN
        and not (r > WHITE_MIN and g > WHITE_MIN and b > WHITE_MIN)
        and not (r < BLACK_MAX and g < BLACK_MAX and b < BLACK_MAX)
    ]
    if len(px) < 32:
        return []
    strip = Image.new("RGB", (len(px), 1))
    strip.putdata(px)
    q = strip.quantize(colors=N_CLUSTERS, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(maxcolors=N_CLUSTERS), reverse=True)
    total = len(px)
    return [(tuple(pal[i * 3 : i * 3 + 3]), n / total) for n, i in counts]


def derive_brand(path: Path) -> dict[str, str] | None:
    clusters = logo_clusters(path)
    saturated = [(rgb, share) for rgb, share in clusters if hsv_of(rgb)[1] >= SAT_MIN]
    if not saturated:
        return None
    primary = saturated[0][0]

    accent = None
    p_l = hsl_of(primary)[2]
    for rgb, share in saturated[1:]:
        if share < ACCENT_SHARE_MIN:
            continue
        if hue_dist_deg(rgb, primary) >= HUE_DELTA_MIN or abs(hsl_of(rgb)[2] - p_l) >= LIGHT_DELTA_MIN:
            accent = rgb
            break

    primary = ensure_dark(primary)
    if accent is None:
        h, s, l = hsl_of(primary)
        accent = rgb_from_hsl(h, s, l * 0.65)
    else:
        accent = ensure_dark(accent)

    h, s, _l = hsl_of(primary)
    page = rgb_from_hsl(h, s * 0.30, 0.96)
    return {"primaryHex": hex_of(primary), "accentHex": hex_of(accent), "pageHex": hex_of(page)}


# --- export ------------------------------------------------------------------

def run(clubs_json: Path) -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT slug, canonical_name, short_name, oib, city,
                  substr(COALESCE(founded_date, registered_at), 1, 4) AS founded_year
           FROM parties WHERE status = 'AKTIVAN' ORDER BY slug"""
    ).fetchall()
    log.info("loaded %d AKTIVAN parties from %s", len(rows), DB_PATH)

    # kolizijski guard — presjek sa svim klupskim labelima na *.ff.hr
    club_labels: set[str] = set(CLUB_ALIASES)
    if clubs_json.exists():
        club_labels |= {c["slug"] for c in json.loads(clubs_json.read_text(encoding="utf-8"))}
        log.info("collision guard: %d club labels from %s", len(club_labels), clubs_json)
    else:
        log.error("clubs-app.json NOT FOUND at %s — guard incomplete, aborting", clubs_json)
        sys.exit(2)
    party_labels = {r["slug"] for r in rows} | set(PARTY_ALIASES)
    overlap = sorted(party_labels & club_labels)
    if overlap:
        log.error("COLLISION klubovi × stranke na *.ff.hr: %s", ", ".join(overlap))
        sys.exit(1)
    log.info("collision guard: 0 overlaps (%d party labels × %d club labels)", len(party_labels), len(club_labels))

    records = []
    n_logo = n_brand = 0
    for r in rows:
        slug = r["slug"]
        logo_path = LOGO_DIR / f"{slug}.png"
        has_logo = logo_path.exists()
        brand = None
        if has_logo:
            n_logo += 1
            brand = derive_brand(logo_path)
            if brand:
                n_brand += 1
        short = (r["short_name"] or r["canonical_name"]).strip()
        rec: dict = {
            "slug": slug,
            "name": short,  # kratica kao display naziv (canonical je ALL-CAPS pravni)
            "shortName": short[:SHORT_NAME_MAX].strip(),
            "fullName": r["canonical_name"],
        }
        if r["city"]:
            rec["town"] = r["city"]
        if r["founded_year"]:
            rec["founded"] = str(r["founded_year"])
        if r["oib"]:
            rec["oib"] = r["oib"]
        rec["logo"] = has_logo
        if brand:
            rec["brand"] = brand
        records.append(rec)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("wrote %s (%.0f KB)", OUT_PATH, OUT_PATH.stat().st_size / 1024)
    log.info(
        "summary: total=%d logo=%d brand=%d logo-but-no-brand=%d no-logo=%d",
        len(records), n_logo, n_brand, n_logo - n_brand, len(records) - n_logo,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clubs-json", type=Path, default=DEFAULT_CLUBS_JSON)
    args = ap.parse_args()
    run(args.clubs_json)
