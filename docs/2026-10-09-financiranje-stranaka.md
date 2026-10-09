# Financiranje stranaka iz proračuna — bilješke iz izrade (2026-10-09)

Metoda, lanac odluka i postupak ažuriranja su u
[`data/financiranje/README.md`](../data/financiranje/README.md). Ovdje je ono
što bi sljedeći prolaz morao ponovno otkriti.

## Tok podataka

```mermaid
flowchart LR
  NN[Narodne novine<br/>odluke Odbora + izvještaji o izvršenju DP] -->|ručna transkripcija| J1[odluke.json<br/>porezni_prihodi.json]
  SAB[sabor.hr<br/>čl. 11 izvješća, skenirani PDF] -->|ručna transkripcija| J2[izvjesca_cl11.json]
  API[sabor.hr API + 150 profila] -->|18_fetch_sabor_zastupnici.py| J3[zastupnici.json]
  J1 & J2 & J3 --> S19[19_export_financiranje.py<br/>kontrola vs izvješća, projekcija]
  S19 --> F[frontend/public/data/financiranje.json] --> P[/financiranje]
```

## Ključne brojke (stanje 9. 10. 2026.)

| | |
|---|---|
| 10. saziv ukupno | 30.921.034,67 € (29 primatelja) |
| 11. saziv do 30. 9. 2026. | 27.558.188,39 € |
| 11. saziv procjena do 15. 5. 2028. | 49,89 mil. € (50,08 po trendu H1 2026.) |
| Mandat mjesečno M / Ž | 2020: 4.159 / 4.575 € · 2026: 7.009,81 / 7.710,79 € · 2027: 7.328,37 / 8.061,20 € |
| Godišnje svim strankama | 2026: 13.113.949 € (≈ 0,416 €/s) · 2027: 13.709.909,70 € |

## Zamke

- **NN pretraga ignorira tekst upita.** Radi samo sadržaj broja:
  `https://narodne-novine.nn.hr/search.aspx?sortiraj=4&kategorija=1&godina=YYYY&broj=N&rpp=500&qtype=1&pretraga=da`,
  tekst članka: `/clanci/sluzbeni/full/YYYY_MM_BROJ_CLANAK.html`. Potpunost se
  dokazuje pregledom svih brojeva godine.
- **Dvije odluke u istom broju** (NN 90/2020 čl. 1732 = kraj 9. saziva, čl.
  1733 = početak 10.) — ključ u JSON-u je `90/2020-1733`.
- **Tiskane brojke zastupnika znaju biti krive**: NN 107/2021 i NN 11/2022
  pišu HDZ 45+17, iznosi su računati na 46+16. Vjeruj iznosima.
- **Novac ne prati zastupnika** (čl. 7.): 15 od 150 današnjih zastupnika nije u
  stranci koja prima novac za njihov mandat (DOMiNO ×3, Drito ×2, nezavisni,
  Boška Ban: izabrana na SDP listi, danas HDZ). Pripisivanje provjerava i
  listu s koje je izabran(a) (`on_list`, 4-slovne osnove riječi zbog genitiva).
- **sabor.hr profili** su spori (~3 s po stranici, 150 profila ≈ 7 min) →
  cache u `data/raw/sabor/`; `--refresh` samo kad treba.
- **Deploy je pao na tuđem putu**: `src/wallet_alias.py` traži
  `clubs-app.json` iz `ss` repoa, koji je preseljen na
  `/Volumes/DOMOVINA2TB/git/ss/`. Sad postoji fallback i `STRANKE_CLUBS_JSON`.
- **OG tagovi su se duplicirali** u workeru (i na `/stranka/*`): `<head>`
  handler se izvrši prije nego rewriter vidi postojeće `<meta>`. Popravljeno
  ubacivanjem na `</head>` (`onEndTag`).
- **Playwright full-page screenshot ne učitava `loading="lazy"` slike** —
  fotografije zastupnika izgledaju prazne iako rade u pregledniku.
- `/data/*` ima `max-age=3600`: nakon deploya produkcijska domena može kratko
  vraćati stari JSON.

## Otvoreno

- Iznos za 2028. ovisi o ostvarenim poreznim prihodima 2026. (izvještaj ~srpanj 2027.).
- Nova odluka Odbora za 2027. očekuje se u siječnju 2027. (+ izmjene kad se
  promijeni omjer M/Ž) → dodati u `odluke.json` i `PERIODS`.
- „Stranka s imenom i prezimenom" (10. saziv) nema zapis u katalogu stranaka.
