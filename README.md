# DOMOVINA Stranke — Hrvatske političke stranke

**Code license:** [MIT](LICENSE)
&nbsp;·&nbsp; **Data license:** [CC-BY 4.0](LICENSE-DATA)
&nbsp;·&nbsp; **Network:** part of [DOMOVINA](https://domovina.ai)

Sister project of [klubovi.domovina.ai](https://github.com/domovinatv/klubovi.domovina.ai) —
same architecture, applied to Croatian political parties instead of football clubs.

---

## English summary

Open public catalog of every Croatian political party ever registered — **434
parties** (155 active, 279 dissolved) — with official registry data (OIB,
registration number, seat address, status and dates), presidents and persons
authorised to represent, historical officials and MP mandates, founding
places, name-change history, and geo-coordinates. Compiled from public
sources: Registar političkih stranaka RH (data.gov.hr), NSK authority files,
Nominatim.

Interfaces shipping from this repo:

- **`web/`** — a local FastAPI + HTMX admin tool over the SQLite catalog
  (list + filters, detail pages, Leaflet map, CSV export).

The ingest + enrichment pipeline (`scripts/`) is fully reproducible and
idempotent — raw responses are cached under `data/raw/`, so reruns don't
re-hit upstream services.

---

## Hrvatski

Sustavna javna baza **svih političkih stranaka ikad registriranih u RH** —
iz službenog Registra političkih stranaka (Ministarstvo pravosuđa i uprave,
preko data.gov.hr), obogaćena NSK-ovim normativnim datotekama (imenik
stranaka + funkcije) i geo-koordinatama.

## Trenutno stanje

| Pokazatelj                          | Brojka  |
|-------------------------------------|--------:|
| Stranaka ukupno                     | **434** |
| Aktivnih (status AKTIVAN)           | 155     |
| Ugašenih (status PRESTANAK)         | 279     |
| S OIB-om, adresom sjedišta, datumima| 434     |
| Osoba ovlaštenih za zastupanje      | 541     |
| Povijesnih funkcija (mandati)       | 4 203   |
| Geokodirano (lat/lng)               | vidi `/api/stats` |

## Financiranje iz proračuna

Stranica [`/financiranje`](https://stranke.domovina.ai/financiranje) prikazuje
koliko je koja parlamentarna stranka dobila iz državnog proračuna u 11. sazivu
Sabora te koliko mjesečno donosi mandat svakog zastupnika (zastupnice +10 %).
Izvori su odluke Odbora za Ustav, Poslovnik i politički sustav (Narodne novine)
i Saborova godišnja izvješća. Metoda i podaci: [`data/financiranje/`](data/financiranje/README.md).

## Izvori podataka

### Registar političkih stranaka RH (`data.gov.hr`, MPU)
Kanonski izvor: JSON dump dataseta
`registar-politickih-stranaka-republike-hrvatske`. Resource **Stranke** nosi
OIB, puni naziv, skraćeni naziv, status (AKTIVAN/PRESTANAK), sjedište
("Grad, Ulica bb"), registarski broj, knjigu, datume upisa i statusa.
Resource **Osobe** nosi osobe ovlaštene za zastupanje (ime, prezime,
svojstvo, zastupa/predstavlja) vezane preko `SBT_ID`.

### NSK Imenik političkih stranaka (`data.gov.hr`)
Normativna datoteka Nacionalne i sveučilišne knjižnice: mjesto osnivanja,
razdoblje djelovanja, povijest promjena naziva, kratice i engleski nazivi
(→ `party_aliases`). Match po ključu neosjetljivom na velika/mala slova,
dijakritike i interpunkciju, s rapidfuzz fallbackom (≥93).

### NSK Funkcije u političkim strankama (`data.gov.hr`)
Povijesne funkcije s mandatima: predsjednici kroz vrijeme, zastupnici u
Hrvatskom saboru itd. (→ `party_functions`).

### Nominatim (`nominatim.openstreetmap.org`)
Besplatno, throttle 1.05 req/s. Per stranka ladder kandidata od
najpreciznijeg do najopćenitijeg (puna adresa + grad → adresa → ZIP → grad),
`addressdetails=1` puni i `parties.county`. Cache po SHA hashu upita.

### Firecrawl v2 (`api.firecrawl.dev`) — opcionalno
Search + LLM ekstrakcija kontakata sa stranačkih stranica (web, email,
telefon, društvene mreže, wiki_url). Multi-key auto-rotate na 402.
Quality guardovi protiv agregatora, poslovnih registara, news portala i
državnih imenika (izbori.hr, gov.hr) — vidi `src/backfill.py`.

## Pipeline

```
1. AKVIZICIJA      01_ingest_registar.py    434 stranke + 541 osoba (JSON, keširano)
2. OBOGAĆIVANJE    02_enrich_imenik.py      mjesto/datum osnivanja, aliasi, povijest naziva
                   03_enrich_funkcije.py    4 203 funkcije s mandatima
3. GEOLOKACIJA     04_geocode_nominatim.py  lat/lng + županija (smart-fallback ladder)
4. INDEKSI         05_build_fts.py          FTS5, dijakritike normalizirane
5. BACKFILL        06_backfill.py           Firecrawl kontakti (traži FIRECRAWL_API_KEYS)
6. EXPORT          07_export_full_csv.py    ~/Desktop/hrvatske-politicke-stranke-YYYY-MM-DD.csv
```

## Pokretanje

```bash
# 1. Pripremi okolinu
uv sync

# 2. Akvizicija + obogaćivanje (idempotentno, <1 min uz keš)
uv run python scripts/01_ingest_registar.py
uv run python scripts/02_enrich_imenik.py
uv run python scripts/03_enrich_funkcije.py

# 3. Geo (~10-15 min prvi put zbog Nominatim throttlea)
uv run python scripts/04_geocode_nominatim.py

# 4. Indeksi
uv run python scripts/05_build_fts.py

# 5. Firecrawl backfill kontakata (opcionalno; .env: FIRECRAWL_API_KEYS=fc-...,fc-...)
uv run python scripts/06_backfill.py --unprocessed

# 6. Web UI
uv run uvicorn web.app:app --port 8000
# → http://localhost:8000        (lista, search, filteri)
# → http://localhost:8000/map    (Leaflet karta)

# 7. CSV snapshot
uv run python scripts/07_export_full_csv.py
```

## Schema

```sql
parties (id, slug PK, canonical_name, short_name, oib, sbt_id, reg_number,
         book_number, status, registered_at, status_date, seat, city, address,
         county, founded_place, founded_date, website, email, phone,
         phone_kind, phone_e164, fb_url, ig_url, x_url, president, wiki_url,
         lat, lng, notes, created_at, updated_at)

party_aliases   (alias_id PK, party_id FK, alias, source)
                 sources: 'registar-skraceni', 'nsk-imenik'

party_people    (person_id PK, party_id FK, full_name, role, represents, source)
                 -- osobe ovlaštene za zastupanje (registar)

party_functions (fn_id PK, party_id FK, function, holder,
                 mandate_start, mandate_end, source)
                 -- povijesni predsjednici, zastupnici u Saboru... (NSK)

backfill_runs   (run_id PK, party_id FK, ran_at, fields_filled JSON,
                 source_urls JSON, raw_dump_path)

parties_fts     (FTS5: slug, name, short_name, city, address, aliases;
                 unicode61 remove_diacritics 2 + pre-stripped đ/Đ)
```

## Sljedeće faze (otvorene ideje)

- **Firecrawl backfill run** — web/email/telefon/društvene mreže za 155
  aktivnih stranaka (skripta spremna, treba `FIRECRAWL_API_KEYS`)
- **Logotipi** — Wikipedia/Wikimedia fetch po `wiki_url` (kao `46_fetch_wiki_logos`
  u klubovi pipelineu) + CDN size ladder
- **DIP integracija** — izborni rezultati po strankama (izbori.hr arhiva),
  financijski izvještaji stranaka
- **Ustrojstveni oblici** — registar ima i podružnice/županijske organizacije
  (resource "Ustrojstveni oblici") — zasebna tablica party_units
- **92 nematchana NSK imenik zapisa** — uglavnom povijesne stranke s bitno
  drukčijim nazivom u registru; ručni alias mapping
- **Frontend PWA** — statični React export na Cloudflare Pages
  (stranke.domovina.ai), po uzoru na klubovi frontend
- **AI verification run** — stratified sample + paralelni subagenti po
  dimenzijama (identitet, lokacija, kontakt), kao `VERIFICATION.md` u klubovima

## Licence

- **Kod** (`scripts/`, `src/`, `web/`) — [MIT](LICENSE)
- **Podaci** (`data/`, exporti) — [CC-BY 4.0](LICENSE-DATA)

Atribucija: *"DOMOVINA Stranke — stranke.domovina.ai"*.
Izvorni podaci: Registar političkih stranaka RH (MPU) i NSK, preko
[data.gov.hr](https://data.gov.hr) (otvorene licence portala).
