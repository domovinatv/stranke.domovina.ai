"""Kompas stranaka: chunking of extracted programmes (S2).

Input: the <doc_id>.pages.json records from src/kompas/extract.py. Output: one
chunk per line in the domovina-rag ETL shape (services/etl/etl/sources.py):

  {"id": "prog_<doc_id>_<NNNN>",
   "text": "<section>\\n\\n<chunk text>",
   "metadata": {"type": "program_section", "doc_id", "party_ids", "list_id",
                "manjine_id", "vrsta", "izvor", "nesiguran", "nesiguran_razlog",
                "naslov", "url", "datum", "format", "page_from", "page_to",
                "section", "chunk_index" (1-based per doc), "total_chunks",
                "words", "overlap_words"}}

Rules:

  sections   a heading starts a section. Headings that follow each other with
             no text between them form one path ("A › B"). A generic heading
             (same text used as a heading ≥ 3 times in the document, e.g.
             "CILJEVI", "Predložene mjere:") keeps the non-generic part of the
             previous path in front of it (only headings directly followed
             by text count; a repeated parent heading is not generic). Text before the first heading gets
             the document title as its section. A heading that starts in
             lowercase right after another one continues it (wrapped line).
  tiny       a section under 80 words merges into the following one(s) until
             the merged section reaches 80 words; the name joins the parts
             with " / " (a path prefix shared with the first part is not
             repeated; more than three parts: "first / … / last"). A tiny
             section at the very end of a document joins the previous section
             and takes that section's name.
  size       per section, n = ceil(words / 550) chunks of about words / n
             words (so 300–600 in practice); paragraphs are packed greedily
             and a chunk closes when the next paragraph's midpoint would pass
             the target. Paragraphs over 250 words are split on sentence
             boundaries first (and a 250+ word "sentence" on word count).
  overlap    each chunk after the first in a section starts with "… " + the
             tail of the previous chunk: whole sentences of about 40–80 words,
             else the last 50 words. Never across a section boundary.
  pages      page_from / page_to cover the chunk's own text (not the overlap);
             an HTML document is one page.

No text leaves data/raw/: chunks.jsonl goes to data/raw/kompas/ (decision 8:
full programme texts are not committed); the committed summary
data/kompas/chunks_stats.json holds counts only.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from src.kompas import programi as P
from src.kompas.extract import words

ROOT = P.ROOT
CHUNKS_PATH = ROOT / "data" / "raw" / "kompas" / "chunks.jsonl"
STATS_PATH = ROOT / "data" / "kompas" / "chunks_stats.json"

CHUNK_MAX = 550          # target ceiling used to pick the number of chunks
PARA_SPLIT = 250         # longer paragraphs are split on sentences
OVERLAP_WORDS = 50
OVERLAP_MIN, OVERLAP_MAX = 40, 80
TINY_SECTION = 80
GENERIC_MIN = 3

# Sources the user approved but that are less certain than the rest
# (programi.json is the authority on what they are; reasons in Croatian,
# they end up in the RAG metadata). Every Wayback document is here; a test
# keeps this list and programi.json's izvor in step.
NESIGURNI: dict[str, str] = {
    "108476029df2": "snimka iz Waybacka (domena socijaldemokrati.hr ne postoji); "
                    "„Ozbiljno za Hrvatsku” su izborne natuknice saveza bez mandata",
    "a23c4dd56c14": "snimka iz Waybacka (kampanjska domena zasveizazove.hr ne postoji)",
    "1c4d71d9b198": "objava sa sažetkom programa „Suverenisti 24” (444 riječi), "
                    "cjeloviti dokument nije pronađen",
    "74d4a5515dd4": "preslika na portalu grabancijas.com; izvorni SDP-ov URL nije pronađen",
    "b185b4e53c79": "snimka iz Waybacka (laburisti.com je iza Cloudflare provjere)",
    "85b6274fc7ee": "snimka iz Waybacka (stara domena fokusnabitno.com danas vraća 404)",
    "42b55b04e20a": "snimka iz Waybacka (deklaracija s naslovnice; domena danas nepovezana)",
    "1336763429f2": "snimka iz Waybacka (domena socijaldemokrati.hr ne postoji)",
    "7f59aaaebcae": "snimka iz Waybacka (stanje 20. 4. 2024.; današnja stranica je novija verzija)",
}


# ------------------------------------------------------------------ sentences

_SENT_RE = re.compile(r"(?<=[.!?…])[\"”»)]?\s+(?=[\"„“«(•–\-]?\s?[A-ZČĆĐŠŽ0-9])")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text) if s.strip()]


def split_paragraph(text: str, limit: int = PARA_SPLIT) -> list[str]:
    """A paragraph over `limit` words → pieces of ≤ limit words on sentence
    boundaries (a sentence longer than `limit` is cut on word count)."""
    if words(text) <= limit:
        return [text]
    pieces: list[str] = []
    cur: list[str] = []
    cur_w = 0
    for s in split_sentences(text):
        sw = words(s)
        if sw > limit:
            if cur:
                pieces.append(" ".join(cur))
                cur, cur_w = [], 0
            toks = s.split()
            # cut on whitespace tokens so that each piece has ≤ limit \w+ words
            piece: list[str] = []
            for t in toks:
                piece.append(t)
                if words(" ".join(piece)) >= limit:
                    pieces.append(" ".join(piece))
                    piece = []
            if piece:
                pieces.append(" ".join(piece))
            continue
        if cur and cur_w + sw > limit:
            pieces.append(" ".join(cur))
            cur, cur_w = [], 0
        cur.append(s)
        cur_w += sw
    if cur:
        pieces.append(" ".join(cur))
    return pieces


# ------------------------------------------------------------------ sections


@dataclass
class Para:
    text: str
    page_from: int
    page_to: int

    @property
    def words(self) -> int:
        return words(self.text)


@dataclass
class Section:
    names: list[str]
    paras: list[Para] = field(default_factory=list)

    @property
    def words(self) -> int:
        return sum(p.words for p in self.paras)

    @property
    def name(self) -> str:
        uniq: list[str] = []
        for n in self.names:
            if n not in uniq:
                uniq.append(n)
        # "A › Ciljevi / A › Mjere" → "A › Ciljevi / Mjere"
        first = uniq[0].split(" › ") if uniq else []
        short = uniq[:1]
        for n in uniq[1:]:
            parts = n.split(" › ")
            k = 0
            while k < min(len(parts) - 1, len(first) - 1) and parts[k] == first[k]:
                k += 1
            short.append(" › ".join(parts[k:]))
        if len(short) > 3:
            return f"{short[0]} / … / {short[-1]}"
        return " / ".join(short)


def _hkey(h: str) -> str:
    return re.sub(r"\W+", " ", h).strip().lower()


def build_sections(doc: dict) -> list[Section]:
    """Sections with paragraphs, in reading order (toc pages skipped)."""
    counts: dict[str, int] = {}
    flat = [b for pg in doc["pages"] if not pg.get("toc") for b in pg.get("blocks", [])]
    for b, nxt in zip(flat, flat[1:]):
        if b["t"] == "h" and nxt["t"] == "p":          # leaf headings only
            counts[_hkey(b["text"])] = counts.get(_hkey(b["text"]), 0) + 1
    generic = {k for k, c in counts.items() if c >= GENERIC_MIN}

    title = doc.get("naslov") or doc["doc_id"]
    sections: list[Section] = [Section([title])]
    path: list[str] = []
    last_heading = False
    for pg in doc["pages"]:
        if pg.get("toc"):
            continue
        n = pg["page"]
        for b in pg.get("blocks", []):
            if b["t"] == "h":
                h = b["text"]
                if last_heading and path and h[:1].islower():
                    path[-1] = f"{path[-1]} {h}"          # heading wrapped onto a 2nd line
                elif last_heading:
                    if not path or _hkey(path[-1]) != _hkey(h):
                        path = (path + [h])[-3:]
                elif _hkey(h) in generic:
                    keep = [x for x in path if _hkey(x) not in generic][-2:]
                    path = keep + [h]
                else:
                    path = [h]
                name = " › ".join(path)
                if sections[-1].paras:
                    sections.append(Section([name]))
                else:
                    sections[-1].names = [name]
                last_heading = True
                continue
            last_heading = False
            cur = sections[-1]
            cont = b.get("cont")
            if cont and cur.paras:
                last = cur.paras[-1]
                last.text = last.text + ("" if cont == "nospace" else " ") + b["text"]
                last.page_to = n
            else:
                cur.paras.append(Para(b["text"], n, n))
    return [s for s in sections if s.paras]


def merge_tiny(sections: list[Section], tiny: int = TINY_SECTION) -> list[Section]:
    out: list[Section] = []
    acc: Section | None = None
    for s in sections:
        if acc is None:
            acc = Section(list(s.names), list(s.paras))
        else:
            acc.names.extend(s.names)
            acc.paras.extend(s.paras)
        if acc.words >= tiny:
            out.append(acc)
            acc = None
    if acc is not None:
        if out:   # a tiny tail joins the previous section under that name
            out[-1].paras.extend(acc.paras)
        else:
            out.append(acc)
    return out


# ------------------------------------------------------------------ chunks


def overlap_tail(text: str) -> str:
    sents = split_sentences(text)
    tail: list[str] = []
    w = 0
    for s in reversed(sents):
        tail.insert(0, s)
        w += words(s)
        if w >= OVERLAP_MIN:
            break
    if OVERLAP_MIN <= w <= OVERLAP_MAX:
        return " ".join(tail)
    toks = text.split()
    out: list[str] = []
    for t in reversed(toks):
        out.insert(0, t)
        if words(" ".join(out)) >= OVERLAP_WORDS:
            break
    return " ".join(out)


def pack_section(sec: Section) -> list[list[Para]]:
    paras: list[Para] = []
    for p in sec.paras:
        for piece in split_paragraph(p.text):
            paras.append(Para(piece, p.page_from, p.page_to))
    total = sum(p.words for p in paras)
    n = max(1, math.ceil(total / CHUNK_MAX))
    target = total / n
    groups: list[list[Para]] = []
    cur: list[Para] = []
    cur_w = 0
    for p in paras:
        w = p.words
        if cur and cur_w + w / 2 > target:
            groups.append(cur)
            cur, cur_w = [], 0
        cur.append(p)
        cur_w += w
    if cur:
        groups.append(cur)
    if len(groups) >= 2:
        last_w = sum(p.words for p in groups[-1])
        prev_w = sum(p.words for p in groups[-2])
        if last_w < 0.4 * target and last_w + prev_w <= CHUNK_MAX + 150:
            groups[-2].extend(groups.pop())
    return groups


def chunk_document(doc: dict) -> list[dict]:
    sections = merge_tiny(build_sections(doc))
    raw: list[tuple[str, list[Para], str]] = []   # (section, paras, overlap)
    for sec in sections:
        prev_text = None
        for group in pack_section(sec):
            body = "\n\n".join(p.text for p in group)
            ov = overlap_tail(prev_text) if prev_text else ""
            raw.append((sec.name, group, ov))
            prev_text = body
    total = len(raw)
    did = doc["doc_id"]
    reason = NESIGURNI.get(did)
    out: list[dict] = []
    for i, (name, group, ov) in enumerate(raw, start=1):
        body = "\n\n".join(p.text for p in group)
        content = (f"… {ov}\n\n{body}") if ov else body
        out.append({
            "id": f"prog_{did}_{i:04d}",
            "text": f"{name}\n\n{content}",
            "metadata": {
                "type": "program_section",
                "doc_id": did,
                "party_ids": list(doc.get("party_ids") or []),
                "list_id": doc.get("list_id"),
                "manjine_id": doc.get("manjine_id"),
                "vrsta": doc.get("vrsta"),
                "izvor": doc.get("izvor"),
                "nesiguran": reason is not None,
                "nesiguran_razlog": reason,
                "naslov": doc.get("naslov"),
                "url": doc.get("url"),
                "datum": doc.get("datum"),
                "format": doc.get("format"),
                "page_from": min(p.page_from for p in group),
                "page_to": max(p.page_to for p in group),
                "section": name,
                "chunk_index": i,
                "total_chunks": total,
                "words": words(content),
                "overlap_words": words(ov),
            },
        })
    return out


def jsonl(chunks: Iterable[dict]) -> str:
    return "".join(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n" for c in chunks)


# ------------------------------------------------------------------ stats


def doc_stats(doc: dict, chunks: list[dict], programi_doc: dict | None = None) -> dict:
    q = doc["quality"]
    cw = [c["metadata"]["words"] for c in chunks]
    return {
        "doc_id": doc["doc_id"],
        "slug": doc.get("slug"),
        "format": doc.get("format"),
        "party_ids": doc.get("party_ids"),
        "pages": q["pages"],
        "toc_pages": len(q["toc_pages"]),
        "empty_pages": len(q["empty_pages"]),
        "empty_page_list": q["empty_pages"],
        "needs_ocr_pages": len(q["needs_ocr_pages"]),
        "words": q["words"],
        "rijeci": (programi_doc or doc).get("rijeci"),
        "headings": q["headings"],
        "heading_method": q["heading_method"],
        "sections": len({c["metadata"]["section"] for c in chunks}),
        "chunks": len(chunks),
        "avg_chunk_words": round(sum(cw) / len(cw), 1) if cw else 0,
        "min_chunk_words": min(cw) if cw else 0,
        "max_chunk_words": max(cw) if cw else 0,
        "diacritics_share": q["diacritics_share"],
        "diacritics_suspicious": q["diacritics_suspicious"],
        "suspicious_raw": q["suspicious_raw"],
        "suspicious_clean": q["suspicious_clean"],
        "nesiguran": doc["doc_id"] in NESIGURNI,
    }


def build_stats(docs: list[dict], chunks_by_doc: dict[str, list[dict]], programi: dict,
                chunks_bytes: bytes, chunks_path: Path = CHUNKS_PATH) -> dict:
    by_id = {d["doc_id"]: d for d in programi["dokumenti"]}
    per_doc = [doc_stats(d, chunks_by_doc.get(d["doc_id"], []), by_id.get(d["doc_id"])) for d in docs]
    slugs = {s["party_id"]: s.get("slug") for s in programi.get("stranke", [])}
    per_party: dict[str, dict[str, Any]] = {}
    for d in per_doc:
        for pid in d["party_ids"] or []:
            e = per_party.setdefault(str(pid), {"slug": slugs.get(pid), "docs": 0, "chunks": 0})
            e["docs"] += 1
            e["chunks"] += d["chunks"]
    all_w = [c["metadata"]["words"] for cs in chunks_by_doc.values() for c in cs]
    try:
        rel = str(chunks_path.relative_to(ROOT))
    except ValueError:
        rel = str(chunks_path)
    return {
        "chunks_path": rel,
        "chunks_bytes": len(chunks_bytes),
        "chunks_sha256": hashlib.sha256(chunks_bytes).hexdigest(),
        "params": {"chunk_max": CHUNK_MAX, "para_split": PARA_SPLIT, "overlap_words": OVERLAP_WORDS,
                   "tiny_section": TINY_SECTION, "generic_heading_min": GENERIC_MIN},
        "totals": {
            "docs": len(per_doc),
            "pages": sum(d["pages"] for d in per_doc),
            "empty_pages": sum(d["empty_pages"] for d in per_doc),
            "needs_ocr_pages": sum(d["needs_ocr_pages"] for d in per_doc),
            "words": sum(d["words"] for d in per_doc),
            "chunks": len(all_w),
            "avg_chunk_words": round(sum(all_w) / len(all_w), 1) if all_w else 0,
            "diacritics_suspicious_docs": [d["doc_id"] for d in per_doc if d["diacritics_suspicious"]],
            "nesigurni_docs": sum(1 for d in per_doc if d["nesiguran"]),
        },
        "dokumenti": per_doc,
        "stranke": dict(sorted(per_party.items(), key=lambda kv: int(kv[0]))),
    }
