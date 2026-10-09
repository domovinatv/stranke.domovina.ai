# Financiranje parlamentarnih stranaka iz državnog proračuna

Ulazni podaci za stranicu `/financiranje` (https://stranke.domovina.ai/financiranje).
Izračun: `scripts/19_export_financiranje.py` → `frontend/public/data/financiranje.json`.

## Pravna osnova

Zakon o financiranju političkih aktivnosti, izborne promidžbe i referenduma
(NN 29/19, 98/19):

- **čl. 5.** — za redovito godišnje financiranje stranaka i nezavisnih
  zastupnika osigurava se **0,075 % ostvarenih poreznih prihoda** iz
  prethodno objavljenog godišnjeg izvještaja o izvršenju proračuna.
- **čl. 7.** — jednak iznos po zastupniku; novac ide stranci **predlagateljici
  liste prema konačnim rezultatima izbora**, ne prema današnjoj stranačkoj
  pripadnosti zastupnika.
- **čl. 9.** — za svakog zastupnika podzastupljenog spola (< 40 % u Saboru)
  pripada još **10 %**. U 11. sazivu to su uvijek žene (49–51 od 151).
- **čl. 10.** — odluku donosi Odbor za Ustav, Poslovnik i politički sustav;
  isplata tromjesečno, razmjerno danima kad mandat ne počinje s tromjesečjem.
- **čl. 11.** — Sabor do 1. ožujka objavljuje izvješće o raspoređenim i
  isplaćenim sredstvima za prethodnu godinu.

Formula u svakoj odluci: `iznos po zastupniku = tromjesečni iznos / (M + 1,1 × Ž)`;
reproducira objavljeni iznos u lipu.

## Pravilo N−2

Iznos za godinu N = 0,075 % poreznih prihoda državnog proračuna (skupina
računa 61) ostvarenih u godini N−2: izvještaj o izvršenju za N−2 objavljuje se
u NN ljeti godine N−1, prije donošenja proračuna za N. Provjereno za
2020.–2026. (`porezni_prihodi.json` → `funding_check`).

## Datoteke

| Datoteka | Izvor | Kako nastaje |
|---|---|---|
| `odluke.json` | Narodne novine: NN 8/24, 74/24, 77/24, 16/25, 102/25, 140/25, 11/26 | ručna transkripcija svakog primatelja; zbroj = ukupni iznos ±0,08 € |
| `izvjesca_cl11.json` | sabor.hr, izvješća po čl. 11. za 2024. i 2025. (skenirani PDF-ovi bez tekstualnog sloja) | ručna transkripcija |
| `porezni_prihodi.json` | godišnji izvještaji o izvršenju DP 2017.–2025. (NN), plan 2026. i projekcije 2027.–2028. (NN 152/2025), polugodišnji izvještaj 2026. | ručno iz NN; iznosi do 2022. u kunama preračunati 7,53450 |
| `zastupnici.json` | sabor.hr API interaktivne sabornice + profil svakog zastupnika | `scripts/18_fetch_sabor_zastupnici.py` |

Sirovi HTML/PDF izvornici su u `data/raw/financiranje/` i `data/raw/sabor/`
(gitignorirano).

Potpunost odluka provjerena je pregledom sadržaja svakog broja NN od 1/2024 do
114/2026. Potpunost za 10. saziv: pregledani svi brojevi NN 2020.–2023. Odluke se ne mijenjaju „odlukom o izmjeni" nego novom cjelovitom
odlukom (npr. kad zamjenica zamijeni zastupnika pa se promijeni omjer M/Ž, a
time i iznos po mandatu).

## Lanac odluka za 10. saziv (22. 7. 2020. – 15. 5. 2024.)

| Razdoblje | Odluka |
|---|---|
| 22. 7. – 30. 9. 2020. | NN 90/2020 (čl. 1733, razmjerni dio; čl. 1732 isti broj = kraj 9. saziva) |
| Q4 2020. | NN 90/2020 (1733) |
| Q1–Q2 2021. · Q3 · Q4 | NN 6/2021 · 78/2021 · 107/2021 |
| Q1–Q2 2022. · Q3 · Q4 | NN 11/2022 · 78/2022 · 115/2022 |
| Q1 2023. · Q2 · Q3–Q4 | NN 146/2022 · 37/2023 · 73/2023 |
| Q1 2024. | NN 8/2024 |
| 1. 4. – 15. 5. 2024. | NN 8/2024 × 7.719,92 / 15.610,45 (ostatak tromjesečja nakon 74/2024; potvrđeno izvješćem za 2024.) |

Do 2022. odluke su u kunama (polje `currency`; iznosi stoje u poljima `*_eur`
radi jedinstvene sheme, preračun radi skripta). NN 107/2021 i tablica u
NN 11/2022 tiskaju HDZ kao 45+17, a svi iznosi računati su na 46+16 —
zapisano 46/16 s napomenom. Preimenovanja (Pametno → Centar, Most nezavisnih
lista → Most, DP Miroslava Škore → DP) spajaju se u `RENAMES` u skripti.

## Projekcija do kraja 11. saziva (15. 5. 2028.)

- Q4 2026.: odluka NN 11/2026 (već raspoređeno).
- 2027.: **po zakonu** — 0,075 % × porezni prihodi 2025. (18,28 mlrd. €, NN 73/2026) = 13.709.909,70 €.
- 2028. (1. 1. – 15. 5., 1 + 45/91 tromjesečja): plan poreznih prihoda 2026.
  (19,08 mlrd. €); alternativa po trendu prvog polugodišta 2026. (+8,1 %).
- Raspodjela po ponderiranim mandatima iz NN 11/2026 (M + 1,1 × Ž).

## Lanac odluka za 11. saziv (konstituiran 16. 5. 2024.)

| Razdoblje | Odluka |
|---|---|
| 16. 5. – 30. 6. 2024. | NN 74/2024 (razmjerni dio tromjesečja) |
| Q3–Q4 2024. | NN 77/2024 |
| Q1–Q2 2025. | NN 16/2025 |
| Q3 2025. | NN 102/2025 |
| Q4 2025. | NN 140/2025 |
| 2026. | NN 11/2026 |

Kontrola: zbroj tromjesečja po primatelju jednak je iznosu „raspoređeno" u
Saborovim izvješćima za 2021., 2022., 2023. i 2025. (112 usporedbi, najveće
odstupanje 0,02), a 2024. — podijeljena između dva saziva — zbroju oba dijela
(0,12 €). Skripta pada ako odstupanje prijeđe 1.

## Ažuriranje

Kad Odbor donese novu odluku (obično siječanj, a unutar godine kad se promijeni
omjer M/Ž): dodaj zapis u `odluke.json`, dodaj/izmijeni razdoblja u `PERIODS`
u `scripts/19_export_financiranje.py`, ponovno pokreni
`scripts/18_fetch_sabor_zastupnici.py --refresh` i deploy.

## Vezani dokumenti

- [docs/2026-10-09-financiranje-stranaka.md](../../docs/2026-10-09-financiranje-stranaka.md) — zamke, ključne brojke, otvorene stavke
