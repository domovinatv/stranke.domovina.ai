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
