# Pokrivenost programa stranaka (S1, 2026-11-19)

Mjerenje za vrata 1 Kompasa stranaka: koliko stranaka i lista iz opsega (odluka 2) ima
program koji se može citirati.

## Naredbe

```bash
uv run scripts/22_liste_2024.py          # → data/kompas/liste_2024.json
uv run scripts/23_fetch_programi.py      # → data/kompas/programi.json (raw u data/raw/programi/)
python3 - <<'EOF'                        # brojke ispod
import json; from collections import Counter
P = json.load(open('data/kompas/programi.json')); D = P['dokumenti']
print(Counter(x['vrsta'] for x in D), Counter(x['format'] for x in D), Counter(x['izvor'] for x in D))
print(sum(x['stranica'] or 0 for x in D), sum(x['rijeci'] or 0 for x in D))
print(Counter(s['status'] for s in P['stranke']))
EOF
```

Izvori koje je pregledao čovjek ili agent (koji URL je stvarno program) su u
`data/kompas/programi_izvori.json`; skripta samo dohvaća i mjeri. Firecrawl: 99 poziva.

## Opseg

- **8 lista s mandatima** (143 mandata) + **8 manjinskih mandata** = 151.
- **39 stranaka**: 36 članica lista, SDSS (manjinski) i 3 stranke sa zastupnicima izvan lista
  (DOMiNO, Drito, Dario Zurovec – NL). Svih 39 mapirano na `party_id` točnim podudaranjem.
- Bez `party_id`: DZMH, Kali Sara, Bošnjaci zajedno! (udruge), Radin i Bilek (grupe birača).

## Brojke

| Mjera | Vrijednost |
| --- | --- |
| Dokumenata | 37 (16 PDF, 21 HTML; 0 skeniranih) |
| Vrsta | 8 izborni-2024, 2 koalicijska, 27 trajnih |
| Izvor | 30 s web stranice stranke, 7 iz Wayback Machinea |
| PDF stranica ukupno | 655 |
| Riječi ukupno (pypdf / HTML tekst) | 269.605 |
| Stranke: pronađen (2024. i trajni) / djelomično / nije pronađen | 17 / 15 / 7 |
| Stranke s barem jednim programom | 32 od 39 |
| Koalicije sa zajedničkim programom | 2 od 8 (SDP – Rijeke pravde, Fokus – Republika) |

Program za 2024. po listi (dokument nositelja ili koalicije):

| Lista | Mandati | Program 2024. |
| --- | --- | --- |
| HDZ, HSLS, HDS, HNS, HSU | 61 | HDZ (69 str.) + HSLS zasebno |
| SDP, Centar, HSS, DO i SIP, Reformisti, GLAS | 42 | koalicijski (207 str., 22.699 riječi) |
| DP, Pravo i pravda | 14 | DP (40 str.) |
| Most, Suverenisti, HKS, NLM | 11 | Most (61 str.) + Suverenisti (444 riječi) |
| Možemo! | 10 | Možemo! (96 str.) |
| IDS, PGS, Unija… | 2 | **nema** (samo trajni IDS) |
| NPS | 2 | **nema** (ništa) |
| Fokus, Republika | 1 | koalicijski (14 str.) |

**6 od 8 lista (139 od 143 mandata) ima program za 2024.**

Bez ikakvog programa (7): Agrameri, DHSS, HDS, HKS, NPS, PGS, Zelena lista.

## Otvorena pitanja (odlučuje korisnik, vrata 1)

1. **Programi nositelja i partneri.** Programi HDZ-a, DP-a, Mosta i Možemo ne spominju partnere.
   Sada su samo program nositelja (`list_id` postavljen, partneri nisu pripojeni). Ako se pripoje,
   pokrivenost partnera skače, ali stav nositelja tada vrijedi za partnera.
2. **Trajni programi su vrlo neujednačeni**: od 151 riječi (NLM) do 22.640 (HNS). Kratke
   deklaracije neće imati stav o većini tvrdnji (`null`), što je odluka 4 i dopušteno.
3. **SDP-ov PDF** ima 207 stranica, ali samo 22.699 riječi (≈ 110 po stranici): vjerojatno
   prezentacijski prijelom; S2 provjerava ekstrakciju. Jedina potpuna kopija je s
   grabancijas.com (izvorni URL SDP-a nije pronađen ni u Waybacku).
4. **OCR**: nijedan PDF nije skeniran, pa OCR za sada nije potreban.
5. Nesigurne odluke agenta (Suverenisti 24 kao izborni program, „Ozbiljno za Hrvatsku” za
   Socijaldemokrate i Laburiste, Wayback snimke za Pravo i pravda, Fokus i Nezavisne, HSS samo
   statut pa nije prihvaćen) zapisane su u `programi_izvori.json` (`napomena`).
