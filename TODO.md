# TODO — Kompas stranaka

Radna lista. Čuva se u repou da napredak preživi između sesija. Označene stavke su gotove
i provjerene (`./scripts/check.sh` zelen; do S1 vrijedi `cd frontend && npm run build`).
Odluke idu u [docs/kompas/decisions.md](docs/kompas/decisions.md).

Plan po sesijama: [docs/kompas/plan.md](docs/kompas/plan.md). Handoff po sesiji: [docs/kompas/handoffs/](docs/kompas/handoffs/).

Legenda: `[x]` gotovo · `[ ]` otvoreno · `[~]` u radu · `(!)` traži korisnika · `→ Sn` planirana sesija

## F0 — Temelj i mjerenje pokrivenosti (ništa javno)

- [ ] `scripts/check.sh`: pytest (`tests/`) + `npm run build` + `npm run lint` (eslint dodan u devDependencies), izlaz ≠ 0 na grešku → S1
- [ ] `data/kompas/liste_2024.json`: sve liste parlamentarnih izbora 2024. s mandatima, članice koalicija mapirane na `party_id` u `stranke.db` → S1
- [ ] `scripts/22_fetch_programi.py`: za svaku stranku s liste nađe program (izborni 2024. i/ili trajni), sprema u `data/raw/programi/`, metapodaci (URL, datum, vrsta, sha256, stranica) u `data/kompas/programi.json` → S1
- [ ] Izmjerena pokrivenost: koliko lista/stranaka ima program, koliko stranica, PDF/HTML/skeniran → `docs/research/2026-..-pokrivenost-programa.md` → S1
- [ ] (!) Vrata 1: korisnik potvrđuje opseg (koje liste, koja vrsta programa) → nakon S1
- [ ] `scripts/23_extract_programi.py`: PDF/HTML → tekst po stranicama, sekcije, chunkovi s `party_id`, `doc_id`, `page`, `section` → `data/kompas/chunks.jsonl` (gitignored ako je velik) → S2
- [ ] Mjerena kvaliteta ekstrakcije (prazne stranice, OCR potreban, dijakritici) → S2
- [ ] domovina-rag: CH tablica `program_chunks` (1024-d, bge-m3), ETL iz `chunks.jsonl`, korak u `scripts/sync-cron.sh` → S3
- [ ] domovina-rag: MCP alat `search_programs(query, party?, limit?)` s vitest testovima, lokalno (bez deploya) → S3
- [ ] Eval: 20 pitanja o stavovima s očekivanim odlomkom, izmjeren recall@5 → S3

## F1 — Metodologija i matrica stavova

- [ ] `docs/kompas/metodologija.md`: osi, pravila izbora tvrdnji, skala, „nema stava”, pravo na odgovor → S4
- [ ] `data/kompas/tvrdnje.json`: nacrt 40 tvrdnji, ravnoteža po osima, svaka s obrazloženjem → S4
- [ ] Shema `data/kompas/matrica.json` + validator (pytest): svaka ćelija ima vrijednost ili `null`, citat, dokument, stranicu, status → S4
- [ ] (!) Vrata 2: korisnik odobrava tvrdnje (neutralnost) → nakon S4
- [ ] Alat za pregled ćelija u `web/` (FastAPI+HTMX): prihvati / ispravi / odbij, bilježi tko i kada → S5
- [ ] Provjera citata: citat mora doslovno postojati u tekstu dokumenta (normalizirani razmaci) → S5
- [ ] (!) Vrata 3: procjena broja poziva i trošak LLM prijedloga, korisnik odobrava → prije S6
- [ ] LLM prijedlozi ocjena s citatima za sve ćelije, dva neovisna prolaza, izmjereno slaganje → S6
- [ ] (!) Ljudski pregled svih ćelija (korisnik ili urednici) → nakon S6

## F2 — Podudaranje, stranica i pravo na odgovor

- [ ] `frontend/src/lib/kompas.ts` + `scripts/kompas_match.py`: ista formula, golden testovi (vitest + pytest) daju identične rezultate → S7
- [ ] Ruta `/kompas`: tvrdnje, težine, rezultati s citatima, bez slanja odgovora na server → S8
- [ ] Export `frontend/public/data/kompas.json` u `09_export_static.py` / deploy skripti → S8
- [ ] Mailovi strankama s njihovim retkom matrice kao Gmail draftovi (ne šalju se iz sesije) → S9
- [ ] Pravna bilješka: izborna šutnja, GDPR čl. 9, pravo citiranja → `docs/research/` → S9
- [ ] (!) Vrata 4: korisnik šalje mailove, prikuplja odgovore, odobrava objavu → nakon S9
- [ ] Deploy `/kompas` + MCP alati `get_party_positions`, `match` u domovina-rag (deploy.sh) → S10

## F3 — Druga dimenzija: kako su glasali u Saboru

- [ ] Istraživanje izvora glasanja Sabora (format, pokrivenost 11. saziva), fetch skripta, raw cache → S11
- [ ] Mapiranje glasanja na tvrdnje (samo jasni slučajevi, s poveznicom na glasanje) → S11
- [ ] (!) Vrata 5: korisnik odobrava mapiranje glasanja → nakon S11
- [ ] `/kompas` i MCP prikazuju „program vs glasanje” po stranci i tvrdnji → S12
