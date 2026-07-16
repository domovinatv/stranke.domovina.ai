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

-- ============================================================
-- Blok 2 (2026-07-16, logo-review audit): cross-party website/kontakt
-- leakovi iz backfilla — stranke bez vlastitog weba dobile su tuđi.
-- Pravilo: domena ostaje samo stranci kojoj stvarno pripada.

-- strankadomino.hr pripada stranci DOMiNO (dom-i-nacionalno-okupljanje)
UPDATE parties SET website=NULL WHERE website LIKE '%strankadomino.hr%'
  AND slug IN ('zagorska-stranka','hrvatska-stranka-buducnosti','nova-politika','stranka-za-narod');
UPDATE parties SET website=NULL, email=NULL, phone=NULL, phone_kind=NULL,
                   phone_e164=NULL, fb_url=NULL
  WHERE slug='pokret-zajedno' AND website LIKE '%strankadomino.hr%';

-- mozemo.hr pripada platformi Možemo!
UPDATE parties SET website=NULL, email=NULL, fb_url=NULL
  WHERE website LIKE '%mozemo.hr%'
  AND slug IN ('zelena-lista-1000123','umirovljenicka-demokratska-unija');

-- most-hrvatska.hr pripada MOST-u
UPDATE parties SET website=NULL, email=NULL, phone=NULL, phone_kind=NULL,
                   phone_e164=NULL, fb_url=NULL
  WHERE slug='zajedno-hrvatska' AND website LIKE '%most-hrvatska.hr%';

-- sdp.hr pripada SDP-u
UPDATE parties SET website=NULL
  WHERE slug='demokratsko-socijalna-stranka-hrvatske' AND website LIKE '%sdp.hr%';

-- sdss.hr pripada SDSS-u (Samostalna demokratska srpska stranka),
-- ne Demokratskom savezu Srba; fb je bio addtoany share-widget
UPDATE parties SET website=NULL, fb_url=NULL
  WHERE slug='demokratski-savez-srba' AND website LIKE '%sdss.hr%';

-- hss.hr pripada matičnoj HSS; splinter stranke ga ne smiju nositi
UPDATE parties SET website=NULL WHERE website LIKE '%hss.hr%'
  AND slug IN ('hrvatska-seljacka-stranka-stjepan-radic','hrvatska-seljacka-stranka-brace-radic-600837');
UPDATE parties SET website='https://hss.hr'
  WHERE slug='hrvatska-seljacka-stranka' AND website IS NULL;

-- stranka-umirovljenika.hr pripada Stranci umirovljenika
UPDATE parties SET website=NULL WHERE website LIKE '%stranka-umirovljenika.hr%'
  AND slug IN ('stranka-hrvatskih-umirovljenika-umirovljenici','stranka-umirovljenika-sjever');

-- desno.hr pripada stranci DESNO (Demokratski Savez Nacionalne Obnove)
UPDATE parties SET website=NULL
  WHERE slug='nezavisna-lista-ante-dapica' AND website LIKE '%desno.hr%';

-- reformisti.hr pripada NS Reformisti
UPDATE parties SET website=NULL, email=NULL, fb_url=NULL
  WHERE slug='demokratska-lokalna-stranka' AND website LIKE '%reformisti.hr%';

-- ktc.hr je trgovački lanac, ne stranka
UPDATE parties SET website=NULL WHERE website LIKE '%ktc.hr%';

-- hdz-zapresic.hr pripada HDZ-ovom ogranku, ne Nezavisnima za Zaprešić
UPDATE parties SET website=NULL, email=NULL
  WHERE slug='nezavisni-za-zapresic' AND website LIKE '%hdz-zapresic.hr%';

-- za-orah.hr pripada Zelenoj alternativi – ORaH, ne Plavo-zelenoj stranci
UPDATE parties SET website=NULL, email=NULL, fb_url=NULL
  WHERE slug='plavo-zelena-stranka' AND website LIKE '%za-orah.hr%';

-- HDZ-ov ogranak kao FB Demokratske kneginečke stranke
UPDATE parties SET fb_url=NULL
  WHERE slug='demokratska-kneginecka-stranka' AND fb_url LIKE '%hdzkneginec%';
