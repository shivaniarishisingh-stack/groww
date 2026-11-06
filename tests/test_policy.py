import pytest

from src.policy import (
    INTENT_FACT,
    INTENT_REFUSE_ADVICE,
    INTENT_REFUSE_PII,
    INTENT_REFUSE_RETURNS,
    REFUSAL_MESSAGES,
    refusal_message,
    scan,
)


@pytest.mark.parametrize(
    "question",
    [
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        "What is the lock-in for HDFC ELSS Tax Saver?",
        "What is the minimum SIP for HDFC Mid Cap Fund Direct Growth?",
        "What is the exit load if redeemed within 1 year?",
        "What is the benchmark of HDFC Large Cap?",
        "What is the riskometer of HDFC Large Cap?",
        "What is the AUM of HDFC Large Cap Fund?",
        "What is the NAV of HDFC Large Cap Fund?",
        "How can I download a capital gains statement?",
    ],
)
def test_factual_questions_pass_policy(question):
    assert scan(question).intent == INTENT_FACT


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Should I buy HDFC Flexi Cap?", INTENT_REFUSE_ADVICE),
        ("Should I switch from Large Cap to Mid Cap?", INTENT_REFUSE_ADVICE),
        ("Which fund is best for me?", INTENT_REFUSE_ADVICE),
        ("Is this a good fund?", INTENT_REFUSE_ADVICE),
        ("Help me build a portfolio.", INTENT_REFUSE_ADVICE),
        ("Is Large Cap better than Mid Cap?", INTENT_REFUSE_RETURNS),
        ("What was 1Y return of HDFC ELSS?", INTENT_REFUSE_RETURNS),
        ("What is the 3-year annualised return?", INTENT_REFUSE_RETURNS),
        ("How has the fund performed?", INTENT_REFUSE_RETURNS),
        ("Compare Large Cap and Mid Cap.", INTENT_REFUSE_RETURNS),
        ("How much would ₹10,000 grow?", INTENT_REFUSE_RETURNS),
    ],
)
def test_refusal_intents(question, expected):
    decision = scan(question)
    assert decision.intent == expected
    assert decision.pii_type is None


@pytest.mark.parametrize(
    "question,pii_type",
    [
        ("My PAN is ABCDE1234F, show holdings", "pan"),
        ("OTP 482911 email me the statement", "otp"),
        ("My Aadhaar is 1234 5678 9012", "aadhaar"),
        ("Call me on 9876543210", "phone"),
        ("Send it to user@example.com", "email"),
        ("My folio number is 12345678", "account"),
    ],
)
def test_pii_intents(question, pii_type):
    decision = scan(question)
    assert decision.intent == INTENT_REFUSE_PII
    assert decision.pii_type == pii_type


def test_pii_is_checked_before_other_intents():
    decision = scan("Should I buy more? My PAN is ABCDE1234F")
    assert decision.intent == INTENT_REFUSE_PII
    assert decision.pii_type == "pan"


def test_pii_decision_does_not_echo_value():
    decision = scan("My PAN is ABCDE1234F")
    assert "ABCDE1234F" not in repr(decision)


def test_refusal_messages_are_safe_and_short():
    advice = refusal_message(INTENT_REFUSE_ADVICE).lower()
    assert "buy" not in advice
    assert "sell" not in advice
    assert "recommend" in advice or "advice" in advice

    returns = refusal_message(INTENT_REFUSE_RETURNS)
    assert not any(character.isdigit() for character in returns)
    assert "return" in returns.lower()

    pii = refusal_message(INTENT_REFUSE_PII)
    assert "ABCDE1234F" not in pii
    assert "482911" not in pii

    for intent, message in REFUSAL_MESSAGES.items():
        assert message
        assert len(message.split(".")) <= 4, intent
