from __future__ import annotations

import re
from dataclasses import dataclass

# Policy runs before retrieval/generation. It is intentionally regex-first so
# the safety behaviour is inspectable and does not depend on an LLM.

INTENT_FACT = "fact"
INTENT_REFUSE_ADVICE = "refuse_advice"
INTENT_REFUSE_RETURNS = "refuse_returns"
INTENT_REFUSE_PII = "refuse_pii"

REFUSAL_MESSAGES: dict[str, str] = {
    INTENT_REFUSE_PII: (
        "I can't accept PAN, Aadhaar, account, OTP, email, or phone details. "
        "Please ask a facts-only question without personal information."
    ),
    INTENT_REFUSE_ADVICE: (
        "I can only share facts from the listed Groww pages and can't offer "
        "investment advice or recommendations. Please ask about a specific fact "
        "such as expense ratio, exit load, or minimum SIP."
    ),
    INTENT_REFUSE_RETURNS: (
        "I can't calculate, compare, or comment on returns or performance. "
        "You can check the official scheme page for published figures."
    ),
    "out_of_corpus": (
        "That fact isn't available on the five sourced Groww pages. "
        "Please check the linked official page for details."
    ),
}

PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pan", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)),
    (
        "aadhaar",
        re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"),
    ),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", re.IGNORECASE)),
    (
        "phone",
        re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)"),
    ),
    (
        "otp",
        re.compile(
            r"\botp\b[^\d]{0,20}\d{4,8}\b|\b\d{4,8}\b[^\n]{0,20}\botp\b",
            re.IGNORECASE,
        ),
    ),
    (
        "account",
        re.compile(
            r"\b(?:account|a/c|folio)\s*(?:number|no\.?|#)?\s*"
            r"(?:is|=|:)?\s*[:#-]?\s*\d{6,}\b",
            re.IGNORECASE,
        ),
    ),
)

_ADVICE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "should_buy_sell",
        re.compile(
            r"\b(?:should|shall|can|could|would|do)\s+(?:i|we)\s+"
            r"(?:buy|sell|switch|invest|redeem|hold|exit|book|start|stop|choose)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "buy_sell_command",
        re.compile(
            r"\b(?:buy|sell|switch|redeem|invest)\s+"
            r"(?:in|into|this|the|hdfc|a|an)\b[^.\n]{0,60}"
            r"\b(?:fund|scheme|plan|now)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "recommendation",
        re.compile(
            r"\b(?:best|top|recommended|recommend|suggest|suggestion|good|safe)\b"
            r"[^.\n]{0,50}\b(?:fund|scheme|investment|option|plan)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "portfolio",
        re.compile(
            r"\b(?:portfolio|asset\s+allocation|diversif(?:y|ication))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "which_fund",
        re.compile(
            r"\bwhich\s+(?:fund|scheme|one)\s+(?:is|should|would|to)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "worth_investing",
        re.compile(
            r"\b(?:worth\s+(?:buying|investing)|good\s+time\s+to\s+invest|"
            r"market\s+timing)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "hold_or_sell",
        re.compile(
            r"\b(?:hold|buy|sell|switch)\s+or\s+(?:sell|hold|switch)\b|"
            r"\bbook\s+(?:profit|loss)\b",
            re.IGNORECASE,
        ),
    ),
)

_RETURNS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("return_word", re.compile(r"\breturns?\b", re.IGNORECASE)),
    ("cagr_xirr", re.compile(r"\b(?:cagr|xirr)\b", re.IGNORECASE)),
    ("annualised", re.compile(r"\bannuali[sz]ed\b", re.IGNORECASE)),
    (
        "performance",
        re.compile(r"\b(?:performance|performed|performing)\b", re.IGNORECASE),
    ),
    ("profit", re.compile(r"\bprofits?\b", re.IGNORECASE)),
    (
        "period_return",
        re.compile(
            r"\b(?:1|3|5|7|10)\s*[- ]?y(?:ear|r)?\s+"
            r"(?:returns?|performance|cagr)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "comparison",
        re.compile(
            r"\b(?:better|worse)\b[^.\n]{0,40}"
            r"\b(?:than|fund|scheme|cap|option)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "compare",
        re.compile(r"\bcompare\b|\bcomparison\b", re.IGNORECASE),
    ),
    (
        "growth_hypothetical",
        re.compile(r"\bhow\s+much\s+(?:would|will|could|has|have)\b", re.IGNORECASE),
    ),
    (
        "outperform",
        re.compile(r"\boutperform(?:ed|ing|s)?\b", re.IGNORECASE),
    ),
    (
        "fund_performed",
        re.compile(
            r"\bhow\s+(?:has|have|did)\s+(?:the\s+)?(?:fund|scheme)\s+"
            r"(?:done|do|perform)\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class PolicyDecision:
    intent: str
    pii_type: str | None = None
    rule: str | None = None


def detect_pii(text: str) -> str | None:
    """Return the PII kind found in text, or None. Never returns the value."""
    for kind, pattern in PII_PATTERNS:
        if pattern.search(text):
            return kind
    return None


def _first_match(
    patterns: tuple[tuple[str, re.Pattern[str]], ...], text: str
) -> str | None:
    for name, pattern in patterns:
        if pattern.search(text):
            return name
    return None


def scan(text: str) -> PolicyDecision:
    """Classify a question before any retrieval or generation.

    PII is checked first so a query containing personal data is never used for
    retrieval or stored in a trace. Advice and returns intent are refused before
    Chroma is queried.
    """
    value = text or ""

    pii_type = detect_pii(value)
    if pii_type:
        return PolicyDecision(INTENT_REFUSE_PII, pii_type=pii_type, rule=pii_type)

    advice_rule = _first_match(_ADVICE_PATTERNS, value)
    if advice_rule:
        return PolicyDecision(INTENT_REFUSE_ADVICE, rule=advice_rule)

    returns_rule = _first_match(_RETURNS_PATTERNS, value)
    if returns_rule:
        return PolicyDecision(INTENT_REFUSE_RETURNS, rule=returns_rule)

    return PolicyDecision(INTENT_FACT)


def refusal_message(intent: str) -> str:
    return REFUSAL_MESSAGES.get(
        intent,
        "I can only answer facts from the five sourced Groww pages.",
    )
