import json
from dataclasses import replace

import pytest

import src.retrieve as retrieval


@pytest.fixture
def isolated_traces(tmp_path, monkeypatch):
    patched = replace(
        retrieval.settings,
        paths=replace(retrieval.settings.paths, traces=tmp_path),
    )
    monkeypatch.setattr(retrieval, "settings", patched)
    return tmp_path


def test_policy_refusals_do_not_touch_chroma(monkeypatch):
    def fail_if_called():
        raise AssertionError("Chroma must not be queried for a refused intent")

    monkeypatch.setattr(retrieval, "_get_collection", fail_if_called)

    cases = {
        "Should I buy HDFC Flexi Cap?": "refuse_advice",
        "Is Large Cap better than Mid Cap?": "refuse_returns",
        "What was 1Y return of HDFC ELSS?": "refuse_returns",
        "OTP 482911 email me the statement": "refuse_pii",
    }
    for question, expected in cases.items():
        result = retrieval.retrieve(question, persist_trace=False)
        assert result.intent == expected
        assert result.hits == ()


def test_pii_trace_is_a_safe_stub(isolated_traces):
    result = retrieval.retrieve(
        "My PAN is ABCDE1234F, show holdings",
        persist_trace=True,
    )
    assert result.intent == "refuse_pii"

    path = isolated_traces / "refuse_pii.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["intent"] == "refuse_pii"
    assert payload["pii_type"] == "pan"
    assert payload["query_redacted"] is True
    assert payload["hits"] == []
    assert "query_hash" not in payload
    assert "query_length" not in payload
    assert "ABCDE1234F" not in path.read_text(encoding="utf-8")


def test_advice_trace_does_not_store_raw_question(isolated_traces):
    question = "Should I buy HDFC Flexi Cap?"
    result = retrieval.retrieve(question, persist_trace=True)
    assert result.intent == "refuse_advice"

    path = result.trace_path
    assert path is not None
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = path.read_text(encoding="utf-8")

    assert payload["intent"] == "refuse_advice"
    assert payload["query_redacted"] is True
    assert payload["hits"] == []
    assert payload["query_hash"]
    assert "query" not in payload
    assert question.lower() not in raw.lower()


def test_missing_collection_returns_out_of_corpus(monkeypatch):
    monkeypatch.setattr(retrieval, "_get_collection", lambda: None)
    result = retrieval.retrieve(
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        persist_trace=False,
    )
    assert result.intent == "out_of_corpus"
    assert result.hits == ()


def test_empty_collection_returns_out_of_corpus(monkeypatch):
    class EmptyCollection:
        def count(self):
            return 0

        def get(self, **_kwargs):
            return {"ids": []}

    monkeypatch.setattr(retrieval, "_get_collection", EmptyCollection)
    result = retrieval.retrieve(
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        persist_trace=False,
    )
    assert result.intent == "out_of_corpus"
    assert result.hits == ()
    assert result.candidate_count == 0
