"""Kompas stranaka: text extraction from party programmes (S2).

Testable logic behind scripts/24_extract_programi.py. Input is a document from
data/kompas/programi.json and its raw file data/raw/programi/<slug>/<doc_id>.<ext>;
output is <doc_id>.pages.json next to it (full text, so it stays under the
gitignored data/raw/):

  {"doc_id", "slug", "format", "sha256", "extractor_version", "naslov", ...,
   "pages": [{"page": 1, "text", "headings": [...], "words", "blocks": [...],
              "toc", "empty", "images", "needs_ocr"}],
   "quality": {...}}

`blocks` is what the chunker reads: {"t": "h"|"p", "text"} in reading order;
a paragraph that continues from the previous page carries "cont": "space" |
"nospace" (nospace = a word was split by a hyphen across the page break).

PDF pipeline (per document, because some steps need the whole document):

  1. pypdf extract_text() gives the lines; visitor_text gives each text
     fragment's effective font size and font name. Lines are mapped to
     fragments by whitespace-free matching, so each line gets a size and a
     bold flag.
  2. Normalisation: NFC, ligatures (ﬁ → fi), spacing/combining carons
     ("c ˇ" → č), private-use bullets → •, soft hyphens, NBSP.
  3. Standalone page numbers in the top/bottom 4 lines are dropped.
  4. Running headers/footers: an edge line (same text, digits ignored) on
     > 50 % of the pages (min. 3 pages) is dropped everywhere. Running
     section labels (SDP prints "UVOD" at the foot of every page of the
     chapter): an edge line with the same text and size on ≥ 3 pages, with
     at least two consecutive pages, is kept once per run as a heading at the
     top of the run's first page and dropped elsewhere (a run tolerates a
     one-page gap). A lone big capital before a lowercase line is a drop cap
     and is glued back to its word.
  5. Table-of-contents pages (≥ 60 % of lines end in a page number) are
     marked "toc" and produce no blocks.
  6. Headings: a line is a candidate when its font size ≥ 1.15 × the body
     size (char-weighted mode of the document) and ≥ body + 1 pt, or when
     the whole line is bold and at most 12 words. Consecutive candidates of
     the same size merge into one block; the block is a heading if it has
     ≤ 20 words and does not end with . , ; ! ? (that filters pull quotes).
     Without any font-based heading in the whole document the fallback is
     short ALL-CAPS lines and numbered headings ("3.2. Zdravstvo").
  7. Paragraphs: lines join with a space; a paragraph ends at a blank line,
     a bullet, a heading, or a short line (< 80 % of the document's p75 line
     length) that ends with sentence punctuation. Line-end hyphenation
     "rije-\\nči" is joined when the next line starts lowercase, unless the
     hyphenated form occurs elsewhere in the document (then the hyphen is a
     real compound and is kept); "rije -\\nči" (pypdf spacing) is joined only
     when the joined word occurs elsewhere in the document.

HTML: one logical page (page 1); main content as in programi.html_main();
headings from h1–h6 and from paragraphs that are entirely bold and short;
every block element (p, li, div text, br) is a paragraph, li gets "• ";
lines that are only site chrome (social links, "Preuzmi dokument", ©, a bare
e-mail or URL) are dropped.

No OCR (decision: there are no scanned programmes); pages without text that
carry an image are only counted ("needs_ocr").
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from src.kompas import programi as P

log = logging.getLogger(__name__)

EXTRACTOR_VERSION = 3
WORD_RE = re.compile(r"\w+", re.UNICODE)
EMPTY_PAGE_WORDS = 5

# ------------------------------------------------------------------ normalisation

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
BULLETS = "•●▪■◆◦‣∙·➢➤►▶✓✔"
_PUA_RE = re.compile("[-]")
_SPACING_CARON_RE = (re.compile(r"([cszCSZ]) ?ˇ"), re.compile(r"ˇ ?([cszCSZ])"))
_SPACING_ACUTE_RE = (re.compile(r"([cC]) ?´"), re.compile(r"´ ?([cC])"))

# what quality_counts() looks for (in the raw pypdf text, and after cleaning)
SUSPICIOUS = {
    "combining_caron": re.compile("̌"),
    "combining_acute": re.compile("́"),
    "spacing_caron": re.compile("ˇ"),
    "spacing_acute_c": re.compile(r"[cC] ?´"),
    "replacement_char": re.compile("�"),
    "ligature": re.compile("[" + "".join(LIGATURES) + "]"),
    "private_use": _PUA_RE,
    "control_char": re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]"),
}


def normalize(s: str) -> str:
    """NFC + the pypdf repairs described in the module docstring."""
    for rx in _SPACING_CARON_RE:
        s = rx.sub(lambda m: m.group(1) + "̌", s)
    for rx in _SPACING_ACUTE_RE:
        s = rx.sub(lambda m: m.group(1) + "́", s)
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    s = _PUA_RE.sub("•", s)
    s = s.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    s = re.sub("[​‌‍﻿]", "", s)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    s = unicodedata.normalize("NFC", s)
    return s


def suspicious_counts(text: str) -> dict[str, int]:
    return {k: len(rx.findall(text)) for k, rx in SUSPICIOUS.items() if rx.search(text)}


def words(text: str) -> int:
    return len(WORD_RE.findall(text))


_DIA = re.compile("[čćđšž]")


def diacritics_share(text: str) -> tuple[float, int]:
    """Share of lowercase alphabetic words that contain č ć đ š ž (and the
    number of such lowercase words). Croatian prose sits around 0.15–0.20;
    below 0.03 the diacritics are probably broken."""
    low = [w for w in WORD_RE.findall(text) if w.isalpha() and w.islower()]
    if not low:
        return 0.0, 0
    return sum(1 for w in low if _DIA.search(w)) / len(low), len(low)


# ------------------------------------------------------------------ line model

_PAGE_NO_RE = re.compile(
    r"^(?:[-–—]?\s*\d{1,3}\s*[-–—]?|\d{1,3}\s*/\s*\d{1,3}|str(?:ana|\.)?\s*\d{1,3}"
    r"|\d{1,3}\s+\d{1,3})$", re.I)
_BULLET_RE = re.compile(r"^(?:[" + BULLETS + r"\-–—*]\s+|[" + BULLETS + r"]|\d{1,2}[.)]\s+\S|[a-zA-Z][.)]\s+\S)")
_NUMBERED_HEAD_RE = re.compile(r"^\d{1,2}(?:\.\d{1,2})*\.?\s+[A-ZČĆĐŠŽ]")
_TOC_LINE_RE = re.compile(r"\S.*?(?:\s|\.{2,}|…)\s*\d{1,3}\s*$")
_END_SENTENCE = tuple(".!?:;…\"“”»)")
_HEAD_BAD_END = tuple(".,;!?")


def line_key(s: str) -> str:
    """Comparable form of a line for header/footer detection (digits ignored)."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", " ", s)).strip().lower()


def is_caps_heading(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 4 or len(s.split()) > 10:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= 0.9 and not s.endswith(_HEAD_BAD_END[1:])


def is_numbered_heading(s: str) -> bool:
    return bool(_NUMBERED_HEAD_RE.match(s)) and len(s.split()) <= 10 and not s.endswith(_HEAD_BAD_END)


class Line:
    __slots__ = ("text", "size", "bold", "head", "label", "floating")

    def __init__(self, text: str, size: float | None = None, bold: bool = False):
        self.text = text
        self.size = size
        self.bold = bold
        self.head = False      # classified as (part of) a heading
        self.label = False     # running section label kept as heading
        self.floating = False  # sidebar title that interrupts a sentence

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Line({self.text!r}, {self.size}, b={self.bold}, h={self.head})"


def _nows(s: str) -> str:
    return re.sub(r"\s+", "", s)


def attach_fonts(lines: list[str], frags: list[tuple[str, float, bool]]) -> list[Line]:
    """Give every extract_text() line the size/bold of the visitor fragments it
    came from (whitespace-free substring matching with a moving cursor)."""
    chars: list[str] = []
    meta: list[tuple[float, bool]] = []
    for text, size, bold in frags:
        t = _nows(normalize(text))
        chars.append(t)
        meta.extend([(size, bold)] * len(t))
    s = "".join(chars)
    out: list[Line] = []
    cur = 0
    for raw in lines:
        text = raw.strip()
        key = _nows(text)
        if not key:
            out.append(Line(""))
            continue
        idx = s.find(key, cur)
        if idx < 0:
            idx = s.find(key)
        if idx < 0 and len(key) > 8:
            idx = s.find(key[:8], cur)
        if idx < 0:
            out.append(Line(text))
            continue
        span = meta[idx: idx + len(key)]
        cur = idx + len(key)
        sizes = Counter(round(m[0] * 2) / 2 for m in span)
        size = sizes.most_common(1)[0][0] if sizes else None
        bold = bool(span) and sum(1 for m in span if m[1]) >= 0.8 * len(span)
        out.append(Line(text, size, bold))
    return out


# ------------------------------------------------------------------ PDF reading


_BOLD_RE = re.compile(r"bold|black|heavy|semibold|demi", re.I)


def _font_name(fd: Any) -> str:
    try:
        return str(fd.get("/BaseFont", "")) if fd else ""
    except Exception:
        return ""


def _page_images(page: Any) -> int:
    try:
        res = page.get("/Resources")
        res = res.get_object() if res is not None else None
        xo = res.get("/XObject") if res is not None else None
        if xo is None:
            return 0
        xo = xo.get_object()
        n = 0
        for v in xo.values():
            obj = v.get_object()
            if obj.get("/Subtype") == "/Image":
                n += 1
            elif obj.get("/Subtype") == "/Form":
                inner = obj.get("/Resources")
                inner = inner.get_object().get("/XObject") if inner is not None else None
                if inner is not None:
                    n += sum(1 for w in inner.get_object().values()
                             if w.get_object().get("/Subtype") == "/Image")
        return n
    except Exception:
        return 0


def read_pdf(body: bytes) -> tuple[list[list[Line]], list[int], str]:
    """Per page: Lines with fonts; per page image count; the raw (unnormalised)
    text for the suspicious-characters measurement."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    pages: list[list[Line]] = []
    images: list[int] = []
    raw_all: list[str] = []
    for page in reader.pages:
        frags: list[tuple[str, float, bool]] = []

        def visit(text, cm, tm, fd, fs, frags=frags):
            if not text or not text.strip():
                return
            c = tm[2] * cm[0] + tm[3] * cm[2]
            d = tm[2] * cm[1] + tm[3] * cm[3]
            scale = (c * c + d * d) ** 0.5 or 1.0
            frags.append((text, float(fs or 0) * scale, bool(_BOLD_RE.search(_font_name(fd)))))

        try:
            raw = page.extract_text(visitor_text=visit) or ""
        except Exception as e:  # pypdf raises a zoo of errors on odd PDFs
            log.debug("pdf page text failed: %s", e)
            raw, frags = "", []
        raw_all.append(raw)
        lines = [normalize(x) for x in raw.split("\n")]
        pages.append(attach_fonts(lines, frags))
        images.append(_page_images(page))
    return pages, images, "\n".join(raw_all)


# ------------------------------------------------------------------ PDF cleaning


def _edge_idx(lines: list[Line], n: int = 4) -> list[int]:
    idx = [i for i, ln in enumerate(lines) if ln.text]
    return sorted(set(idx[:n] + idx[-n:]))


def strip_page_numbers(lines: list[Line]) -> list[Line]:
    edge = set(_edge_idx(lines))
    return [ln for i, ln in enumerate(lines) if not (i in edge and _PAGE_NO_RE.match(ln.text))]


def strip_running(pages: list[list[Line]]) -> list[list[Line]]:
    """Running headers/footers (> 50 % of pages) out; running section labels
    kept once per run of consecutive pages, as a heading at the page top."""
    n_text = sum(1 for p in pages if any(ln.text for ln in p))
    edge_keys: list[dict[str, list[int]]] = []
    for p in pages:
        d: dict[str, list[int]] = {}
        for i in _edge_idx(p):
            k = line_key(p[i].text)
            if sum(c.isalpha() for c in k) >= 3:
                d.setdefault(k, []).append(i)
        edge_keys.append(d)
    on_pages = Counter(k for d in edge_keys for k in d)
    running = {k for k, c in on_pages.items() if n_text >= 3 and c > n_text / 2}

    # labels: same text + same size at the edge on ≥ 3 pages, ≥ 2 of them consecutive
    lab_pages: dict[tuple[str, float | None], list[int]] = {}
    for pi, (p, d) in enumerate(zip(pages, edge_keys)):
        for k, idxs in d.items():
            if k in running or len(k.split()) > 8:
                continue
            for size in {p[i].size for i in idxs}:
                lab_pages.setdefault((k, size), []).append(pi)
    labels: dict[tuple[str, float | None], set[int]] = {}
    for key, pis in lab_pages.items():
        pis = sorted(set(pis))
        if len(pis) < 3 or not any(b - a == 1 for a, b in zip(pis, pis[1:])):
            continue
        firsts = {pi for j, pi in enumerate(pis) if j == 0 or pis[j - 1] < pi - 2}  # 1-page gaps
        labels[key] = firsts

    out: list[list[Line]] = []
    for pi, (p, d) in enumerate(zip(pages, edge_keys)):
        edge = {i for idxs in d.values() for i in idxs}
        top: list[Line] = []
        keep: list[Line] = []
        for i, ln in enumerate(p):
            if i in edge:
                k = line_key(ln.text)
                if k in running:
                    continue
                lab = labels.get((k, ln.size))
                if lab is not None:
                    if pi in lab:
                        ln.head = ln.label = True
                        top.append(ln)
                    continue
            keep.append(ln)
        out.append(top + keep)
    return out


def is_toc_page(lines: list[Line]) -> bool:
    texts = [ln.text for ln in lines if ln.text]
    if len(texts) < 5:
        return False
    hits = sum(1 for t in texts if _TOC_LINE_RE.match(t) and not t.rstrip().endswith("."))
    return hits / len(texts) >= 0.6


def join_drop_caps(lines: list[Line], body: float | None) -> list[Line]:
    """A lone big capital followed by a lowercase line is a drop cap
    ("Z" + "a nas je ...") → glue it to that line."""
    out: list[Line] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if (len(ln.text) == 1 and ln.text.isupper() and body and ln.size and ln.size > body * 1.5):
            j = next((k for k in range(i + 1, len(lines)) if lines[k].text), None)
            if j is not None and lines[j].text[:1].islower():
                lines[j].text = ln.text + lines[j].text
                i += 1
                continue
        out.append(ln)
        i += 1
    return out


def body_size(pages: list[list[Line]]) -> float | None:
    c: Counter = Counter()
    for p in pages:
        for ln in p:
            if ln.size and ln.text:
                c[ln.size] += len(ln.text)
    return c.most_common(1)[0][0] if c else None


def classify_headings(pages: list[list[Line]], body: float | None,
                      typical: float = 0.0) -> tuple[int, str]:
    """Mark heading lines in place (font heuristic, else ALL-CAPS fallback).
    Returns (heading blocks found, "font" | "fallback").

    Font candidates are lines ≥ 1.15 × body size ("big") or wholly bold lines
    of body size. Consecutive candidates of the same kind and size form a
    block; a block is a heading when it is short (≤ 20 words, ≤ 4 lines),
    does not end like a sentence and is not a table-of-contents entry. A bold
    block must also stand on its own (≤ 12 words, the line before ends a
    sentence, the line after does not continue in lowercase), which keeps
    bold emphasis inside paragraphs out. A big block that interrupts a
    sentence (line before has no sentence end, line after starts lowercase)
    is a floating sidebar title: it becomes a heading after that paragraph.
    """

    def big(ln: Line) -> bool:
        return bool(ln.text) and ln.size is not None and body is not None and (
            ln.size >= body * 1.15 and ln.size - body >= 1.0)

    def bold(ln: Line) -> bool:
        return (bool(ln.text) and ln.bold and ln.size is not None and body is not None
                and ln.size >= body * 0.95 and not big(ln) and len(ln.text.split()) <= 12)

    def toc_like(block_lines: list[Line]) -> bool:
        hits = sum(1 for x in block_lines
                   if _TOC_LINE_RE.match(x.text) or re.match(r"^\d{1,3}\s*[-–]\s", x.text))
        return hits * 2 >= len(block_lines)

    def neighbours(p: list[Line], i: int, j: int) -> tuple[Line | None, Line | None]:
        prev = next((p[k] for k in range(i - 1, -1, -1) if p[k].text), None)
        nxt = next((p[k] for k in range(j, len(p)) if p[k].text), None)
        return prev, nxt

    def ends_sentence(ln: Line | None) -> bool:
        return ln is None or ln.head or ln.text.rstrip().endswith(_END_SENTENCE)

    def starts_lower(ln: Line | None) -> bool:
        return ln is not None and not ln.head and ln.text[:1].islower()

    def mark(cand, kind: str) -> int:
        found = 0
        for p in pages:
            i = 0
            while i < len(p):
                ln = p[i]
                if ln.label or ln.head or not cand(ln):
                    i += 1
                    continue
                j = i + 1
                while j < len(p) and not p[j].label and cand(p[j]) and (
                        ln.size is None or p[j].size is None or abs(p[j].size - ln.size) <= 0.6):
                    j += 1
                blk = p[i:j]
                text = " ".join(x.text for x in blk)
                ok = (words(text) <= 20 and j - i <= 4 and sum(c.isalpha() for c in text) >= 3
                      and not text.rstrip().endswith(_HEAD_BAD_END)
                      and not _PAGE_NO_RE.match(text) and not toc_like(blk))
                prev, nxt = neighbours(p, i, j)
                floating = False
                if ok and kind == "bold":
                    ok = (words(text) <= 12 and ends_sentence(prev) and not starts_lower(nxt)
                          and (not typical or len(blk[-1].text) < 0.85 * typical))
                elif ok and kind == "big":
                    floating = not ends_sentence(prev) and starts_lower(nxt)
                if ok:
                    for x in blk:
                        x.head = True
                        x.floating = floating
                    found += 1
                i = j
        return found

    n = mark(big, "big") + mark(bold, "bold")
    if n:
        return n, "font"
    n = mark(lambda ln: bool(ln.text) and (is_caps_heading(ln.text) or is_numbered_heading(ln.text)),
             "fallback")
    return n, "fallback"


# ------------------------------------------------------------------ paragraphs


def dehyphen_join(a: str, b: str, vocab: set[str], hyph: set[str]) -> tuple[str, bool]:
    """Join line `a` with following line `b`. Returns (joined, was_dehyphenated)."""
    b = b.lstrip()
    if a.endswith("­"):
        return a[:-1] + b, True
    m = re.search(r"(\w+)(\s?)-$", a)
    n = re.match(r"(\w+)", b)
    if m and n and b[:1].islower():
        left, space, right = m.group(1), m.group(2), n.group(1)
        joined = (left + right).lower()
        if not space:
            if f"{left}-{right}".lower() in hyph and joined not in vocab:
                return a + b, False                     # real compound: keep "-"
            return a[:-1] + b, True
        if joined in vocab:
            return a[: m.start(2)] + b, True            # "neovi -" + "snog"
        return a + " " + b, False
    return a.rstrip() + " " + b, False


def doc_vocab(pages: list[list[Line]]) -> tuple[set[str], set[str]]:
    """Words of the document (not at a line end) and hyphenated compounds
    seen inside a line: the evidence dehyphen_join() relies on."""
    vocab: set[str] = set()
    hyph: set[str] = set()
    for p in pages:
        for ln in p:
            t = re.sub(r"\w+\s?-$", "", ln.text).lower()
            vocab.update(WORD_RE.findall(t))
            hyph.update(re.findall(r"\w+-\w+", t))
    return vocab, hyph


def _p75(values: list[int]) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    return float(v[int(0.75 * (len(v) - 1))])


def build_blocks(lines: list[Line], typical: float, vocab: set[str], hyph: set[str]) -> list[dict]:
    """Blocks of one page: headings and paragraphs, in order."""
    blocks: list[dict] = []
    para: str | None = None
    pending: list[str] = []     # floating headings, emitted when the paragraph ends

    def flush():
        nonlocal para
        if para is not None and para.strip():
            blocks.append({"t": "p", "text": re.sub(r"[ \t]+", " ", para).strip()})
        para = None
        for h in pending:
            blocks.append({"t": "h", "text": h})
        pending.clear()

    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.text:
            flush()
            i += 1
            continue
        if ln.head:
            j = i + 1
            head = ln.text
            while (j < len(lines) and lines[j].head and lines[j].label == ln.label
                   and lines[j].size == ln.size and lines[j].floating == ln.floating):
                head, _ = dehyphen_join(head, lines[j].text, vocab, hyph)
                j += 1
            head = re.sub(r"\s+", " ", head).strip()
            if ln.floating and para is not None:
                pending.append(head)
            else:
                flush()
                blocks.append({"t": "h", "text": head})
            i = j
            continue
        t = ln.text
        if para is not None and _BULLET_RE.match(t):
            flush()
        if para is None:
            para = t
        else:
            para, _ = dehyphen_join(para, t, vocab, hyph)
        if t.endswith(_END_SENTENCE) and typical and len(t) < 0.8 * typical:
            flush()
        i += 1
    flush()
    return blocks


def link_pages(pages: list[dict], vocab: set[str], hyph: set[str]) -> None:
    """Mark a page's first paragraph as continuing the previous page's last
    one (no sentence end before the break, lowercase start after it)."""
    prev: dict | None = None
    for pg in pages:
        if pg["toc"]:
            prev = None
            continue
        bl = pg["blocks"]
        if prev is not None and bl and bl[0]["t"] == "p":
            a, b = prev["text"], bl[0]["text"]
            if not a.endswith(_END_SENTENCE) and b[:1].islower():
                joined, dehy = dehyphen_join(a, b, vocab, hyph)
                if dehy:
                    # keep the hyphen-less left part on the previous page
                    prev["text"] = a[:-1].rstrip() if a.endswith(("-", "­")) else a
                    if prev["text"].endswith(" -"):
                        prev["text"] = prev["text"][:-2]
                    bl[0]["cont"] = "nospace"
                else:
                    bl[0]["cont"] = "space"
        if bl:  # an empty (design) page between two text pages keeps prev
            prev = bl[-1] if bl[-1]["t"] == "p" else None


def page_record(n: int, blocks: list[dict], toc: bool, images: int) -> dict:
    text = "\n\n".join(b["text"] for b in blocks)
    w = words(text)
    return {
        "page": n,
        "text": text,
        "headings": [b["text"] for b in blocks if b["t"] == "h"],
        "words": w,
        "blocks": blocks,
        "toc": toc,
        "empty": w < EMPTY_PAGE_WORDS,
        "images": images,
        "needs_ocr": w < EMPTY_PAGE_WORDS and images > 0,
    }


def extract_pdf(body: bytes) -> tuple[list[dict], dict]:
    raw_pages, images, raw_text = read_pdf(body)
    pages = [strip_page_numbers(p) for p in raw_pages]
    pages = strip_running(pages)
    toc = [is_toc_page(p) for p in pages]
    content = [p if not t else [] for p, t in zip(pages, toc)]
    body_pt = body_size(content)
    content = [join_drop_caps(p, body_pt) for p in content]
    typical = _p75([len(ln.text) for p in content for ln in p if ln.text and not ln.label])
    n_heads, method = classify_headings(content, body_pt, typical)
    vocab, hyph = doc_vocab(content)
    out = []
    for n, (p, c, t, im) in enumerate(zip(pages, content, toc, images), start=1):
        blocks = [] if t else build_blocks(c, typical, vocab, hyph)
        if t:
            rec = page_record(n, [], True, im)
            rec["text"] = "\n".join(ln.text for ln in p if ln.text)
            rec["words"] = words(rec["text"])
            rec["empty"] = rec["words"] < EMPTY_PAGE_WORDS
            rec["needs_ocr"] = rec["empty"] and im > 0
            out.append(rec)
        else:
            out.append(page_record(n, blocks, False, im))
    link_pages(out, vocab, hyph)
    for rec in out:  # cross-page dehyphenation may have trimmed a block
        if not rec["toc"]:
            rec["text"] = "\n\n".join(b["text"] for b in rec["blocks"])
    info = {"body_pt": body_pt, "heading_blocks": n_heads, "raw_text": raw_text,
            "heading_method": method}
    return out, info


# ------------------------------------------------------------------ HTML

_H_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "section", "article", "main", "blockquote",
               "tr", "table", "dd", "dt", "figcaption", "pre", "header", "footer", "aside"}
# sentinels (private-use code points: lxml refuses control characters);
# normalize() runs only after they have been parsed out
_H_OPEN, _H_CLOSE, _WEAK = "\ue0f1", "\ue0f2", "\ue0f3"


# site chrome that survives the main-content selection (footers, share
# buttons, download links); dropped line by line, measured in "boilerplate"
_BOILERPLATE_RE = re.compile(
    r"^(?:facebook|instagram|tiktok|twitter|x|youtube|linkedin|read more|pročitaj više|"
    r"saznaj više|preuzmi(?: dokument| pdf)?|podijeli.*|share.*|.*©.*|.*sva prava pridržana.*|"
    r"oib:?\s*\d+|\S+@\S+\.\w+|https?://\S+|www\.\S+)$", re.I)


def is_boilerplate(line: str) -> bool:
    return bool(_BOILERPLATE_RE.match(line.strip()))


def extract_html(body: bytes) -> tuple[list[dict], dict]:
    root, _title = P.html_main(body)
    if root is None:
        return [page_record(1, [], False, 0)], {"raw_text": "", "heading_blocks": 0,
                                                "heading_method": "html", "body_pt": None}
    raw_text = root.text_content()
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.lower()
        if tag in _H_TAGS:
            el.text = "\n" + _H_OPEN + (el.text or "")
            el.tail = _H_CLOSE + "\n" + (el.tail or "")
        elif tag == "br":
            el.tail = "\n" + (el.tail or "")
        elif tag in _BLOCK_TAGS:
            if tag == "p" and _all_bold(el):
                el.text = "\n" + _WEAK + (el.text or "")
            elif tag == "li":
                el.text = "\n• " + (el.text or "")
            else:
                el.text = "\n" + (el.text or "")
            el.tail = "\n" + (el.tail or "")
    text = root.text_content()
    blocks: list[dict] = []
    for part in re.split(f"({_H_OPEN}.*?{_H_CLOSE})", text, flags=re.S):
        if part.startswith(_H_OPEN):
            h = normalize(re.sub(r"\s+", " ", part.strip(_H_OPEN + _H_CLOSE + _WEAK).replace(_WEAK, ""))).strip()
            if h and any(c.isalpha() for c in h):
                blocks.append({"t": "h", "text": h})
            continue
        for line in part.split("\n"):
            weak = _WEAK in line
            line = normalize(re.sub(r"\s+", " ", line.replace(_WEAK, ""))).strip()
            if not line or line == "•" or is_boilerplate(line.lstrip("• ")):
                continue
            if (weak and words(line) <= 12 and not line.endswith(_HEAD_BAD_END)) or (
                    is_caps_heading(line) and words(line) <= 8):
                blocks.append({"t": "h", "text": line})
            else:
                blocks.append({"t": "p", "text": line})
    rec = page_record(1, blocks, False, 0)
    return [rec], {"raw_text": raw_text, "heading_blocks": len(rec["headings"]),
                   "heading_method": "html", "body_pt": None}


def _all_bold(p_el) -> bool:
    txt = re.sub(r"\s+", "", p_el.text_content())
    if not txt:
        return False
    bold = "".join(re.sub(r"\s+", "", b.text_content())
                   for b in p_el.xpath("./strong|./b|./span/strong|./span/b"))
    return bold == txt


# ------------------------------------------------------------------ documents

RAW_DIR = P.RAW_DIR


def find_raw(doc: dict, raw_dir: Path = RAW_DIR) -> Path | None:
    hits = sorted(p for p in raw_dir.glob(f"*/{doc['doc_id']}.{doc['format']}")
                  if not p.parent.name.startswith("_"))
    return hits[0] if hits else None


def pages_path(raw: Path) -> Path:
    return raw.with_suffix(".pages.json")


DOC_FIELDS = ("doc_id", "format", "party_ids", "list_id", "manjine_id", "vrsta", "izvor",
              "naslov", "url", "wayback_url", "datum", "rijeci", "stranica")


def extract_document(doc: dict, body: bytes, slug: str) -> dict:
    if doc["format"] == "pdf":
        pages, info = extract_pdf(body)
    else:
        pages, info = extract_html(body)
    clean = "\n".join(p["text"] for p in pages if not p["toc"])
    share, low = diacritics_share(clean)
    out = {k: doc.get(k) for k in DOC_FIELDS}
    out.update({
        "slug": slug,
        "sha256": hashlib.sha256(body).hexdigest(),
        "extractor_version": EXTRACTOR_VERSION,
        "pages": pages,
        "quality": {
            "pages": len(pages),
            "toc_pages": [p["page"] for p in pages if p["toc"]],
            "empty_pages": [p["page"] for p in pages if p["empty"]],
            "needs_ocr_pages": [p["page"] for p in pages if p["needs_ocr"]],
            "words": sum(p["words"] for p in pages if not p["toc"]),
            "words_raw": words(info["raw_text"]),
            "headings": sum(len(p["headings"]) for p in pages),
            "heading_method": info["heading_method"],
            "body_pt": info["body_pt"],
            "diacritics_share": round(share, 4),
            "lowercase_words": low,
            "diacritics_suspicious": low > 50 and share < 0.03,
            "suspicious_raw": suspicious_counts(info["raw_text"]),
            "suspicious_clean": suspicious_counts(clean),
        },
    })
    return out


def dump(obj: Any) -> str:
    return P.dump(obj)


def extract_all(docs: list[dict], force: bool = False, raw_dir: Path = RAW_DIR) -> tuple[list[dict], dict]:
    """Extract every document (skipping unchanged ones). Returns (extracted
    documents, counters)."""
    out: list[dict] = []
    stats = {"extracted": 0, "skipped": 0, "missing": []}
    for doc in docs:
        raw = find_raw(doc, raw_dir)
        if raw is None:
            stats["missing"].append(doc["doc_id"])
            log.warning("raw file missing for %s", doc["doc_id"])
            continue
        body = raw.read_bytes()
        sha = hashlib.sha256(body).hexdigest()
        pj = pages_path(raw)
        if pj.exists() and not force:
            try:
                old = json.loads(pj.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                old = None
            if old and old.get("sha256") == sha and old.get("extractor_version") == EXTRACTOR_VERSION:
                # metadata may have changed in programi.json without the file changing
                old.update({k: doc.get(k) for k in DOC_FIELDS})
                out.append(old)
                stats["skipped"] += 1
                continue
        rec = extract_document(doc, body, raw.parent.name)
        pj.write_text(dump(rec), encoding="utf-8")
        out.append(rec)
        stats["extracted"] += 1
    return out, stats
