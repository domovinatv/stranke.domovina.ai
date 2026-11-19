"""Kompas stranaka: party programmes (izborni 2024, koalicijski, trajni).

Testable logic behind scripts/23_fetch_programi.py:

  Fetcher          plain-httpx GET with a disk cache under data/raw/programi/_http/
                   (every response is cached, errors included, so a re-run with a
                   warm cache makes no network calls; `offline=True` forbids misses)
  wayback_*        Wayback Machine: raw snapshot nearest a date (`<ts>id_/`) and
                   the CDX index (which PDFs a party site served in 2024)
  analyse()        format (pdf | html | skeniran), PDF pages, rough word count
  check_programme  heuristics that flag a document which does not read like a
                   programme of the right year (warnings, not verdicts)
  build_output()   programi.json from the curated sources
                   (data/kompas/programi_izvori.json) and the fetched documents
  validate()       hand-written schema check of programi.json

Which URL is a programme is a judgement made by a person and recorded in
programi_izvori.json; this module only fetches, measures and cross-checks it.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urljoin, urlparse

import httpx

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "programi"
HTTP_DIR = RAW_DIR / "_http"
OUT_PATH = ROOT / "data" / "kompas" / "programi.json"
IZVORI_PATH = ROOT / "data" / "kompas" / "programi_izvori.json"
LISTE_PATH = ROOT / "data" / "kompas" / "liste_2024.json"

VRSTE = ("izborni-2024", "koalicijski", "trajni")
IZVORI = ("web", "wayback", "firecrawl")
FORMATI = ("pdf", "html", "skeniran")
STATUSI = ("pronađen", "djelomično", "nije-pronađen")

# Parliamentary election day was 17 April 2024; snapshots just before it.
WAYBACK_TS_2024 = "20240416"
SCANNED_CHARS_PER_PAGE = 50
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 stranke.domovina.ai-kompas"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- fetch


class OfflineMiss(RuntimeError):
    """A URL is not in the cache and the run is --offline."""


@dataclass
class Response:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    fetched_at: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and bool(self.body)


TRANSIENT = {429, 502, 503, 504}


def _key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:20]


class Fetcher:
    """GET with a permanent disk cache (meta .json + body .bin per URL)."""

    def __init__(self, cache_dir: Path = HTTP_DIR, offline: bool = False,
                 throttle_s: float = 0.4, timeout: float = 60.0):
        self.cache_dir = cache_dir
        self.offline = offline
        self.throttle_s = throttle_s
        self.timeout = timeout
        self.network_calls = 0
        self._client: httpx.Client | None = None
        self._last: dict[str, float] = {}

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": USER_AGENT, "Accept-Language": "hr,en;q=0.8"},
                follow_redirects=True, timeout=self.timeout, verify=True,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def cached(self, url: str) -> Response | None:
        meta_p = self.cache_dir / f"{_key(url)}.json"
        if not meta_p.exists():
            return None
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        body_p = self.cache_dir / f"{_key(url)}.bin"
        body = body_p.read_bytes() if body_p.exists() else b""
        return Response(meta["url"], meta["final_url"], meta["status"],
                        meta.get("content_type", ""), body, meta["fetched_at"],
                        meta.get("error"))

    def get(self, url: str) -> Response:
        hit = self.cached(url)
        if hit is not None:
            return hit
        if self.offline:
            raise OfflineMiss(url)
        host = urlparse(url).netloc
        wait = self.throttle_s - (time.monotonic() - self._last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            self.network_calls += 1
            try:
                r = self._http().get(url)
                resp = Response(url, str(r.url), r.status_code,
                                r.headers.get("content-type", ""), r.content, now_iso())
            except httpx.HTTPError as e:
                resp = Response(url, url, 0, "", b"", now_iso(),
                                f"{type(e).__name__}: {e}"[:300])
            self._last[host] = time.monotonic()
            if resp.status not in TRANSIENT:
                break
            time.sleep(4 * (attempt + 1))
        if resp.status not in TRANSIENT:  # overloaded Wayback etc.: retry next run
            self._store(resp)
        return resp

    def _store(self, r: Response) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        k = _key(r.url)
        if r.body:
            (self.cache_dir / f"{k}.bin").write_bytes(r.body)
        meta = {"url": r.url, "final_url": r.final_url, "status": r.status,
                "content_type": r.content_type, "fetched_at": r.fetched_at,
                "bytes": len(r.body)}
        if r.error:
            meta["error"] = r.error
        (self.cache_dir / f"{k}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- wayback

_WB_RE = re.compile(r"web\.archive\.org/web/(\d{14})(?:id_)?/(.+)$")


def wayback_raw_url(url: str, ts: str = WAYBACK_TS_2024) -> str:
    """Raw original bytes (no toolbar) of the snapshot nearest `ts`."""
    return f"https://web.archive.org/web/{ts}id_/{url}"


def wayback_view_url(final_url: str) -> str | None:
    """Human-facing snapshot URL from the redirect target of a raw fetch."""
    m = _WB_RE.search(final_url)
    if not m:
        return None
    return f"https://web.archive.org/web/{m.group(1)}/{m.group(2)}"


def wayback_date(final_url: str) -> str | None:
    m = _WB_RE.search(final_url)
    if not m:
        return None
    s = m.group(1)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def cdx_url(domain: str, frm: str = "2023", to: str = "2024",
            mimetype: str = "application/pdf") -> str:
    q = (f"url={quote(domain)}/*&output=json&from={frm}&to={to}"
         f"&filter=mimetype:{quote(mimetype, safe='')}&collapse=urlkey&limit=2000")
    return f"https://web.archive.org/cdx/search/cdx?{q}"


def parse_cdx(body: bytes) -> list[dict[str, str]]:
    try:
        rows = json.loads(body.decode("utf-8") or "[]")
    except (ValueError, UnicodeDecodeError):
        return []
    if not rows:
        return []
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:]]


# --------------------------------------------------------------------------- analysis

_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass
class Analysis:
    format: str               # pdf | html | skeniran
    ext: str                  # pdf | html
    stranica: int | None
    rijeci: int | None
    tekst: str                # extracted text (not stored in git)
    naslov: str | None        # <title> or PDF metadata title


def is_pdf(body: bytes) -> bool:
    return body[:1024].lstrip().startswith(b"%PDF") or b"%PDF-" in body[:1024]


def pdf_analysis(body: bytes) -> Analysis:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    texts: list[str] = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception as e:  # pypdf raises a zoo of errors on odd PDFs
            log.debug("pdf page text failed: %s", e)
            texts.append("")
    pages = len(reader.pages)
    text = "\n".join(texts)
    chars = len(re.sub(r"\s+", "", text))
    fmt = "skeniran" if pages and chars / pages < SCANNED_CHARS_PER_PAGE else "pdf"
    title = None
    try:
        meta = reader.metadata
        title = (meta.title or None) if meta else None
    except Exception:
        title = None
    return Analysis(fmt, "pdf", pages, len(_WORD_RE.findall(text)), text, title)


def html_main(body: bytes):
    """(main-content element or None, <title>): drops script/style/nav/header/
    footer/form and picks the first <main>/<article>, else the whole document.
    Shared with src/kompas/extract.py so word counts agree."""
    import lxml.html

    try:
        doc = lxml.html.fromstring(body)
    except (ValueError, lxml.etree.ParserError):
        return None, None
    title_el = doc.find(".//title")
    title = title_el.text_content().strip() if title_el is not None else None
    for bad in doc.xpath("//script|//style|//noscript|//nav|//header|//footer|//form"):
        bad.drop_tree()
    main = doc.xpath("//main|//article")
    return (main[0] if main else doc), (title or None)


def html_text(body: bytes) -> tuple[str, str | None]:
    root, title = html_main(body)
    if root is None:
        return "", None
    text = re.sub(r"[ \t]+", " ", root.text_content())
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text, title or None


def analyse(body: bytes) -> Analysis:
    if is_pdf(body):
        return pdf_analysis(body)
    text, title = html_text(body)
    return Analysis("html", "html", None, len(_WORD_RE.findall(text)), text, title)


def page_links(body: bytes, base_url: str) -> list[tuple[str, str]]:
    """(absolute href, anchor text) for every <a> on an HTML page."""
    import lxml.html

    try:
        doc = lxml.html.fromstring(body)
    except (ValueError, lxml.etree.ParserError):
        return []
    out = []
    for a in doc.xpath("//a[@href]"):
        href = a.get("href", "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        out.append((urljoin(base_url, href), " ".join(a.text_content().split())))
    return out


PROGRAM_HINT = re.compile(r"program|deklaracij|manifest|izborn|platform", re.I)


def programme_links(body: bytes, base_url: str) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out = []
    for href, text in page_links(body, base_url):
        if (PROGRAM_HINT.search(href) or PROGRAM_HINT.search(text)) and href not in seen:
            seen.add(href)
            out.append((href, text))
    return out


def check_programme(text: str, vrsta: str) -> list[str]:
    """Warnings for a document that may not be a programme of the right year."""
    head = text[:6000].lower()
    warn = []
    if len(text.strip()) < 200:
        warn.append("malo teksta")
    if not re.search(r"program|deklaracij|manifest|načel|vizij|ciljev", head):
        warn.append("na početku nema riječi program/deklaracija")
    if vrsta in ("izborni-2024", "koalicijski"):
        if "2024" not in text and "2028" not in text:
            warn.append("ne spominje 2024 ni 2028")
        if re.search(r"lokaln\w+ izbor\w* 2025|izbori 2025|2025\.?\s*[–-]\s*2029", head):
            warn.append("spominje lokalne izbore 2025")
    return warn


_PUB_RES = (
    re.compile(rb'property=["\']article:published_time["\']\s+content=["\'](\d{4}-\d{2}-\d{2})'),
    re.compile(rb'content=["\'](\d{4}-\d{2}-\d{2})[^"\']*["\']\s+property=["\']article:published_time'),
    re.compile(rb'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})'),
)


def html_published(body: bytes) -> str | None:
    """Publication date an HTML page states about itself (OpenGraph / JSON-LD)."""
    for rx in _PUB_RES:
        m = rx.search(body)
        if m:
            return m.group(1).decode()
    return None


def date_from_text(text: str) -> str | None:
    """A full date stated near the start of a document (DD. MM. YYYY.)."""
    m = re.search(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d{2})\.?", text[:3000])
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


# --------------------------------------------------------------------------- output


def dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def doc_id_for(sha256: str) -> str:
    return sha256[:12]


def raw_path(slug: str, sha256: str, ext: str) -> Path:
    return RAW_DIR / slug / f"{sha256[:12]}.{ext}"


def party_status(vrste: set[str], izvan_lista: bool) -> str:
    """pronađen = election programme (own or coalition) and a standing one;
    for parties that ran on no 2024 list only the standing one is expected."""
    election = bool(vrste & {"izborni-2024", "koalicijski"})
    standing = "trajni" in vrste
    if izvan_lista:
        if standing:
            return "pronađen"
        return "djelomično" if election else "nije-pronađen"
    if election and standing:
        return "pronađen"
    if election or standing:
        return "djelomično"
    return "nije-pronađen"


def stable(new: dict, old: dict | None) -> dict:
    """Carry over `preuzeto` per doc and `generated_at` when nothing changed,
    so a warm re-run leaves programi.json byte-identical."""
    if not old:
        return new
    old_docs = {d["doc_id"]: d for d in old.get("dokumenti", [])}
    for d in new["dokumenti"]:
        prev = old_docs.get(d["doc_id"])
        if prev and prev.get("preuzeto"):
            d["preuzeto"] = prev["preuzeto"]
    cand = json.loads(dump(new))
    cand["generated_at"] = old.get("generated_at")
    if cand == old:
        new["generated_at"] = old["generated_at"]
    return new


# --------------------------------------------------------------------------- validation

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _need(errs: list[str], where: str, obj: dict, key: str, types: tuple, nullable=False):
    if key not in obj:
        errs.append(f"{where}: nema '{key}'")
        return False
    v = obj[key]
    if v is None:
        if not nullable:
            errs.append(f"{where}: '{key}' je null")
        return False
    if not isinstance(v, types) or (isinstance(v, bool) and bool not in types):
        errs.append(f"{where}: '{key}' krivog tipa {type(v).__name__}")
        return False
    return True


def validate(data: Any, liste: dict | None = None) -> list[str]:
    """Return a list of problems (empty = valid). With `liste` (liste_2024.json)
    also checks scope: one `stranke` entry per party, list_ids exist."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["vrh nije objekt"]
    for k in ("generated_at", "dokumenti", "stranke", "manjine"):
        if k not in data:
            errs.append(f"nema '{k}'")
    if errs:
        return errs
    if not isinstance(data["generated_at"], str) or not _ISO_RE.match(data["generated_at"]):
        errs.append("generated_at nije ISO timestamp")

    list_ids = {l["list_id"] for l in liste["liste"]} if liste else None
    docs: dict[str, dict] = {}
    shas: set[str] = set()
    for i, d in enumerate(data["dokumenti"] if isinstance(data["dokumenti"], list) else []):
        w = f"dokumenti[{i}]"
        if not isinstance(d, dict):
            errs.append(f"{w}: nije objekt")
            continue
        if _need(errs, w, d, "doc_id", (str,)):
            if d["doc_id"] in docs:
                errs.append(f"{w}: doc_id {d['doc_id']} ponovljen")
            docs[d["doc_id"]] = d
        if _need(errs, w, d, "sha256", (str,)):
            if not _SHA_RE.match(d["sha256"]):
                errs.append(f"{w}: sha256 nije hex64")
            elif d["sha256"] in shas:
                errs.append(f"{w}: isti sha256 dvaput (preuzeto dvaput?)")
            shas.add(d["sha256"])
            if isinstance(d.get("doc_id"), str) and not d["sha256"].startswith(d["doc_id"]):
                errs.append(f"{w}: doc_id nije prefiks sha256")
        if _need(errs, w, d, "vrsta", (str,)) and d["vrsta"] not in VRSTE:
            errs.append(f"{w}: vrsta '{d['vrsta']}'")
        _need(errs, w, d, "list_id", (str,), nullable=True)
        if d.get("vrsta") == "koalicijski":
            if not d.get("list_id"):
                errs.append(f"{w}: koalicijski bez list_id")
            elif list_ids is not None and d["list_id"] not in list_ids:
                errs.append(f"{w}: nepoznat list_id {d['list_id']}")
        elif d.get("list_id") is not None and d.get("vrsta") == "trajni":
            errs.append(f"{w}: trajni s list_id")
        if _need(errs, w, d, "party_ids", (list,)):
            if not all(isinstance(p, int) and not isinstance(p, bool) for p in d["party_ids"]):
                errs.append(f"{w}: party_ids nisu int")
            if d["party_ids"] != sorted(set(d["party_ids"])):
                errs.append(f"{w}: party_ids nisu sortirani/jedinstveni")
            if not d["party_ids"] and not d.get("manjine_id"):
                errs.append(f"{w}: bez party_ids i bez manjine_id")
        _need(errs, w, d, "naslov", (str,))
        if _need(errs, w, d, "url", (str,)) and not d["url"].startswith(("http://", "https://")):
            errs.append(f"{w}: url")
        if _need(errs, w, d, "izvor", (str,)) and d["izvor"] not in IZVORI:
            errs.append(f"{w}: izvor '{d['izvor']}'")
        if d.get("izvor") == "wayback" and not str(d.get("wayback_url", "")).startswith(
                "https://web.archive.org/web/"):
            errs.append(f"{w}: wayback bez wayback_url")
        if _need(errs, w, d, "datum", (str,), nullable=True) and not _DATE_RE.match(d["datum"]):
            errs.append(f"{w}: datum nije YYYY-MM-DD")
        if _need(errs, w, d, "format", (str,)) and d["format"] not in FORMATI:
            errs.append(f"{w}: format '{d['format']}'")
        _need(errs, w, d, "stranica", (int,), nullable=True)
        _need(errs, w, d, "rijeci", (int,), nullable=True)
        if d.get("format") in ("pdf", "skeniran") and not isinstance(d.get("stranica"), int):
            errs.append(f"{w}: PDF bez broja stranica")
        if d.get("format") == "html" and d.get("stranica") is not None:
            errs.append(f"{w}: HTML sa stranicama")
        if _need(errs, w, d, "preuzeto", (str,)) and not _ISO_RE.match(d["preuzeto"]):
            errs.append(f"{w}: preuzeto nije ISO")
        if "napomena" in d and not isinstance(d["napomena"], str):
            errs.append(f"{w}: napomena nije string")
        if "ujedno_trajni" in d and (d["ujedno_trajni"] is not True or d.get("vrsta") == "trajni"):
            errs.append(f"{w}: ujedno_trajni samo kao true na izbornom dokumentu")

    referenced: set[str] = set()
    entries: dict[int, dict] = {}
    for i, s in enumerate(data["stranke"] if isinstance(data["stranke"], list) else []):
        w = f"stranke[{i}]"
        if not isinstance(s, dict):
            errs.append(f"{w}: nije objekt")
            continue
        if _need(errs, w, s, "party_id", (int,)):
            if s["party_id"] in entries:
                errs.append(f"{w}: party_id {s['party_id']} ponovljen")
            entries[s["party_id"]] = s
        _need(errs, w, s, "slug", (str,))
        if _need(errs, w, s, "status", (str,)) and s["status"] not in STATUSI:
            errs.append(f"{w}: status '{s['status']}'")
        _need(errs, w, s, "provjereno", (list,))
        if _need(errs, w, s, "doc_ids", (list,)):
            for did in s["doc_ids"]:
                referenced.add(did)
                if did not in docs:
                    errs.append(f"{w}: doc_id {did} ne postoji")
                elif s.get("party_id") not in docs[did].get("party_ids", []):
                    errs.append(f"{w}: dokument {did} ne navodi party_id {s.get('party_id')}")
            if s.get("status") == "nije-pronađen" and s["doc_ids"]:
                errs.append(f"{w}: nije-pronađen a ima dokumente")
            if s.get("status") in ("pronađen", "djelomično") and not s["doc_ids"]:
                errs.append(f"{w}: {s['status']} bez dokumenata")
            if s.get("status") != "pronađen" and not s.get("provjereno"):
                errs.append(f"{w}: {s.get('status')} bez popisa provjerenog")
    for did, d in docs.items():
        for pid in d.get("party_ids", []):
            if pid not in entries:
                errs.append(f"dokument {did}: party_id {pid} nema unos u stranke")
            elif did not in entries[pid].get("doc_ids", []):
                errs.append(f"dokument {did}: stranka {pid} ga ne navodi u doc_ids")

    for i, m in enumerate(data["manjine"] if isinstance(data["manjine"], list) else []):
        w = f"manjine[{i}]"
        if not isinstance(m, dict):
            errs.append(f"{w}: nije objekt")
            continue
        _need(errs, w, m, "manjine_id", (str,))
        _need(errs, w, m, "party_id", (int,), nullable=True)
        if _need(errs, w, m, "status", (str,)) and m["status"] not in STATUSI:
            errs.append(f"{w}: status '{m['status']}'")
        if _need(errs, w, m, "doc_ids", (list,)):
            for did in m["doc_ids"]:
                referenced.add(did)
                if did not in docs:
                    errs.append(f"{w}: doc_id {did} ne postoji")
        _need(errs, w, m, "provjereno", (list,))
    for did in docs:
        if did not in referenced:
            errs.append(f"dokument {did} nitko ne navodi")

    if liste is not None:
        want = {s["party_id"] for s in liste["stranke"]}
        missing = want - set(entries)
        extra = set(entries) - want
        if missing:
            errs.append(f"stranke bez unosa: {sorted(missing)}")
        if extra:
            errs.append(f"unosi izvan opsega: {sorted(extra)}")
    return errs


# --------------------------------------------------------------------------- build


@dataclass
class Fetched:
    """One curated source after fetching: bytes + where they came from."""
    body: bytes
    izvor: str                # web | wayback | firecrawl
    url: str                  # original URL
    wayback_url: str | None
    wayback_datum: str | None
    preuzeto: str


def build_output(
    liste: dict,
    izvori: dict,
    fetch: Callable[[dict], Fetched | None],
    store: Callable[[str, str, str, bytes], None] | None = None,
    log_warn: Callable[[str], None] = log.warning,
) -> dict:
    """Assemble programi.json.

    `izvori` is programi_izvori.json; `fetch(src)` returns the bytes of a curated
    source (or None when it cannot be had); `store(slug, sha, ext, body)` keeps
    the original. Coalition documents are fetched once and attached to every
    member of their list."""
    by_pid = {s["party_id"]: s for s in liste["stranke"]}
    by_slug = {s["slug"]: s for s in liste["stranke"]}
    lists = {l["list_id"]: l for l in liste["liste"]}
    docs: dict[str, dict] = {}
    party_docs: dict[int, list[str]] = {pid: [] for pid in by_pid}
    party_vrste: dict[int, set[str]] = {pid: set() for pid in by_pid}
    manjine_docs: dict[str, list[str]] = {}

    def add(src: dict, owner_slug: str, vrsta: str, list_id: str | None,
            party_ids: list[int], manjine_id: str | None = None) -> str | None:
        f = fetch(src)
        if f is None:
            log_warn(f"nije preuzeto: {src['url']}")
            return None
        sha = hashlib.sha256(f.body).hexdigest()
        a = analyse(f.body)
        warn = check_programme(a.tekst, vrsta)
        if warn and not src.get("prihvati_upozorenja"):
            log_warn(f"{owner_slug} {vrsta} {src['url']}: {', '.join(warn)}")
        did = doc_id_for(sha)
        if did in docs:  # same bytes reached from two entries: merge parties
            d = docs[did]
            d["party_ids"] = sorted(set(d["party_ids"]) | set(party_ids))
            return did
        if store is not None:
            store(owner_slug, sha, a.ext, f.body)
        d = {
            "doc_id": did,
            "sha256": sha,
            "vrsta": vrsta,
            "list_id": list_id,
            "party_ids": sorted(set(party_ids)),
            "naslov": src["naslov"],
            "url": f.url,
            "izvor": f.izvor,
            "datum": src.get("datum") or (html_published(f.body) if a.ext == "html" else None),
            "format": a.format,
            "stranica": a.stranica,
            "rijeci": a.rijeci,
            "preuzeto": f.preuzeto,
        }
        if f.wayback_url:
            d["wayback_url"] = f.wayback_url
        if manjine_id:
            d["manjine_id"] = manjine_id
        if src.get("napomena"):
            d["napomena"] = src["napomena"]
        if src.get("ujedno_trajni"):
            d["ujedno_trajni"] = True
        docs[did] = d
        return did

    for list_id, entry in sorted(izvori.get("koalicije", {}).items()):
        if list_id not in lists:
            raise ValueError(f"programi_izvori: nepoznat list_id {list_id}")
        members = [c["party_id"] for c in lists[list_id]["clanice"] if c.get("party_id")]
        lead = lists[list_id]["nositelj"]["slug"]
        for src in entry.get("izvori", []):
            pids = [p for p in members if p not in src.get("bez", [])]
            did = add(src, src.get("objavio", lead), "koalicijski", list_id, pids)
            if did:
                for p in pids:
                    party_docs[p].append(did)
                    party_vrste[p].add("koalicijski")
                    if src.get("ujedno_trajni"):
                        party_vrste[p].add("trajni")

    for slug, entry in sorted(izvori.get("stranke", {}).items()):
        if slug not in by_slug:
            raise ValueError(f"programi_izvori: nepoznat slug {slug}")
        pid = by_slug[slug]["party_id"]
        for src in entry.get("izvori", []):
            vrsta = src["vrsta"]
            if vrsta not in ("izborni-2024", "trajni"):
                raise ValueError(f"{slug}: vrsta {vrsta} (koalicijski idu pod 'koalicije')")
            did = add(src, src.get("objavio", slug), vrsta, src.get("list_id"), [pid])
            if did:
                party_docs[pid].append(did)
                party_vrste[pid].add(vrsta)
                if src.get("ujedno_trajni"):
                    party_vrste[pid].add("trajni")

    man_meta = {m["manjine_id"]: m for m in liste.get("manjine", [])}
    for mid, entry in sorted(izvori.get("manjine", {}).items()):
        if mid not in man_meta:
            raise ValueError(f"programi_izvori: nepoznat manjine_id {mid}")
        clan = man_meta[mid]["clanice"][0]
        pid = clan.get("party_id")
        owner = clan.get("slug") or mid
        for src in entry.get("izvori", []):
            vrsta = src.get("vrsta", "izborni-2024")
            did = add(src, owner, vrsta, None, [pid] if pid else [], manjine_id=mid)
            if did:
                manjine_docs.setdefault(mid, []).append(did)
                if pid in party_docs:
                    party_docs[pid].append(did)
                    party_vrste[pid].add(vrsta)

    stranke_out = []
    for s in sorted(liste["stranke"], key=lambda s: s["slug"]):
        pid = s["party_id"]
        entry = izvori.get("stranke", {}).get(s["slug"], {})
        dids = list(dict.fromkeys(party_docs[pid]))
        status = party_status(party_vrste[pid], s.get("izvan_lista", False))
        provj = [] if status == "pronađen" else list(entry.get("provjereno", []))
        out = {"party_id": pid, "slug": s["slug"], "status": status,
               "doc_ids": dids, "provjereno": provj}
        if entry.get("napomena"):
            out["napomena"] = entry["napomena"]
        stranke_out.append(out)

    manjine_out = []
    for m in liste.get("manjine", []):
        mid = m["manjine_id"]
        entry = izvori.get("manjine", {}).get(mid, {})
        clan = m["clanice"][0]
        dids = manjine_docs.get(mid, [])
        out = {"manjine_id": mid, "naziv": clan["naziv"].strip(),
               "party_id": clan.get("party_id"),
               "status": "pronađen" if dids else "nije-pronađen",
               "doc_ids": dids, "provjereno": list(entry.get("provjereno", []))}
        if entry.get("napomena"):
            out["napomena"] = entry["napomena"]
        manjine_out.append(out)

    dokumenti = sorted(docs.values(), key=lambda d: (VRSTE.index(d["vrsta"]),
                                                    d["list_id"] or "", d["party_ids"],
                                                    d["doc_id"]))
    return {"generated_at": now_iso(), "dokumenti": dokumenti,
            "stranke": stranke_out, "manjine": manjine_out}


# --------------------------------------------------------------------------- firecrawl budget


class BudgetExceeded(RuntimeError):
    pass


class FirecrawlBudget:
    """Counts Firecrawl calls that miss the cache (cache hits are free) and
    enforces a per-party and a total cap. `client_factory` is lazy so offline
    and cached runs never need an API key."""

    def __init__(self, client_factory: Callable[[], Any], per_party: int = 12,
                 total: int = 450, offline: bool = False):
        self._factory = client_factory
        self._client = None
        self.per_party = per_party
        self.total = total
        self.offline = offline
        self.calls = 0
        self.by_party: dict[str, int] = {}
        self.exhausted = False

    def _cli(self):
        if self._client is None:
            self._client = self._factory()
        return self._client

    def _post(self, party: str, endpoint: str, payload: dict) -> dict:
        from src.firecrawl import _cache_key

        cache = _cache_key(endpoint, payload)
        if cache.exists():
            return json.loads(cache.read_text())
        if self.offline:
            raise OfflineMiss(f"firecrawl {endpoint} {payload}")
        if self.exhausted:
            raise BudgetExceeded("firecrawl credits exhausted")
        if self.calls >= self.total or self.by_party.get(party, 0) >= self.per_party:
            raise BudgetExceeded(f"firecrawl budget ({party}: {self.by_party.get(party, 0)}, "
                                 f"total {self.calls})")
        self.calls += 1
        self.by_party[party] = self.by_party.get(party, 0) + 1
        return self._cli()._post(endpoint, payload)

    def search(self, party: str, query: str, limit: int = 8) -> list[dict]:
        data = self._post(party, "search", {"query": query, "limit": limit})
        return ((data.get("data") or {}).get("web")) or []

    def scrape_links(self, party: str, url: str) -> list[str]:
        data = self._post(party, "scrape", {"url": url, "formats": ["links"]})
        return ((data.get("data") or {}).get("links")) or []

    def scrape_html(self, party: str, url: str) -> str | None:
        data = self._post(party, "scrape", {"url": url, "formats": ["rawHtml"]})
        return (data.get("data") or {}).get("rawHtml")
