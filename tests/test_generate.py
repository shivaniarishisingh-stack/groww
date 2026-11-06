import pytest

from src.config import settings
from src.generate import (
    answer,
    latest_source_date,
    parse_llm_response,
    split_sentences,
    trim_to_sentences,
)
from src.llm.base import LLMConfigurationError, LLMResponseError
from src.llm.groq_client import GroqClient
from src.retrieve import RetrievalHit, RetrievalResult

TOP_URL = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
SECOND_URL = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
OTHER_ALLOWED_URL = (
    "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth"
)


def make_hit(
    *,
    chunk_id="hdfc-large-cap-fund-direct-growth-005",
    url=TOP_URL,
    section="expense_ratio",
    text="Expense ratio 1.02%",
    fetched_at="2026-11-03T16:23:56+00:00",
    score=0.82,
):
    return RetrievalHit(
        chunk_id=chunk_id,
        url=url,
        title="HDFC fund page",
        section=section,
        text=text,
        fetched_at=fetched_at,
        score=score,
        vector_score=score - 0.3,
        distance=1 - (score - 0.3),
        fact_match=True,
    )


def make_result(*hits, intent="fact", trace_path=None):
    return RetrievalResult(
        intent=intent,
        hits=tuple(hits),
        trace_path=trace_path,
    )


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.response


class NoCallClient:
    def complete(self, system, user):
        raise AssertionError("LLM must not be called on a refusal path")


def run_answer(question, response, *hits, client=None):
    fake = client or FakeClient(response)
    result = answer(
        question,
        client=fake,
        retrieval=lambda _question: make_result(*hits),
    )
    return result, fake


def test_fact_answer_is_trimmed_to_three_sentences_and_cites_a_hit():
    result, fake = run_answer(
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        '{"answer": "One. Two. Three. Four. Five.", "source_url": "https://example.com"}',
        make_hit(),
    )
    assert result.intent == "fact"
    assert result.llm_used is True
    assert len(split_sentences(result.answer)) == 3
    assert result.source_url == TOP_URL
    assert result.last_updated == "03 Nov 2026"
    assert fake.calls


def test_fenced_json_is_parsed_and_tolerated():
    answer_text, source = parse_llm_response(
        '```json\n{"answer": "The expense ratio is 1.02%.", '
        f'"source_url": "{TOP_URL}"}}\n```'
    )
    assert answer_text == "The expense ratio is 1.02%."
    assert source == TOP_URL


def test_valid_second_hit_source_is_kept_and_latest_date_wins():
    first = make_hit(fetched_at="2026-11-03T16:23:56+00:00")
    second = make_hit(
        chunk_id="hdfc-mid-cap-fund-direct-growth-025",
        url=SECOND_URL,
        section="min_sip",
        text="Minimum SIP Investment is set to ₹100.",
        fetched_at="2026-11-04T09:00:00+00:00",
    )
    result, _ = run_answer(
        "What is the minimum SIP for HDFC Mid Cap Fund Direct Growth?",
        '{"answer": "The minimum SIP is ₹100.", '
        f'"source_url": "{SECOND_URL}"}}',
        first,
        second,
    )
    assert result.source_url == SECOND_URL
    assert result.last_updated == "04 Nov 2026"


def test_other_allowlisted_url_is_accepted():
    result, _ = run_answer(
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        '{"answer": "The expense ratio is 1.02%.", '
        f'"source_url": "{OTHER_ALLOWED_URL}"}}',
        make_hit(),
    )
    assert result.source_url == OTHER_ALLOWED_URL


def test_plain_text_response_falls_back_to_top_hit():
    result, _ = run_answer(
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        "The expense ratio is 1.02%.",
        make_hit(),
    )
    assert result.answer == "The expense ratio is 1.02%."
    assert result.source_url == TOP_URL


def test_empty_answer_raises():
    with pytest.raises(LLMResponseError):
        parse_llm_response('{"answer": "", "source_url": "https://example.com"}')


def test_malformed_json_raises():
    with pytest.raises(LLMResponseError):
        parse_llm_response('{"answer": "broken"')


def test_split_sentences_handles_decimals_and_abbreviations():
    text = "The rate is 1.02%. Rs. 500 is the SIP. Dr. Smith agrees."
    assert len(split_sentences(text)) == 3
    assert trim_to_sentences(text) == text


def test_latest_source_date_handles_missing_values():
    assert latest_source_date([]) is None
    assert latest_source_date([make_hit(fetched_at="")]) is None


@pytest.mark.parametrize(
    "intent",
    ["refuse_advice", "refuse_returns", "refuse_pii", "out_of_corpus"],
)
def test_refusals_do_not_call_the_llm(intent):
    result = answer(
        "Should I buy HDFC Flexi Cap?",
        client=NoCallClient(),
        retrieval=lambda _question: make_result(intent=intent),
    )
    assert result.intent == intent
    assert result.llm_used is False
    assert result.last_updated is None
    assert result.source_url.startswith("https://groww.in/")


def test_fact_with_no_hits_becomes_out_of_corpus():
    result = answer(
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        client=NoCallClient(),
        retrieval=lambda _question: make_result(intent="fact"),
    )
    assert result.intent == "out_of_corpus"
    assert result.llm_used is False
    assert "available" in result.answer


def test_model_not_found_answer_becomes_out_of_corpus():
    result, _ = run_answer(
        "What is the weather in Mumbai?",
        '{"answer": "The fact is not on the sourced pages.", '
        '"source_url": "https://example.com"}',
        make_hit(text="HDFC Large Cap Fund AUM is ₹9,34,076 Cr."),
    )
    assert result.intent == "out_of_corpus"
    assert result.source_url == settings.educational_link
    assert result.last_updated is None


def test_model_not_explicitly_stated_answer_becomes_out_of_corpus():
    result, _ = run_answer(
        "What is the lock-in for HDFC ELSS Tax Saver?",
        '{"answer": "The lock-in period is not explicitly stated in the '
        'provided context.", "source_url": "' + OTHER_ALLOWED_URL + '"}',
        make_hit(
            url=OTHER_ALLOWED_URL,
            section="lock_in",
            text="Lock-in Equity ELSS Very High Risk +13.51 % 3Y annualised",
        ),
    )
    assert result.intent == "out_of_corpus"
    assert result.source_url == settings.educational_link
    assert result.last_updated is None


def test_invented_lockin_duration_becomes_out_of_corpus():
    hit = make_hit(
        chunk_id="hdfc-elss-tax-saver-fund-direct-plan-growth-004",
        url=OTHER_ALLOWED_URL,
        section="lock_in",
        text=(
            "Lock-in Equity ELSS Very High Risk +13.51 % 3Y annualised "
            "+2.13 % 1D 1M 6M 1Y 3Y 5Y All NAV: 05 Nov 26 ₹1,512.20"
        ),
    )
    result, _ = run_answer(
        "What is the lock-in for HDFC ELSS Tax Saver?",
        '{"answer": "The lock-in period for HDFC ELSS Tax Saver is 3 years.", '
        f'"source_url": "{OTHER_ALLOWED_URL}"}}',
        hit,
    )
    assert result.intent == "out_of_corpus"
    assert result.source_url == settings.educational_link
    assert result.last_updated is None


def test_supported_lockin_duration_is_kept():
    hit = make_hit(
        chunk_id="hdfc-elss-tax-saver-fund-direct-plan-growth-004",
        url=OTHER_ALLOWED_URL,
        section="lock_in",
        text="HDFC ELSS Tax Saver ELSS • 3Y Lock-in Equity ELSS Very High Risk",
    )
    result, _ = run_answer(
        "What is the lock-in for HDFC ELSS Tax Saver?",
        '{"answer": "The lock-in period for HDFC ELSS Tax Saver is 3 years.", '
        f'"source_url": "{OTHER_ALLOWED_URL}"}}',
        hit,
    )
    assert result.intent == "fact"
    assert "3 years" in result.answer
    assert result.source_url == OTHER_ALLOWED_URL


def test_missing_groq_key_raises_clear_error():
    with pytest.raises(LLMConfigurationError, match="GROQ_API_KEY"):
        GroqClient(api_key="", model="qwen/qwen3-32b")


def test_missing_llm_model_raises_clear_error():
    with pytest.raises(LLMConfigurationError, match="LLM_MODEL"):
        GroqClient(api_key="test-key", model="   ")
