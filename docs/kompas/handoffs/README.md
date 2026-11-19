# Handoffi — Kompas stranaka (S1–S12)

Plan je u [`../plan.md`](../plan.md), odluke u [`../decisions.md`](../decisions.md), radna lista u
[`../../../TODO.md`](../../../TODO.md). Korisnik nakon `/clear` kaže „nastavi kompas” ili zalijepi
prompt iz clipboarda; to znači prvi red u „Stanje lanca” koji nije gotov.

## Lanac

1. Sesija N počinje iz `SN.md`.
2. Sesija N radi svoj paket po pravilima ispod.
3. Na kraju sesija N:
   - označi `SN` u tablici „Stanje lanca” (commit, testovi, kratka napomena) i stavke u `TODO.md`;
   - **ako je naučila nešto što mijenja sljedeće pakete, uredi `S(N+1).md`**, po potrebi i
     kasnije handoffe i plan. Nedovršeni dio paketa N ide na **vrh** `S(N+1).md`;
   - u `S(N+1).md` upiše polazni commit i izlaz `./scripts/check.sh`;
   - pozove `/wrap-up`. Handoff prompt je **sadržaj `S(N+1).md`**.
4. Ako sesija ostane bez konteksta usred paketa, nastavak je opet `SN` s popisom ostatka na
   vrhu datoteke. Broj se ne povećava.
5. **Vrata:** kad paket završava odlukom korisnika, sesija pitanje upiše na vrh `S(N+1).md`
   i lanac staje dok korisnik ne odluči. Sljedeća sesija prvo provjeri je li odluka upisana.
6. Handoff se mijenja samo prema naprijed: gotovi `SN` se ne prepisuju.

## Stanje lanca

| Sesija | Paket | Stanje | Commit | Testovi | Napomena |
| --- | --- | --- | --- | --- | --- |
| S0 | Plan | gotovo | 2849e71 | build zelen, lint ne radi (nema eslinta) | plan, odluke 1–12 |
| S1 | check.sh, liste 2024, programi, pokrivenost | otvoreno | | | |
| S2 | Ekstrakcija i chunking | otvoreno | | | iza vrata 1 |
| S3 | domovina-rag: program_chunks, search_programs, eval | otvoreno | | | paralelno sa S4 |
| S4 | Metodologija, tvrdnje, shema matrice | otvoreno | | | vrata 2 nakon |
| S5 | Alat za pregled, provjera citata | otvoreno | | | |
| S6 | LLM prijedlozi ocjena | otvoreno | | | iza vrata 3 |
| S7 | Formula TS + Python | otvoreno | | | može paralelno sa S5/S6 |
| S8 | Ruta /kompas | otvoreno | | | iza ljudskog pregleda matrice |
| S9 | Pravo na odgovor, pravna bilješka | otvoreno | | | vrata 4 nakon |
| S10 | Deploy /kompas + MCP | otvoreno | | | |
| S11 | Glasanja Sabora | otvoreno | | | vrata 5 nakon |
| S12 | Program vs glasanje | otvoreno | | | |

## Zajednička pravila (vrijede u svakoj sesiji)

- **Polazak:** `./scripts/check.sh` (od S1; prije toga `cd frontend && npm run build`) i potvrda
  u jednoj rečenici da je zeleno. Ako nije zeleno, prvo to popravi.
- **Repo je javan** (`domovinatv/stranke.domovina.ai`), wrap-up pusha `main`. U git ne idu puni
  tekstovi programa (odluka 8), `.env` ni tajne. domovina-rag je također javan.
- **Opseg:** u ovom repou `scripts/22+`, `tests/`, `data/kompas/`, `web/` (alat za pregled),
  `frontend/src/` (ruta i lib), `docs/kompas/`, `docs/research/`. Postojeće stranice
  (`/financiranje`, karta, stranke) se ne diraju osim uvezivanja rute i navigacije.
  U domovina-rag samo ono što paket kaže; poštuj njegov `CLAUDE.md` (sync-cron pravilo, deploy).
- **Orkestracija:** posao rade Opus 5.5 subagenti (`model: "opus"`), glavna sesija orkestrira.
  Paket razbij na (a) implementaciju, (b) testove i spajanje. `effort` uvijek eksplicitno:
  `high` za kod, `medium` za čitanje i istraživanje. Najviše 2–3 agenta paralelno. Fable samo
  kad korisnik izričito traži.
- **Agentima zabrani** `TODO.md`, `docs/kompas/plan.md`, `decisions.md` i handoffe; orkestrator ih ažurira.
- **Testovi:** bez mreže (raw cache i fiksture), `skipped 0`. Skripte koje dohvaćaju podatke
  keširaju odgovore u `data/raw/` i idempotentne su, kao postojeće `scripts/01`–`21`.
- **Trošak:** prije svega što prelazi ~100 LLM poziva procjena i pitanje korisniku. Nikad
  `claude -p` petlja. Prvi prolaz bulk posla na Sonnetu.
- **Brojke samo uz naredbu** kojom su izmjerene, zapisanu u izvještaju.
- **Autonomno:** odluči sam i zapiši odluku u `decisions.md` (blok sesije). Svaki zeleni korak
  commitaj na `main` (konvencionalni commit, scope `kompas`, trailer
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`). Nepovratno (deploy, mail, objava) ostavi korisniku.
- **Paralelne Claude sesije:** stageaj samo imenovane datoteke, nikad `git add -A`.
- **Token budget:** bez Monitora za napredak; dugi jobovi s `run_in_background` i javljanje tek
  na kraju ili grešci. Oko 150k konteksta orkestratora zatvori sesiju po koraku 3.
- **Mac mini:** MPS embedder bez ograničenja memorije može srušiti stroj; embedding s malim
  batchom i jednim procesom.
- **Preglednik:** provjere u pravom pregledniku (Brave, profil iz globalnog `CLAUDE.md`), ne samo curl.
- Svako istraživanje ide u `docs/research/YYYY-MM-DD-*.md`.
