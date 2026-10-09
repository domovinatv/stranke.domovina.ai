"""State funding of parliamentary parties, 10th and 11th Sabor → static JSON.

Inputs (committed, see data/financiranje/README.md):
  * odluke.json          — every decision of the Odbor za Ustav, Poslovnik i
                           politički sustav (NN 7/20 … 11/26), transcribed
                           recipient by recipient from Narodne novine
  * izvjesca_cl11.json   — the Sabor's annual čl. 11 reports (allocated +
                           paid) for 2020–2025, used as a cross-check
  * zastupnici.json      — currently seated MPs with gender and the list they
                           were elected on (scripts/18_fetch_sabor_zastupnici.py)
  * porezni_prihodi.json — state-budget tax revenue by year (ostvareno / plan),
                           the base of the projection to the end of the 11th
                           convocation

Funding is paid quarterly (ZFPAIP čl. 10). For each quarter of a convocation
this picks the decision in force and takes its per-recipient quarterly amount;
partial quarters at the start/end of a convocation come from the decision's
stub column or a day-share factor. Kuna amounts (decisions before 2023) are
converted at the fixed rate 7.53450 HRK/EUR.

The 11th convocation is projected to its end (15.5.2028): the yearly total is
0.075 % of the tax revenue reported two years earlier (čl. 5), split by the
current decision's weighted seats (M + 1.1 × Ž).

Output: frontend/public/data/financiranje.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.normalize import norm_key  # noqa: E402

SRC = ROOT / "data" / "financiranje"
MAKRO = SRC / "makro.json"  # scripts/20_fetch_eurostat_makro.py
REVIZIJA = SRC / "revizija_stranke.json"  # scripts/21_fetch_revizija_stranke.py
KREDITI = SRC / "krediti.json"  # ručno iz poglavlja „Obveze“ revizijskih izvješća

# Naslovi revizijskih izvješća koji se razlikuju od naziva u odlukama.
AUDIT_ALIASES = {
    "HRVATSKA NARODA STRANKA – LIBERALNI DEMOKRATI": "Hrvatska narodna stranka – liberalni demokrati",
    "HRVATSKA NARODNA STRANKA": "Hrvatska narodna stranka – liberalni demokrati",
    "HRVATSKA KONZERVATIVNA STANKA": "Hrvatska konzervativna stranka",
    "HRAST": "HRAST – pokret za uspješnu Hrvatsku",
    "NARODNA STRANKA - REFORMISTI": "Narodna stranka – Reformisti",
}
DB = ROOT / "data" / "stranke.db"
OUT = ROOT / "frontend" / "public" / "data" / "financiranje.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("financiranje")

HRK_PER_EUR = 7.53450
FUNDING_SHARE = 0.00075  # čl. 5: 0,075 % ostvarenih poreznih prihoda
FEMALE_WEIGHT = 1.1      # čl. 9: +10 % za podzastupljeni spol

# 1.4.–15.5.2024 had no decision of its own: the 10th convocation got what
# was left of Q2 after NN 74/2024's 16.5.–30.6. stub (2024 čl. 11 report:
# 7,719.92 + 7,890.53 = 15,610.45 per MP).
STUB_2024_10TH = 7719.92 / 15610.45
# The 11th convocation's mandate runs to 15.5.2028, mirroring 2024: 45 of the
# 91 days of Q2 in a leap year.
STUB_2028 = 45 / 91

Q = "quarterly_amount_eur"

# (from, to, decision, amount column, factor) — the in-force chain per
# convocation; superseded decisions stay in odluke.json for reference.
CONVOCATIONS = {
    10: {
        "label": "10. saziv",
        "start": "2020-07-22",
        "end": "2024-05-15",
        "periods": [
            ("2020-07-22", "2020-09-30", "90/2020-1733", "amount_stub_2020_07_22_to_09_30_eur", 1),
            ("2020-10-01", "2020-12-31", "90/2020-1733", Q, 1),
            ("2021-01-01", "2021-03-31", "6/2021", Q, 1),
            ("2021-04-01", "2021-06-30", "6/2021", Q, 1),
            ("2021-07-01", "2021-09-30", "78/2021", Q, 1),
            ("2021-10-01", "2021-12-31", "107/2021", Q, 1),
            ("2022-01-01", "2022-03-31", "11/2022", Q, 1),
            ("2022-04-01", "2022-06-30", "11/2022", Q, 1),
            ("2022-07-01", "2022-09-30", "78/2022", Q, 1),
            ("2022-10-01", "2022-12-31", "115/2022", Q, 1),
            ("2023-01-01", "2023-03-31", "146/2022", Q, 1),
            ("2023-04-01", "2023-06-30", "37/2023", Q, 1),
            ("2023-07-01", "2023-09-30", "73/2023", Q, 1),
            ("2023-10-01", "2023-12-31", "73/2023", Q, 1),
            ("2024-01-01", "2024-03-31", "8/2024", Q, 1),
            ("2024-04-01", "2024-05-15", "8/2024", Q, STUB_2024_10TH),
        ],
        "reports": (2021, 2022, 2023),
    },
    11: {
        "label": "11. saziv",
        "start": "2024-05-16",
        "end": "2028-05-15",
        "periods": [
            ("2024-05-16", "2024-06-30", "74/2024", "amount_stub_2024_05_16_to_06_30_eur", 1),
            ("2024-07-01", "2024-09-30", "77/2024", Q, 1),
            ("2024-10-01", "2024-12-31", "77/2024", Q, 1),
            ("2025-01-01", "2025-03-31", "16/2025", Q, 1),
            ("2025-04-01", "2025-06-30", "16/2025", Q, 1),
            ("2025-07-01", "2025-09-30", "102/2025", Q, 1),
            ("2025-10-01", "2025-12-31", "140/2025", Q, 1),
            ("2026-01-01", "2026-03-31", "11/2026", Q, 1),
            ("2026-04-01", "2026-06-30", "11/2026", Q, 1),
            ("2026-07-01", "2026-09-30", "11/2026", Q, 1),
            ("2026-10-01", "2026-12-31", "11/2026", Q, 1),
        ],
        "reports": (2025,),
    },
}

# Same recipient under different names across decisions → latest name.
RENAMES = {
    "Pametno": "Centar",
    "Most nezavisnih lista": "Most",
    "Domovinski pokret Miroslava Škore": "Domovinski pokret",
    "Možemo – politička platforma": "Možemo! – Politička platforma",
    "Možemo-politička platforma": "Možemo! – Politička platforma",
    "Ermina Lekaj – Prljaskaj": "Ermina Lekaj-Prljaskaj",
}
_RENAMES = {norm_key(k): v for k, v in RENAMES.items()}

# Ballot/decision names whose registry spelling differs beyond norm_key.
SLUG_OVERRIDES = {
    "Nezavisni": "nezavisni",  # stranka Nezavisni (Željko Lacković), DP-coalition list
}


# norm_key → spelling from the latest decision; filled by load_canon().
_SPELLING: dict[str, str] = {}


def load_canon(odluke: list[dict]) -> None:
    for o in sorted(odluke, key=lambda o: o["date_adopted"]):
        for r in o["recipients"]:
            name = _RENAMES.get(norm_key(r["name"]), r["name"])
            _SPELLING[norm_key(name)] = name


def canon(name: str) -> str:
    name = _RENAMES.get(norm_key(name), name)
    return _SPELLING.get(norm_key(name), name)


def fmt_day(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)}.{int(m)}."


def period_label(start: str, end: str) -> str:
    y, m, d = start.split("-")
    if d != "01" or end[5:] not in ("03-31", "06-30", "09-30", "12-31"):
        return f"{fmt_day(start)}–{fmt_day(end)}{y}."
    return f"Q{(int(m) - 1) // 3 + 1}/{y}"


def catalog_index(conn: sqlite3.Connection) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    rows = conn.execute(
        "SELECT slug, canonical_name, short_name FROM parties ORDER BY status = 'AKTIVAN'"
    ).fetchall()
    for slug, name, short in rows:
        idx[norm_key(name)] = {"slug": slug, "short": short}
    for alias, slug, short in conn.execute(
        "SELECT a.alias, p.slug, p.short_name FROM party_aliases a JOIN parties p ON p.id = a.party_id"
    ):
        idx.setdefault(norm_key(alias), {"slug": slug, "short": short})
    return idx


def on_list(party: str, elected_on: str | None) -> bool:
    """Is `party` one of the proposers of the list the MP was elected on?

    The profile names the list in the genitive ("lista Hrvatske demokratske
    zajednice, …"), so compare 4-letter word stems of the party name against
    word prefixes of the list text.
    """
    words = norm_key(elected_on or "").split()
    stems = [w[:4] for w in norm_key(party).split() if len(w) >= 4]
    return bool(stems) and all(any(w.startswith(st) for w in words) for st in stems)


def r2(x: float) -> float:
    return round(x + 1e-9, 2)


def to_eur(amount: float, currency: str) -> float:
    return amount / HRK_PER_EUR if currency == "HRK" else amount


def rate_row(o: dict) -> dict:
    cur = o.get("currency", "EUR")
    return {
        "nn": o["nn"].split("-")[0],
        "url": o["url"],
        "adopted": o["date_adopted"],
        "in_force": o["in_force"],
        "period_from": o["period_from"],
        "period_to": o["period_to"],
        "currency": cur,
        "annual_budget_eur": r2(to_eur(o["annual_budget_eur"], cur)),
        "quarter_total_eur": r2(to_eur(o["quarterly_total_eur"], cur)),
        "mps_male": o["mps_male"],
        "mps_female": o["mps_female"],
        "quarter_m": r2(to_eur(o["amount_per_mp_eur"], cur)),
        "quarter_f": r2(to_eur(o["amount_per_mp_underrepresented_sex_eur"], cur)),
        "month_m": r2(to_eur(o["amount_per_mp_eur"], cur) / 3),
        "month_f": r2(to_eur(o["amount_per_mp_underrepresented_sex_eur"], cur) / 3),
    }


def build_convocation(cid: int, odluke: dict, as_of: str, catalog: dict) -> dict:
    conf = CONVOCATIONS[cid]
    periods = []
    for start, end, nn, key, factor in conf["periods"]:
        o = odluke[nn]
        cur = o.get("currency", "EUR")
        raw = defaultdict(float)
        for r in o["recipients"]:
            raw[canon(r["name"])] += r[key] * factor
        periods.append({
            "label": period_label(start, end),
            "from": start,
            "to": end,
            "nn": nn.split("-")[0],
            "ended": end <= as_of,
            "currency": cur,
            "raw": dict(raw),
            "amounts": {k: to_eur(v, cur) for k, v in raw.items()},
        })
    ended = [p for p in periods if p["ended"]]

    last = odluke[conf["periods"][-1][2]]
    seats = {canon(r["name"]): r for r in last["recipients"]}
    names = list(dict.fromkeys(n for p in periods for n in p["amounts"]))
    parties = []
    for name in names:
        r = seats.get(name)
        independent = r["independent"] if r else any(
            rr["independent"] for p in conf["periods"] for rr in odluke[p[2]]["recipients"] if canon(rr["name"]) == name
        )
        hit = None if independent else (
            {"slug": SLUG_OVERRIDES[name], "short": None} if name in SLUG_OVERRIDES
            else catalog.get(norm_key(name))
        )
        if not independent and not hit:
            log.warning("[%d] no catalog match for %s", cid, name)
        cur = last.get("currency", "EUR")
        parties.append({
            "name": name,
            "slug": hit["slug"] if hit else None,
            "short": hit["short"] if hit else None,
            "independent": independent,
            "mps_male": r["mps_male"] if r else 0,
            "mps_female": r["mps_female"] if r else 0,
            "month_eur": r2(to_eur(r[Q], cur) / 3) if r else 0.0,
            "year_eur": r2(to_eur(r["amount_eur"], cur)) if r and last["period_from"].endswith("01-01") else None,
            "total_eur": r2(sum(p["amounts"].get(name, 0.0) for p in ended)),
            "by_period": {p["label"]: r2(p["amounts"].get(name, 0.0)) for p in periods},
        })
    parties.sort(key=lambda p: -p["total_eur"])

    nns = list(dict.fromkeys(p[2] for p in conf["periods"]))
    return {
        "id": cid,
        "label": conf["label"],
        "start": conf["start"],
        "end": conf["end"],
        "periods": periods,
        "parties": parties,
        "rates": [rate_row(odluke[nn]) for nn in nns],
        "received_eur": r2(sum(p["total_eur"] for p in parties)),
        "mps_male": last["mps_male"],
        "mps_female": last["mps_female"],
    }


def check_reports(conv: dict, izvjesca: list[dict]) -> list[dict]:
    """Our quarter sums per calendar year vs the Sabor's čl. 11 'raspoređeno'."""
    out = []
    for year in CONVOCATIONS[conv["id"]]["reports"]:
        rep = next(x for x in izvjesca if x["year"] == year)
        rep_by = {norm_key(canon(x["name"].replace(" (NZ)", ""))): x for x in rep["recipients"]}
        for p in conv["parties"]:
            ours = sum(per["raw"].get(p["name"], 0.0) for per in conv["periods"] if per["from"][:4] == str(year))
            if not ours:
                continue
            x = rep_by.get(norm_key(p["name"]))
            out.append({"year": year, "name": p["name"], "ours": r2(ours),
                        "report": x and x["allocated_eur"],
                        "diff": r2(ours - x["allocated_eur"]) if x else None})
    return out


def check_2024(convs: dict, izvjesca: list[dict]) -> float:
    """2024 is split between both convocations; the report has the sum."""
    rep = next(x for x in izvjesca if x["year"] == 2024)
    worst = 0.0
    for x in rep["recipients"]:
        key = norm_key(canon(x["name"].replace(" (NZ)", "")))
        ours = sum(per["amounts"].get(p["name"], 0.0)
                   for c in convs.values() for p in c["parties"] if norm_key(p["name"]) == key
                   for per in c["periods"] if per["from"][:4] == "2024")
        worst = max(worst, abs(ours - x["allocated_eur"]))
    return worst


def build_projection(conv: dict, odluke: dict, taxes: dict, h1: dict | None) -> dict:
    """Project the 11th convocation from the last known decision to 15.5.2028."""
    last = odluke[CONVOCATIONS[11]["periods"][-1][2]]
    weights = {canon(r["name"]): r["mps_male"] + FEMALE_WEIGHT * r["mps_female"] for r in last["recipients"]}
    total_w = sum(weights.values())
    known_last_year = int(last["period_from"][:4])

    years = []
    for year in range(known_last_year + 1, int(CONVOCATIONS[11]["end"][:4]) + 1):
        t = taxes.get(year - 2)
        if not t:
            log.warning("no tax revenue for %d → projection stops before %d", year - 2, year)
            break
        annual = r2(t["tax_revenue_eur"] * FUNDING_SHARE)
        quarters = 4 if year < 2028 else 1 + STUB_2028
        # Alternative for a not-yet-realised base year: last realised year
        # grown by the first-half trend of the base year.
        alt = None
        if t["kind"] != "ostvareno" and h1 and h1["year"] == year - 2 and taxes.get(year - 3, {}).get("kind") == "ostvareno":
            alt_rev = taxes[year - 3]["tax_revenue_eur"] * (1 + h1["growth"])
            alt = {"tax_revenue_eur": r2(alt_rev), "growth": h1["growth"],
                   "amount_eur": r2(alt_rev * FUNDING_SHARE / 4 * quarters)}
        years.append({
            "alt": alt,
            "year": year,
            "tax_year": year - 2,
            "tax_revenue_eur": t["tax_revenue_eur"],
            "tax_kind": t["kind"],
            "tax_source": t.get("source_url"),
            "tax_note": t.get("note"),
            "annual_eur": annual,
            "quarters": quarters,
            "amount_eur": r2(annual / 4 * quarters),
            "month_m": r2(annual / 4 / total_w / 3),
            "month_f": r2(annual / 4 / total_w * FEMALE_WEIGHT / 3),
        })

    open_periods = [p for p in conv["periods"] if not p["ended"]]
    parties = {}
    for p in conv["parties"]:
        share = weights.get(p["name"], 0.0) / total_w
        by_year = {str(y["year"]): r2(y["amount_eur"] * share) for y in years}
        rest = r2(sum(per["amounts"].get(p["name"], 0.0) for per in open_periods))
        projected = r2(rest + sum(by_year.values()))
        alt_extra = sum((y["alt"]["amount_eur"] - y["amount_eur"]) * share for y in years if y["alt"])
        parties[p["name"]] = {
            "open_eur": rest,
            "by_year": by_year,
            "projected_eur": projected,
            "saziv_total_eur": r2(p["total_eur"] + projected),
            "saziv_total_alt_eur": r2(p["total_eur"] + projected + alt_extra),
        }
    return {
        "end": CONVOCATIONS[11]["end"],
        "open_periods": [p["label"] for p in open_periods],
        "years": years,
        "parties": parties,
        "projected_eur": r2(sum(v["projected_eur"] for v in parties.values())),
        "saziv_total_eur": r2(sum(v["saziv_total_eur"] for v in parties.values())),
        "saziv_total_alt_eur": r2(sum(v["saziv_total_alt_eur"] for v in parties.values())),
        "h1": h1,
        "assumptions": [
            "Godišnji iznos = 0,075 % poreznih prihoda iz izvještaja o izvršenju proračuna za godinu N−2 (čl. 5.).",
            f"Raspodjela po mandatima iz odluke NN {last['nn']} (M + 1,1 × Ž); zamjene zastupnika i promjene omjera spolova nisu predviđene.",
            "Mandat traje do 15. 5. 2028.; drugo tromjesečje 2028. računa se razmjerno (45/91 dana), kao 2024.",
        ],
    }


def build_audits(convs: dict) -> dict | None:
    """Revidirani prihodi, rashodi i bilanca stranaka koje primaju novac u 10. ili 11. sazivu."""
    if not REVIZIJA.exists():
        return None
    doc = json.loads(REVIZIJA.read_text())
    recipients: dict[str, dict] = {}
    for cid in (10, 11):  # 11. saziv prepisuje slug/kraticu iz 10.
        for p in convs[cid]["parties"]:
            if not p["independent"]:
                recipients[norm_key(p["name"])] = {"name": p["name"], "slug": p["slug"], "short": p["short"]}
    current = {norm_key(p["name"]) for p in convs[11]["parties"]}
    by_name: dict[str, dict] = {}
    for a in doc["parties"].values():
        title = AUDIT_ALIASES.get(a["title"], a["title"])
        key = norm_key(canon(title))
        if key not in recipients:
            continue
        r = recipients[key]
        entry = by_name.setdefault(r["name"], {**r, "current": key in current, "years": {}})
        entry["years"].update(a["years"])
    missing = sorted(set(r["name"] for r in recipients.values()) - set(by_name))
    if missing:
        log.info("revizija: nema izvješća za %s", ", ".join(missing))
    parties = sorted(by_name.values(), key=lambda e: -max((y["revenue"]["total"] or 0) for y in e["years"].values()))
    for e in parties:
        e["years"] = dict(sorted(e["years"].items()))
    loans = None
    if KREDITI.exists():
        kd = json.loads(KREDITI.read_text())
        names = {e["name"] for e in parties}
        unknown = [x["party"] for x in kd["loans"] if x["party"] not in names]
        if unknown:
            raise SystemExit(f"krediti.json: nepoznate stranke {unknown}")
        src = {e["name"]: e["years"].get(kd["as_of"][:4], {}).get("source") for e in parties}
        loans = {**kd, "loans": [{**x, "source_url": src[x["party"]]} for x in kd["loans"]]}
    return {"source": doc["source"], "note": doc["note"], "parties": parties, "missing": missing, "loans": loans}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=date.today().isoformat(),
                    help="count quarters that ended on or before this date (YYYY-MM-DD)")
    args = ap.parse_args()

    odluke_list = json.loads((SRC / "odluke.json").read_text())
    load_canon(odluke_list)
    odluke = {o["nn"]: o for o in odluke_list}
    izvjesca = json.loads((SRC / "izvjesca_cl11.json").read_text())
    seated = json.loads((SRC / "zastupnici.json").read_text())
    tax_path = SRC / "porezni_prihodi.json"
    taxes, h1 = {}, None
    if tax_path.exists():
        tax_doc = json.loads(tax_path.read_text())
        h1 = tax_doc.get("h1")
        for y in tax_doc["years"]:
            # Prefer realised revenue over a plan for the same year.
            if y["year"] not in taxes or y["kind"] == "ostvareno":
                taxes[y["year"]] = y
    catalog = catalog_index(sqlite3.connect(DB))

    convs = {cid: build_convocation(cid, odluke, args.as_of, catalog) for cid in CONVOCATIONS}
    cur11 = convs[11]

    checks = []
    for c in convs.values():
        checks += check_reports(c, izvjesca)
    bad = [c for c in checks if c["diff"] is None or abs(c["diff"]) > 1]
    worst = max(abs(c["diff"]) for c in checks if c["diff"] is not None)
    worst24 = check_2024(convs, izvjesca)
    log.info("čl. 11 cross-check: %d rows, max |diff| = %.2f (report currency); 2024 split: %.2f EUR",
             len(checks), worst, worst24)
    if bad or worst24 > 1:
        log.error("cross-check failed: %s", bad[:5])
        return 1

    # Seated MPs → recipient in the 11th convocation's current decision.
    current = odluke[CONVOCATIONS[11]["periods"][-1][2]]
    recipient_keys = {norm_key(r["name"]): canon(r["name"]) for r in current["recipients"]}
    per_q_m = current["amount_per_mp_eur"]
    per_q_f = current["amount_per_mp_underrepresented_sex_eur"]
    mps = []
    for m in seated["mps"]:
        rec = recipient_keys.get(norm_key(m["party_full"] or "")) or recipient_keys.get(norm_key(m["name"]))
        note = None
        if m["party_full"] == "stranka Nezavisni":
            rec = "Nezavisni"
        # An MP who switched party (e.g. elected on the SDP coalition list,
        # now in HDZ) still funds the list's proposer, not the new party.
        if rec and not m["minority"] and not on_list(rec, m["elected_on"]):
            log.info("%s: member of %s but elected on %s", m["name"], rec, m["elected_on"])
            rec, note = None, "switched"
        if rec is None and m["minority"] and "zamjen" in (m.get("mandate_changes") or ""):
            # A minority substitute; the decision still names the MP replaced.
            rec = next((canon(r["name"]) for r in current["recipients"]
                        if r["independent"] and on_list(r["name"], m["mandate_changes"])), None)
            note = "substitute" if rec else None
        if rec is None and note is None:
            note = "switched"
        q = per_q_f if m["gender"] == "F" else per_q_m
        mps.append({
            "name": m["name"],
            "gender": m["gender"],
            "party": m["party"],
            "party_full": m["party_full"],
            "club": m["club"],
            "elected_on": m["elected_on"],
            "constituency": m["constituency"],
            "mandate_start": m["mandate_start"],
            "minority": m["minority"],
            "img": m["img"],
            "profile": m["profile"],
            "recipient": rec,
            "recipient_note": note,
            "mandate_changes": m.get("mandate_changes"),
            "seat_month_eur": r2(q / 3),
        })
    for p in cur11["parties"]:
        members = [m for m in mps if m["recipient"] == p["name"]]
        p["seated_male"] = sum(m["gender"] == "M" for m in members)
        p["seated_female"] = sum(m["gender"] == "F" for m in members)

    projection = build_projection(cur11, odluke, taxes, h1)
    ended11 = [p for p in cur11["periods"] if p["ended"]]

    def strip(c: dict) -> dict:
        return {**c, "periods": [{k: v for k, v in p.items() if k not in ("raw", "amounts")} for p in c["periods"]]}

    prev = strip(convs[10])
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": ended11[-1]["to"],
        "year": current["period_from"][:4],
        "convocation_start": cur11["start"],
        "totals": {
            "received_eur": cur11["received_eur"],
            "year_eur": current["annual_budget_eur"],
            "month_eur": r2(current["quarterly_total_eur"] / 3),
            "mps_male": current["mps_male"],
            "mps_female": current["mps_female"],
            "seated": len(mps),
            "seated_female": sum(m["gender"] == "F" for m in mps),
        },
        "rates": cur11["rates"],
        "periods": strip(cur11)["periods"],
        "parties": cur11["parties"],
        "mps": sorted(mps, key=lambda m: (m["recipient"] is None, m["name"])),
        "projection": projection,
        "previous": prev,
        "taxes": [taxes[y] for y in sorted(taxes)],
        "macro": json.loads(MAKRO.read_text()) if MAKRO.exists() else None,
        "audits": build_audits(convs),
        "reports": [{"year": x["year"], "page_url": x["page_url"], "pdf_url": x["pdf_url"],
                     "currency": x.get("currency", "EUR"),
                     "allocated_eur": r2(to_eur(x["total_allocated_eur"], x.get("currency", "EUR"))),
                     "paid_eur": r2(to_eur(x["total_paid_eur"], x.get("currency", "EUR")))}
                    for x in sorted(izvjesca, key=lambda x: x["year"])],
        "checks": {"rows": len(checks), "max_diff": worst, "split_2024_max_diff": r2(worst24)},
        "seated_fetched_at": seated["fetched_at"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("10th: %.2f EUR to %d recipients; 11th as of %s: %.2f EUR, projected +%.2f → %.2f EUR",
             prev["received_eur"], len(prev["parties"]), out["as_of"], cur11["received_eur"],
             projection["projected_eur"], projection["saziv_total_eur"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
