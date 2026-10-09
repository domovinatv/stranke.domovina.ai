#!/usr/bin/env python3
"""Inflacija i BDP Hrvatske s Eurostata → data/financiranje/makro.json.

Uz porezne prihode (porezni_prihodi.json) stranica /financiranje pokazuje
koliko su rasle cijene i gospodarstvo, pa se vidi raste li novac strankama
brže ili sporije od njih. Iznos za stranke prati porezne prihode (čl. 5.),
a ne inflaciju ni BDP; ovo je samo usporedba.

Serije (Eurostat dissemination API, geo=HR):
  prc_hicp_aind  CP00 RCH_A_AVG      HICP, prosječna godišnja stopa (%)
  nama_10_gdp    B1GQ CP_MEUR        BDP u tekućim cijenama (mil. €; prije 2023. preračunato 7,53450)
  nama_10_gdp    B1GQ CLV_PCH_PRE    realni rast BDP-a (%)

    python3 scripts/20_fetch_eurostat_makro.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "financiranje" / "makro.json"
RAW = ROOT / "data" / "raw" / "financiranje" / "eurostat"
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
FROM_YEAR = 2016

SERIES = {
    "hicp_pct": ("prc_hicp_aind", "coicop=CP00&unit=RCH_A_AVG",
                 "https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_aind/default/table?lang=en"),
    "gdp_nominal_meur": ("nama_10_gdp", "na_item=B1GQ&unit=CP_MEUR",
                         "https://ec.europa.eu/eurostat/databrowser/view/nama_10_gdp/default/table?lang=en"),
    "gdp_real_pct": ("nama_10_gdp", "na_item=B1GQ&unit=CLV_PCH_PRE",
                     "https://ec.europa.eu/eurostat/databrowser/view/nama_10_gdp/default/table?lang=en"),
}


def fetch(key: str, dataset: str, query: str) -> tuple[dict[int, float], str | None]:
    url = f"{API}/{dataset}?geo=HR&{query}&format=JSON&lang=EN"
    with urllib.request.urlopen(url, timeout=60) as r:
        body = r.read()
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{key}.json").write_bytes(body)
    d = json.loads(body)
    pos = {v: k for k, v in d["dimension"]["time"]["category"]["index"].items()}
    vals = {int(pos[int(i)]): v for i, v in d["value"].items()}
    return {y: v for y, v in sorted(vals.items()) if y >= FROM_YEAR}, d.get("updated")


def main() -> int:
    series, sources = {}, {}
    for key, (dataset, query, page) in SERIES.items():
        series[key], updated = fetch(key, dataset, query)
        sources[key] = {"dataset": dataset, "query": f"geo=HR&{query}", "page": page, "updated": updated}
        print(f"{key}: {min(series[key])}–{max(series[key])}, updated {updated}")
    years = sorted(set().union(*series.values()))
    out = {
        "retrieved": date.today().isoformat(),
        "sources": sources,
        "notes": [
            "Inflacija je HICP (harmonizirani indeks potrošačkih cijena, Eurostat), ne nacionalni CPI DZS-a; razlika je obično nekoliko desetinki postotnog boda.",
            "BDP prije 2023. Eurostat iskazuje u eurima preračunom fiksnim tečajem 7,53450 kn/€, isto kao porezne prihode.",
            "Zadnje godine BDP-a su privremene i Eurostat ih revidira.",
        ],
        "years": [{"year": y, **{k: series[k].get(y) for k in SERIES}} for y in years],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
