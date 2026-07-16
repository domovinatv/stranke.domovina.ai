"""Fetch party logos (max resolution, SVG preferred) + official brand colors.

Source cascade per party (mirrors the klubovi pipeline, adapted to parties):

  1. Wikidata — resolve the entity (via hr/en wiki_url title -> pageprops,
     else wbsearchentities gated on "instance of political party" + country
     Croatia). P154 = logo image on Commons (often SVG -> true vector
     original), P465 = official sRGB brand color.
  2. Wikipedia pageimages (hr, then en) — original article image. Risky
     (may be a leader photo / building) -> staged for review, never trusted.
  3. Party website — og:image / apple-touch-icon / header <img> with
     "logo" in src|class|alt.
  4. Facebook profile picture (unauthenticated Graph redirect, width 720).

Nothing is written to the catalog directly: candidates are staged to
data/verification/logo_candidates/ with a manifest.tsv
(slug, source, detail, WxH, is_vector, brand_color). A human/vision pass
marks accepted slugs; then:

  --apply FILE   copy originals to data/logos_orig/ (SVG kept as SVG),
                 render quantized web PNG (<=512) to data/logos/,
                 write parties.brand_color when discovered.

Idempotent; every HTTP response cached under data/raw/logos/.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import connect  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch_logos")

LOGO_DIR = ROOT / "data" / "logos"
ORIG_DIR = ROOT / "data" / "logos_orig"
STAGING = ROOT / "data" / "verification" / "logo_candidates"
RAW = ROOT / "data" / "raw" / "logos"

SVG_RENDER_WIDTH = 1024
WEB_MAX = 512
UA = {"User-Agent": "stranke.domovina.ai logo backfill (stepanic.matija@gmail.com)"}

# Wikidata: political party and common subclasses seen for HR parties.
PARTY_CLASSES = {"Q7278", "Q2023214", "Q124964", "Q25796237"}
CROATIA = "Q224"


def _cache_get(client: httpx.Client, url: str, params: dict | None = None) -> bytes | None:
    key = hashlib.sha256(
        (url + json.dumps(params or {}, sort_keys=True)).encode()
    ).hexdigest()[:20]
    p = RAW / f"{key}.bin"
    if p.exists():
        return p.read_bytes()
    try:
        r = client.get(url, params=params)
    except httpx.HTTPError as e:
        log.debug("http error %s: %s", url, e)
        return None
    if r.status_code != 200:
        return None
    RAW.mkdir(parents=True, exist_ok=True)
    p.write_bytes(r.content)
    time.sleep(0.05)
    return r.content


def _json(blob: bytes | None) -> dict:
    if not blob:
        return {}
    try:
        return json.loads(blob)
    except ValueError:
        return {}


# --------------------------------------------------------------- wikidata

def qid_from_wiki_url(client: httpx.Client, wiki_url: str) -> str | None:
    m = re.match(r"https?://(hr|en)\.wikipedia\.org/wiki/(.+)$", wiki_url)
    if not m:
        return None
    lang, title = m.group(1), urllib.parse.unquote(m.group(2))
    data = _json(_cache_get(
        client,
        f"https://{lang}.wikipedia.org/w/api.php",
        {"action": "query", "titles": title, "prop": "pageprops",
         "ppprop": "wikibase_item", "redirects": 1, "format": "json"},
    ))
    for page in (data.get("query", {}).get("pages") or {}).values():
        qid = (page.get("pageprops") or {}).get("wikibase_item")
        if qid:
            return qid
    return None


def entity(client: httpx.Client, qid: str) -> dict:
    data = _json(_cache_get(
        client,
        f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
    ))
    return (data.get("entities") or {}).get(qid) or {}


def _claim_values(ent: dict, prop: str) -> list:
    out = []
    for c in (ent.get("claims") or {}).get(prop, []):
        val = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if val is not None:
            out.append(val)
    return out


def qid_search(client: httpx.Client, name: str) -> str | None:
    """wbsearchentities gated on party-class + Croatia."""
    for lang in ("hr", "en"):
        data = _json(_cache_get(
            client,
            "https://www.wikidata.org/w/api.php",
            {"action": "wbsearchentities", "search": name, "language": lang,
             "type": "item", "limit": 5, "format": "json"},
        ))
        for hit in data.get("search", []):
            ent = entity(client, hit["id"])
            classes = {v.get("id") for v in _claim_values(ent, "P31")}
            countries = {v.get("id") for v in _claim_values(ent, "P17")}
            if classes & PARTY_CLASSES and (not countries or CROATIA in countries):
                return hit["id"]
    return None


def commons_original(client: httpx.Client, filename: str) -> bytes | None:
    return _cache_get(
        client,
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        + urllib.parse.quote(filename),
    )


def render_svg(svg_bytes: bytes, width: int = SVG_RENDER_WIDTH) -> Image.Image | None:
    try:
        out = subprocess.run(
            ["rsvg-convert", "-w", str(width), "--keep-aspect-ratio"],
            input=svg_bytes, capture_output=True, check=True,
        ).stdout
        img = Image.open(io.BytesIO(out))
        img.load()
        return img
    except Exception as e:
        log.debug("svg render failed: %s", e)
        return None


# ---------------------------------------------------- website + facebook

_LOGO_IMG_RE = re.compile(
    r'<img[^>]+(?:src|data-src)=["\']([^"\']*logo[^"\']*)["\']', re.IGNORECASE
)
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.IGNORECASE,
)
_TOUCH_ICON_RE = re.compile(
    r'<link[^>]+rel=["\'][^"\']*apple-touch-icon[^"\']*["\'][^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def website_candidates(client: httpx.Client, website: str) -> list[str]:
    blob = _cache_get(client, website)
    if not blob:
        return []
    html = blob.decode("utf-8", errors="replace")
    urls: list[str] = []
    for m in _LOGO_IMG_RE.finditer(html):
        urls.append(m.group(1))
    for m in _OG_IMAGE_RE.finditer(html):
        urls.append(m.group(1) or m.group(2))
    for m in _TOUCH_ICON_RE.finditer(html):
        urls.append(m.group(1))
    out, seen = [], set()
    for u in urls:
        u = urllib.parse.urljoin(website, u.strip())
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:4]


def fb_picture_url(fb_url: str) -> str | None:
    m = re.match(r"https?://(?:www\.|web\.|m\.)?facebook\.com/([^/?#]+)", fb_url)
    if not m:
        return None
    page = m.group(1)
    if page in ("profile.php", "pages", "people", "groups"):
        return None
    return f"https://graph.facebook.com/{page}/picture?type=large&width=720&height=720"


# ----------------------------------------------------------------- fetch

def load_image(blob: bytes) -> Image.Image | None:
    try:
        img = Image.open(io.BytesIO(blob))
        img.load()
        return img
    except Exception:
        return None


def stage(slug: str, source: str, detail: str, blob: bytes,
          img: Image.Image | None, is_vector: bool, color: str | None,
          lines: list[str]) -> None:
    if is_vector:
        (STAGING / f"{slug}.svg").write_bytes(blob)
        preview = render_svg(blob, 512)
        if preview:
            preview.save(STAGING / f"{slug}.preview.png")
        size = f"vector({SVG_RENDER_WIDTH})"
    else:
        ext = (img.format or "png").lower().replace("jpeg", "jpg") if img else "png"
        (STAGING / f"{slug}.{ext}").write_bytes(blob)
        size = f"{img.size[0]}x{img.size[1]}" if img else "?"
    lines.append(f"{slug}\t{source}\t{detail}\t{size}\t{int(is_vector)}\t{color or ''}")
    log.info("staged %-40s %-9s %s %s", slug, source, size, color or "")


def fetch_candidates(only_active: bool) -> None:
    STAGING.mkdir(parents=True, exist_ok=True)
    conn = connect()
    where = "WHERE status = 'AKTIVAN' OR status IS NULL" if only_active else ""
    rows = conn.execute(
        f"SELECT slug, canonical_name, short_name, wiki_url, website, fb_url "
        f"FROM parties {where} ORDER BY slug"
    ).fetchall()
    log.info("parties to sweep: %d", len(rows))

    stats = {"wikidata_svg": 0, "wikidata_png": 0, "pageimage": 0,
             "website": 0, "facebook": 0, "none": 0}
    lines: list[str] = []
    with httpx.Client(timeout=30, follow_redirects=True, headers=UA) as client:
        for r in rows:
            slug = r["slug"]
            if list(STAGING.glob(f"{slug}.svg")) or list(STAGING.glob(f"{slug}.png")) \
               or list(STAGING.glob(f"{slug}.jpg")):
                continue  # resumable

            color: str | None = None
            staged = False

            # 1) Wikidata
            qid = None
            if r["wiki_url"]:
                qid = qid_from_wiki_url(client, r["wiki_url"])
            if not qid:
                qid = qid_search(client, r["canonical_name"].title())
            if not qid and r["short_name"] and len(r["short_name"]) >= 3:
                qid = qid_search(client, r["short_name"])
            sitelink_title = None
            if qid:
                ent = entity(client, qid)
                colors = _claim_values(ent, "P465")
                color = f"#{colors[0]}" if colors else None
                sitelinks = ent.get("sitelinks") or {}
                for sl in ("hrwiki", "enwiki"):
                    if sl in sitelinks:
                        sitelink_title = (sl[:2], sitelinks[sl]["title"])
                        break
                logos = _claim_values(ent, "P154")
                if logos:
                    fname = str(logos[0])
                    blob = commons_original(client, fname)
                    if blob:
                        if fname.lower().endswith(".svg"):
                            stage(slug, "wikidata", f"{qid}:{fname}", blob, None,
                                  True, color, lines)
                            stats["wikidata_svg"] += 1
                            staged = True
                        else:
                            img = load_image(blob)
                            if img:
                                stage(slug, "wikidata", f"{qid}:{fname}", blob, img,
                                      False, color, lines)
                                stats["wikidata_png"] += 1
                                staged = True

            # 2) Wikipedia pageimage (article original)
            if not staged and (sitelink_title or r["wiki_url"]):
                if sitelink_title:
                    lang, title = sitelink_title
                elif m := re.match(r"https?://(hr|en)\.wikipedia\.org/wiki/(.+)$",
                                   r["wiki_url"]):
                    lang, title = m.group(1), urllib.parse.unquote(m.group(2))
                else:
                    lang = title = None
                if title:
                    data = _json(_cache_get(
                        client, f"https://{lang}.wikipedia.org/w/api.php",
                        {"action": "query", "titles": title, "prop": "pageimages",
                         "piprop": "original", "format": "json", "redirects": 1},
                    ))
                    for page in (data.get("query", {}).get("pages") or {}).values():
                        src = (page.get("original") or {}).get("source")
                        if not src:
                            continue
                        if src.lower().endswith(".svg"):
                            blob = commons_original(client, src.rsplit("/", 1)[-1])
                            if blob:
                                stage(slug, "pageimage", f"{lang}:{title}", blob,
                                      None, True, color, lines)
                                stats["pageimage"] += 1
                                staged = True
                        else:
                            blob = _cache_get(client, src)
                            img = load_image(blob) if blob else None
                            if img and max(img.size) >= 96:
                                stage(slug, "pageimage", f"{lang}:{title}", blob,
                                      img, False, color, lines)
                                stats["pageimage"] += 1
                                staged = True
                        break

            # 3) Website logo/og-image
            if not staged and r["website"]:
                for cand in website_candidates(client, r["website"]):
                    if cand.lower().endswith(".svg"):
                        blob = _cache_get(client, cand)
                        if blob and b"<svg" in blob[:2048].lower():
                            stage(slug, "website", cand, blob, None, True,
                                  color, lines)
                            stats["website"] += 1
                            staged = True
                            break
                    blob = _cache_get(client, cand)
                    img = load_image(blob) if blob else None
                    if img and max(img.size) >= 96:
                        stage(slug, "website", cand, blob, img, False, color, lines)
                        stats["website"] += 1
                        staged = True
                        break

            # 4) Facebook profile picture
            if not staged and r["fb_url"]:
                pic = fb_picture_url(r["fb_url"])
                blob = _cache_get(client, pic) if pic else None
                img = load_image(blob) if blob else None
                if img and max(img.size) >= 96:
                    stage(slug, "facebook", pic, blob, img, False, color, lines)
                    stats["facebook"] += 1
                    staged = True

            if not staged:
                stats["none"] += 1
                if color:
                    # still record the brand color even without a logo
                    lines.append(f"{slug}\tcolor-only\t{qid}\t-\t0\t{color}")

    manifest = STAGING / "manifest.tsv"
    existing = manifest.read_text() if manifest.exists() else ""
    manifest.write_text(existing + "\n".join(lines) + ("\n" if lines else ""))
    log.info("done. %s (staging: %s)", stats, STAGING)


# ----------------------------------------------------------------- apply

def write_web_png(img: Image.Image, dst: Path) -> None:
    img = img.convert("RGBA")
    if max(img.size) > WEB_MAX:
        img.thumbnail((WEB_MAX, WEB_MAX), Image.LANCZOS)
    img.quantize(colors=256, method=Image.Quantize.FASTOCTREE).save(
        dst, "PNG", optimize=True
    )


def apply(accept_file: Path) -> None:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    ORIG_DIR.mkdir(parents=True, exist_ok=True)
    slugs = [s.strip() for s in accept_file.read_text().splitlines()
             if s.strip() and not s.startswith("#")]
    colors: dict[str, str] = {}
    manifest = STAGING / "manifest.tsv"
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) >= 6 and parts[5]:
                colors[parts[0]] = parts[5]

    conn = connect()
    applied = 0
    for slug in slugs:
        svg = STAGING / f"{slug}.svg"
        rasters = [p for p in STAGING.glob(f"{slug}.*")
                   if p.suffix in (".png", ".jpg", ".gif", ".webp")
                   and not p.name.endswith(".preview.png")]
        if svg.exists():
            for old in ORIG_DIR.glob(f"{slug}.*"):
                old.unlink()
            (ORIG_DIR / svg.name).write_bytes(svg.read_bytes())
            img = render_svg(svg.read_bytes(), SVG_RENDER_WIDTH)
            if img:
                write_web_png(img, LOGO_DIR / f"{slug}.png")
        elif rasters:
            src = rasters[0]
            img = Image.open(src)
            img.load()
            for old in ORIG_DIR.glob(f"{slug}.*"):
                old.unlink()
            (ORIG_DIR / src.name).write_bytes(src.read_bytes())
            write_web_png(img, LOGO_DIR / f"{slug}.png")
        else:
            log.warning("no staged candidate for %s", slug)
            continue
        applied += 1

    # Brand colors go in for every slug in the manifest that has one —
    # including color-only rows (no logo but official P465 color).
    n_colors = 0
    for slug, color in colors.items():
        cur = conn.execute(
            "UPDATE parties SET brand_color = ? WHERE slug = ?", (color, slug)
        )
        n_colors += cur.rowcount
    conn.commit()
    log.info("applied %d/%d logos, %d brand colors", applied, len(slugs), n_colors)


if __name__ == "__main__":
    if "--apply" in sys.argv:
        apply(Path(sys.argv[sys.argv.index("--apply") + 1]))
    else:
        fetch_candidates(only_active="--all" not in sys.argv)
