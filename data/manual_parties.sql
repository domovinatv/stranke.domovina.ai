-- Stranke koje POSTOJE (kandidirale se na parlamentarnim izborima 2024.,
-- imaju žive webove/FB), ali ih NEMA u data.gov.hr JSON dumpu Registra
-- političkih stranaka (provjereno na dumpu od 2026-07-15 — dump očito nije
-- potpun mirror živog registra na registri-npo-mpu.gov.hr).
--
-- Otkriveno kroz scripts/08_crosscheck_parlament.py (DIP parlament-2024).
-- Status je ostavljen NULL jer bez registra ne znamo je li danas AKTIVAN.
-- Idempotentno: INSERT OR IGNORE po slug-u.

INSERT OR IGNORE INTO parties
  (slug, canonical_name, short_name, city, founded_date, president, notes)
VALUES
  ('hrvatsko-bilo', 'HRVATSKO BILO', 'HRB', 'Zadar', '2023-09-24',
   'Nada Šikić',
   'Nije u data.gov.hr dumpu registra (2026-07-15). Osnivačka skupština '
   || '24.09.2023. (Zagreb, osnivači udruge Hrvatski Ratnik, Hrvatsko Bilo, '
   || 'Hrvatska Mati; izvor: croativ.net, novilist.hr). Kandidirala na '
   || 'parlamentarnim izborima 2024. (DIP arhiva).'),
  ('akcija-za-promjene', 'AKCIJA ZA PROMJENE', 'AP', NULL, '2023-04-01',
   NULL,
   'Nije u data.gov.hr dumpu registra (2026-07-15). Osnovana u travnju 2023., '
   || 'četiri supredsjednika (među njima Ivica Žuvela; izvor: nacional.hr, '
   || 'zadarskilist.novilist.hr, akcijazapromjene.hr). Kandidirala na '
   || 'parlamentarnim izborima 2024. u koaliciji s Agrarnom strankom (DIP arhiva).');
