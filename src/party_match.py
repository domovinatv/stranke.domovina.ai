"""Match a party name from an outside source (ballot, Sabor, …) to the catalog.

Factored out of scripts/08_crosscheck_parlament.py so the Kompas list builder
(scripts/22_liste_2024.py) maps names exactly the way the 2024 cross-check
does. The rules:

  1. normalised keys (norm_key: case/diacritics/punctuation-insensitive) of
     the name and of its abbr-stripped variants ("… - HDZ" → "…"), most
     specific first;
  2. looked up against canonical_name / short_name / aliases of every catalog
     party. Exact catalog keys win over abbr-stripped ones, and active parties
     win over defunct ones (the caller passes rows in that priority order —
     see load_catalog), so "SDP" resolves to today's SDP, not the 1990s one;
  3. otherwise rapidfuzz token_sort_ratio >= 93 against canonical names.

Pure: CatalogMatcher works on any sequence of mappings, so it is testable
without data/stranke.db.
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz, process

from src.normalize import norm_key

FUZZY_CUTOFF = 93

_ABBR_SUFFIX = re.compile(r"\s*-\s*\"?[A-ZČĆĐŠŽ][A-ZČĆĐŠŽa-zčćđšž !.]{0,30}\"?\s*$")


def name_variants(name: str) -> list[str]:
    """Normalised match keys for a ballot party name, most specific first.

    Ballot names stack suffixes ("AUTOHTONA - HSP - DRAŽEN KELEMINEC -
    A - HSP - Dražen Keleminec"), so the abbr-strip is applied iteratively.
    """
    name = name.strip().strip('"')
    keys = [norm_key(name)]
    current = name
    for _ in range(3):
        stripped = _ABBR_SUFFIX.sub("", current).strip()
        if not stripped or stripped == current:
            break
        keys.append(norm_key(stripped))
        current = stripped
    out: list[str] = []
    for k in keys:
        if k and k not in out:
            out.append(k)
    return out


@dataclass(frozen=True)
class Match:
    row: Mapping[str, Any] | None
    how: str  # "exact" | "alias" | "fuzzy:<score>" | "none"

    @property
    def party_id(self) -> int | None:
        return None if self.row is None else self.row["id"]


def _aliases(row: Mapping[str, Any]) -> list[str]:
    a = row.get("aliases") if hasattr(row, "get") else row["aliases"]
    if not a:
        return []
    if isinstance(a, str):
        return [x for x in a.split(";") if x]
    return [x for x in a if x]


class CatalogMatcher:
    """Name → catalog row. `rows` must be in priority order (see load_catalog);
    each row needs id, canonical_name, short_name and aliases (list or
    ';'-joined string)."""

    def __init__(self, rows: Sequence[Mapping[str, Any]]):
        self.rows = list(rows)
        # key → (row, "exact" | "alias"); first writer wins.
        self._by_key: dict[str, tuple[Mapping[str, Any], str]] = {}

        def candidates(r):
            yield r["canonical_name"], "exact"
            yield r["short_name"] or "", "exact"
            for a in _aliases(r):
                yield a, "alias"

        for r in self.rows:
            for c, how in candidates(r):
                if c:
                    self._by_key.setdefault(norm_key(c), (r, how))
        for r in self.rows:
            for c, how in candidates(r):
                for k in name_variants(c):
                    self._by_key.setdefault(k, (r, how))
        # Last row per canonical name wins here (dict semantics) — kept as-is
        # from 08 so its output does not change.
        self._fuzz_map = {r["canonical_name"]: r for r in self.rows}

    def match(self, name: str) -> Match:
        for k in name_variants(name):
            hit = self._by_key.get(k)
            if hit:
                return Match(hit[0], hit[1])
        best = process.extractOne(
            name, self._fuzz_map.keys(), scorer=fuzz.token_sort_ratio,
            processor=norm_key, score_cutoff=FUZZY_CUTOFF,
        )
        if best:
            return Match(self._fuzz_map[best[0]], f"fuzzy:{round(best[1])}")
        return Match(None, "none")


def load_catalog(
    conn: sqlite3.Connection, exclude_alias_sources: Iterable[str] = ()
) -> list[dict[str, Any]]:
    """Every catalog party with its aliases, in match-priority order: active
    before defunct, then most recently changed first."""
    excl = tuple(exclude_alias_sources)
    cond = ""
    if excl:
        cond = f" AND a.source NOT IN ({', '.join('?' * len(excl))})"
    cur = conn.execute(
        f"""SELECT p.id, p.slug, p.canonical_name, p.short_name, p.status,
                   p.status_date, p.website,
                   COALESCE(GROUP_CONCAT(a.alias, ';'), '') AS aliases
            FROM parties p LEFT JOIN party_aliases a ON a.party_id = p.id{cond}
            GROUP BY p.id
            ORDER BY (p.status != 'AKTIVAN'),
                     COALESCE(p.status_date, '9999-12-31') DESC, p.id""",
        excl,
    )
    cols = [c[0] for c in cur.description]
    out = []
    for r in cur.fetchall():
        d = dict(zip(cols, r))
        d["aliases"] = [a for a in d["aliases"].split(";") if a]
        out.append(d)
    return out
