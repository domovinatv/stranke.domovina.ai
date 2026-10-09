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

## Datoteke

| Datoteka | Izvor | Kako nastaje |
|---|---|---|
| `odluke.json` | Narodne novine: NN 8/24, 74/24, 77/24, 16/25, 102/25, 140/25, 11/26 | ručna transkripcija svakog primatelja; zbroj = ukupni iznos ±0,08 € |
| `izvjesca_cl11.json` | sabor.hr, izvješća po čl. 11. za 2024. i 2025. (skenirani PDF-ovi bez tekstualnog sloja) | ručna transkripcija |
| `zastupnici.json` | sabor.hr API interaktivne sabornice + profil svakog zastupnika | `scripts/18_fetch_sabor_zastupnici.py` |

Sirovi HTML/PDF izvornici su u `data/raw/financiranje/` i `data/raw/sabor/`
(gitignorirano).

Potpunost odluka provjerena je pregledom sadržaja svakog broja NN od 1/2024 do
114/2026. Odluke se ne mijenjaju „odlukom o izmjeni" nego novom cjelovitom
odlukom (npr. kad zamjenica zamijeni zastupnika pa se promijeni omjer M/Ž, a
time i iznos po mandatu).

## Lanac odluka za 11. saziv (konstituiran 16. 5. 2024.)

| Razdoblje | Odluka |
|---|---|
| 16. 5. – 30. 6. 2024. | NN 74/2024 (razmjerni dio tromjesečja) |
| Q3–Q4 2024. | NN 77/2024 |
| Q1–Q2 2025. | NN 16/2025 |
| Q3 2025. | NN 102/2025 |
| Q4 2025. | NN 140/2025 |
| 2026. | NN 11/2026 |

Kontrola: zbroj četiri tromjesečja 2025. po svakom primatelju jednak je iznosu
„raspoređeno" u Saborovu izvješću za 2025. (najveće odstupanje 0,02 €).
Skripta pada ako odstupanje prijeđe 1 €.

## Ažuriranje

Kad Odbor donese novu odluku (obično siječanj, a unutar godine kad se promijeni
omjer M/Ž): dodaj zapis u `odluke.json`, dodaj/izmijeni razdoblja u `PERIODS`
u `scripts/19_export_financiranje.py`, ponovno pokreni
`scripts/18_fetch_sabor_zastupnici.py --refresh` i deploy.
