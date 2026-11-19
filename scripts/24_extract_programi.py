"""Kompas stranaka: extract text from the programmes and chunk it for RAG (S2).

Reads data/kompas/programi.json and the raw files under data/raw/programi/
(fetched by scripts/23_fetch_programi.py), then:

  1. per document → data/raw/programi/<slug>/<doc_id>.pages.json
     (pages with text, headings, paragraphs and quality counters; skipped when
     the source's sha256 and the extractor version are unchanged, unless --force)
  2. all documents → data/raw/kompas/chunks.jsonl (domovina-rag ETL shape,
     full text, never committed: decision 8)
  3. counts only → data/kompas/chunks_stats.json (committed)

--report prints the quality table (empty pages, OCR candidates, diacritics,
suspicious characters, chunks per document and per party). Logic lives in
src/kompas/extract.py and src/kompas/chunk.py. Offline; no LLM calls.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.kompas import chunk as C  # noqa: E402
from src.kompas import extract as E  # noqa: E402
from src.kompas import programi as P  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("extract")
logging.getLogger("pypdf").setLevel(logging.ERROR)


def report(stats: dict) -> str:
    rows = [f"{'doc_id':12} {'slug':34} {'fmt':4} {'pg':>4} {'empty':>5} {'ocr':>3} "
            f"{'words':>6} {'rijeci':>6} {'chunks':>6} {'avg':>5} {'dia':>5} {'susp(raw→clean)':16} nes"]
    for d in stats["dokumenti"]:
        raw = sum(d["suspicious_raw"].values())
        clean = sum(d["suspicious_clean"].values())
        dia = f"{d['diacritics_share']:.3f}" + ("!" if d["diacritics_suspicious"] else "")
        rows.append(
            f"{d['doc_id']:12} {(d['slug'] or '')[:34]:34} {d['format']:4} {d['pages']:>4} "
            f"{d['empty_pages']:>5} {d['needs_ocr_pages']:>3} {d['words']:>6} {d['rijeci'] or 0:>6} "
            f"{d['chunks']:>6} {d['avg_chunk_words']:>5} {dia:>5} {f'{raw}→{clean}':16} "
            f"{'da' if d['nesiguran'] else ''}")
    t = stats["totals"]
    rows.append("")
    rows.append(f"total: {t['docs']} docs, {t['pages']} pages, {t['empty_pages']} empty, "
                f"{t['needs_ocr_pages']} need OCR, {t['words']} words, {t['chunks']} chunks "
                f"(avg {t['avg_chunk_words']} words), {t['nesigurni_docs']} uncertain docs; "
                f"suspicious diacritics: {t['diacritics_suspicious_docs'] or 'none'}")
    rows.append(f"{stats['chunks_path']}: {stats['chunks_bytes']} bytes")
    rows.append("")
    rows.append("chunks per party:")
    for pid, e in stats["stranke"].items():
        rows.append(f"  {pid:>4} {(e['slug'] or '?')[:50]:50} docs {e['docs']:>2}  chunks {e['chunks']:>4}")
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-extract even when the source is unchanged")
    ap.add_argument("--report", action="store_true", help="print the quality table")
    args = ap.parse_args()

    programi = json.loads(P.OUT_PATH.read_text(encoding="utf-8"))
    docs, counters = E.extract_all(programi["dokumenti"], force=args.force)
    log.info("extracted %d, unchanged %d, missing %d", counters["extracted"], counters["skipped"],
             len(counters["missing"]))
    if counters["missing"]:
        log.error("raw files missing for %s", ", ".join(counters["missing"]))

    by_doc = {d["doc_id"]: C.chunk_document(d) for d in docs}
    body = C.jsonl(c for d in docs for c in by_doc[d["doc_id"]]).encode("utf-8")
    C.CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    C.CHUNKS_PATH.write_bytes(body)
    stats = C.build_stats(docs, by_doc, programi, body)
    C.STATS_PATH.write_text(P.dump(stats), encoding="utf-8")
    log.info("%d chunks → %s (%d bytes); stats → %s", stats["totals"]["chunks"],
             C.CHUNKS_PATH.relative_to(ROOT), len(body), C.STATS_PATH.relative_to(ROOT))
    if args.report:
        print(report(stats))
    return 1 if counters["missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
