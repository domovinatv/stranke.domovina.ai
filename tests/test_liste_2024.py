"""Kompas scope builder (src/kompas/liste.py, scripts/22_liste_2024.py).

Offline: a tiny izbori.sqlite and stranke.db are built in tmp_path; neither
the external disk nor data/stranke.db is needed.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from src.db import SCHEMA
from src.kompas.liste import (
    build, crosscheck_rh, group_lists, minority_seats, read_rows, unmatched,
)
from src.party_match import CatalogMatcher, load_catalog, name_variants

ROOT = Path(__file__).resolve().parent.parent

# (vrsta, p1, level, rbr, naziv, glasova, mandata, stranke)
ROWS = [
    # Two constituencies + diaspora; the AA coalition varies by jedinica.
    ("02", "001", "zup", 1, "AA, BB", 1000, 2, "ALFA STRANKA - AA; BETA SAVEZ - BB"),
    ("02", "001", "zup", 2, "DELTA, GAMA", 300, 0, "DELTA POKRET - DP; GAMA SAVEZ HRVATSKE"),
    ("02", "001", "zup", 3, "ZETA", 50, 0, "ZETA"),
    ("02", "002", "zup", 1, "AA, BB, NOVA OPCIJA", 800, 1,
     "ALFA STRANKA - AA; BETA SAVEZ - BB; NOVA OPCIJA"),
    ("02", "002", "zup", 2, "DELTA, GAMA, ZELENA OPCIJA", 200, 1,
     "DELTA POKRET - DP; GAMA SAVEZ HRVATSKE; ZELENA OPCIJA"),
    ("02", "011", "zup", 1, "AA", 100, 1, "ALFA STRANKA - AA"),
    # RH-level aggregates (one row per ballot variant).
    ("02", "00", "rh", 1, "AA, BB", 1000, 2, "ALFA STRANKA - AA; BETA SAVEZ - BB"),
    ("02", "00", "rh", 2, "AA, BB, NOVA OPCIJA", 800, 1,
     "ALFA STRANKA - AA; BETA SAVEZ - BB; NOVA OPCIJA"),
    ("02", "00", "rh", 3, "DELTA, GAMA", 300, 0, "DELTA POKRET - DP; GAMA SAVEZ HRVATSKE"),
    ("02", "00", "rh", 4, "DELTA, GAMA, ZELENA OPCIJA", 200, 1,
     "DELTA POKRET - DP; GAMA SAVEZ HRVATSKE; ZELENA OPCIJA"),
    ("02", "00", "rh", 5, "AA", 100, 1, "ALFA STRANKA - AA"),
    ("02", "00", "rh", 6, "ZETA", 50, 0, "ZETA"),
    # Minorities (XII): a party with two seats + a loser, a grupa birača.
    ("13", "012", "zup", 1, "PERO PERIĆ", 900, 1, "MANJINSKA STRANKA - MS"),
    ("13", "012", "zup", 2, "ANA ANIĆ", 950, 1, "MANJINSKA STRANKA - MS"),
    ("13", "012", "zup", 3, "LOŠ KANDIDAT", 100, 0, "DRUGA - DR"),
    ("33", "012", "zup", 1, "IVO IVIĆ", 500, 1, "IVO IVIĆ  - KANDIDAT GRUPE BIRAČA"),
]

# (id, canonical_name, slug, short_name, status, status_date, website, aliases[(alias, source)])
PARTIES = [
    (1, "ALFA STRANKA", "alfa-stranka", "AA", "AKTIVAN", None, "https://alfa.example", []),
    (2, "BETA SAVEZ", "beta-savez", None, "AKTIVAN", None, None, []),
    (3, "DELTA POKRET HRVATSKE", "delta-pokret-hrvatske", None, "AKTIVAN", None, None,
     [("DELTA POKRET", "nsk-imenik")]),
    (4, "GAMMA SAVEZ HRVATSKE", "gamma-savez-hrvatske", None, "AKTIVAN", None, None, []),
    (5, "ZELENA OPCIJA", "zelena-opcija", None, "PRESTANAK", "2010-01-01", None, []),
    (6, "ZELENA OPCIJA", "zelena-opcija-2", None, "AKTIVAN", None, None, []),
    (7, "MANJINSKA STRANKA", "manjinska-stranka", "MS", "AKTIVAN", None, None, []),
    # The self-written ballot alias must be ignored by the Kompas matcher.
    (8, "OMEGA", "omega", None, "AKTIVAN", None, None,
     [("NOVA OPCIJA", "dip-parlament-2024")]),
    (9, "SIGMA", "sigma", None, "AKTIVAN", None, None, []),
    # A catalog party named like the grupa-birača candidate: must not match.
    (10, "IVO IVIĆ", "ivo-ivic", None, "AKTIVAN", None, None, []),
]

MPS = [
    {"name": "A1", "party": "AA", "party_full": "Alfa stranka", "elected_on": "lista AA"},
    {"name": "A2", "party": "AA", "party_full": "Alfa stranka", "elected_on": "lista AA"},
    {"name": "N1", "party": "NZ", "party_full": "nezavisni zastupnici", "elected_on": "lista AA"},
    {"name": "O1", "party": "Omega", "party_full": "Omega", "elected_on": "lista Delte",
     "club": "Klub Omega"},
    {"name": "S1", "party": "stranka Sigma", "party_full": "stranka Sigma",
     "elected_on": "lista AA"},
    {"name": "X1", "party": "XX", "party_full": "Nepostojeća stranka", "elected_on": "lista AA"},
]


def make_izbori(path: Path) -> Path:
    c = sqlite3.connect(path)
    c.executescript(
        """CREATE TABLE rezultat (id INTEGER PRIMARY KEY, election TEXT, krug INTEGER,
               vrsta TEXT, p1 TEXT, p2 TEXT, p3 TEXT, level TEXT);
           CREATE TABLE rezultat_lista (id INTEGER PRIMARY KEY, rezultat_id INTEGER,
               rbr INTEGER, naziv TEXT, glasova INTEGER, mandata INTEGER, stranke TEXT,
               predlagatelji TEXT);"""
    )
    rid = {}
    for vrsta, p1, level, rbr, naziv, glasova, mandata, stranke in ROWS:
        key = (vrsta, p1, level)
        if key not in rid:
            cur = c.execute(
                "INSERT INTO rezultat (election, krug, vrsta, p1, p2, p3, level) "
                "VALUES ('parlament-2024', 1, ?, ?, '', '', ?)", key)
            rid[key] = cur.lastrowid
        c.execute(
            "INSERT INTO rezultat_lista (rezultat_id, rbr, naziv, glasova, mandata, stranke) "
            "VALUES (?, ?, ?, ?, ?, ?)", (rid[key], rbr, naziv, glasova, mandata, stranke))
    # Another election must be ignored.
    c.execute("INSERT INTO rezultat (election, krug, vrsta, p1, p2, p3, level) "
              "VALUES ('parlament-2020', 1, '02', '001', '', '', 'zup')")
    c.execute("INSERT INTO rezultat_lista (rezultat_id, rbr, naziv, glasova, mandata, stranke) "
              "VALUES (last_insert_rowid(), 1, 'OLD', 1, 14, 'OLD')")
    c.commit()
    c.close()
    return path


def make_catalog_db(path: Path | str) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.executescript(SCHEMA)
    for pid, name, slug, short, status, sdate, web, aliases in PARTIES:
        c.execute(
            "INSERT INTO parties (id, canonical_name, slug, short_name, status, status_date, "
            "website) VALUES (?, ?, ?, ?, ?, ?, ?)", (pid, name, slug, short, status, sdate, web))
        for alias, src in aliases:
            c.execute("INSERT INTO party_aliases (party_id, alias, source) VALUES (?, ?, ?)",
                      (pid, alias, src))
    c.commit()
    return c


@pytest.fixture
def rows(tmp_path):
    c = sqlite3.connect(make_izbori(tmp_path / "izbori.sqlite"))
    try:
        return read_rows(c)
    finally:
        c.close()


@pytest.fixture
def catalog():
    c = make_catalog_db(":memory:")
    try:
        return load_catalog(c, exclude_alias_sources=["dip-parlament-2024"])
    finally:
        c.close()


@pytest.fixture
def out(rows, catalog):
    return build(rows, catalog, MPS)


def test_name_variants_strips_stacked_abbreviations():
    assert name_variants("ALFA STRANKA - AA") == ["alfa stranka aa", "alfa stranka"]
    assert name_variants('"DO i SIP"') == ["do i sip"]


def test_load_catalog_priority_and_alias_exclusion(catalog):
    ids = [c["id"] for c in catalog]
    assert ids.index(6) < ids.index(5)  # active before defunct
    omega = next(c for c in catalog if c["id"] == 8)
    assert omega["aliases"] == []
    delta = next(c for c in catalog if c["id"] == 3)
    assert delta["aliases"] == ["DELTA POKRET"]


def test_matcher_kinds(catalog):
    m = CatalogMatcher(catalog)
    assert (m.match("ALFA STRANKA - AA").party_id, m.match("ALFA STRANKA - AA").how) == (1, "exact")
    assert m.match("AA").party_id == 1  # short_name
    assert (m.match("DELTA POKRET - DP").party_id, m.match("DELTA POKRET - DP").how) == (3, "alias")
    fz = m.match("GAMA SAVEZ HRVATSKE")
    assert fz.party_id == 4 and fz.how.startswith("fuzzy:") and int(fz.how[6:]) >= 93
    assert m.match("ZELENA OPCIJA").party_id == 6
    assert (m.match("NOVA OPCIJA").party_id, m.match("NOVA OPCIJA").how) == (None, "none")


def test_read_rows_only_this_election(rows):
    assert len(rows) == len(ROWS)
    assert all(r["naziv"] != "OLD" for r in rows)


def test_grouping_by_lead_party(rows):
    lists = group_lists(rows)
    assert [l["list_id"] for l in lists] == ["aa-bb", "delta-gama"]  # ZETA: no seats
    aa, delta = lists
    assert aa["mandati"] == 4 and delta["mandati"] == 1
    assert aa["izborne_jedinice"] == [
        {"jedinica": "I", "mandati": 2}, {"jedinica": "II", "mandati": 1},
        {"jedinica": "XI", "mandati": 1}]
    assert [v["naziv"] for v in aa["varijante"]] == ["AA, BB", "AA, BB, NOVA OPCIJA", "AA"]
    assert [c["naziv"] for c in aa["clanice"]] == [
        "ALFA STRANKA - AA", "BETA SAVEZ - BB", "NOVA OPCIJA"]
    nova = aa["clanice"][2]
    assert nova["jedinice"] == ["II"] and nova["mandati_varijanti"] == 1
    # A member only on a 0-seat variant would show mandati_varijanti 0;
    # DELTA's main variant is the 0-seat one (more votes, same jedinice count).
    assert delta["naziv"] == "DELTA, GAMA"
    assert crosscheck_rh(lists, rows) == []


def test_crosscheck_detects_mismatch(rows):
    bad = [dict(r) for r in rows]
    for r in bad:
        if r["level"] == "rh" and r["naziv"] == "AA, BB":
            r["mandata"] = 3
    problems = crosscheck_rh(group_lists(bad), bad)
    assert len(problems) == 1 and problems[0].startswith("AA, BB:")


def test_minority_seats(rows):
    m = minority_seats(rows)
    assert [g["manjine_id"] for g in m] == ["manjina-13-ms", "manjina-33-ivo-ivic"]
    ms = m[0]
    assert ms["mandati"] == 2 and ms["manjina"] == "srpska"
    assert [k["ime"] for k in ms["kandidati"]] == ["ANA ANIĆ", "PERO PERIĆ"]


def test_build_mapping_and_totals(out):
    assert out["mandati"] == {"liste": 5, "liste_rh_razina": 5, "manjine": 3, "ukupno": 8}
    aa, delta = out["liste"]
    assert aa["nositelj"] == {"naziv": "ALFA STRANKA - AA", "party_id": 1, "slug": "alfa-stranka"}
    got = {c["naziv"]: (c["party_id"], c["match"], c["vrsta"]) for c in aa["clanice"] + delta["clanice"]}
    assert got["ALFA STRANKA - AA"] == (1, "exact", "stranka")
    assert got["BETA SAVEZ - BB"] == (2, "exact", "stranka")
    assert got["NOVA OPCIJA"] == (None, "none", "izvan-kataloga")
    assert got["DELTA POKRET - DP"] == (3, "alias", "stranka")
    assert got["GAMA SAVEZ HRVATSKE"][0] == 4 and got["GAMA SAVEZ HRVATSKE"][1].startswith("fuzzy:")
    assert got["ZELENA OPCIJA"] == (6, "exact", "stranka")

    ms, grupa = out["manjine"]
    assert ms["clanice"][0]["party_id"] == 7
    g = grupa["clanice"][0]
    assert (g["party_id"], g["vrsta"], g["match"]) == (None, "grupa-biraca", "none")

    assert unmatched(out) == [
        ("aa-bb", "NOVA OPCIJA", "izvan-kataloga"),
        ("manjina-33-ivo-ivic", "IVO IVIĆ  - KANDIDAT GRUPE BIRAČA", "grupa-biraca"),
    ]


def test_build_mps(out):
    izvan = out["zastupnici_izvan_lista"]
    assert [(e["slug"], e["broj_zastupnika"]) for e in izvan] == [("omega", 1), ("sigma", 1)]
    assert izvan[0]["zastupnici"] == [
        {"ime": "O1", "izabran_na": "lista Delte", "klub": "Klub Omega"}]
    assert out["nezavisni_zastupnici"]["broj"] == 1
    assert [z["stranka"] for z in out["zastupnici_bez_kataloga"]] == ["Nepostojeća stranka"]

    st = {s["party_id"]: s for s in out["stranke"]}
    assert sorted(st) == [1, 2, 3, 4, 6, 7, 8, 9]
    assert st[1]["list_ids"] == ["aa-bb"] and st[1]["broj_zastupnika"] == 2
    assert st[1]["website"] == "https://alfa.example" and st[2]["website"] is None
    assert st[7]["list_ids"] == ["manjina-13-ms"]
    assert st[8]["izvan_lista"] is True and st[8]["list_ids"] == []
    assert [s["slug"] for s in out["stranke"]] == sorted(s["slug"] for s in out["stranke"])


def test_cli_writes_deterministic_json(tmp_path):
    izbori = make_izbori(tmp_path / "izbori.sqlite")
    make_catalog_db(tmp_path / "stranke.db").close()
    zast = tmp_path / "zastupnici.json"
    zast.write_text(json.dumps({"source": "test", "fetched_at": "2026-01-01", "mps": MPS}),
                    encoding="utf-8")
    out_path = tmp_path / "kompas" / "liste_2024.json"
    cmd = [sys.executable, str(ROOT / "scripts" / "22_liste_2024.py"),
           "--izbori-db", str(izbori), "--stranke-db", str(tmp_path / "stranke.db"),
           "--zastupnici", str(zast), "--out", str(out_path), "--ukupno-mandata", "8"]
    subprocess.run(cmd, check=True, capture_output=True)
    first = out_path.read_text(encoding="utf-8")
    data = json.loads(first)
    assert set(data) == {"izvor", "mandati", "liste", "manjine", "zastupnici_izvan_lista",
                         "nezavisni_zastupnici", "zastupnici_bez_kataloga", "stranke"}
    assert set(data["liste"][0]) == {"list_id", "naziv", "nositelj", "mandati", "glasova",
                                     "izborne_jedinice", "varijante", "clanice"}
    assert set(data["liste"][0]["clanice"][0]) == {
        "naziv", "party_id", "slug", "status", "match", "vrsta", "jedinice", "mandati_varijanti"}
    assert "Ć" in first  # ensure_ascii=False
    assert data["izvor"]["election"] == "parlament-2024"

    subprocess.run(cmd, check=True, capture_output=True)
    assert out_path.read_text(encoding="utf-8") == first  # idempotent, generated_at kept

    bad = subprocess.run(cmd[:-1] + ["151"], capture_output=True, text=True)
    assert bad.returncode != 0 and "seat total 8 != 151" in bad.stderr
