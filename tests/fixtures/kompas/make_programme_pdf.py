"""Builds tests/fixtures/kompas/programme.pdf (committed; re-run to regenerate).

    uv run python tests/fixtures/kompas/make_programme_pdf.py

Three A4 pages in Helvetica (Type1, standard 14 font, nothing embedded) whose
/Differences encoding maps bytes 128–137 to the Croatian glyph names, so pypdf
decodes č ć đ š ž through its glyph list. Every page has a running header and
a page number; page 1 has a big heading, diacritics and a hyphenated line
break; page 2 has a numbered heading and a paragraph that continues on page 3.
"""
from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject, NameObject,
                           NumberObject)

OUT = Path(__file__).with_name("programme.pdf")

GLYPHS = ["Ccaron", "ccaron", "cacute", "dcroat", "scaron", "zcaron", "Scaron", "Zcaron",
          "Cacute", "Dcroat"]
CHARS = "ČčćđšžŠŽĆĐ"
ENC = {c: 128 + i for i, c in enumerate(CHARS)}

HEADER = "Testni program stranke"
PAGES: list[list[tuple[float, str]]] = [
    [
        (10, HEADER),
        (18, "ZDRAVSTVO"),
        (10, "Čakovec, đak, šuma, žaba, ćup i Šibenik su riječi s dijakriticima."),
        (10, "Stranka se zalaže za dostupnu i kvalitetnu zdrav-"),
        (10, "stvenu skrb u svim krajevima, od Čakovca do Dubrovnika."),
        (10, "Bolnice će dobiti nove liječnike i medicinske sestre."),
        (10, "1"),
    ],
    [
        (10, HEADER),
        (18, "1.2. Obrazovanje"),
        (10, "Škola mora biti besplatna za svako dijete, a udžbenici"),
        (10, "dostupni svima. Ovaj odlomak se nastavlja na"),
        (10, "2"),
    ],
    [
        (10, HEADER),
        (10, "sljedećoj stranici i tu završava."),
        (10, "3"),
    ],
]


def encode(text: str) -> bytes:
    out = bytearray()
    for ch in text:
        b = ENC.get(ch, None)
        if b is None:
            b = ord(ch)
            assert b < 128, ch
        if b in (ord("("), ord(")"), ord("\\")):
            out += b"\\"
        out.append(b)
    return bytes(out)


def build() -> bytes:
    w = PdfWriter()
    enc = DictionaryObject({
        NameObject("/Type"): NameObject("/Encoding"),
        NameObject("/BaseEncoding"): NameObject("/WinAnsiEncoding"),
        NameObject("/Differences"): ArrayObject(
            [NumberObject(128)] + [NameObject("/" + g) for g in GLYPHS]),
    })
    font = w._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
        NameObject("/Encoding"): w._add_object(enc),
    }))
    for lines in PAGES:
        page = w.add_blank_page(595, 842)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        y = 800
        ops = bytearray()
        for size, text in lines:
            ops += b"BT /F1 %d Tf 50 %d Td (" % (size, y) + encode(text) + b") Tj ET\n"
            y -= int(size * 1.6)
        s = DecodedStreamObject()
        s.set_data(bytes(ops))
        page[NameObject("/Contents")] = w._add_object(s)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


if __name__ == "__main__":
    OUT.write_bytes(build())
    print(f"{OUT} ({OUT.stat().st_size} bytes)")
