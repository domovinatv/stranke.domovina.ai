#!/usr/bin/env python3
"""Revidirani financijski izvještaji stranaka → data/financiranje/revizija_stranke.json.

Državni ured za reviziju svake godine revidira sve parlamentarne i veće
izvanparlamentarne stranke (40–55 godišnje) i za svaku objavljuje izvješće s
tri tablice:
  1. prihodi po izvorima (državni proračun, lokalni proračuni, članarine,
     donacije, drugi) za prethodnu i tekuću godinu
  2. rashodi po vrstama (zaposleni, promidžba, ...) i višak/manjak prihoda
  3. imovina, obveze i vlastiti izvori na početku i kraju godine
Iz izvješća za godinu N uzimaju se i usporedni podaci za N−1, pa revizije
2020.–2024. pokrivaju 2019.–2024. Iznosi do 2022. su u kunama → EUR 7,53450.

    python3 scripts/21_fetch_revizija_stranke.py            # preuzmi što nedostaje i parsiraj
    python3 scripts/21_fetch_revizija_stranke.py --refresh  # ponovno preuzmi popise i PDF-ove
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "financiranje" / "revizija"
OUT = ROOT / "data" / "financiranje" / "revizija_stranke.json"
SITE = "https://www.revizija.hr"
HRK = 7.53450

# Revidirana godina → (godinaID, tema „Političke stranke / pojedinačna izvješća“)
# na https://www.revizija.hr/izvjesca/10 (izvješća izlaze u prosincu sljedeće godine).
YEARS = {
    2024: (3035, 3093),
    2023: (2901, 2970),
    2022: (2810, 2874),
    2021: (2686, 2753),
    2020: (1465, 2618),
}

NUM = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}(?!\d)")

ROWS = {
    1: [  # prihodi
        ("state", r"državnog\s+proračuna"),
        ("local", r"lokaln|jedinica"),
        ("members", r"članarin"),
        ("donations", r"dobrovoljn|donacij"),
        ("other", r"drugi\s+prihodi"),
        ("total", r"ukupn\w*\s+prihodi"),
    ],
    2: [  # rashodi
        ("staff", r"zaposlen"),
        ("promo", r"promidžb"),
        ("material_other", r"drugi\s+materijalni"),
        ("material", r"materijalni\s+rashodi"),
        ("amortization", r"amortizacij"),
        ("financial", r"financijski"),
        ("donations", r"donacij"),
        ("other", r"drugi\s+rashodi"),
        ("total_rev", r"ukupni\s+prihodi"),
        ("total", r"ukupn\w*\s+rashodi"),
        ("surplus", r"višak"),
        ("deficit", r"manjak"),
    ],
    3: [  # bilanca
        ("cash", r"novac\s+u\s+banci"),
        ("assets", r"ukupno\s+imovina"),
        ("loans", r"kredit"),
        ("liabilities", r"^obveze$"),
        ("equity", r"vlastiti\s+izvori"),
    ],
}


def deburr(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


def get(url: str) -> bytes:
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (stranke.domovina.ai)"})
            return urllib.request.urlopen(req, timeout=90).read()
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(3)
    raise RuntimeError("unreachable")


def list_reports(year: int, refresh: bool) -> list[tuple[str, str]]:
    cache = RAW / f"popis_{year}.json"
    if cache.exists() and not refresh:
        return [tuple(x) for x in json.loads(cache.read_text())]
    gid, tema = YEARS[year]
    items: list[tuple[str, str]] = []
    for page in range(1, 6):
        html = get(f"{SITE}/izvjesca/10?t=1&tema={tema}&godinaID={gid}&page={page}").decode("utf-8", "replace")
        found = [(t.strip(), u.replace("\\", "/"))
                 for u, t in re.findall(r"<a href='(/UserDocsImages[^']+\.pdf)'\s*>([^<]+)</a>", html, re.I)
                 if "POJEDIN" in u.upper()]
        new = [x for x in found if x not in items]
        if not new:
            break
        items += new
    cache.write_text(json.dumps(items, ensure_ascii=False, indent=0))
    return items


def slugify(title: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", deburr(title)).strip("_")[:80]


def table_lines(text: str, n: int) -> list[str]:
    m = re.search(rf"^\s*Tablica broj {n}\s*$", text, re.M)
    if not m:
        return []
    rest = text[m.end():]
    end = re.search(r"^\s*Tablica broj \d+\s*$", rest, re.M)
    chunk = rest[: end.start()] if end else rest
    # Tekst iza tablice ne smeta: iznose u rečenicama preskače table_nums, a za
    # svaki redak vrijedi prvi pogodak (redci tablice dolaze prije teksta).
    out = chunk.splitlines()[:80]
    return out


def table_nums(line: str) -> list[str]:
    """Iznosi iz stupaca tablice; iznos u rečenici („… 267.704,00 kn“) se preskače."""
    return [m.group() for m in NUM.finditer(line) if not re.match(r"\s?(kn|kuna|eur|€|%)", line[m.end():])]


def label_of(line: str) -> str:
    s = NUM.sub(" ", line)
    s = re.sub(r"^\s*\d+(\.\d+)*\.\s*", "", s)
    s = re.sub(r"\s\d[\d ]*,\d\b|\s-\s*$", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_table(lines: list[str], n: int) -> dict[str, list[float | None]]:
    """Retci → [prethodna godina, tekuća godina]. Stranka osnovana te godine ima
    samo jedan stupac; tada je prethodna godina None."""
    data: dict[str, list[float | None]] = {}
    ncols = min(2, max((len(table_nums(x)) for x in lines), default=0))
    for i, line in enumerate(lines):
        nums = table_nums(line)
        if not nums or len(nums) < ncols:
            continue
        own = label_of(line)
        if not re.search(r"[A-Za-zčćžšđ]{3}", own):
            above = label_of(lines[i - 1]) if i > 0 and not NUM.search(lines[i - 1]) else ""
            below = label_of(lines[i + 1]) if i + 1 < len(lines) and not NUM.search(lines[i + 1]) else ""
            own = f"{above} {below}".strip()
        low = own.lower()
        for key, pat in ROWS[n]:
            if key in data:
                continue
            if re.search(pat, low):
                vals = [float(x.replace(".", "").replace(",", ".")) for x in nums[:ncols]]
                data[key] = vals if ncols == 2 else [None, vals[0]]
                break
    return data


def parse_report(pdf: Path) -> dict:
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    tables = {n: parse_table(table_lines(text, n), n) for n in (1, 2, 3)}
    unit = "HRK" if re.search(r"u\s+(kunama|kn)\s*$", text[: text.find("Tablica broj 1") + 600], re.M) else "EUR"
    return {"unit": unit, "tables": tables}


def checks(rec: dict) -> list[str]:
    errs = []
    t1, t2, t3 = rec["tables"][1], rec["tables"][2], rec["tables"][3]
    for col in (0, 1):
        if t1.get("total", [None, None])[col] is None:
            continue
        parts = sum(t1[k][col] or 0 for k in ("state", "local", "members", "donations", "other") if k in t1)
        if "total" in t1 and abs(parts - t1["total"][col]) > 1:
            errs.append(f"prihodi stupac {col}: dijelovi {parts:.2f} ≠ ukupno {t1['total'][col]:.2f}")
        if "total" in t1 and "total" in t2:
            diff = t1["total"][col] - t2["total"][col]
            got = (t2.get("surplus", [0, 0])[col] or 0) - (t2.get("deficit", [0, 0])[col] or 0)
            if abs(diff - got) > 1:
                errs.append(f"višak/manjak stupac {col}: {got:.2f} ≠ prihodi−rashodi {diff:.2f}")
        if all(k in t3 and t3[k][col] is not None for k in ("assets", "liabilities", "equity")):
            if abs(t3["assets"][col] - t3["liabilities"][col] - t3["equity"][col]) > 1:
                errs.append(f"bilanca stupac {col}: imovina ≠ obveze + vlastiti izvori")
    for k in ("total",):
        if k not in t1:
            errs.append("nema ukupnih prihoda")
        if k not in t2:
            errs.append("nema ukupnih rashoda")
    if "equity" not in t3 or "cash" not in t3:
        errs.append("nema bilance (novac / vlastiti izvori)")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    parties: dict[str, dict] = {}
    problems = []
    for year in sorted(YEARS):
        reports = list_reports(year, args.refresh)
        ydir = RAW / str(year)
        ydir.mkdir(parents=True, exist_ok=True)
        print(f"{year}: {len(reports)} izvješća", flush=True)
        for title, path in reports:
            pdf = ydir / f"{slugify(title)}.pdf"
            url = SITE + urllib.parse.quote(path, safe="/~")
            if not pdf.exists() or args.refresh:
                pdf.write_bytes(get(url))
                time.sleep(0.3)
            rec = parse_report(pdf)
            errs = checks(rec)
            if errs:
                problems.append((year, title, errs))
            k = 1.0 / HRK if rec["unit"] == "HRK" else 1.0
            key = slugify(title)
            p = parties.setdefault(key, {"title": title, "years": {}})
            p["title"] = title  # najnoviji naziv
            t1, t2, t3 = rec["tables"][1], rec["tables"][2], rec["tables"][3]

            def val(t, name, col):
                v = t.get(name)
                return None if v is None or v[col] is None else round(v[col] * k, 2)

            for col, y in ((0, year - 1), (1, year)):
                if col == 0 and (str(y) in p["years"] or t1.get("total", [None])[0] is None):
                    continue  # tekući stupac vlastite revizije ima prednost; nova stranka nema prethodnu godinu
                p["years"][str(y)] = {
                    "source": url,
                    "audit_year": year,
                    "currency": rec["unit"],
                    "revenue": {n: val(t1, n, col) for n in ("state", "local", "members", "donations", "other", "total")},
                    "expenses": {n: val(t2, n, col) for n in ("staff", "promo", "material", "material_other",
                                                              "amortization", "financial", "donations", "other", "total")},
                    "result": round(((t2.get("surplus", [0, 0])[col] or 0) - (t2.get("deficit", [0, 0])[col] or 0)) * k, 2),
                    # Bilanca: stupac 0 = 1. siječnja (= 31. 12. prethodne), 1 = 31. prosinca.
                    "balance": {n: val(t3, n, col) for n in ("cash", "assets", "liabilities", "loans", "equity")},
                }
    for year, title, errs in problems:
        print(f"  ! {year} {title}: {'; '.join(errs)}")
    out = {
        "source": f"{SITE}/izvjesca/10",
        "note": "Državni ured za reviziju, izvješća o obavljenoj financijskoj reviziji političkih stranaka. "
                "Iznosi do 2022. preračunati iz kuna (7,53450). Bilanca je stanje 31. prosinca.",
        "parties": dict(sorted(parties.items())),
        "problems": [{"year": y, "title": t, "errors": e} for y, t, e in problems],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}: {len(parties)} stranaka, {len(problems)} izvješća s upozorenjima")
    return 0


if __name__ == "__main__":
    sys.exit(main())
