"""Kompas stranaka: retrieval eval for search_programs over the gold set (S3).

For each question in data/kompas/eval/search_programs_gold.json:
  1. embed the question through the domovina-rag embedder (POST /embed,
     {"texts": [...]} → {"vectors": [...]}, bge-m3, L2-normalized; the query is
     sent as-is, exactly like search_podcasts in services/mcp does),
  2. rank rag.program_chunks in local ClickHouse by cosineDistance, filtered by
     has(party_ids, x) when the question names a party (query parameters only),
  3. score hit@1, hit@k, recall@k and reciprocal rank (src/kompas/eval_search.py).

Writes data/kompas/eval/search_programs_results.json (ids, ranks and scores, no
chunk texts) and prints a table. Number 26 because 25 is reserved for
25_fetch_glasanja.py (decision 100).

--rerank re-scores the top 20 with sentence-transformers
CrossEncoder("BAAI/bge-reranker-v2-m3") on CPU before scoring and writes
search_programs_results_rerank.json. It needs the package
(`uv run --with sentence-transformers ...`) and downloads the model (~2.3 GB)
on first use, so it is opt-in.

Credentials: CLICKHOUSE_USER / CLICKHOUSE_PASSWORD from the environment, else
from domovina-rag's .env (DOMOVINA_RAG_ENV overrides its path). URLs:
EMBEDDER_URL (default http://localhost:8008), CLICKHOUSE_URL (default
http://localhost:8123).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.kompas import eval_search as S  # noqa: E402

RAG_ENV = Path(os.environ.get("DOMOVINA_RAG_ENV", ROOT.parent / "domovina-rag" / ".env"))
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


class EvalError(RuntimeError):
    """Expected failure with a message for the user (printed without a traceback)."""


# ------------------------------------------------------------------ config


def config() -> dict[str, str]:
    file_env: dict[str, str] = {}
    if RAG_ENV.is_file():
        file_env = S.parse_env(RAG_ENV.read_text(encoding="utf-8"))

    def get(key: str, default: str = "") -> str:
        return os.environ.get(key) or file_env.get(key) or default

    return {
        "embedder_url": get("EMBEDDER_URL", "http://localhost:8008").rstrip("/"),
        "clickhouse_url": get("CLICKHOUSE_URL", "http://localhost:8123").rstrip("/"),
        "user": get("CLICKHOUSE_USER", "default"),
        "password": get("CLICKHOUSE_PASSWORD"),
    }


# ------------------------------------------------------------------ HTTP


def embed(client: httpx.Client, url: str, texts: list[str]) -> list[list[float]]:
    try:
        r = client.post(f"{url}/embed", json={"texts": texts}, timeout=120)
    except httpx.HTTPError as e:
        raise EvalError(f"Embedder nije dostupan na {url} ({type(e).__name__}). "
                        "Pokreni ga u domovina-rag (services/embedder) pa ponovi.") from None
    if r.status_code != 200:
        raise EvalError(f"Embedder je vratio HTTP {r.status_code}: {r.text[:300]}")
    vectors = r.json().get("vectors")
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise EvalError("Embedder je vratio neočekivan odgovor (nema 'vectors' za svaki tekst).")
    return vectors


def ch_query(client: httpx.Client, cfg: dict[str, str], sql: str,
             params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run a SELECT over ClickHouse HTTP; parameters go as param_<name>, never into the SQL."""
    qs = {"database": "rag", "default_format": "JSONEachRow"}
    qs.update({f"param_{k}": S.format_param(v) for k, v in (params or {}).items()})
    headers = {"X-ClickHouse-User": cfg["user"], "X-ClickHouse-Key": cfg["password"]}
    try:
        r = client.post(cfg["clickhouse_url"] + "/", params=qs, content=sql.encode("utf-8"),
                        headers=headers, timeout=120)
    except httpx.HTTPError as e:
        raise EvalError(f"ClickHouse nije dostupan na {cfg['clickhouse_url']} ({type(e).__name__}). "
                        "Pokreni ga u domovina-rag (docker compose) pa ponovi.") from None
    if r.status_code != 200:
        msg = r.text.strip().splitlines()[0][:300] if r.text.strip() else ""
        if r.status_code in (401, 403) or "Authentication failed" in msg:
            raise EvalError("ClickHouse je odbio prijavu: provjeri CLICKHOUSE_USER / CLICKHOUSE_PASSWORD "
                            f"(okolina ili {RAG_ENV}).")
        raise EvalError(f"ClickHouse je vratio HTTP {r.status_code}: {msg}")
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]


def check_table(client: httpx.Client, cfg: dict[str, str], gold: list[dict[str, Any]]) -> int:
    db, name = S.TABLE.split(".")
    exists = ch_query(client, cfg, "SELECT count() AS n FROM system.tables "
                                   "WHERE database = {db:String} AND name = {name:String}",
                      {"db": db, "name": name})
    if not exists or int(exists[0]["n"]) == 0:
        raise EvalError(f"Tablica {S.TABLE} ne postoji. Napravi je i napuni ETL-om u domovina-rag "
                        "(S3: program_chunks iz data/raw/kompas/chunks.jsonl) pa ponovi.")
    n = int(ch_query(client, cfg, f"SELECT count() AS n FROM {S.TABLE}")[0]["n"])
    if n == 0:
        raise EvalError(f"Tablica {S.TABLE} je prazna. Pokreni ETL za programe pa ponovi.")
    ids = sorted({cid for q in gold for cid in S.expected_ids(q)})
    found = {r["chunk_id"] for r in ch_query(
        client, cfg, f"SELECT chunk_id FROM {S.TABLE} WHERE has({{ids:Array(String)}}, chunk_id)",
        {"ids": ids})}
    missing = [c for c in ids if c not in found]
    if missing:
        print(f"UPOZORENJE: {len(missing)} označenih chunkova nema u {S.TABLE} "
              f"(npr. {', '.join(missing[:3])}); ta pitanja ne mogu postići puni rezultat.",
              file=sys.stderr)
    return n


# ------------------------------------------------------------------ rerank


def load_reranker():
    try:
        from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]
    except ImportError:
        raise EvalError("--rerank traži paket sentence-transformers: pokreni s "
                        "`uv run --with sentence-transformers python scripts/26_eval_search_programs.py "
                        "--rerank` (prvi put preuzima model BAAI/bge-reranker-v2-m3, ~2,3 GB).") from None
    # CPU on purpose: an uncapped MPS model next to the embedder can take the Mac mini down.
    return CrossEncoder(RERANK_MODEL, device="cpu", max_length=512)


# ------------------------------------------------------------------ main


def run(args: argparse.Namespace) -> dict[str, Any]:
    gold = S.load_gold(S.GOLD_PATH)
    if args.limit_questions:
        gold = gold[: args.limit_questions]
    cfg = config()
    k = args.k
    reranker = load_reranker() if args.rerank else None

    with httpx.Client() as client:
        total = check_table(client, cfg, gold)
        vectors = embed(client, cfg["embedder_url"], [q["question"] for q in gold])
        rows_out = []
        for q, vec in zip(gold, vectors):
            sql, params = S.build_search_sql(q["party_ids"], with_text=reranker is not None)
            params.update({"q": vec, "limit": max(S.CANDIDATES, k)})
            rows = ch_query(client, cfg, sql, params)
            if reranker is not None:
                rows = S.rerank_rows(q["question"], rows,
                                     lambda pairs: reranker.predict(pairs, batch_size=4))
            ranked = [r["chunk_id"] for r in rows]
            scored = S.score_question(S.expected_ids(q), ranked, k)
            rows_out.append({
                "id": q["id"], "party": q["party"], "party_ids": q["party_ids"], "topic": q["topic"],
                **scored,
                "top": [{"chunk_id": r["chunk_id"], "distance": round(float(r["distance"]), 6),
                         **({"rerank_score": r["rerank_score"]} if "rerank_score" in r else {})}
                        for r in rows[:max(k, 10)]],
            })

    return {
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "table": S.TABLE, "table_rows": total, "k": k, "candidates": max(S.CANDIDATES, k),
        "rerank": RERANK_MODEL if reranker is not None else None,
        "embedder_url": cfg["embedder_url"],
        "definitions": {
            "hit@k": "1 ako je barem jedan označeni chunk u prvih k",
            "recall@k": "udio označenih chunkova u prvih k",
            "mrr": "prosjek 1/rang prvog označenog chunka unutar dohvaćenih kandidata (0 ako ga nema)",
            "recall@5 (plan S3)": "izvještava se kao prosječni hit@5; prosječni recall@5 stoji uz njega",
        },
        "summary": S.aggregate(rows_out, k),
        "questions": rows_out,
    }


def table(res: dict[str, Any]) -> str:
    k = res["k"]
    lines = [f"{'id':4} {'party':10} {'topic':24} {'hit@1':>5} {f'hit@{k}':>5} {f'rec@{k}':>6} "
             f"{'rr':>5} {'rank':>4}"]
    for r in res["questions"]:
        lines.append(f"{r['id']:4} {(r['party'] or '—')[:10]:10} {r['topic'][:24]:24} {r['hit@1']:>5} "
                     f"{r[f'hit@{k}']:>5} {r[f'recall@{k}']:>6.2f} {r['rr']:>5.2f} "
                     f"{r['first_rank'] if r['first_rank'] is not None else '—':>4}")
    lines.append("")
    for name, b in res["summary"].items():
        if not b["n"]:
            continue
        lines.append(f"{name:10} n={b['n']:>2}  hit@1 {b['hit@1']:.3f}  hit@{k} {b[f'hit@{k}']:.3f}  "
                     f"recall@{k} {b[f'recall@{k}']:.3f}  MRR@{res['candidates']} {b['mrr']:.3f}")
    lines.append(f"(recall@{k} u planu = prosječni hit@{k}; rerank: {res['rerank'] or 'ne'})")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=5, help="cut-off for hit@k / recall@k (default 5)")
    ap.add_argument("--limit-questions", type=int, default=0, help="only the first N questions")
    ap.add_argument("--rerank", action="store_true",
                    help=f"rerank the top {S.CANDIDATES} with {RERANK_MODEL} (CPU, needs sentence-transformers)")
    ap.add_argument("--out", type=Path, default=None, help="results path (default data/kompas/eval/…)")
    args = ap.parse_args()
    if args.k < 1:
        ap.error("--k mora biti barem 1")

    try:
        res = run(args)
    except EvalError as e:
        print(f"GREŠKA: {e}", file=sys.stderr)
        return 2
    out = args.out or (S.RESULTS_PATH.with_name(S.RESULTS_PATH.stem + "_rerank.json")
                       if args.rerank else S.RESULTS_PATH)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(table(res))
    print(f"\n→ {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
