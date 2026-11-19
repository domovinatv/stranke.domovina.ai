"""Retrieval eval for search_programs (src/kompas/eval_search.py, S3).

Offline: metrics on hand-made rankings, the committed gold file and the SQL
builder. data/raw/kompas/chunks.jsonl is gitignored; when it is present the
gold labels are also checked against it, otherwise only their shape is.
"""
from __future__ import annotations

import copy
import json
import re

import pytest

from src.kompas import eval_search as S

GOLD = json.loads(S.GOLD_PATH.read_text(encoding="utf-8"))
STRANKE = json.loads(S.LISTE_PATH.read_text(encoding="utf-8"))["stranke"]


# ------------------------------------------------------------------ metrics


def test_metrics_on_hand_made_ranking():
    ranked = ["a", "x", "b", "y", "z", "c"]
    exp = ["b", "c", "d"]
    assert S.first_rank(exp, ranked) == 3
    assert S.hit_at(exp, ranked, 1) == 0
    assert S.hit_at(exp, ranked, 3) == 1
    assert S.recall_at(exp, ranked, 5) == pytest.approx(1 / 3)
    assert S.recall_at(exp, ranked, 6) == pytest.approx(2 / 3)
    assert S.reciprocal_rank(exp, ranked) == pytest.approx(1 / 3)


def test_metrics_when_nothing_is_found_and_when_first_is_right():
    assert S.first_rank(["q"], ["a", "b"]) is None
    assert S.reciprocal_rank(["q"], ["a", "b"]) == 0.0
    assert S.hit_at(["q"], ["a", "b"], 5) == 0
    assert S.recall_at(["q"], [], 5) == 0.0
    assert S.reciprocal_rank(["a"], ["a", "b"]) == 1.0
    with pytest.raises(ValueError):
        S.recall_at([], ["a"], 5)


def test_score_question_reports_rank_of_every_expected_chunk():
    s = S.score_question(["c", "a", "zz"], ["a", "b", "c", "d", "e", "f", "c"], 5)
    assert s["hit@1"] == 1 and s["hit@5"] == 1
    assert s["recall@5"] == pytest.approx(0.6667)
    assert s["rr"] == 1.0 and s["first_rank"] == 1
    assert s["ranks"] == {"c": 3, "a": 1, "zz": None}  # first occurrence wins


def test_aggregate_splits_filtered_and_unfiltered():
    rows = [
        {**S.score_question(["a"], ["a", "b"], 5), "party_ids": [182]},
        {**S.score_question(["b"], ["a", "b"], 5), "party_ids": [258]},
        {**S.score_question(["z"], ["a", "b"], 5), "party_ids": None},
    ]
    agg = S.aggregate(rows, 5)
    assert agg["all"] == {"n": 3, "hit@1": pytest.approx(0.3333), "hit@5": pytest.approx(0.6667),
                          "recall@5": pytest.approx(0.6667), "mrr": pytest.approx(0.5)}
    assert agg["filtered"]["n"] == 2 and agg["filtered"]["mrr"] == pytest.approx(0.75)
    assert agg["unfiltered"] == {"n": 1, "hit@1": 0.0, "hit@5": 0.0, "recall@5": 0.0, "mrr": 0.0}
    assert S.aggregate([], 5)["all"]["mrr"] is None


# ------------------------------------------------------------------ gold file


def test_gold_file_is_valid_and_parties_resolve():
    assert S.validate_gold(GOLD, stranke=STRANKE) == []
    qs = S.load_gold()
    assert len(qs) == 20
    assert [q["id"] for q in qs] == [f"q{i:02d}" for i in range(1, 21)]


def test_gold_spread_over_parties_topics_and_filters():
    qs = GOLD["pitanja"]
    filtered = [q for q in qs if q["party"]]
    assert 12 <= len(filtered) <= 16 and len(qs) - len(filtered) >= 4
    parties = {p for q in filtered for p in q["party_ids"]}
    assert len(parties) >= 10
    assert {182, 258, 390, 261, 149} <= parties  # HDZ, DP, Most, Možemo!, SDP
    assert len({q["topic"] for q in qs}) >= 10
    # Unfiltered questions are cross-party: labels from more than one document.
    for q in qs:
        if not q["party"]:
            assert len({e["doc_id"] for e in q["expected"]}) >= 2, q["id"]


def test_gold_labels_have_valid_ids_and_short_snippets():
    for q in GOLD["pitanja"]:
        assert 1 <= len(q["expected"]) <= 5, q["id"]
        for e in q["expected"]:
            m = re.fullmatch(r"^prog_[0-9a-f]{12}_\d{4}$", e["chunk_id"])
            assert m, e["chunk_id"]
            assert e["chunk_id"][5:17] == e["doc_id"]
            assert 1 <= len(e["snippet"].split()) <= 15
        # The IDS Italian duplicate is never the only target (decision 205).
        assert any(not e["chunk_id"].startswith("prog_5111e0ffaee2_00") or
                   int(e["chunk_id"][-4:]) < 17 for e in q["expected"]), q["id"]


def test_gold_labels_exist_in_chunks_when_raw_file_is_present():
    """chunks.jsonl is gitignored (decision 203): without it this checks the id
    format only, with it every label must exist and its snippet must be verbatim."""
    ids = {e["chunk_id"] for q in GOLD["pitanja"] for e in q["expected"]}
    assert all(S.CHUNK_ID_RE.match(c) for c in ids)
    if not S.CHUNKS_PATH.exists():
        return
    texts = {}
    for line in S.CHUNKS_PATH.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        texts[r["id"]] = re.sub(r"\s+", " ", r["text"])
    assert S.validate_gold(GOLD, chunk_ids=set(texts)) == []
    for q in GOLD["pitanja"]:
        for e in q["expected"]:
            assert re.sub(r"\s+", " ", e["snippet"]) in texts[e["chunk_id"]], (q["id"], e["chunk_id"])


@pytest.mark.parametrize("mutate, needle", [
    (lambda d: d["pitanja"][1].update(id="q01"), "dupli id"),
    (lambda d: d["pitanja"][0].update(id="Q1"), "oblika q01"),
    (lambda d: d["pitanja"][0]["expected"][0].update(chunk_id="prog_XYZ_1"), "nije oblika"),
    (lambda d: d["pitanja"][0]["expected"][0].update(doc_id="000000000000"), "ne odgovara"),
    (lambda d: d["pitanja"][0]["expected"][0].update(snippet="riječ " * 16), "više od 15"),
    (lambda d: d["pitanja"][0].update(party_ids=None), "bez ispravnih party_ids"),
    (lambda d: d["pitanja"][0].update(party_ids=[13]), "ne razrješava"),
    (lambda d: d["pitanja"][14].update(party_ids=[182]), "party_ids bez party"),
    (lambda d: d["pitanja"][0].update(expected=[]), "nema očekivanih"),
    (lambda d: d["pitanja"][0]["expected"].append(dict(d["pitanja"][0]["expected"][0])), "dvaput"),
])
def test_validate_gold_catches_errors(mutate, needle):
    doc = copy.deepcopy(GOLD)
    mutate(doc)
    errors = S.validate_gold(doc, stranke=STRANKE)
    assert any(needle in e for e in errors), errors


def test_validate_gold_checks_existence_against_given_ids():
    errors = S.validate_gold(GOLD, chunk_ids={"prog_000000000000_0001"})
    assert len(errors) == sum(len(q["expected"]) for q in GOLD["pitanja"])
    assert S.validate_gold({"nesto": 1}) == ["dokument nema listu 'pitanja'"]


def test_resolve_party_by_short_name_slug_and_canonical_name():
    assert S.resolve_party("HDZ", STRANKE) == [182]
    assert S.resolve_party("most", STRANKE) == [390]
    assert S.resolve_party("možemo!", STRANKE) == [261]
    assert S.resolve_party("domovinski-pokret", STRANKE) == [258]
    assert S.resolve_party("Centar", STRANKE) == [304]
    assert S.resolve_party("nepostojeća", STRANKE) == []


# ------------------------------------------------------------------ SQL


def test_sql_without_filter_binds_everything_as_parameters():
    sql, params = S.build_search_sql(None)
    assert "WHERE" not in sql
    assert "{q:Array(Float32)}" in sql and "{limit:UInt32}" in sql
    assert "FROM rag.program_chunks" in sql
    assert "ORDER BY distance ASC" in sql and "cosineDistance(embedding" in sql
    assert params == {}
    assert ", text," not in sql


def test_sql_party_filter_uses_has_with_parameters_only():
    sql, params = S.build_search_sql([149, 304], with_text=True)
    assert "WHERE has(party_ids, {p0:UInt32}) OR has(party_ids, {p1:UInt32})" in sql
    assert params == {"p0": 149, "p1": 304}
    assert "149" not in sql and "304" not in sql
    assert "chunk_id, doc_id, party_ids, text" in sql


@pytest.mark.parametrize("bad", [["1; DROP TABLE x"], [0], [-3], [True], [1.5]])
def test_sql_rejects_non_integer_party_ids(bad):
    with pytest.raises(ValueError):
        S.build_search_sql(bad)


def test_sql_rejects_odd_table_names():
    with pytest.raises(ValueError):
        S.build_search_sql(None, table="rag.x; DROP")


def test_format_param_for_clickhouse_http():
    assert S.format_param([0.5, -1.25, 0]) == "[0.5,-1.25,0]"
    assert S.format_param(20) == "20"
    assert S.format_param(["prog_a", "it's"]) == "['prog_a','it\\'s']"
    with pytest.raises(ValueError):
        S.format_param([float("nan")])
    with pytest.raises(TypeError):
        S.format_param({"a": 1})


# ------------------------------------------------------------------ helpers


def test_parse_env():
    env = S.parse_env("# c\n\nCLICKHOUSE_USER=rag\nexport CLICKHOUSE_PASSWORD=\"s3 cr#t\"\n"
                      "CLICKHOUSE_DB=rag # inline\nBROKEN\n")
    assert env == {"CLICKHOUSE_USER": "rag", "CLICKHOUSE_PASSWORD": "s3 cr#t", "CLICKHOUSE_DB": "rag"}


def test_rerank_orders_by_score_and_keeps_ties_stable():
    rows = [{"chunk_id": c, "text": c * 2, "distance": d} for c, d in [("a", .1), ("b", .2), ("c", .3)]]
    seen = []

    def predict(pairs):
        seen.extend(pairs)
        return [0.1, 0.9, 0.1]

    out = S.rerank_rows("upit", rows, predict)
    assert [r["chunk_id"] for r in out] == ["b", "a", "c"]
    assert out[0]["rerank_score"] == 0.9
    assert seen == [("upit", "aa"), ("upit", "bb"), ("upit", "cc")]
    assert S.rerank_rows("upit", [], predict) == []
    with pytest.raises(ValueError):
        S.apply_rerank(rows, [1.0])
