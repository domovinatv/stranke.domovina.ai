# Odluke — Kompas stranaka

Svaka odluka ima broj, datum, razlog i uvjet revizije. Odluka se ne briše nego zamjenjuje
novom koja se poziva na staru. Sesija SN numerira od N×100 (S1 od 100, S2 od 200…).

## S0 (2026-11-19)

**1. Preporuka se računa formulom, ne vektorskom sličnošću ni LLM-om.** Kosinusna sličnost
mjeri temu, a ne stav (za i protiv imaju sličan embedding), duljina programa iskrivljuje broj
pogodaka, a LLM nije deterministički. Revizija: nikad za izračun; RAG ostaje za dokaze i razgovor.

**2. Opseg MVP-a: liste parlamentarnih izbora 2024. koje su osvojile barem jedan mandat**,
plus stranke trenutno zastupljene u Saboru. Ostale aktivne stranke dolaze kasnije. Razlog:
od 155 aktivnih stranaka mnoge nemaju program, a glasa se za liste. Revizija: vrata 1 nakon S1.

**3. Jedinica rezultata je stranka, s prikazom liste/koalicije u kojoj je nastupila.** Ako
koalicija ima zajednički program, članice dijele redak matrice uz oznaku izvora. Revizija: S1
ako se pokaže da su koalicijski programi pravilo.

**4. Skala −2 … +2 i `null` (program ne zauzima stav).** `null` se ne računa kao 0; ulazi u
zasebno prikazanu pokrivenost. Revizija: S4 (metodologija), S7 (formula).

**5. Formula: ponderirana city-block sličnost** (Smartvote oblik): po tvrdnji
`1 − |u − p| / 4`, težina korisnika 0/1/2, prosjek preko tvrdnji gdje oba imaju stav.
Točan oblik, normalizacija i razrješenje izjednačenja fiksira S7. Revizija: S7.

**6. LLM samo predlaže, čovjek potvrđuje.** Ćelija ima status `predloženo` → `potvrđeno` /
`ispravljeno` / `odbijeno`, a opcionalno i `stranka-potvrdila` / `stranka-osporila`.
Citat se provjerava doslovno nad tekstom dokumenta. Revizija: nikad.

**7. GDPR: izračun u pregledniku, odgovori se ne spremaju.** MCP `match` je bez stanja i ne
logira argumente; nema analitike odgovora. Revizija: samo uz pravni savjet i izričit pristanak.

**8. Javni repo: puni tekstovi programa ne idu u git.** U git idu URL, datum, sha256,
kratki citati i matrica (CC-BY kao ostali podaci). Revizija: ako stranka izričito dopusti.

**9. RAG u domovina-rag, zasebna CH tablica `program_chunks`**, isti bge-m3 (1024-d) i MCP
server. Embedding lokalno uz ograničenje memorije (MPS embedder može srušiti Mac mini).
Revizija: S3.

**10. Tehnologija u ovom repou:** Python skripte s brojevima 22+ u `scripts/` (uv), testovi
pytest u `tests/`, frontend vitest za `lib/kompas.ts`, ruta u postojećem React/Vite PWA-u.
`scripts/check.sh` je jedina provjera lanca. Revizija: S1.

**11. LLM za prijedloge ocjena: Sonnet subagenti, po jedna stranka po pozivu**, bez `claude -p`
petlji i bez Fablea. Broj poziva i trošak procjenjuju se prije S6 (vrata 3). Revizija: S6.

**12. Neutralnost:** metodologija i tvrdnje objavljuju se prije rezultata; tvrdnje se biraju
ravnomjerno po osima (gospodarstvo, društvo/vrijednosti, suverenitet/EU, država i institucije,
okoliš/energija, regije i demografija), svaka stranka dobiva svoj redak na odgovor prije
objave. Revizija: vrata 2 i 4.

## S1 (2026-11-19)

**100. Brojevi skripti: `22_liste_2024.py`, `23_fetch_programi.py`, `24_extract_programi.py`,
`25_fetch_glasanja.py`.** Liste trebaju vlastitu skriptu prije dohvata programa, a postojeća
konvencija `scripts/NN_` ima jedinstvene brojeve. Testabilna logika ide u `src/kompas/`, skripte
su tanki CLI. Revizija: nikad (samo naprijed).

**101. Lista = sve varijante istog nositelja.** Varijante po izbornim jedinicama (SDP s/bez
Reformista, DP s raznim partnerima, Možemo s/bez Hoćemo pravedno) jedna su lista s `list_id` iz
glavne varijante; članica nosi jedinice i mandate svojih varijanti. Liste drugih nositelja bez
mandata ostaju izvan opsega. Revizija: vrata 1.

**102. Što je program, odlučuje pregled, ne skripta.** Prihvaćeni URL-ovi i razlozi su u
`data/kompas/programi_izvori.json` (u gitu); `23_fetch_programi.py` ih dohvaća, kešira i mjeri,
a `--discover` samo predlaže kandidate. Medijski sažeci i programi za lokalne izbore 2025. ne
vrijede kao izborni-2024. Revizija: S2 ako ekstrakcija pokaže krive dokumente.

**103. Program nositelja koalicije ne pripisuje se partnerima** dok korisnik ne odluči na vratima 1
(dokument ima `list_id`, pa je to jedna izmjena). Zajednički su samo SDP – Rijeke pravde i
Fokus – Republika. Revizija: vrata 1.

## S2 (2026-11-19)

**200. Vrata 1 (korisnik, 2026-11-19):** u opsegu su svih 8 lista te SDSS, DOMiNO, Drito i Zurovec.
Stranke bez programa ostaju u matrici sa ćelijama `null` i oznakom „nema programa”. Izborni program 2024.
je primarni, trajni je dopuna, a izvor se označava po ćeliji. Program nositelja ne pripisuje se partnerima
(odluka 103 ostaje). Bez OCR-a. Odobreni su svi nesigurni izvori, uz oznaku `nesiguran` i razlog.
Zamjenjuje odluke 2 i 101 (opseg) te potvrđuje 103. Revizija: nikad (odluka korisnika).

**201. Ekstrakcija:** pypdf s `visitor_text`.
- **Naslovi:** naslov je redak s fontom ≥ 1,15 × tijela i ≥ tijelo + 1 pt, ili samostalan redak u cijelosti
  podebljan. Blokovi dulji od 20 riječi ili s interpunkcijom na kraju nisu naslovi.
- **Fallback:** kad dokument nema naslova po fontu, naslovi su kratki retci u velikim slovima ili numerirani.
- **Uklanja se:** ponavljani rubni retci (više od 50 % stranica), brojevi stranica i stranice sadržaja.
- **Normalizacija:** NFC, a znakovi oznaka iz privatnog područja Unicodea mapiraju se u obične oznake.
- **De-hyphenation:** samo kad spojeni oblik ne postoji drugdje u dokumentu kao oblik s crticom.
- **HTML:** jedna logička stranica, isti izbor glavnog sadržaja kao `programi.html_main()`.
Izlaz: `<doc_id>.pages.json` (gitignored). Idempotentno po sha256 i `EXTRACTOR_VERSION`.
Revizija: ako S5 ili S6 nađu citate koji se zbog ekstrakcije ne mogu doslovno pronaći.

**202. Chunking:**
- **Granice:** chunk ne prelazi granicu sekcije, a naziv sekcije je put naslova „A › B” (najviše 3 razine).
- **Male sekcije:** sekcija ispod 80 riječi spaja se sa sljedećom („A / B”).
- **Veličina:** n = ceil(riječi / 550) chunkova po sekciji, dobiveno je prosječno 280 riječi.
- **Preklop:** 40–80 riječi iz cijelih rečenica.
- **ID:** `prog_<doc_id>_<NNNN>`, s `chunk_index` od 1.
Format je oblik ETL-a u domovina-rag (`id`, `text`, `metadata.type = "program_section"`). Dokument s
više stranaka daje jedan chunk s `party_ids`, ne kopiju po stranci. Revizija: S3, ako recall@5 traži
drukčiju veličinu.

**203. `chunks.jsonl` je uvijek u `data/raw/kompas/` (gitignored), jer sadrži pune tekstove**
(odluka 8), bez obzira na veličinu (2,7 MB). U git ide samo `data/kompas/chunks_stats.json`, koji ima
brojke bez teksta. Revizija: nikad.

**204. `nesiguran` je eksplicitan popis `NESIGURNI` u `src/kompas/chunk.py`** (doc_id → razlog).
Popis ima 9 dokumenata: svih 7 s Waybacka, Suverenisti 24, „Ozbiljno za Hrvatsku” i SDP s
grabancijas.com. Test drži popis usklađenim s `izvor == "wayback"`. Revizija: kad se izvor zamijeni
izvornim URL-om stranke.

**205. Poznate mane ostaju za kasnije:**
- **IDS (`5111e0ffaee2`):** dvojezičan je, pa je oko polovice chunkova talijanski duplikat.
- **DP (`7c54f0dd36a8`):** prijelom je 2-up, pa ponegdje stupci isprepliću rečenice.
- **Nezavisni i NLM:** imaju tanku HTML stranicu s ostacima izbornika.
Ne blokiraju S3. Revizija: IDS-ov filtar jezika u S3 ako duplikati kvare recall, a DP-ov prijelom u S5
ako citati ne prolaze doslovnu provjeru.

## S3 (2026-11-19, prvi dio; ingest i recall@5 nisu izmjereni)

**300. `rag.program_chunks`** (domovina-rag `aaf1be2`): sva polja iz `chunks.jsonl` kao stupci (null → `''`/0),
uz `party_names`, `party_short` i `party_slugs`. To su nizovi paralelni s `party_ids`, a ETL ih spaja iz
`data/kompas/liste_2024.json`, da MCP može filtrirati po imenu stranke bez stranke repoa.
`ReplacingMergeTree(inserted_at) ORDER BY (doc_id, chunk_index)`, HNSW cosine kao `rag_chunks`.
Revizija: kad se promijeni oblik `chunks.jsonl` (odluka 202).

**301. ETL `python -m etl programs`** (`d8226b2`) radi u ETL containeru (`docker compose --profile etl run`),
s ulazima montiranima read-only.
- **Odluka po dokumentu:** otisak čine `chunk_id`, `text_hash`, metapodaci i imena stranaka. Kad se otisak ne
  promijeni, dokument se preskače bez embeddera. Kad se promijeni, briše se `ALTER … DELETE` s `mutations_sync`
  tek kad su novi embeddinzi gotovi, a dokumenti kojih više nema u datoteci se brišu.
- **Embeddinzi se ponovno koriste** po `text_hash`, pa promjena samih metapodataka ne zove embedder.
- **Batch ≤ 8**, jedan proces. Kad je embedder dolje, WARN i izlaz 0. Prazan ulaz je greška, da ne obriše tablicu.

Revizija: ako lightweight `DELETE` proradi uz vektorski indeks.

**302. Cloud sync `scripts/sync-programs.sh --cloud`** (`cdffe82`):
- **Tablica:** sama je kreira DDL-om iz `init.sql`, jer se `init.sql` na cloudu ne pokreće ponovno.
- **Usporedba:** usporedi otisak po dokumentu (broj redaka i hash) lokalno i na cloudu, pa prenese samo
  promijenjene dokumente (Native). Puna zamjena je odbačena jer bi tablica na trenutak bila prazna.
- **Cron:** korak 6c u `sync-cron.sh`, lokalno pa `--cloud`, best-effort.

`--cloud` još nije pokrenut (S10).

**303. `search_programs`** (`0c457cd`):
- **`party`:** prima broj (`has(party_ids, …)`), slug, točan kratki naziv ili podniz imena od ≥ 3 znaka, bez
  obzira na velika slova i dijakritike. Kratki naziv se ne traži kao podniz, jer bi „DP” pogodio „SDP”.
- **Nepoznata stranka:** filtar ostaje, a odgovor kaže da program nije nađen.
- **`limit`:** 5, kapica 20.
- **Upit:** bez `FINAL`, duplikati se uklanjaju po `chunk_id`.
- **Odgovor:** citat do 700 znakova, stranica ili „web stranica”, a za `nesiguran` oznaka „⚠ izvor: …”.

Revizija: S10 (deploy) ili kad eval pokaže da filtar po imenu griješi.

**304. Testovi MCP-a su `node:test` (`npm test`), ne vitest:** repo tako testira. „Vitest zelen” iz plana znači
`npm test` zelen. Revizija: nikad.

**305. Eval** (`b5e94ab`): `scripts/26_eval_search_programs.py`. Broj 25 je rezerviran za `25_fetch_glasanja.py`
(S11).
- **Zlatni skup:** `data/kompas/eval/search_programs_gold.json`, 20 pitanja (14 s filtrom stranke, 6 bez filtra),
  46 ručno označenih chunkova, svaki s doslovnim isječkom do 15 riječi.
- **„recall@5” iz plana** = prosječni hit@5. Uz njega se mjere i recall@5 i MRR@20, odvojeno za upite s filtrom
  i bez njega.
- **Slaba pitanja:** popisana su u commitu (q05, q11, q14, q20, a q17 i q19 imaju po 5 oznaka).

Revizija: kad se promijene chunk ID-jevi (odluka 202). Isječci tada služe za ponovno mapiranje.

**306. Reranker ne postoji u domovina-rag** (`services/reranker` je samo README). Eval ima `--rerank`
(CrossEncoder `BAAI/bge-reranker-v2-m3` na CPU-u nad top 20, kao `uv run --with sentence-transformers`).
Pokreće se samo ako je hit@5 nizak, a prvi put skida oko 2,3 GB. Revizija: ako pomogne, reranker ide u MCP (S10).
