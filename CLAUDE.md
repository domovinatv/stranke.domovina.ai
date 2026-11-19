# CLAUDE.md — stranke.domovina.ai

Javni repo (`domovinatv/stranke.domovina.ai`): katalog hrvatskih političkih stranaka,
`/financiranje` i (u izradi) Kompas stranaka. Opis podataka i pipelinea je u `README.md`.

## Kompas stranaka (lanac sesija)

Plan: `docs/kompas/plan.md`, odluke: `docs/kompas/decisions.md`, radna lista: `TODO.md`,
handoffi i stanje lanca: `docs/kompas/handoffs/README.md`.

„Nastavi kompas” znači: otvori prvi red u „Stanje lanca” koji nije gotov i radi po njegovom
`SN.md`. Ako je na vrhu handoffa pitanje za korisnika (vrata), ne radi ništa dok nije odgovoreno.

Provjera: `./scripts/check.sh` (nastaje u S1; do tada `cd frontend && npm run build`).
