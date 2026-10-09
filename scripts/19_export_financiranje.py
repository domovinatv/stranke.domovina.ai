"""State funding of parliamentary parties in the 11th Sabor → static JSON.

Inputs (committed, see data/financiranje/README.md):
  * odluke.json        — every decision of the Odbor za Ustav, Poslovnik i
                         politički sustav (NN 74/24 … 11/26), transcribed
                         recipient by recipient from Narodne novine
  * izvjesca_cl11.json — the Sabor's annual čl. 11 reports (allocated + paid)
                         for 2024 and 2025, used as a cross-check
  * zastupnici.json    — currently seated MPs with gender and the list they
                         were elected on (scripts/18_fetch_sabor_zastupnici.py)

Funding is paid quarterly (ZFPAIP čl. 10). For each quarter of the 11th
convocation this picks the decision in force and takes its per-recipient
quarterly amount; the 16.5.–30.6.2024 stub comes from NN 74/2024. Quarters
that have ended by --as-of are summed into "received so far"; the current
year's full allocation is reported separately.

Output: frontend/public/data/financiranje.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.normalize import norm_key  # noqa: E402

SRC = ROOT / "data" / "financiranje"
DB = ROOT / "data" / "stranke.db"
OUT = ROOT / "frontend" / "public" / "data" / "financiranje.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("financiranje")

CONVOCATION_START = "2024-05-16"

# Which decision governs each payment period of the 11th convocation.
# Superseded decisions are listed in odluke.json; this is the in-force chain.
PERIODS = [
    ("2024-05-16", "2024-06-30", "74/2024", "amount_stub_2024_05_16_to_06_30_eur"),
    ("2024-07-01", "2024-09-30", "77/2024", "quarterly_amount_eur"),
    ("2024-10-01", "2024-12-31", "77/2024", "quarterly_amount_eur"),
    ("2025-01-01", "2025-03-31", "16/2025", "quarterly_amount_eur"),
    ("2025-04-01", "2025-06-30", "16/2025", "quarterly_amount_eur"),
    ("2025-07-01", "2025-09-30", "102/2025", "quarterly_amount_eur"),
    ("2025-10-01", "2025-12-31", "140/2025", "quarterly_amount_eur"),
    ("2026-01-01", "2026-03-31", "11/2026", "quarterly_amount_eur"),
    ("2026-04-01", "2026-06-30", "11/2026", "quarterly_amount_eur"),
    ("2026-07-01", "2026-09-30", "11/2026", "quarterly_amount_eur"),
    ("2026-10-01", "2026-12-31", "11/2026", "quarterly_amount_eur"),
]

# Ballot/decision names whose registry spelling differs beyond norm_key.
SLUG_OVERRIDES = {
    "Nezavisni": "nezavisni",  # stranka Nezavisni (Željko Lacković), DP-coalition list
}


def period_label(start: str) -> str:
    y, m, d = start.split("-")
    if start == CONVOCATION_START:
        return "16.5.–30.6.2024."
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=date.today().isoformat(),
                    help="count quarters that ended on or before this date (YYYY-MM-DD)")
    args = ap.parse_args()

    odluke = {o["nn"]: o for o in json.loads((SRC / "odluke.json").read_text())}
    izvjesca = json.loads((SRC / "izvjesca_cl11.json").read_text())
    seated = json.loads((SRC / "zastupnici.json").read_text())
    conn = sqlite3.connect(DB)
    catalog = catalog_index(conn)

    current = odluke[PERIODS[-1][2]]
    year = current["period_from"][:4]

    periods = []
    for start, end, nn, key in PERIODS:
        periods.append({
            "label": period_label(start),
            "from": start,
            "to": end,
            "nn": nn,
            "ended": end <= args.as_of,
            "amounts": {r["name"]: r[key] for r in odluke[nn]["recipients"]},
        })
    ended = [p for p in periods if p["ended"]]
    as_of = ended[-1]["to"]

    # Seated MPs → recipient. Funding follows the list, not the person, so an
    # MP who left the party that holds the mandate maps to no recipient.
    recipient_keys = {norm_key(r["name"]): r["name"] for r in current["recipients"]}
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
            rec = next((r["name"] for r in current["recipients"]
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

    parties = []
    for r in current["recipients"]:
        name = r["name"]
        by_period = {p["label"]: p["amounts"].get(name, 0.0) for p in periods}
        total = sum(p["amounts"].get(name, 0.0) for p in ended)
        hit = None if r["independent"] else (
            {"slug": SLUG_OVERRIDES[name], "short": None} if name in SLUG_OVERRIDES
            else catalog.get(norm_key(name))
        )
        if not r["independent"] and not hit:
            log.warning("no catalog match for %s", name)
        members = [m for m in mps if m["recipient"] == name]
        parties.append({
            "name": name,
            "slug": hit["slug"] if hit else None,
            "short": hit["short"] if hit else None,
            "independent": r["independent"],
            "mps_male": r["mps_male"],
            "mps_female": r["mps_female"],
            "month_eur": r2(r["quarterly_amount_eur"] / 3),
            "year_eur": r["amount_eur"],
            "total_eur": r2(total),
            "by_period": by_period,
            "seated_male": sum(m["gender"] == "M" for m in members),
            "seated_female": sum(m["gender"] == "F" for m in members),
        })
    parties.sort(key=lambda p: -p["total_eur"])

    # Cross-check against the Sabor's own čl. 11 report for 2025: our four
    # quarters must equal what the report says was allocated.
    checks = []
    rep25 = next(x for x in izvjesca if x["year"] == 2025)
    rep_by_key = {norm_key(x["name"].replace(" (NZ)", "")): x for x in rep25["recipients"]}
    for p in parties:
        ours = sum(v for k, v in p["by_period"].items() if k.endswith("/2025"))
        rep = rep_by_key.get(norm_key(p["name"]))
        diff = r2(ours - rep["allocated_eur"]) if rep else None
        checks.append({"name": p["name"], "ours": r2(ours),
                       "report_allocated": rep and rep["allocated_eur"],
                       "report_paid": rep and rep["paid_eur"], "diff": diff})
    worst = max(abs(c["diff"]) for c in checks if c["diff"] is not None)
    unmatched = [c["name"] for c in checks if c["diff"] is None]
    log.info("2025 cross-check vs čl. 11 report: max |diff| = %.2f EUR, unmatched: %s", worst, unmatched)
    if worst > 1 or unmatched:
        log.error("cross-check failed")
        return 1

    rates = []
    for nn in ("74/2024", "77/2024", "16/2025", "102/2025", "140/2025", "11/2026"):
        o = odluke[nn]
        rates.append({
            "nn": nn,
            "url": o["url"],
            "adopted": o["date_adopted"],
            "in_force": o["in_force"],
            "period_from": o["period_from"],
            "period_to": o["period_to"],
            "annual_budget_eur": o["annual_budget_eur"],
            "quarter_total_eur": o["quarterly_total_eur"],
            "mps_male": o["mps_male"],
            "mps_female": o["mps_female"],
            "quarter_m": o["amount_per_mp_eur"],
            "quarter_f": o["amount_per_mp_underrepresented_sex_eur"],
            "month_m": r2(o["amount_per_mp_eur"] / 3),
            "month_f": r2(o["amount_per_mp_underrepresented_sex_eur"] / 3),
        })

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": as_of,
        "year": year,
        "convocation_start": CONVOCATION_START,
        "totals": {
            "received_eur": r2(sum(p["total_eur"] for p in parties)),
            "year_eur": current["annual_budget_eur"],
            "month_eur": r2(current["quarterly_total_eur"] / 3),
            "mps_male": current["mps_male"],
            "mps_female": current["mps_female"],
            "seated": len(mps),
            "seated_female": sum(m["gender"] == "F" for m in mps),
        },
        "rates": rates,
        "periods": [{k: v for k, v in p.items() if k != "amounts"} for p in periods],
        "parties": parties,
        "mps": sorted(mps, key=lambda m: (m["recipient"] is None, m["name"])),
        "reports": [{"year": x["year"], "page_url": x["page_url"], "pdf_url": x["pdf_url"],
                     "allocated_eur": x["total_allocated_eur"], "paid_eur": x["total_paid_eur"]}
                    for x in izvjesca],
        "check_2025": checks,
        "seated_fetched_at": seated["fetched_at"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log.info("as of %s: %.2f EUR to %d recipients → %s",
             as_of, out["totals"]["received_eur"], len(parties), OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
