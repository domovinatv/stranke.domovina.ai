from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "stranke.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS parties (
  id               INTEGER PRIMARY KEY,
  canonical_name   TEXT NOT NULL,
  slug             TEXT UNIQUE NOT NULL,
  short_name       TEXT,    -- SKRACENI_NAZIV iz registra (npr. "HDZ")
  oib              TEXT,
  sbt_id           INTEGER UNIQUE,  -- interni ID Registra političkih stranaka
  reg_number       TEXT,    -- REGISTARSKI_BROJ
  book_number      INTEGER, -- BROJ_KNJIGE
  status           TEXT,    -- 'AKTIVAN' | 'PRESTANAK'
  registered_at    TEXT,    -- DATUM_UPISA (ISO date)
  status_date      TEXT,    -- DATUM_STATUSA (za PRESTANAK = datum brisanja)
  seat             TEXT,    -- SJEDISTE sirovo, "Grad, Ulica bb"
  city             TEXT,    -- izparsirano iz SJEDISTE (prvi chunk)
  address          TEXT,    -- izparsirano iz SJEDISTE (ostatak)
  county           TEXT,    -- iz Nominatim addressdetails reverse-a
  founded_place    TEXT,    -- NSK imenik: "Mjesto osnivanja"
  founded_date     TEXT,    -- NSK imenik: početak razdoblja djelovanja
  website          TEXT,
  email            TEXT,
  phone            TEXT,
  phone_kind       TEXT,    -- 'mobile' | 'landline' | 'unknown' (src/phones.py)
  phone_e164       TEXT,    -- +385...
  fb_url           TEXT,
  ig_url           TEXT,
  x_url            TEXT,
  president        TEXT,    -- iz registra Osobe (SVOJSTVO=PREDSJEDNIK)
  wiki_url         TEXT,
  brand_color      TEXT,    -- #RRGGBB — Wikidata P465 ili dominantna boja loga
  lat              REAL,
  lng              REAL,
  notes            TEXT,
  created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS party_aliases (
  alias_id   INTEGER PRIMARY KEY,
  party_id   INTEGER NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
  alias      TEXT NOT NULL,
  source     TEXT,
  UNIQUE(party_id, alias, source)
);

-- Osobe ovlaštene za zastupanje (registar, resource "Osobe").
CREATE TABLE IF NOT EXISTS party_people (
  person_id  INTEGER PRIMARY KEY,
  party_id   INTEGER NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
  full_name  TEXT NOT NULL,
  role       TEXT,    -- SVOJSTVO ('PREDSJEDNIK', 'TAJNIK', ...)
  represents INTEGER, -- PREDSTAVLJA == 'DA'
  source     TEXT NOT NULL,
  UNIQUE(party_id, full_name, role, source)
);

-- Povijesne funkcije (NSK "Funkcije u političkim strankama"): predsjednici
-- kroz mandate, zastupnici u Saboru itd.
CREATE TABLE IF NOT EXISTS party_functions (
  fn_id         INTEGER PRIMARY KEY,
  party_id      INTEGER NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
  function      TEXT NOT NULL,
  holder        TEXT NOT NULL,
  mandate_start TEXT,
  mandate_end   TEXT,
  source        TEXT NOT NULL,
  UNIQUE(party_id, function, holder, mandate_start)
);

CREATE TABLE IF NOT EXISTS backfill_runs (
  run_id         INTEGER PRIMARY KEY,
  party_id       INTEGER NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
  ran_at         TEXT DEFAULT CURRENT_TIMESTAMP,
  fields_filled  TEXT,
  source_urls    TEXT,
  raw_dump_path  TEXT
);

CREATE INDEX IF NOT EXISTS idx_parties_canonical ON parties(canonical_name);
CREATE INDEX IF NOT EXISTS idx_parties_city ON parties(city);
CREATE INDEX IF NOT EXISTS idx_parties_status ON parties(status);
CREATE INDEX IF NOT EXISTS idx_aliases_alias ON party_aliases(alias);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def upsert_party(conn: sqlite3.Connection, slug: str, canonical_name: str, **fields) -> int:
    cols = ["slug", "canonical_name", *fields.keys()]
    vals = [slug, canonical_name, *fields.values()]
    placeholders = ", ".join(["?"] * len(cols))
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "slug")
    sql = (
        f"INSERT INTO parties ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(slug) DO UPDATE SET {updates}, updated_at=CURRENT_TIMESTAMP "
        "RETURNING id"
    )
    row = conn.execute(sql, vals).fetchone()
    return row["id"]


def add_alias(conn: sqlite3.Connection, party_id: int, alias: str, source: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO party_aliases (party_id, alias, source) VALUES (?, ?, ?)",
        (party_id, alias, source),
    )


def add_person(
    conn: sqlite3.Connection,
    party_id: int,
    full_name: str,
    role: str | None,
    represents: bool,
    source: str,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO party_people (party_id, full_name, role, represents, source) "
        "VALUES (?, ?, ?, ?, ?)",
        (party_id, full_name, role, int(represents), source),
    )


def add_function(
    conn: sqlite3.Connection,
    party_id: int,
    function: str,
    holder: str,
    mandate_start: str | None,
    mandate_end: str | None,
    source: str,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO party_functions "
        "(party_id, function, holder, mandate_start, mandate_end, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (party_id, function, holder, mandate_start, mandate_end, source),
    )
