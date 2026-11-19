# Kvaliteta ekstrakcije i chunkinga programa (S2, 2026-11-19)

Naredba: `uv run python scripts/24_extract_programi.py --force --report`
(izlaz `data/raw/kompas/chunks.jsonl`, gitignored; brojke u `data/kompas/chunks_stats.json`).

## Ukupno

| Mjera | Vrijednost |
| --- | --- |
| Dokumenti | 37 (16 PDF, 21 HTML) |
| Stranice | 676 |
| Riječi | 264.946 |
| Chunkovi | 961, prosjek 280,4 riječi (min 80, max 653) |
| Prazne stranice (< 5 riječi) | 18 |
| Stranice bez teksta sa slikom (kandidati za OCR) | 10, sve naslovnice ili zadnje stranice; OCR nije potreban |
| Dokumenti sa sumnjivim udjelom dijakritika (< 3 %) | 0; najniži je IDS s 0,076 jer je napola talijanski |
| Sumnjivi znakovi nakon čišćenja | 0 (prije čišćenja: 159 znakova oznaka iz privatnog područja Unicodea i kombinirajući kvačice; popravljeni NFC-om) |
| Dokumenti s oznakom `nesiguran` | 9 |
| Veličina `chunks.jsonl` | 2.701.806 B |

Udio dijakritika je udio riječi malim slovima koje sadrže č, ć, đ, š ili ž.

Raspodjela veličina chunkova:

| Riječi | Chunkova |
| --- | --- |
| < 100 | 70 |
| 100–199 | 300 |
| 200–299 | 196 |
| 300–399 | 170 |
| 400–499 | 110 |
| 500–599 | 103 |
| 600 i više | 12 |

Kratkih chunkova ima mnogo jer su sekcije male. SDP-ove sekcije POLAZIŠTA, CILJEVI i MJERE imaju oko
150 riječi, što je iznad praga za spajanje od 80 riječi.

## SDP (provjera iz S1)

207 stranica, 21.283 izvučene riječi (S1 je izmjerio 22.699). Prazna je 1 stranica, a izlaz je
114 chunkova. Mali broj riječi po stranici svojstvo je dokumenta, koji ima grafički prijelom, a ne
greška ekstrakcije.

## Chunkova po stranci

Koalicijski dokumenti broje se za svaku stranku na dokumentu.

| Stranka | Chunkova |
| --- | --- |
| DP | 157 |
| Možemo | 152 |
| Centar | 129 |
| Reformisti | 122 |
| Dalija Orešković | 118 |
| GLAS | 117 |
| HSS | 114 |
| SDP | 114 |
| HDZ | 107 |
| Most | 95 |
| Socijaldemokrati | 57 |
| HNS | 46 |
| IDS | 37 |
| Laburisti | 32 |
| SDSS | 25 |
| Republika | 23 |
| Unija Kvarnera | 20 |
| DOMiNO | 16 |
| HSLS | 12 |
| ISU | 12 |
| Demokrati | 10 |
| Blok | 9 |
| Fokus | 9 |
| Drito | 8 |
| HSU | 8 |
| Nezavisni | 4 |
| Pravo i Pravda | 4 |
| Srđ je Grad | 4 |
| Hoćemo pravedno | 2 |
| Hrvatski suverenisti | 1 |
| NLM | 1 |
| Zurovec | 1 |

## Poznate mane (odluka 205)

- **IDS** (`5111e0ffaee2`): od otprilike 11. stranice slijedi talijanski prijevod, pa je oko polovice
  od 37 chunkova duplikat.
- **DP** (`7c54f0dd36a8`): prijelom je 2-up, a sadržaj je na 9. stranici sadržaja. Izvučeno je oko 96 %
  teksta, ali se ponegdje stupci isprepliću usred rečenice.
- **SDP**: neki dizajnerski naslovi su prelomljeni („NAŠE VRIJED NOSTI”). To utječe samo na nazive sekcija.
- **Nezavisni** (`42b55b04e20a`) i **NLM** (`3abc0adbc608`): stranice su tanke, a u nazive sekcija ulaze
  ostaci izbornika i newslettera.
- **HTML**: broj riječi odstupa od S1-ovog `rijeci` do +6 % (Republika), jer se blok elementi sada
  dijele na nove retke.

Tablica po dokumentu (stranice, prazne, riječi, chunkovi, udio dijakritika) je u `data/kompas/chunks_stats.json`.
