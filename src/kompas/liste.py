"""Lists of the 2024 parliamentary election that won seats → catalog party_ids.

Scope definition for Kompas stranaka. Pure functions: rows in (from the
izbori.domovina.ai mirror of the DIP archive), plain dicts out; the only I/O is
read_rows(), which takes an open sqlite connection.

What a "lista" is here: a coalition as voters saw it. DIP files one list per
izborna jedinica, and the same coalition runs with different partners in
different jedinice (SDP with/without REFORMISTI, DP with five different
partner sets, Možemo! alone / with HOĆEMO PRAVEDNO / with SRĐ JE GRAD, HDZ
alone in the diaspora XI). Variants are grouped by their lead party (first
name in `stranke`, i.e. the ballot's nositelj). Every variant of a winning
coalition is kept — also variants that won 0 seats — so each member carries
the jedinice it ran in and the seats of the variants it was on
(`mandati_varijanti`); a member only on a 0-seat variant is visible as such.

Lead-party grouping deliberately does NOT merge lists led by different
parties even if they share members (the IDS-led list in VIII vs the
SOCIJALDEMOKRATI-led lists elsewhere are different ballots).
"""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from src.normalize import norm_key, slugify
from src.party_match import CatalogMatcher

ELECTION = "parlament-2024"
GENERAL = "02"  # vrsta: general lists, jedinice I–X (14 seats each) + XI diaspora

# p1 → izborna jedinica. XII = national minorities (vrsta 13…63).
JEDINICE = {
    "001": "I", "002": "II", "003": "III", "004": "IV", "005": "V", "006": "VI",
    "007": "VII", "008": "VIII", "009": "IX", "010": "X", "011": "XI", "012": "XII",
}
_JED_ORDER = {v: i for i, v in enumerate(JEDINICE.values())}

# vrsta → national minority (Zakon o izboru zastupnika, čl. 16).
MANJINE = {
    "13": "srpska",
    "23": "mađarska",
    "33": "talijanska",
    "43": "češka i slovačka",
    "53": "austrijska, bugarska, njemačka, poljska, romska, rumunjska, rusinska, "
          "ruska, turska, ukrajinska, vlaška i židovska",
    "63": "albanska, bošnjačka, crnogorska, makedonska i slovenska",
}

ALIAS_SOURCE_SELF = "dip-parlament-2024"  # written by 08 from these very names

_GRUPA_BIRACA = re.compile(r"\s*-\s*KANDIDAT GRUPE BIRA[ČC]A\s*$", re.IGNORECASE)
_NO_PARTY = {norm_key(x) for x in ("NZ", "nezavisni zastupnici", "")}
_STRANKA_PREFIX = re.compile(r"^stranka\s+", re.IGNORECASE)


def split_stranke(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(";") if x.strip()]


def jed_sorted(jedinice: Iterable[str]) -> list[str]:
    return sorted(set(jedinice), key=lambda j: _JED_ORDER.get(j, 99))


def read_rows(conn: sqlite3.Connection, election: str = ELECTION) -> list[dict]:
    """rh- and zup-level list rows of one election, deterministic order."""
    cur = conn.execute(
        """SELECT r.vrsta, r.p1, r.level, l.rbr, l.naziv, l.glasova,
                  COALESCE(l.mandata, 0) AS mandata, l.stranke
           FROM rezultat r JOIN rezultat_lista l ON l.rezultat_id = r.id
           WHERE r.election = ? AND r.level IN ('rh', 'zup')
           ORDER BY r.vrsta, r.p1, l.rbr, l.id""",
        (election,),
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# --- general lists ---------------------------------------------------------

def group_lists(rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Constituency rows (vrsta 02, level zup) → coalitions grouped by lead
    party; only coalitions that won at least one seat. Members are ballot
    names (not yet mapped)."""
    by_lead: dict[str, dict[tuple[str, ...], dict]] = defaultdict(dict)
    for r in rows:
        if r["vrsta"] != GENERAL or r["level"] != "zup":
            continue
        stranke = tuple(split_stranke(r["stranke"]))
        if not stranke:
            continue
        v = by_lead[stranke[0]].setdefault(
            stranke, {"naziv": r["naziv"], "stranke": list(stranke),
                      "jedinice": {}, "glasova": 0, "mandati": 0},
        )
        jed = JEDINICE[r["p1"]]
        if jed in v["jedinice"]:
            raise ValueError(f"{r['naziv']!r} twice in jedinica {jed}")
        v["jedinice"][jed] = r["mandata"] or 0
        v["glasova"] += r["glasova"] or 0
        v["mandati"] += r["mandata"] or 0

    out = []
    for lead, variants in by_lead.items():
        vs = list(variants.values())
        mandati = sum(v["mandati"] for v in vs)
        if mandati == 0:
            continue
        # Main variant names the list: most jedinice, then most votes.
        vs.sort(key=lambda v: (-len(v["jedinice"]), -v["glasova"], v["naziv"]))
        main = vs[0]
        izborne: dict[str, int] = {}
        for v in vs:
            for j, m in v["jedinice"].items():
                if j in izborne:
                    raise ValueError(f"lead {lead!r}: two variants in jedinica {j}")
                izborne[j] = m
        members: dict[str, dict] = {}
        for v in vs:  # main variant first → its member order wins
            for name in v["stranke"]:
                m = members.setdefault(name, {"jedinice": [], "mandati_varijanti": 0})
                m["jedinice"] += list(v["jedinice"])
                m["mandati_varijanti"] += v["mandati"]
        out.append({
            "list_id": slugify(main["naziv"]),
            "naziv": main["naziv"],
            "nositelj": lead,
            "mandati": mandati,
            "glasova": sum(v["glasova"] for v in vs),
            # A list, not {"I": n}: the JSON is written with sort_keys and
            # "IX" would sort before "V".
            "izborne_jedinice": [{"jedinica": j, "mandati": izborne[j]}
                                 for j in jed_sorted(izborne)],
            "varijante": [
                {"naziv": v["naziv"], "stranke": v["stranke"],
                 "jedinice": jed_sorted(v["jedinice"]),
                 "glasova": v["glasova"], "mandati": v["mandati"]}
                for v in vs
            ],
            "clanice": [
                {"naziv": n, "jedinice": jed_sorted(m["jedinice"]),
                 "mandati_varijanti": m["mandati_varijanti"]}
                for n, m in members.items()
            ],
        })
    out.sort(key=lambda l: (-l["mandati"], l["list_id"]))
    ids = [l["list_id"] for l in out]
    if len(ids) != len(set(ids)):
        raise ValueError(f"list_id collision: {ids}")
    return out


def crosscheck_rh(lists: Sequence[Mapping], rows: Sequence[Mapping]) -> list[str]:
    """Each variant's summed votes/seats must equal its RH-level aggregate
    row (same ballot label and composition). Returns problems, [] if OK."""
    rh = {}
    for r in rows:
        if r["vrsta"] == GENERAL and r["level"] == "rh":
            rh[(r["naziv"], tuple(split_stranke(r["stranke"])))] = r
    problems = []
    for l in lists:
        for v in l["varijante"]:
            r = rh.get((v["naziv"], tuple(v["stranke"])))
            if r is None:
                problems.append(f"{v['naziv']}: no RH-level row")
            elif (r["glasova"], r["mandata"] or 0) != (v["glasova"], v["mandati"]):
                problems.append(
                    f"{v['naziv']}: RH {r['glasova']} votes/{r['mandata']} seats, "
                    f"jedinice sum {v['glasova']}/{v['mandati']}")
    return problems


def seat_totals(rows: Sequence[Mapping], lists: Sequence[Mapping],
                manjine: Sequence[Mapping]) -> dict[str, int]:
    """Seat arithmetic: winning lists + minority seats, and the RH-level row
    total for general lists (all lists, also those without seats)."""
    rh_general = sum(r["mandata"] or 0 for r in rows
                     if r["vrsta"] == GENERAL and r["level"] == "rh")
    liste = sum(l["mandati"] for l in lists)
    manj = sum(m["mandati"] for m in manjine)
    return {"liste": liste, "liste_rh_razina": rh_general,
            "manjine": manj, "ukupno": liste + manj}


# --- minorities ------------------------------------------------------------

def is_grupa_biraca(name: str) -> bool:
    return bool(_GRUPA_BIRACA.search(name))


def minority_seats(rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Winning minority candidates (XII), grouped by vrsta + proposer."""
    groups: dict[tuple[str, str], dict] = {}
    for r in rows:
        if r["vrsta"] not in MANJINE or not (r["mandata"] or 0):
            continue
        predlagatelj = (r["stranke"] or "").strip()
        g = groups.setdefault((r["vrsta"], predlagatelj), {
            "vrsta_izbora": r["vrsta"], "manjina": MANJINE[r["vrsta"]],
            "predlagatelj": predlagatelj, "mandati": 0, "glasova": 0, "kandidati": [],
        })
        g["mandati"] += r["mandata"]
        g["glasova"] += r["glasova"] or 0
        g["kandidati"].append({"ime": r["naziv"], "glasova": r["glasova"]})
    out = []
    for (vrsta, pred), g in groups.items():
        g["kandidati"].sort(key=lambda k: (-(k["glasova"] or 0), k["ime"]))
        if is_grupa_biraca(pred):
            label = _GRUPA_BIRACA.sub("", pred)
        else:  # shortest " - " segment ≈ the proposer's abbreviation (SDSS, DZMH)
            label = min((s for s in pred.split(" - ") if s.strip()), key=len)
        g["manjine_id"] = f"manjina-{vrsta}-{slugify(label)}"
        out.append(g)
    out.sort(key=lambda g: (g["vrsta_izbora"], -g["mandati"], g["manjine_id"]))
    return out


# --- mapping ---------------------------------------------------------------

def map_member(name: str, matcher: CatalogMatcher, jedinice: list[str]) -> dict:
    """One ballot name → member record with catalog identity."""
    rec: dict[str, Any] = {"naziv": name, "jedinice": jedinice}
    if is_grupa_biraca(name):
        rec.update(party_id=None, slug=None, status=None, match="none",
                   vrsta="grupa-biraca")
        return rec
    m = matcher.match(name)
    row = m.row
    rec.update(
        party_id=m.party_id,
        slug=row["slug"] if row else None,
        status=row.get("status") if row else None,
        match=m.how,
        vrsta="stranka" if row else "izvan-kataloga",
    )
    return rec


def mp_party_name(mp: Mapping[str, Any]) -> str | None:
    """Party a sitting MP belongs to, None for nezavisni (NZ)."""
    for key in ("party_full", "party"):
        v = (mp.get(key) or "").strip()
        if norm_key(v) in _NO_PARTY:
            return None
        if v:
            return _STRANKA_PREFIX.sub("", v)  # Sabor: "stranka Nezavisni"
    return None


def build(rows: Sequence[Mapping[str, Any]], catalog: Sequence[Mapping[str, Any]],
          mps: Sequence[Mapping[str, Any]]) -> dict:
    """Everything except `izvor`. `catalog` = load_catalog() rows in priority
    order (callers drop the 'dip-parlament-2024' aliases so match kinds
    reflect independent evidence, as in 08's own run)."""
    matcher = CatalogMatcher(catalog)
    by_id = {c["id"]: c for c in catalog}

    lists = group_lists(rows)
    problems = crosscheck_rh(lists, rows)
    if problems:
        raise ValueError("RH cross-check failed:\n  " + "\n  ".join(problems))

    scope: dict[int, dict] = defaultdict(lambda: {"list_ids": [], "zastupnici": 0,
                                                   "izvan_lista": False})
    for l in lists:
        l["clanice"] = [map_member(c["naziv"], matcher, c["jedinice"]) | {
            "mandati_varijanti": c["mandati_varijanti"]} for c in l["clanice"]]
        lead = next(c for c in l["clanice"] if c["naziv"] == l["nositelj"])
        l["nositelj"] = {"naziv": lead["naziv"], "party_id": lead["party_id"],
                         "slug": lead["slug"]}
        for c in l["clanice"]:
            if c["party_id"] is not None:
                scope[c["party_id"]]["list_ids"].append(l["list_id"])

    manjine = minority_seats(rows)
    for g in manjine:
        g["clanice"] = [map_member(g.pop("predlagatelj"), matcher, ["XII"])
                        | {"mandati_varijanti": g["mandati"]}]
        for c in g["clanice"]:
            if c["party_id"] is not None:
                scope[c["party_id"]]["list_ids"].append(g["manjine_id"])

    covered = set(scope)
    izvan: dict[int, dict] = {}
    nezavisni = []
    mp_unmatched = []
    for mp in mps:
        pname = mp_party_name(mp)
        who = {"ime": mp.get("name"), "izabran_na": mp.get("elected_on"),
               "klub": mp.get("club")}
        if pname is None:
            nezavisni.append(who)
            continue
        m = matcher.match(pname)
        if m.row is None:
            mp_unmatched.append({"stranka": pname, **who})
            continue
        pid = m.party_id
        scope[pid]["zastupnici"] += 1
        if pid in covered:
            continue
        e = izvan.setdefault(pid, {"party_id": pid, "slug": m.row["slug"],
                                   "naziv": mp.get("party_full") or pname,
                                   "kratica": mp.get("party"), "match": m.how,
                                   "zastupnici": []})
        e["zastupnici"].append(who)
        scope[pid]["izvan_lista"] = True
    for e in izvan.values():
        e["zastupnici"].sort(key=lambda z: z["ime"] or "")
        e["broj_zastupnika"] = len(e["zastupnici"])
    nezavisni.sort(key=lambda z: z["ime"] or "")

    stranke = []
    for pid, s in scope.items():
        c = by_id[pid]
        stranke.append({
            "party_id": pid, "slug": c["slug"], "canonical_name": c["canonical_name"],
            "short_name": c.get("short_name"), "status": c.get("status"),
            "website": c.get("website") or None,
            "list_ids": sorted(set(s["list_ids"])),
            "izvan_lista": s["izvan_lista"], "broj_zastupnika": s["zastupnici"],
        })
    stranke.sort(key=lambda s: s["slug"])

    return {
        "mandati": seat_totals(rows, lists, manjine),
        "liste": lists,
        "manjine": manjine,
        "zastupnici_izvan_lista": sorted(izvan.values(),
                                         key=lambda e: (-e["broj_zastupnika"], e["slug"])),
        "nezavisni_zastupnici": {"broj": len(nezavisni), "zastupnici": nezavisni},
        "zastupnici_bez_kataloga": mp_unmatched,
        "stranke": stranke,
    }


def unmatched(out: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """(where, ballot name, vrsta) for every member without a party_id."""
    res = []
    for l in out["liste"]:
        for c in l["clanice"]:
            if c["party_id"] is None:
                res.append((l["list_id"], c["naziv"], c["vrsta"]))
    for g in out["manjine"]:
        for c in g["clanice"]:
            if c["party_id"] is None:
                res.append((g["manjine_id"], c["naziv"], c["vrsta"]))
    return res
