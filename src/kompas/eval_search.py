"""Retrieval eval for search_programs (S3): gold set, metrics, SQL (pure logic).

The gold set (data/kompas/eval/search_programs_gold.json, committed) holds 20
voter-style questions with hand-labelled chunks from data/raw/kompas/chunks.jsonl.
scripts/26_eval_search_programs.py embeds each question through the domovina-rag
embedder, ranks rag.program_chunks by cosine distance in ClickHouse and scores
the ranking with the functions below. Everything here is offline and testable;
the script does the HTTP.

Metric definitions (per question, `ranked` = chunk ids best-first, `expected` =
labelled chunk ids):
  hit@k     1 if any expected chunk is in the top k, else 0
  recall@k  fraction of expected chunks found in the top k
  rr        1 / rank of the first expected chunk within the retrieved
            candidates (0 if none was retrieved), so the mean is MRR@candidates
Aggregate "recall@5" in the S3 plan is reported as mean hit@5 (did the voter
get at least one right passage in the first five); mean recall@5 is reported
next to it because several questions have up to five correct chunks.
"""
from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GOLD_PATH = ROOT / "data" / "kompas" / "eval" / "search_programs_gold.json"
RESULTS_PATH = ROOT / "data" / "kompas" / "eval" / "search_programs_results.json"
CHUNKS_PATH = ROOT / "data" / "raw" / "kompas" / "chunks.jsonl"
LISTE_PATH = ROOT / "data" / "kompas" / "liste_2024.json"

TABLE = "rag.program_chunks"
CANDIDATES = 20          # rows fetched per question (rerank pool, MRR depth)
SNIPPET_MAX_WORDS = 15

CHUNK_ID_RE = re.compile(r"^prog_([0-9a-f]{12})_(\d{4})$")
QUESTION_ID_RE = re.compile(r"^q\d{2}$")


# ------------------------------------------------------------------ gold set


def load_gold(path: Path = GOLD_PATH) -> list[dict[str, Any]]:
    """The gold questions; raises ValueError when the file does not validate."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = validate_gold(doc)
    if errors:
        raise ValueError("neispravan zlatni skup:\n  " + "\n  ".join(errors))
    return doc["pitanja"]


def resolve_party(name: str, stranke: Iterable[Mapping[str, Any]]) -> list[int]:
    """Party ids whose short_name, slug or canonical_name equals `name` (case-insensitive)."""
    key = name.strip().casefold()
    return sorted({
        int(s["party_id"]) for s in stranke
        if key in {str(s.get(f) or "").strip().casefold() for f in ("short_name", "slug", "canonical_name")}
    })


def validate_gold(doc: Any, stranke: Iterable[Mapping[str, Any]] | None = None,
                  chunk_ids: set[str] | None = None) -> list[str]:
    """Structural problems in a gold document (empty list = valid).

    With `stranke` (liste_2024.json "stranke") each `party` must resolve to its
    `party_ids`; with `chunk_ids` (ids in chunks.jsonl) every label must exist.
    """
    if not isinstance(doc, Mapping) or not isinstance(doc.get("pitanja"), list):
        return ["dokument nema listu 'pitanja'"]
    stranke = list(stranke) if stranke is not None else None
    errors: list[str] = []
    seen: set[str] = set()
    for i, q in enumerate(doc["pitanja"]):
        if not isinstance(q, Mapping):
            errors.append(f"pitanja[{i}]: nije objekt")
            continue
        qid = q.get("id")
        where = f"{qid or f'pitanja[{i}]'}"
        if not isinstance(qid, str) or not QUESTION_ID_RE.match(qid):
            errors.append(f"{where}: id mora biti oblika q01")
        elif qid in seen:
            errors.append(f"{where}: dupli id")
        else:
            seen.add(qid)
        if not isinstance(q.get("question"), str) or not q["question"].strip():
            errors.append(f"{where}: prazno pitanje")
        if not isinstance(q.get("topic"), str) or not q["topic"].strip():
            errors.append(f"{where}: nema teme")
        party, pids = q.get("party"), q.get("party_ids")
        if party is None:
            if pids is not None:
                errors.append(f"{where}: party_ids bez party")
        elif not isinstance(party, str) or not party.strip():
            errors.append(f"{where}: party mora biti string ili null")
        elif (not isinstance(pids, list) or not pids
              or not all(isinstance(p, int) and not isinstance(p, bool) and p > 0 for p in pids)):
            errors.append(f"{where}: party bez ispravnih party_ids")
        elif stranke is not None and resolve_party(party, stranke) != sorted(pids):
            errors.append(f"{where}: party {party!r} se ne razrješava u {pids}")
        expected = q.get("expected")
        if not isinstance(expected, list) or not expected:
            errors.append(f"{where}: nema očekivanih chunkova")
            continue
        labelled: set[str] = set()
        for j, e in enumerate(expected):
            ew = f"{where}.expected[{j}]"
            if not isinstance(e, Mapping):
                errors.append(f"{ew}: nije objekt")
                continue
            cid = e.get("chunk_id")
            m = CHUNK_ID_RE.match(cid) if isinstance(cid, str) else None
            if not m:
                errors.append(f"{ew}: chunk_id {cid!r} nije oblika prog_<12 hex>_<NNNN>")
            else:
                if e.get("doc_id") != m.group(1):
                    errors.append(f"{ew}: doc_id {e.get('doc_id')!r} ne odgovara {cid}")
                if cid in labelled:
                    errors.append(f"{ew}: chunk {cid} označen dvaput")
                labelled.add(cid)
                if chunk_ids is not None and cid not in chunk_ids:
                    errors.append(f"{ew}: chunk {cid} ne postoji u chunks.jsonl")
            snip = e.get("snippet")
            if not isinstance(snip, str) or not snip.strip():
                errors.append(f"{ew}: prazan snippet")
            elif len(snip.split()) > SNIPPET_MAX_WORDS:
                errors.append(f"{ew}: snippet ima više od {SNIPPET_MAX_WORDS} riječi")
    return errors


def expected_ids(question: Mapping[str, Any]) -> list[str]:
    return [e["chunk_id"] for e in question["expected"]]


# ------------------------------------------------------------------ metrics


def first_rank(expected: Iterable[str], ranked: Sequence[str]) -> int | None:
    """1-based rank of the first expected chunk in `ranked`, or None."""
    want = set(expected)
    for i, cid in enumerate(ranked, 1):
        if cid in want:
            return i
    return None


def hit_at(expected: Iterable[str], ranked: Sequence[str], k: int) -> int:
    return int(bool(set(expected) & set(ranked[:k])))


def recall_at(expected: Iterable[str], ranked: Sequence[str], k: int) -> float:
    want = set(expected)
    if not want:
        raise ValueError("recall bez očekivanih chunkova")
    return len(want & set(ranked[:k])) / len(want)


def reciprocal_rank(expected: Iterable[str], ranked: Sequence[str]) -> float:
    r = first_rank(expected, ranked)
    return 0.0 if r is None else 1.0 / r


def score_question(expected: Sequence[str], ranked: Sequence[str], k: int) -> dict[str, Any]:
    """Per-question metrics plus the rank of every expected chunk (None = not retrieved)."""
    pos = {cid: i for i, cid in reversed(list(enumerate(ranked, 1)))}
    return {
        "hit@1": hit_at(expected, ranked, 1),
        f"hit@{k}": hit_at(expected, ranked, k),
        f"recall@{k}": round(recall_at(expected, ranked, k), 4),
        "rr": round(reciprocal_rank(expected, ranked), 4),
        "first_rank": first_rank(expected, ranked),
        "ranks": {cid: pos.get(cid) for cid in expected},
    }


def _mean(xs: Sequence[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def aggregate(rows: Sequence[Mapping[str, Any]], k: int) -> dict[str, Any]:
    """Means over scored questions: all, with a party filter, without one.

    Each row needs the score_question() keys and `party_ids` (None = unfiltered).
    """
    def block(sub: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return {
            "n": len(sub),
            "hit@1": _mean([r["hit@1"] for r in sub]),
            f"hit@{k}": _mean([r[f"hit@{k}"] for r in sub]),
            f"recall@{k}": _mean([r[f"recall@{k}"] for r in sub]),
            "mrr": _mean([r["rr"] for r in sub]),
        }
    return {
        "all": block(rows),
        "filtered": block([r for r in rows if r.get("party_ids")]),
        "unfiltered": block([r for r in rows if not r.get("party_ids")]),
    }


# ------------------------------------------------------------------ ClickHouse SQL


def build_search_sql(party_ids: Sequence[int] | None, *, with_text: bool = False,
                     table: str = TABLE) -> tuple[str, dict[str, Any]]:
    """Nearest chunks by cosine distance; values only ever travel as query parameters.

    The query vector is bound as {q:Array(Float32)} by the caller (it is large and
    per question); this returns the SQL and the remaining parameters
    (`limit`, and `p0`, `p1`, … for the party filter `has(party_ids, x)` OR-ed).
    """
    if not re.fullmatch(r"[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*", table):
        raise ValueError(f"neispravno ime tablice: {table!r}")
    params: dict[str, Any] = {}
    where = ""
    if party_ids:
        conds = []
        for i, p in enumerate(party_ids):
            if not isinstance(p, int) or isinstance(p, bool) or p <= 0:
                raise ValueError(f"party_id mora biti pozitivan cijeli broj: {p!r}")
            params[f"p{i}"] = p
            conds.append(f"has(party_ids, {{p{i}:UInt32}})")
        where = "WHERE " + " OR ".join(conds) + "\n"
    cols = "chunk_id, doc_id, party_ids" + (", text" if with_text else "")
    sql = (f"SELECT {cols}, cosineDistance(embedding, {{q:Array(Float32)}}) AS distance\n"
           f"FROM {table}\n{where}ORDER BY distance ASC\nLIMIT {{limit:UInt32}}")
    return sql, params


def format_param(value: Any) -> str:
    """A value in ClickHouse's text format for an HTTP `param_<name>`."""
    if isinstance(value, bool):
        raise TypeError("bool parametar nije podržan")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("vektor sadrži NaN ili beskonačno")
        return repr(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        parts = []
        for v in value:
            if isinstance(v, str):
                parts.append("'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'")
            else:
                parts.append(format_param(v))
        return "[" + ",".join(parts) + "]"
    raise TypeError(f"nepodržan tip parametra: {type(value).__name__}")


# ------------------------------------------------------------------ misc helpers


def parse_env(text: str) -> dict[str, str]:
    """KEY=VALUE lines of a .env file (comments, blanks and `export ` ignored, quotes stripped)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        else:
            val = val.split(" #", 1)[0].rstrip()
        out[key.strip()] = val
    return out


def apply_rerank(rows: Sequence[Mapping[str, Any]], scores: Sequence[float]) -> list[dict[str, Any]]:
    """Rows reordered by cross-encoder score (higher first, ties keep vector order)."""
    if len(rows) != len(scores):
        raise ValueError("broj ocjena ne odgovara broju redaka")
    order = sorted(range(len(rows)), key=lambda i: (-float(scores[i]), i))
    return [{**rows[i], "rerank_score": round(float(scores[i]), 6)} for i in order]


def rerank_rows(query: str, rows: Sequence[Mapping[str, Any]],
                predict: Callable[[list[tuple[str, str]]], Sequence[float]]) -> list[dict[str, Any]]:
    """Cross-encoder rerank; `predict` takes (query, passage) pairs (CrossEncoder.predict)."""
    if not rows:
        return []
    return apply_rerank(rows, list(predict([(query, r["text"]) for r in rows])))
