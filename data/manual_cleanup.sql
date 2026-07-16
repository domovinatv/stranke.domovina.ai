-- Ručno čišćenje leakova iz Firecrawl backfilla (audit 2026-07-16).
-- Idempotentno: UPDATE-i su uvjetovani na točno "krivu" vrijednost.

-- 1) HRVATSKA STRANKA DEMOKRATA — dobila kontakte news portala sisak.info.
UPDATE parties SET website=NULL, email=NULL, fb_url=NULL
 WHERE slug='hrvatska-stranka-demokrata' AND website='https://www.sisak.info/';

-- 2) ISTARSKA STRANKA UMIROVLJENIKA — website pokazivao na news portal
--    parentium.com; službena stranica je isu-pip.org (prvi search hit).
UPDATE parties SET website='https://www.isu-pip.org/'
 WHERE slug='istarska-stranka-umirovljenika-partito-istriano-dei-pensionati'
   AND website='https://www.parentium.com/';

-- 3) ISTARSKI DEMOKRATI (osnovani 2025.) — dobili kompletne kontakte IDS-a
--    (ids-ddi.com) zbog preklapanja imena/kratica.
UPDATE parties SET website=NULL, email=NULL, phone=NULL, phone_kind=NULL,
                   phone_e164=NULL, fb_url=NULL, x_url=NULL
 WHERE slug='istarski-demokrati-democratici-istriani-id-di'
   AND website='http://www.ids-ddi.com/';

-- 3b) DOMOVINSKI POKRET — backfill završio na FB profilu (social-only pick);
--     službena stranica je opće poznata.
UPDATE parties SET website='https://domovinskipokret.hr/'
 WHERE slug='domovinski-pokret' AND website IS NULL;

-- 4) ŽUPSKA STRANKA (Brašina) — dobila kontakte Srpske radikalne stranke
--    (.org.rs). Vlastita stranica je zupka.org (bila među search hitovima).
UPDATE parties SET website='http://www.zupka.org/', phone=NULL, phone_kind=NULL,
                   phone_e164=NULL, fb_url=NULL, ig_url=NULL, x_url=NULL
 WHERE slug='zupska-stranka'
   AND website='https://www.srpskaradikalnastranka.org.rs';
