"""Per-party Firecrawl backfill of contact + meta fields.

Pipeline per party:

  1) firecrawl /v2/search for "<name> politička stranka kontakt"
     -> returns up to N candidate URLs
  2) pick the most-plausible "official" URL via a small heuristic;
     a Wikipedia hit among the candidates is captured as wiki_url on the side
  3) firecrawl /v2/scrape on the top URL with a JSON schema covering our fields
  4) write non-empty fields back to parties; audit run to backfill_runs

Idempotent thanks to FirecrawlClient response caching.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.db import connect  # noqa: F401  (re-exported for the runner script)
from src.firecrawl import FirecrawlClient
from src.normalize import strip_diacritics
from src.phones import classify as classify_phone, to_e164 as phone_e164

logger = logging.getLogger(__name__)

EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "email": {"type": "string", "description": "Primary contact email of the party"},
        "phone": {"type": "string", "description": "Primary contact phone in any format"},
        "address": {"type": "string", "description": "Full postal address of the party headquarters"},
        "website": {"type": "string", "description": "Official party website URL"},
        "facebook_url": {"type": "string", "description": "Official Facebook page URL"},
        "instagram_url": {"type": "string", "description": "Official Instagram URL"},
        "twitter_url": {"type": "string", "description": "Official X/Twitter URL"},
        "president_name": {"type": "string", "description": "Current party president full name"},
        "city": {"type": "string", "description": "City where the party is headquartered"},
    },
}

EXTRACT_PROMPT = (
    "You are extracting contact and meta information for a Croatian political party. "
    "Return only fields that appear explicitly on the page. Leave fields empty if "
    "not stated. URLs must be absolute. Do not confuse a local branch (podružnica, "
    "županijska/gradska organizacija) with the national party headquarters."
)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}")

# Sites we cannot scrape but whose URL is still worth keeping verbatim.
_SOCIAL_DOMAINS = {"facebook.com", "instagram.com", "twitter.com", "x.com"}

_WIKI_RE = re.compile(r"https?://(?:hr\.)?wikipedia\.org/wiki/\S+", re.IGNORECASE)

# Croatian parties don't live on neighbouring-country ccTLDs — a .rs/.ba/...
# website or email is a namesake foreign party leaking through extraction.
_FOREIGN_TLD_RE = re.compile(r"\.(?:rs|ba|me|mk|al)(?:[/:]|$)", re.IGNORECASE)


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, int) and v == 0:
        return True
    return False


def search_query(name: str, city: str | None) -> str:
    bits = [name.title() if name.isupper() else name, city or "", "politička stranka kontakt"]
    return " ".join(b for b in bits if b)


def score_url(url: str, party_name: str, short_name: str | None) -> int:
    """Rank candidate URLs — bigger = more likely the party's own site."""
    url_l = url.lower()
    score = 0
    if url_l.startswith(("https://", "http://")):
        score += 1
    # Aggregators / media / registries — they carry articles or the legal
    # entity's registry row, not the party's own contact page.
    if any(d in url_l for d in (
        # encyclopedias & data aggregators (wikipedia is captured separately
        # as wiki_url — it must never win the "website" slot)
        "wikipedia.org", "wikiwand.com", "enciklopedija.hr",
        # news portals that outrank small parties for their own name
        "index.hr", "24sata.hr", "tportal.hr", "vecernji.hr", "jutarnji.hr",
        "telegram.hr", "n1info", "net.hr", "dnevnik.hr", "novilist.hr",
        "slobodnadalmacija.hr", "glas-slavonije.hr", "hrt.hr",
        # business/legal registries leak the legal entity, not the party site
        "poslovna.hr", "companywall.hr", "sudreg.hr", "fininfo.hr",
        "boniteti.hr", "fina.hr",
        # state election commission / government portals list every party
        "izbori.hr", "gov.hr", "sabor.hr",
        # local-news portals that outrank small parties for their own name
        # (2026-07-16 audit: sisak.info leaked into HSD, parentium.com into ISU)
        "sisak.info", "parentium.com",
        # foreign-party sites surfaced for namesake Croatian parties
        # (Srpska radikalna stranka leaked into Župska stranka)
        ".org.rs", ".gov.rs", "srpskaradikalnastranka",
    )):
        score -= 5
    # Documents almost always come from DIP/ministry directories that mix
    # one row per party — LLM extraction frequently grabs the wrong row.
    if url_l.endswith((".pdf", ".docx", ".doc", ".xlsx", ".xls")):
        score -= 8
    if "addtoany.com" in url_l:
        score -= 10  # share-widget links, never a real profile
    if "facebook.com" in url_l:
        if "/sharer" in url_l or "/dialog" in url_l or "/share" in url_l:
            score -= 10
        else:
            score += 1
    if "twitter.com" in url_l or "x.com" in url_l:
        if "?status=" in url_l or "/intent/tweet" in url_l:
            score -= 10
    if url_l.endswith(".hr") or ".hr/" in url_l:
        score += 3
    # Strong bonus when the URL includes parts of the party name or its
    # abbreviation ("hdz.hr", "most-nl.com" ...).
    name_tokens = {
        t for t in strip_diacritics(party_name.lower()).replace("-", " ").split()
        if len(t) > 3
    }
    if short_name:
        abbr = strip_diacritics(short_name.lower()).strip()
        if len(abbr) >= 3:
            name_tokens.add(abbr)
    if name_tokens and any(t in url_l for t in name_tokens):
        score += 4
    for kw in ("kontakt", "stranka", "contact", "o-nama", "about"):
        if kw in url_l:
            score += 1
    return score


def pick_url(results: list[dict], party_name: str, short_name: str | None) -> str | None:
    if not results:
        return None
    scored = sorted(
        ((score_url(r.get("url", ""), party_name, short_name), r) for r in results),
        key=lambda x: -x[0],
    )
    top_score, top = scored[0]
    if top_score <= 0:
        return None
    return top.get("url")


def find_wiki_url(results: list[dict]) -> str | None:
    """Prefer hr.wikipedia over other language editions."""
    urls = [r.get("url", "") for r in results]
    for u in urls:
        if "hr.wikipedia.org/wiki/" in u.lower():
            return u
    for u in urls:
        if _WIKI_RE.match(u or ""):
            return u
    return None


def update_party(conn, party_id: int, fields: dict[str, Any]) -> list[str]:
    """Write non-blank, currently-empty fields back to parties. Returns the
    columns we actually wrote (used for the audit trail)."""
    current = dict(conn.execute(
        "SELECT * FROM parties WHERE id = ?", (party_id,)
    ).fetchone())
    incoming = {
        "email": fields.get("email"),
        "phone": fields.get("phone"),
        "address": fields.get("address"),
        "website": fields.get("website"),
        "fb_url": fields.get("facebook_url"),
        "ig_url": fields.get("instagram_url"),
        "x_url": fields.get("twitter_url"),
        "president": fields.get("president_name"),
        "city": fields.get("city"),
        "wiki_url": fields.get("wiki_url"),
    }
    to_write: dict[str, Any] = {}
    for col, val in incoming.items():
        if _is_blank(val):
            continue
        if col == "email":
            v = str(val).strip()
            if not _EMAIL_RE.fullmatch(v) or _FOREIGN_TLD_RE.search(v):
                continue
        if col in ("website", "fb_url", "ig_url", "x_url") and _FOREIGN_TLD_RE.search(
            str(val).split("?")[0]
        ):
            continue
        # Fill-in only — never overwrite registry data.
        if not _is_blank(current.get(col)):
            continue
        to_write[col] = val

    if "phone" in to_write:
        to_write["phone_kind"] = classify_phone(to_write["phone"])
        to_write["phone_e164"] = phone_e164(to_write["phone"])

    if to_write:
        sets = ", ".join(f"{c} = ?" for c in to_write)
        vals = list(to_write.values()) + [party_id]
        conn.execute(
            f"UPDATE parties SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            vals,
        )
    return [k for k in to_write.keys() if k not in ("phone_kind", "phone_e164")]


def backfill_party(
    conn,
    client: FirecrawlClient,
    party_row: dict,
    search_limit: int = 5,
) -> dict[str, Any]:
    name = party_row["canonical_name"]
    query = search_query(name, party_row.get("city"))
    logger.info("search: %r", query)

    results = client.search(query, limit=search_limit)
    if not results:
        return {"party_id": party_row["id"], "name": name, "status": "no-results", "fields": []}

    wiki_url = find_wiki_url(results)
    url = pick_url(results, name, party_row.get("short_name"))
    if not url:
        written = (
            update_party(conn, party_row["id"], {"wiki_url": wiki_url}) if wiki_url else []
        )
        return {
            "party_id": party_row["id"], "name": name, "status": "no-good-url",
            "candidates": [r.get("url") for r in results[:3]], "fields": written,
        }

    url_l = url.lower()
    if any(dom in url_l for dom in _SOCIAL_DOMAINS):
        social_field = {
            "facebook.com": "facebook_url",
            "instagram.com": "instagram_url",
            "twitter.com": "twitter_url",
            "x.com": "twitter_url",
        }[next(d for d in _SOCIAL_DOMAINS if d in url_l)]
        written = update_party(
            conn, party_row["id"], {social_field: url, "wiki_url": wiki_url}
        )
        conn.execute(
            "INSERT INTO backfill_runs (party_id, fields_filled, source_urls) "
            "VALUES (?, ?, ?)",
            (
                party_row["id"],
                json.dumps(written),
                json.dumps([r.get("url") for r in results[:3]], ensure_ascii=False),
            ),
        )
        return {
            "party_id": party_row["id"], "name": name, "status": "social-only",
            "url": url, "fields": written,
        }

    logger.info("scrape: %s", url)
    try:
        extracted = client.scrape_json(url, EXTRACT_SCHEMA, EXTRACT_PROMPT)
    except RuntimeError as e:
        return {
            "party_id": party_row["id"], "name": name, "status": "scrape-error",
            "url": url, "error": str(e)[:200], "fields": [],
        }

    extracted["wiki_url"] = wiki_url
    written = update_party(conn, party_row["id"], extracted)
    source_urls = [r.get("url") for r in results[:3]]

    conn.execute(
        "INSERT INTO backfill_runs (party_id, fields_filled, source_urls) VALUES (?, ?, ?)",
        (
            party_row["id"],
            json.dumps(written),
            json.dumps(source_urls, ensure_ascii=False),
        ),
    )
    return {
        "party_id": party_row["id"], "name": name, "status": "ok",
        "url": url, "fields": written, "raw": extracted,
    }
