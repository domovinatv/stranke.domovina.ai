"""Party programmes (src/kompas/programi.py, scripts/23_fetch_programi.py).

Offline: PDFs are generated in memory with pypdf; the real data/kompas/
programi.json and liste_2024.json are read from the repo, nothing is fetched.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from src.kompas import programi as P

ROOT = Path(__file__).resolve().parent.parent
LISTE = json.loads((ROOT / "data/kompas/liste_2024.json").read_text(encoding="utf-8"))
PROGRAMI = json.loads((ROOT / "data/kompas/programi.json").read_text(encoding="utf-8"))
IZVORI = json.loads((ROOT / "data/kompas/programi_izvori.json").read_text(encoding="utf-8"))


def make_pdf(pages: list[str]) -> bytes:
    """A PDF with one Helvetica text line per page ('' = page without text)."""
    w = PdfWriter()
    font = w._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    for text in pages:
        page = w.add_blank_page(595, 842)
        if not text:
            continue
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        s = DecodedStreamObject()
        s.set_data(f"BT /F1 10 Tf 40 800 Td ({text}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = w._add_object(s)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ format detection

TEXT = ("Izborni program za parlamentarne izbore 2024 donosi ciljeve za gospodarstvo, "
        "zdravstvo, obrazovanje i pravosudje u razdoblju 2024 do 2028 godine.")


def test_pdf_with_text_is_pdf():
    a = P.analyse(make_pdf([TEXT, TEXT]))
    assert a.format == "pdf" and a.ext == "pdf"
    assert a.stranica == 2
    assert a.rijeci >= 40
    assert "program" in a.tekst.lower()


def test_pdf_without_text_is_skeniran():
    a = P.analyse(make_pdf(["", "", ""]))
    assert a.format == "skeniran" and a.ext == "pdf"
    assert a.stranica == 3
    assert a.rijeci == 0


def test_pdf_with_little_text_is_skeniran():
    # 3 pages, one short caption: < 50 extractable chars per page on average.
    a = P.analyse(make_pdf(["Naslovnica", "", ""]))
    assert a.format == "skeniran"


def test_html_is_html_without_boilerplate():
    body = ("<html><head><title>Program</title><script>var x=1;</script></head><body>"
            "<nav>Izbornik Naslovnica Kontakt</nav><main><h1>Program stranke</h1>"
            "<p>Načela i ciljevi.</p></main><footer>© 2024</footer></body></html>").encode()
    a = P.analyse(body)
    assert a.format == "html" and a.stranica is None
    assert a.naslov == "Program"
    assert "Izbornik" not in a.tekst and "var x" not in a.tekst
    assert a.rijeci == 5


def test_check_programme_flags_wrong_year_and_local_elections():
    assert P.check_programme("Program " + TEXT * 3, "izborni-2024") == []
    w = P.check_programme("Program za lokalne izbore 2025. " + "riječ " * 100, "izborni-2024")
    assert "spominje lokalne izbore 2025" in w
    assert "ne spominje 2024 ni 2028" in w
    assert P.check_programme("Programska deklaracija " + "riječ " * 100, "trajni") == []


def test_wayback_helpers():
    final = "https://web.archive.org/web/20240410123456id_/https://example.hr/program.pdf"
    assert P.wayback_view_url(final) == \
        "https://web.archive.org/web/20240410123456/https://example.hr/program.pdf"
    assert P.wayback_date(final) == "2024-04-10"
    assert P.wayback_view_url("https://example.hr/") is None
    rows = P.parse_cdx(b'[["urlkey","timestamp","original"],["hr,x)/a.pdf","20240101","https://x.hr/a.pdf"]]')
    assert rows == [{"urlkey": "hr,x)/a.pdf", "timestamp": "20240101", "original": "https://x.hr/a.pdf"}]
    assert P.parse_cdx(b"") == [] and P.parse_cdx(b"not json") == []


def test_programme_links():
    html = (b'<a href="/o-nama">O nama</a><a href="/dokumenti/Program-2024.pdf">PDF</a>'
            b'<a href="https://x.hr/deklaracija">Temeljna deklaracija</a><a href="mailto:a@b">m</a>')
    got = P.programme_links(html, "https://x.hr/")
    assert [u for u, _ in got] == ["https://x.hr/dokumenti/Program-2024.pdf", "https://x.hr/deklaracija"]


# ------------------------------------------------------------------ build: coalition sharing

MINI_LISTE = {
    "liste": [{"list_id": "aa-bb-cc", "nositelj": {"slug": "aa", "party_id": 1},
               "clanice": [{"party_id": 1}, {"party_id": 2}, {"party_id": 3}, {"party_id": None}]}],
    "manjine": [{"manjine_id": "manjina-x", "clanice": [{"party_id": None, "naziv": "UDRUGA X ",
                                                         "slug": None}]}],
    "stranke": [{"party_id": 1, "slug": "aa", "list_ids": ["aa-bb-cc"]},
                {"party_id": 2, "slug": "bb", "list_ids": ["aa-bb-cc"]},
                {"party_id": 3, "slug": "cc", "list_ids": ["aa-bb-cc"]},
                {"party_id": 4, "slug": "dd", "list_ids": [], "izvan_lista": True}],
}
PDF_A = make_pdf([TEXT])
PDF_B = make_pdf(["Programska deklaracija stranke BB, temeljna nacela i ciljevi stranke."])


def fake_fetch(calls):
    bodies = {"https://aa.hr/program-2024.pdf": PDF_A, "https://bb.hr/deklaracija.pdf": PDF_B}

    def fetch(src):
        calls.append(src["url"])
        body = bodies.get(src["url"])
        if body is None:
            return None
        return P.Fetched(body, "web", src["url"], None, None, "2026-11-19T10:00:00+00:00")
    return fetch


MINI_IZVORI = {
    "koalicije": {"aa-bb-cc": {"izvori": [{"url": "https://aa.hr/program-2024.pdf",
                                           "naslov": "Program koalicije 2024"}]}},
    "stranke": {"aa": {"provjereno": [{"url": "https://aa.hr/", "napomena": "nema trajnog"}]},
                "bb": {"izvori": [{"vrsta": "trajni", "url": "https://bb.hr/deklaracija.pdf",
                                   "naslov": "Programska deklaracija"}]},
                "cc": {"provjereno": [{"url": "https://cc.hr/", "napomena": "nema programa"}]},
                "dd": {"provjereno": [{"url": "https://dd.hr/"}]}},
    "manjine": {"manjina-x": {"provjereno": [{"url": "https://x.hr/"}]}},
}


def test_coalition_document_shared_by_all_members():
    calls: list[str] = []
    stored: list[tuple] = []
    out = P.build_output(MINI_LISTE, MINI_IZVORI, fake_fetch(calls),
                         store=lambda *a: stored.append(a[:3]))
    assert calls.count("https://aa.hr/program-2024.pdf") == 1  # downloaded once
    koal = [d for d in out["dokumenti"] if d["vrsta"] == "koalicijski"]
    assert len(koal) == 1
    d = koal[0]
    assert d["list_id"] == "aa-bb-cc" and d["party_ids"] == [1, 2, 3]
    assert d["sha256"] == hashlib.sha256(PDF_A).hexdigest() and d["doc_id"] == d["sha256"][:12]
    assert ("aa", d["sha256"], "pdf") in stored  # kept under the lead party's slug
    st = {s["slug"]: s for s in out["stranke"]}
    for slug in ("aa", "bb", "cc"):
        assert d["doc_id"] in st[slug]["doc_ids"]
    assert st["bb"]["status"] == "pronađen" and len(st["bb"]["doc_ids"]) == 2
    assert st["aa"]["status"] == "djelomično" and st["aa"]["provjereno"]
    assert st["cc"]["status"] == "djelomično" and st["cc"]["provjereno"]
    assert st["dd"]["status"] == "nije-pronađen"
    assert out["manjine"][0]["status"] == "nije-pronađen"
    assert out["manjine"][0]["naziv"] == "UDRUGA X"
    assert P.validate(out, MINI_LISTE) == []


def test_coalition_member_can_be_excluded():
    izv = copy.deepcopy(MINI_IZVORI)
    izv["koalicije"]["aa-bb-cc"]["izvori"][0]["bez"] = [3]
    out = P.build_output(MINI_LISTE, izv, fake_fetch([]))
    d = next(x for x in out["dokumenti"] if x["vrsta"] == "koalicijski")
    assert d["party_ids"] == [1, 2]
    st = {s["slug"]: s for s in out["stranke"]}
    assert st["cc"]["status"] == "nije-pronađen"


def test_election_doc_can_count_as_standing():
    izv = copy.deepcopy(MINI_IZVORI)
    izv["koalicije"]["aa-bb-cc"]["izvori"][0]["ujedno_trajni"] = True
    out = P.build_output(MINI_LISTE, izv, fake_fetch([]))
    st = {s["slug"]: s for s in out["stranke"]}
    assert st["aa"]["status"] == "pronađen" and st["cc"]["status"] == "pronađen"
    assert P.validate(out, MINI_LISTE) == []


def test_same_document_from_two_parties_is_one_record():
    izv = copy.deepcopy(MINI_IZVORI)
    izv["stranke"]["cc"]["izvori"] = [{"vrsta": "trajni", "url": "https://bb.hr/deklaracija.pdf",
                                       "naslov": "Programska deklaracija"}]
    stored: list[tuple] = []
    out = P.build_output(MINI_LISTE, izv, fake_fetch([]), store=lambda *a: stored.append(a[0]))
    trajni = [d for d in out["dokumenti"] if d["vrsta"] == "trajni"]
    assert len(trajni) == 1 and trajni[0]["party_ids"] == [2, 3]
    assert stored.count("bb") == 1 and "cc" not in stored
    assert P.validate(out, MINI_LISTE) == []


def test_unfetchable_source_is_not_a_document():
    izv = copy.deepcopy(MINI_IZVORI)
    izv["stranke"]["cc"]["izvori"] = [{"vrsta": "trajni", "url": "https://cc.hr/404.pdf",
                                       "naslov": "x"}]
    out = P.build_output(MINI_LISTE, izv, fake_fetch([]), log_warn=lambda m: None)
    assert len(out["dokumenti"]) == 2
    assert P.validate(out, MINI_LISTE) == []


def test_stable_keeps_timestamps_when_unchanged():
    out1 = P.build_output(MINI_LISTE, MINI_IZVORI, fake_fetch([]))
    old = json.loads(P.dump(out1))
    out2 = P.build_output(MINI_LISTE, MINI_IZVORI, fake_fetch([]))
    out2["generated_at"] = "2099-01-01T00:00:00+00:00"
    for d in out2["dokumenti"]:
        d["preuzeto"] = "2099-01-01T00:00:00+00:00"
    assert P.dump(P.stable(out2, old)) == P.dump(old)


def test_party_status_rules():
    assert P.party_status({"koalicijski", "trajni"}, False) == "pronađen"
    assert P.party_status({"izborni-2024"}, False) == "djelomično"
    assert P.party_status({"trajni"}, False) == "djelomično"
    assert P.party_status(set(), False) == "nije-pronađen"
    assert P.party_status({"trajni"}, True) == "pronađen"  # ran on no 2024 list


# ------------------------------------------------------------------ validator on bad fixtures

GOOD = P.build_output(MINI_LISTE, MINI_IZVORI, fake_fetch([]))


def mutate(fn):
    data = copy.deepcopy(GOOD)
    fn(data)
    return P.validate(data, MINI_LISTE)


@pytest.mark.parametrize("fn, expect", [
    (lambda d: d.pop("manjine"), "nema 'manjine'"),
    (lambda d: d["dokumenti"][0].update(vrsta="letak"), "vrsta 'letak'"),
    (lambda d: d["dokumenti"][0].update(list_id=None), "koalicijski bez list_id"),
    (lambda d: d["dokumenti"][0].update(list_id="nema-liste"), "nepoznat list_id"),
    (lambda d: d["dokumenti"][0].update(format="docx"), "format 'docx'"),
    (lambda d: d["dokumenti"][0].update(stranica=None), "PDF bez broja stranica"),
    (lambda d: d["dokumenti"][0].update(datum="17. 4. 2024."), "datum nije YYYY-MM-DD"),
    (lambda d: d["dokumenti"][0].update(izvor="wayback"), "wayback bez wayback_url"),
    (lambda d: d["dokumenti"][0].update(doc_id="ffffffffffff"), "doc_id nije prefiks sha256"),
    (lambda d: d["dokumenti"][1].update(sha256=d["dokumenti"][0]["sha256"]), "isti sha256 dvaput"),
    (lambda d: d["dokumenti"][0].update(party_ids=[3, 1, 2]), "nisu sortirani"),
    (lambda d: d["dokumenti"][0].pop("preuzeto"), "nema 'preuzeto'"),
    (lambda d: d["stranke"].pop(), "stranke bez unosa"),
    (lambda d: d["stranke"][0].update(status="možda"), "status 'možda'"),
    (lambda d: d["stranke"][0].update(doc_ids=["abc"]), "doc_id abc ne postoji"),
    (lambda d: next(s for s in d["stranke"] if s["slug"] == "cc").update(
        status="nije-pronađen"), "nije-pronađen a ima dokumente"),
    (lambda d: next(s for s in d["stranke"] if s["slug"] == "dd").update(provjereno=[]),
     "bez popisa provjerenog"),
    (lambda d: next(s for s in d["stranke"] if s["slug"] == "aa").update(doc_ids=[]),
     "ga ne navodi u doc_ids"),
    (lambda d: d.update(generated_at="jučer"), "generated_at nije ISO"),
    (lambda d: d["dokumenti"][1].update(ujedno_trajni=True), "ujedno_trajni samo"),
])
def test_validator_rejects_bad_fixture(fn, expect):
    errs = mutate(fn)
    assert any(expect in e for e in errs), errs


def test_validator_accepts_good_fixture():
    assert P.validate(GOOD, MINI_LISTE) == []
    assert P.validate([], MINI_LISTE) == ["vrh nije objekt"]


# ------------------------------------------------------------------ the real data

def test_real_programi_json_is_valid():
    assert P.validate(PROGRAMI, LISTE) == []


def test_every_party_in_scope_has_an_entry():
    want = sorted(s["party_id"] for s in LISTE["stranke"])
    got = sorted(s["party_id"] for s in PROGRAMI["stranke"])
    assert got == want
    assert len(PROGRAMI["manjine"]) == len(LISTE["manjine"])


def test_real_coalition_docs_cover_their_lists():
    lists = {l["list_id"]: l for l in LISTE["liste"]}
    for d in PROGRAMI["dokumenti"]:
        if d["vrsta"] != "koalicijski":
            continue
        members = {c["party_id"] for c in lists[d["list_id"]]["clanice"] if c["party_id"]}
        assert set(d["party_ids"]) <= members
        src = next(s for s in IZVORI["koalicije"][d["list_id"]]["izvori"]
                   if s["naslov"] == d["naslov"])
        assert set(d["party_ids"]) == members - set(src.get("bez", []))


def test_real_file_is_deterministic_dump():
    text = (ROOT / "data/kompas/programi.json").read_text(encoding="utf-8")
    assert text == P.dump(PROGRAMI)


def test_izvori_reference_scope():
    slugs = {s["slug"] for s in LISTE["stranke"]}
    assert set(IZVORI["stranke"]) <= slugs
    assert set(IZVORI["koalicije"]) <= {l["list_id"] for l in LISTE["liste"]}
    assert set(IZVORI["manjine"]) <= {m["manjine_id"] for m in LISTE["manjine"]}
