"""Programme text extraction and chunking (src/kompas/extract.py, chunk.py).

Offline: text post-processing is tested on synthetic lines, PDF extraction on
the committed tests/fixtures/kompas/programme.pdf (made by
make_programme_pdf.py), HTML on programme.html, chunking on synthetic
documents. The real data/kompas/programi.json and chunks_stats.json are read
from the repo; no raw programme is needed.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from src.kompas import chunk as C
from src.kompas import extract as E
from src.kompas.extract import Line

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "kompas"
PROGRAMI = json.loads((ROOT / "data/kompas/programi.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ normalisation


def test_normalize_repairs_pypdf_diacritics_and_ligatures():
    assert E.normalize("čak") == "čak"                 # combining caron → NFC
    assert E.normalize("Kc ˇ") == "Kč"                       # spacing caron
    assert E.normalize("sˇuma zˇaba") == "šuma žaba"
    assert E.normalize("c´up") == "ćup"                      # spacing acute
    assert E.normalize("ﬁnancije ﬂota") == "financije flota"
    assert E.normalize(" stavka") == "• stavka"         # private-use bullet
    assert E.normalize("a b​c") == "a bc"
    assert E.normalize("Čakovec, đak, šuma, žaba, ćup") == "Čakovec, đak, šuma, žaba, ćup"


def test_suspicious_counts():
    got = E.suspicious_counts("č ﬁ � c ˇ ")
    assert got == {"combining_caron": 1, "ligature": 1, "replacement_char": 1,
                   "spacing_caron": 1, "private_use": 1}
    assert E.suspicious_counts(E.normalize("č ﬁ c ˇ")) == {}


def test_diacritics_share():
    share, low = E.diacritics_share("Čakovec je grad gdje đak i žaba žive u šumi")
    assert low == 9 and share == pytest.approx(4 / 9)   # đak, žaba, žive, šumi
    assert E.diacritics_share("")[0] == 0.0


# ------------------------------------------------------------------ dehyphenation


def test_dehyphen_join():
    vocab, hyph = {"neovisnog", "zdravstvenu"}, {"socijalno-liberalni"}
    assert E.dehyphen_join("politika zdrav-", "stvenu skrb", vocab, hyph) == ("politika zdravstvenu skrb", True)
    # unknown word: still joined (the common case: a word split at the line end)
    assert E.dehyphen_join("duo-", "pol vlasti", vocab, hyph)[0] == "duopol vlasti"
    # a compound seen elsewhere with its hyphen keeps it
    assert E.dehyphen_join("socijalno-", "liberalni program", vocab, hyph)[0] == "socijalno-liberalni program"
    # pypdf's "neovi -" spacing: joined only when the word exists in the document
    assert E.dehyphen_join("medija neovi -", "snog prostora", vocab, hyph)[0] == "medija neovisnog prostora"
    assert E.dehyphen_join("eufemizmu -", "regija", vocab, hyph)[0] == "eufemizmu - regija"
    # uppercase continuation is a dash/list, not hyphenation
    assert E.dehyphen_join("Hrvatska -", "Europa", vocab, hyph)[0] == "Hrvatska - Europa"
    assert E.dehyphen_join("kraj rečenice.", "Nova", vocab, hyph) == ("kraj rečenice. Nova", False)
    assert E.dehyphen_join("soft­", "hyphen", vocab, hyph) == ("softhyphen", True)


# ------------------------------------------------------------------ page cleaning


def L(text: str, size: float | None = 10.0, bold: bool = False) -> Line:
    return Line(text, size, bold)


def test_strip_page_numbers_only_at_edges():
    page = [L("12"), L("Naslov"), L("tekst " * 5), L("2024"), L("tekst"), L("još"), L("teksta"),
            L("i još"), L("kraj"), L("- 13 -")]
    out = [ln.text for ln in E.strip_page_numbers(page)]
    assert "12" not in out and "- 13 -" not in out
    assert "2024" in out          # 4 digits: a year, not a page number


def _body(n: int) -> list[Line]:
    return [L(f"Rečenica broj {i} u tijelu stranice ima dovoljno riječi.") for i in range(n)]


def test_running_header_dropped_and_section_label_kept_once():
    pages = []
    for i in range(10):
        p = [L("Program stranke 2024.", 7)] + _body(6)
        if 1 <= i <= 4:   # SDP style: chapter label at the foot of every page of the chapter
            p.append(L("GOSPODARSTVO", 20))
        pages.append(p)
    out = E.strip_running(pages)
    assert all("Program stranke 2024." not in [ln.text for ln in p] for p in out)
    labels = [(pi, ln.text) for pi, p in enumerate(out) for ln in p if ln.label]
    assert labels == [(1, "GOSPODARSTVO")]
    assert out[1][0].text == "GOSPODARSTVO" and out[1][0].head    # moved to the page top


def test_toc_page():
    toc = [L("SADRŽAJ")] + [L(f"Poglavlje {i} {i * 3}") for i in range(1, 9)]
    assert E.is_toc_page(toc)
    assert not E.is_toc_page(_body(9))


def test_headings_by_font_size_and_filters():
    page = [
        L("ZDRAVSTVO", 18),
        L("Prva rečenica tijela teksta koja je dovoljno duga za redak.", 10),
        L("Bolnice moraju biti bliže građanima, a liječnici", 10),
        L("plaćeni bolje nego danas.", 10),
        L("Ovo je istaknuti citat koji se proteže preko", 16),     # pull quote: ends with "."
        L("dva retka i završava točkom.", 16),
        L("Tekst se nastavlja u", 10),
        L("Okvir", 16),                                             # floating sidebar title
        L("drugom retku iste rečenice.", 10),
    ]
    n, method = E.classify_headings([page], 10.0, 60)
    assert method == "font" and n == 2
    assert [ln.text for ln in page if ln.head] == ["ZDRAVSTVO", "Okvir"]
    assert page[7].floating
    blocks = E.build_blocks(page, 60, set(), set())
    assert blocks[0] == {"t": "h", "text": "ZDRAVSTVO"}
    # the floating title comes after the paragraph it interrupted
    texts = [b["text"] for b in blocks]
    assert texts.index("Okvir") == len(texts) - 1
    assert "Tekst se nastavlja u drugom retku iste rečenice." in texts[-2]


def test_bold_emphasis_inside_paragraph_is_not_a_heading():
    page = [
        L("Uvod u poglavlje završava ovdje.", 10),
        L("Vode", 10, bold=True),                                   # standalone bold line
        L("Rijeke i jezera dragocjen su resurs koji treba štititi od", 10),
        L("onečišćenja i isušivanja u", 10),
        L("urbanističkih strategija i primjenom", 10, bold=True),  # emphasis mid-sentence
        L("rješenja temeljenih na prirodi.", 10),
    ]
    E.classify_headings([page], 10.0, 60)
    assert [ln.text for ln in page if ln.head] == ["Vode"]


def test_heading_fallback_caps_and_numbered_without_fonts():
    page = [L("O LIBERALIZMU", None), L("Stranka se zalaže za slobodu.", None),
            L("3.2. Zdravstvena skrb", None), L("Bolnice su važne.", None),
            L("1. Smanjiti porez na dohodak.", None)]
    n, method = E.classify_headings([page], None)
    assert method == "fallback"
    assert [ln.text for ln in page if ln.head] == ["O LIBERALIZMU", "3.2. Zdravstvena skrb"]


def test_drop_cap_glued_back():
    page = [L("Solidarnost", 24), L("Z", 30), L("a Most pravednost znači jednakost.", 11)]
    out = E.join_drop_caps(page, 11.0)
    assert [ln.text for ln in out] == ["Solidarnost", "Za Most pravednost znači jednakost."]


def test_paragraph_breaks_and_bullets():
    lines = [L("Prvi odlomak ima dugačak redak koji ide do kraja stupca teksta"),
             L("i završava kratko."),
             L("Drugi odlomak počinje velikim slovom i ide do kraja stupca"),
             L("teksta bez prekida."),
             L("• prva stavka"),
             L("• druga stavka")]
    blocks = E.build_blocks(lines, 62, set(), set())
    assert [b["text"] for b in blocks] == [
        "Prvi odlomak ima dugačak redak koji ide do kraja stupca teksta i završava kratko.",
        "Drugi odlomak počinje velikim slovom i ide do kraja stupca teksta bez prekida.",
        "• prva stavka", "• druga stavka"]


# ------------------------------------------------------------------ fixtures


def test_pdf_fixture_extraction():
    body = (FIX / "programme.pdf").read_bytes()
    doc = {"doc_id": "fixturepdf01", "format": "pdf", "naslov": "Testni program", "rijeci": 60}
    rec = E.extract_document(doc, body, "testna-stranka")
    pages = rec["pages"]
    assert [p["page"] for p in pages] == [1, 2, 3]
    assert pages[0]["headings"] == ["ZDRAVSTVO"]
    assert pages[1]["headings"] == ["1.2. Obrazovanje"]
    text = "\n".join(p["text"] for p in pages)
    assert "Čakovec, đak, šuma, žaba, ćup" in text
    assert "zdravstvenu skrb" in text and "zdrav-" not in text
    assert "Testni program stranke" not in text                # running header
    assert not re.search(r"(?m)^\d$", text)                    # page numbers
    assert pages[2]["blocks"][0]["cont"] == "space"
    q = rec["quality"]
    assert q["heading_method"] == "font" and q["empty_pages"] == [] and q["suspicious_clean"] == {}
    assert q["diacritics_share"] > 0.1 and not q["diacritics_suspicious"]
    assert rec["sha256"] == __import__("hashlib").sha256(body).hexdigest()


def test_html_fixture_extraction():
    body = (FIX / "programme.html").read_bytes()
    pages, info = E.extract_html(body)
    assert len(pages) == 1 and pages[0]["page"] == 1
    p = pages[0]
    assert p["headings"] == ["Program Testne stranke", "Gospodarstvo", "Poljoprivreda", "Zdravstvo"]
    texts = [b["text"] for b in p["blocks"] if b["t"] == "p"]
    assert "• Niži PDV na hranu." in texts
    assert "Hitna pomoć stiže za petnaest minuta." in texts      # <br> splits
    joined = "\n".join(texts)
    assert "Čakovec, đak, šuma, žaba i ćup" in joined
    for gone in ("izbornik", "Naslovnica", "Facebook", "info@", "©"):
        assert gone not in p["text"]


def test_extract_all_is_idempotent(tmp_path):
    slug_dir = tmp_path / "testna-stranka"
    slug_dir.mkdir()
    shutil.copy(FIX / "programme.pdf", slug_dir / "fixturepdf01.pdf")
    doc = {"doc_id": "fixturepdf01", "format": "pdf", "naslov": "Testni program", "party_ids": [1]}
    out1, s1 = E.extract_all([doc], raw_dir=tmp_path)
    pj = slug_dir / "fixturepdf01.pages.json"
    first = pj.read_bytes()
    out2, s2 = E.extract_all([doc], raw_dir=tmp_path)
    assert (s1["extracted"], s2["extracted"], s2["skipped"]) == (1, 0, 1)
    assert pj.read_bytes() == first and out1[0]["pages"] == out2[0]["pages"]
    _, s3 = E.extract_all([doc], force=True, raw_dir=tmp_path)
    assert s3["extracted"] == 1 and pj.read_bytes() == first
    _, s4 = E.extract_all([{**doc, "doc_id": "nemaganigdje"}], raw_dir=tmp_path)
    assert s4["missing"] == ["nemaganigdje"]


# ------------------------------------------------------------------ chunking

SENT = "Rečenica {i} u odlomku {p} govori o temi {s} i zalaže se za bolje javne politike."


def para(s: str, p: int, n_sent: int) -> str:
    return " ".join(SENT.format(i=i, p=p, s=s) for i in range(n_sent))


def make_doc(sections: list[tuple[str, int, int]], doc_id: str = "abcdef012345", **meta) -> dict:
    """sections: (heading, paragraphs, sentences per paragraph), two sections a page."""
    pages = []
    for k, (h, n_par, n_sent) in enumerate(sections):
        blocks = [{"t": "h", "text": h}] + [{"t": "p", "text": para(h, j, n_sent)} for j in range(n_par)]
        if k % 2 == 0:
            pages.append({"page": len(pages) + 1, "toc": False, "blocks": blocks})
        else:
            pages[-1]["blocks"].extend(blocks)
    return {"doc_id": doc_id, "naslov": "Testni program", "party_ids": [7], "list_id": "l1",
            "manjine_id": None, "vrsta": "izborni-2024", "izvor": "web", "url": "https://x.hr/p.pdf",
            "datum": "2024-04-01", "format": "pdf", "pages": pages, **meta}


def test_chunks_sizes_overlap_and_sections():
    doc = make_doc([("Gospodarstvo", 12, 6), ("Zdravstvo", 3, 5), ("Obrazovanje", 20, 4)])
    chunks = C.chunk_document(doc)
    n = len(chunks)
    assert [c["metadata"]["chunk_index"] for c in chunks] == list(range(1, n + 1))
    assert all(c["metadata"]["total_chunks"] == n for c in chunks)
    assert [c["id"] for c in chunks] == [f"prog_abcdef012345_{i:04d}" for i in range(1, n + 1)]
    for c in chunks:
        m = c["metadata"]
        assert m["type"] == "program_section" and m["doc_id"] == "abcdef012345"
        assert c["text"].startswith(m["section"] + "\n\n")
        body = c["text"][len(m["section"]) + 2:]
        # no section crossing: every sentence belongs to the chunk's section
        topics = set(re.findall(r"o temi (\w+)", body))
        assert topics == {m["section"]}, (m["section"], topics)
        assert 80 <= m["words"] <= 700
    big = [c for c in chunks if c["metadata"]["section"] in ("Gospodarstvo", "Obrazovanje")]
    assert all(250 <= c["metadata"]["words"] <= 700 for c in big)
    # overlap: every chunk after the first in a section starts with the previous tail
    for a, b in zip(chunks, chunks[1:]):
        if a["metadata"]["section"] != b["metadata"]["section"]:
            assert b["metadata"]["overlap_words"] == 0
            continue
        ov = b["text"].split("\n\n")[1]
        assert ov.startswith("… ")
        assert a["text"].endswith(ov[2:])
        assert 40 <= b["metadata"]["overlap_words"] <= 80
    # deterministic
    assert C.jsonl(C.chunk_document(doc)) == C.jsonl(chunks)


def test_tiny_sections_merge_forward_and_tail_joins_previous():
    doc = make_doc([("Uvod", 1, 2), ("Ciljevi", 2, 3), ("Mjere", 3, 6), ("Kontakt", 1, 1)])
    chunks = C.chunk_document(doc)
    names = [c["metadata"]["section"] for c in chunks]
    assert names[0] == "Uvod / Ciljevi"            # 34 words < 80 → merged with the next
    assert "Kontakt" not in " ".join(names)        # tiny tail joins "Mjere"
    assert "o temi Kontakt" in chunks[-1]["text"]


def test_generic_headings_keep_parent_and_paths():
    pages = [{"page": 1, "toc": False, "blocks": []}]
    for ch in ("Zdravstvo", "Obrazovanje", "Promet"):
        pages[0]["blocks"] += [{"t": "h", "text": "STUP"}, {"t": "h", "text": ch},
                               {"t": "p", "text": para(ch, 0, 8)}]
        for g in ("CILJEVI", "MJERE"):
            pages[0]["blocks"] += [{"t": "h", "text": g}, {"t": "p", "text": para(ch, 1, 8)}]
    doc = make_doc([])
    doc["pages"] = pages
    names = [s.name for s in C.build_sections(doc)]
    # STUP repeats but is always a parent, so it is not generic; CILJEVI/MJERE are
    # leaf headings used 3×, so they keep (up to two) non-generic ancestors
    assert names[:3] == ["STUP › Zdravstvo", "STUP › Zdravstvo › CILJEVI", "STUP › Zdravstvo › MJERE"]
    assert names[-3:] == ["STUP › Promet", "STUP › Promet › CILJEVI", "STUP › Promet › MJERE"]


def test_giant_paragraph_split_on_sentences():
    text = para("Velika", 0, 120)                       # ~1900 words, one paragraph
    pieces = C.split_paragraph(text)
    assert len(pieces) > 1 and all(E.words(p) <= C.PARA_SPLIT for p in pieces)
    assert all(p.endswith(".") for p in pieces)
    assert " ".join(pieces) == text
    doc = make_doc([])
    doc["pages"] = [{"page": 1, "toc": False, "blocks": [{"t": "h", "text": "Velika"},
                                                          {"t": "p", "text": text}]}]
    chunks = C.chunk_document(doc)
    assert len(chunks) >= 3 and all(c["metadata"]["words"] <= 700 for c in chunks)


def test_cross_page_paragraph_and_page_range():
    doc = make_doc([])
    doc["pages"] = [
        {"page": 1, "toc": False, "blocks": [{"t": "h", "text": "Naslov"},
                                             {"t": "p", "text": para("Naslov", 0, 6) + " nasta"}]},
        {"page": 2, "toc": True, "blocks": []},
        {"page": 3, "toc": False, "blocks": [{"t": "p", "text": "vak odlomka.", "cont": "nospace"}]},
    ]
    (c,) = C.chunk_document(doc)
    assert "nastavak odlomka." in c["text"]
    assert (c["metadata"]["page_from"], c["metadata"]["page_to"]) == (1, 3)


# ------------------------------------------------------------------ uncertain sources


def test_nesigurni_constant_matches_programi():
    docs = {d["doc_id"]: d for d in PROGRAMI["dokumenti"]}
    assert set(C.NESIGURNI) <= set(docs)
    wayback = {i for i, d in docs.items() if d["izvor"] == "wayback"}
    assert wayback <= set(C.NESIGURNI)
    assert {"1c4d71d9b198", "108476029df2", "74d4a5515dd4"} <= set(C.NESIGURNI)
    assert "grabancijas.com" in docs["74d4a5515dd4"]["url"]
    assert docs["1c4d71d9b198"]["rijeci"] == 444
    assert all(r.strip() for r in C.NESIGURNI.values())


def test_nesiguran_flag_in_chunks():
    sec = [("Program", 2, 5)]
    c_unsure = C.chunk_document(make_doc(sec, doc_id="74d4a5515dd4"))[0]["metadata"]
    c_sure = C.chunk_document(make_doc(sec, doc_id="492e03c11720"))[0]["metadata"]
    assert c_unsure["nesiguran"] is True and "grabancijas" in c_unsure["nesiguran_razlog"]
    assert c_sure["nesiguran"] is False and c_sure["nesiguran_razlog"] is None


# ------------------------------------------------------------------ stats


def test_stats_have_no_text():
    doc = make_doc([("Gospodarstvo", 6, 6)])
    doc["quality"] = {"pages": 1, "toc_pages": [], "empty_pages": [], "needs_ocr_pages": [],
                      "words": 999, "headings": 1, "heading_method": "font",
                      "diacritics_share": 0.18, "diacritics_suspicious": False,
                      "suspicious_raw": {}, "suspicious_clean": {}}
    doc["slug"] = "testna"
    chunks = C.chunk_document(doc)
    body = C.jsonl(chunks).encode()
    stats = C.build_stats([doc], {doc["doc_id"]: chunks}, {"dokumenti": [], "stranke": []}, body)
    s = json.dumps(stats, ensure_ascii=False)
    assert "Rečenica" not in s and "Gospodarstvo" not in s
    assert stats["totals"]["chunks"] == len(chunks)
    assert stats["stranke"]["7"]["chunks"] == len(chunks)


def test_committed_stats_cover_programi():
    stats = json.loads((ROOT / "data/kompas/chunks_stats.json").read_text(encoding="utf-8"))
    assert {d["doc_id"] for d in stats["dokumenti"]} == {d["doc_id"] for d in PROGRAMI["dokumenti"]}
    assert stats["chunks_path"] == "data/raw/kompas/chunks.jsonl"
    assert stats["totals"]["chunks"] > 0 and all(d["chunks"] > 0 for d in stats["dokumenti"])
    assert stats["totals"]["diacritics_suspicious_docs"] == []
