from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.config import settings
from src.generate import AnswerResult, answer
from src.llm import LLMConfigurationError, LLMError

FULL_DISCLAIMER = (
    "Answers are based on public Groww pages for the listed HDFC schemes and may "
    "be incomplete or out of date. Always verify on the cited source. Mutual fund "
    "investments are subject to market risks."
)

# These are question prompts only. The assistant still answers only when the
# requested fact is present in the five-page source corpus.
MORE_QUESTIONS = (
    "What is the exit load for HDFC Flexi Cap?",
    "What is the benchmark of HDFC Large Cap Fund?",
    "What is the riskometer level of HDFC Mid Cap Fund?",
    "What is the AUM of HDFC ELSS Tax Saver Fund?",
    "What is the NAV of HDFC Large Cap Fund?",
    "What information is available about HDFC Mutual Fund?",
)

# Human-readable labels for the five allowlisted corpus pages. The URLs come
# from config.yaml so the displayed list cannot drift from the retrieval scope.
SOURCE_LABELS = {
    "https://groww.in/mutual-funds/amc/hdfc-mutual-funds": (
        "HDFC Mutual Fund — AMC overview"
    ),
    "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth": (
        "HDFC Large Cap Fund Direct Growth"
    ),
    "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth": (
        "HDFC Flexi Cap Direct Plan Growth"
    ),
    "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth": (
        "HDFC ELSS Tax Saver Fund Direct Plan Growth"
    ),
    "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth": (
        "HDFC Mid Cap Fund Direct Growth"
    ),
}

# Verified examples from sample_qa.md. These are illustrative; generated
# wording may vary, but the facts still come only from the cited page.
SAMPLE_QA = (
    (
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        "The expense ratio is 1.01%.",
    ),
    (
        "What is the minimum SIP for HDFC Mid Cap Fund Direct Growth?",
        "The minimum SIP investment is ₹100.",
    ),
    (
        "What is the lock-in for HDFC ELSS Tax Saver?",
        "Not stated on the five sourced pages; the assistant refuses to invent it.",
    ),
    (
        "Should I buy HDFC Flexi Cap?",
        "Refused: the assistant is facts-only and does not give investment advice.",
    ),
)



def _set_example(value: str) -> None:
    st.session_state.question = value
    st.session_state.answer_result = None


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        /* The app paints a light surface. Force dark text here so a browser or
           Streamlit dark theme cannot leave white text on a light background. */
        .stApp {
            color: #1F2937 !important;
            color-scheme: light !important;
            background:
                radial-gradient(circle at 8% 0%, rgba(31, 111, 235, .09), transparent 28rem),
                linear-gradient(180deg, #f7f9fc 0%, #ffffff 42%);
        }
        .stApp [data-testid="stAppViewContainer"],
        .stApp [data-testid="stMain"],
        .stApp .block-container {
            color: #1F2937 !important;
        }
        .block-container { max-width: 920px; padding-top: 2.2rem; padding-bottom: 3rem; }

        /* General body copy, form labels, expanders, and generated answers. */
        .stApp [data-testid="stMarkdownContainer"],
        .stApp [data-testid="stMarkdownContainer"] p,
        .stApp [data-testid="stMarkdownContainer"] li,
        .stApp [data-testid="stText"],
        .stApp [data-testid="stWidgetLabel"],
        .stApp [data-testid="stWidgetLabel"] p,
        .stApp [data-testid="stWidgetLabel"] label,
        .stApp [data-testid="stExpander"] summary,
        .stApp [data-testid="stExpander"] summary *,
        .stApp [data-testid="stForm"] label,
        .stApp [data-testid="stForm"] label * {
            color: #1F2937 !important;
            -webkit-text-fill-color: #1F2937 !important;
        }

        /* Answer panel. Covers both newer Streamlit border wrappers and the
           stVerticalBlock border used by Streamlit 1.66. */
        .stApp [data-testid="stVerticalBlockBorderWrapper"],
        .stApp [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .answer-label) {
            background-color: #ffffff !important;
            border: 1px solid #dbe7f1 !important;
            border-radius: 16px !important;
            box-shadow: 0 8px 24px rgba(15, 39, 64, .06) !important;
        }
        .stApp [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] p,
        .stApp [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .answer-label) [data-testid="stMarkdownContainer"] p {
            color: #1F2937 !important;
            -webkit-text-fill-color: #1F2937 !important;
            font-size: 1.02rem;
            line-height: 1.65;
        }

        /* Source and inline links stay blue, underlined, and readable. */
        .stApp a,
        .stApp a:visited,
        .stApp [data-testid="stMarkdownContainer"] a,
        .stApp [data-testid="stMarkdownContainer"] a:visited {
            color: #1D4ED8 !important;
            -webkit-text-fill-color: #1D4ED8 !important;
            text-decoration: underline !important;
            text-underline-offset: 2px;
            font-weight: 600;
        }
        .stApp a:hover,
        .stApp [data-testid="stMarkdownContainer"] a:hover {
            color: #1E40AF !important;
            -webkit-text-fill-color: #1E40AF !important;
        }

        /* Last-updated caption. */
        .stApp [data-testid="stCaptionContainer"],
        .stApp [data-testid="stCaptionContainer"] p,
        .stApp [data-testid="stCaptionContainer"] span {
            color: #4B5563 !important;
            -webkit-text-fill-color: #4B5563 !important;
        }

        /* Warning, disclaimer, errors, and empty-question notices. */
        .stApp div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]),
        .stApp div[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {
            background-color: #FFF8E1 !important;
            border: 1px solid #F1D18A !important;
            border-radius: 12px !important;
        }
        .stApp div[data-testid="stAlert"] *,
        .stApp div[data-testid="stAlertContainer"] *,
        .stApp div[data-testid="stAlertContentWarning"] * {
            color: #1F2937 !important;
            -webkit-text-fill-color: #1F2937 !important;
        }

        /* Spinner and status text. */
        .stApp [data-testid="stSpinner"],
        .stApp [data-testid="stSpinner"] * {
            color: #1F2937 !important;
            -webkit-text-fill-color: #1F2937 !important;
        }

        /* Question input and placeholder. */
        .stApp [data-testid="stTextAreaRootElement"] {
            background-color: #ffffff !important;
            border-radius: 12px !important;
            color: #1F2937 !important;
        }
        .stApp [data-testid="stTextArea"] textarea,
        .stApp textarea {
            color: #1F2937 !important;
            -webkit-text-fill-color: #1F2937 !important;
            caret-color: #1F2937 !important;
            background-color: #ffffff !important;
            border: 1px solid #d7e1ec !important;
            border-radius: 12px !important;
        }
        .stApp [data-testid="stTextArea"] textarea::placeholder,
        .stApp textarea::placeholder {
            color: #6B7280 !important;
            -webkit-text-fill-color: #6B7280 !important;
            opacity: 1 !important;
        }
        .stApp [data-testid="stTextArea"] textarea:focus,
        .stApp textarea:focus {
            border-color: #1D4ED8 !important;
            box-shadow: 0 0 0 3px rgba(29, 78, 216, .14) !important;
        }

        /* Question buttons. */
        div.stButton > button {
            border-radius: 12px; min-height: 3.2rem; white-space: normal;
            border: 1px solid #dbe4ee; background: white; color: #17324d;
            font-weight: 600; transition: all .15s ease;
        }
        div.stButton > button p,
        div.stButton > button span {
            color: #17324d !important;
            -webkit-text-fill-color: #17324d !important;
        }
        div.stButton > button:hover {
            border-color: #4c91c9; color: #124b78;
            box-shadow: 0 4px 14px rgba(31, 91, 140, .10);
        }
        div.stButton > button:hover p,
        div.stButton > button:hover span {
            color: #124b78 !important;
            -webkit-text-fill-color: #124b78 !important;
        }

        /* Primary submit button. */
        div.stFormSubmitButton > button {
            border-radius: 11px; min-height: 2.9rem; font-weight: 700;
            background: #1D4ED8 !important;
            border-color: #1D4ED8 !important;
            color: #FFFFFF !important;
        }
        div.stFormSubmitButton > button p,
        div.stFormSubmitButton > button span {
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }
        div.stFormSubmitButton > button:hover {
            background: #1E40AF !important;
            border-color: #1E40AF !important;
        }

        /* Hero/header keeps white text on its dark gradient. These rules come
           after the global text rules so they win at equal specificity. */
        .hero {
            padding: 1.55rem 1.7rem;
            border: 1px solid rgba(100, 116, 139, .18);
            border-radius: 20px;
            background: linear-gradient(125deg, #102a43 0%, #174a72 65%, #21618c 100%);
            color: #ffffff !important;
            box-shadow: 0 12px 30px rgba(15, 39, 64, .12);
            margin-bottom: 1rem;
        }
        .stApp .hero-kicker {
            color: #c7e3ff !important;
            -webkit-text-fill-color: #c7e3ff !important;
            font-size: .76rem; font-weight: 700;
            letter-spacing: .12em; text-transform: uppercase; margin-bottom: .45rem;
        }
        .stApp .hero h1 {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            font-size: 2rem; line-height: 1.2; margin: 0 0 .45rem 0;
        }
        .stApp .hero p {
            color: #e4f1fb !important;
            -webkit-text-fill-color: #e4f1fb !important;
            margin: 0; font-size: 1rem;
        }

        .stApp .section-label {
            color: #53677b !important;
            -webkit-text-fill-color: #53677b !important;
            font-size: .78rem; font-weight: 700;
            letter-spacing: .08em; text-transform: uppercase;
            margin: .4rem 0 .65rem 0;
        }
        .stApp .answer-label {
            color: #1b6597 !important;
            -webkit-text-fill-color: #1b6597 !important;
            font-size: .75rem; font-weight: 800;
            letter-spacing: .1em; text-transform: uppercase; margin-bottom: .5rem;
        }
        .stApp .footer-note {
            color: #4B5563 !important;
            -webkit-text-fill-color: #4B5563 !important;
            font-size: .83rem;
        }
        @media (max-width: 640px) {
            .block-container { padding-top: 1rem; }
            .hero { padding: 1.2rem; border-radius: 15px; }
            .hero h1 { font-size: 1.55rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_result(result: AnswerResult) -> None:
    with st.container(border=True):
        st.markdown(
            '<div class="answer-label">Answer</div>', unsafe_allow_html=True
        )
        st.write(result.answer)

        if result.source_url:
            st.markdown(f"**Source:** [{result.source_url}]({result.source_url})")

        if result.last_updated:
            st.caption(f"Last updated from sources: {result.last_updated}")


def _render_reference_sections() -> None:
    with st.expander("Sources — the only pages this assistant uses"):
        for url in settings.urls:
            label = SOURCE_LABELS.get(url, url)
            st.markdown(f"- [{label}]({url})")
        st.caption(
            "No other pages are crawled or cited. Each answer links to exactly "
            "one source from this list."
        )

    with st.expander("Sample questions and answers"):
        for question, sample_answer in SAMPLE_QA:
            st.markdown(f"**{question}**")
            st.markdown(sample_answer)
        st.caption(
            "Generated wording may vary. Facts come from the cited Groww page; "
            "out-of-corpus and policy questions are refused."
        )



def main() -> None:
    st.set_page_config(
        page_title="Groww HDFC Mutual Fund FAQ",
        page_icon="📘",
        layout="centered",
    )
    _inject_styles()

    if "question" not in st.session_state:
        st.session_state.question = ""
    if "answer_result" not in st.session_state:
        st.session_state.answer_result = None

    st.markdown(
        f"""
        <section class="hero">
          <div class="hero-kicker">Facts-only mutual fund assistant</div>
          <h1>HDFC Mutual Fund FAQ</h1>
          <p>{settings.ui.welcome}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.warning(
        f"**{settings.ui.disclaimer}**  "
        "Answers are limited to the five listed Groww pages.",
        icon="⚠️",
    )

    st.markdown('<div class="section-label">Start with a common question</div>',
                unsafe_allow_html=True)
    columns = st.columns(len(settings.ui.examples))
    for index, (column, example) in enumerate(zip(columns, settings.ui.examples)):
        with column:
            st.button(
                example,
                key=f"example_{index}",
                use_container_width=True,
                on_click=_set_example,
                args=(example,),
            )

    with st.expander("Explore more question ideas"):
        more_columns = st.columns(2)
        for index, question in enumerate(MORE_QUESTIONS):
            with more_columns[index % 2]:
                st.button(
                    question,
                    key=f"more_example_{index}",
                    use_container_width=True,
                    on_click=_set_example,
                    args=(question,),
                )

    st.markdown('<div class="section-label">Ask about a listed HDFC scheme</div>',
                unsafe_allow_html=True)
    with st.form("ask_form"):
        question = st.text_area(
            "Your question",
            key="question",
            height=105,
            placeholder=(
                "For example: What is the expense ratio, exit load, minimum SIP, "
                "benchmark, AUM or NAV?"
            ),
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Find an answer", type="primary",
                                          use_container_width=True)

    if submitted:
        cleaned = question.strip()
        if not cleaned:
            st.warning("Please enter a question.")
        else:
            with st.spinner("Checking the sourced Groww pages..."):
                try:
                    result = answer(cleaned)
                except LLMConfigurationError as exc:
                    st.session_state.answer_result = None
                    st.error(str(exc))
                except LLMError as exc:
                    st.session_state.answer_result = None
                    st.error(str(exc))
                except Exception:  # noqa: BLE001 - keep UI failures user-safe
                    st.session_state.answer_result = None
                    st.error(
                        "I couldn't complete that request. Please try again. "
                        "If this is a fresh setup, run the ingest pipeline first."
                    )
                else:
                    st.session_state.answer_result = result

    result = st.session_state.get("answer_result")
    if result is not None:
        st.markdown("")
        _render_result(result)

    _render_reference_sections()

    st.divider()
    st.markdown('<div class="section-label">Disclaimer</div>',
                unsafe_allow_html=True)
    st.caption(FULL_DISCLAIMER)
    st.markdown(
        '<p class="footer-note">Facts-only. No investment advice. This prototype '
        'does not provide investment recommendations, calculate returns, or access '
        'personal investment accounts.</p>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
