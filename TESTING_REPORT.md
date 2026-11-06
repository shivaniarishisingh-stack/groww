# Testing Report — Mutual Fund FAQ Assistant

**Review date:** 06 November 2026  
**Project:** Groww HDFC Mutual Fund FAQ Assistant (updated ZIP)  
**Environment:** Windows, Python 3.12.10, Streamlit 1.66.1, ChromaDB 1.5.9, Groq SDK 1.7.0  
**Final test result:** `67 passed`

---

## 1. What works

| Area | Verified result |
|---|---|
| Project structure | Streamlit app, ingest pipeline, retrieval, policy, generation, tests, config, and docs are present and importable |
| Dependencies | All required packages import successfully; `pip check` reports no broken requirements |
| Configuration | `.env` is excluded from the package; `GROQ_API_KEY` was present during review but never displayed; `LLM_MODEL=qwen/qwen3.8-27b` |
| Five-page scope | Exactly 5 unique `https://groww.in/mutual-funds/...` URLs; unchanged |
| Allowlist guard | Approved URL accepted; unapproved URL rejected with a clear error |
| Ingestion | 5 pages returned HTTP 200; 5 cleaned documents; 201 chunks; 201 × 384 normalized vectors; Chroma cosine index built |
| Retrieval | Correct sections returned for expense ratio, minimum SIP, exit load, benchmark, AUM, and NAV; every hit URL is allowlisted |
| Groq integration | Live answers generated successfully with `qwen/qwen3.8-27b` |
| Streamlit UI | Headless `AppTest` passed; real server health returned `ok`; page returned HTTP 200 |
| Factual answers | Grounded answers with exactly one source URL and `Last updated from sources: 06 Nov 2026` |
| Advice questions | Deterministic refusal; policy blocks retrieval and the LLM |
| Returns questions | Deterministic refusal; no calculations |
| PII questions | Deterministic refusal; no raw PII stored in traces |
| Unsupported questions | `out_of_corpus` refusal with the educational link |
| Answer display | Answer card renders correctly with source and last-updated line |

### Verified live answers

| Question | Answer | Source |
|---|---|---|
| Expense ratio of HDFC Large Cap Fund Direct Growth | 1.01% | HDFC Large Cap Fund Direct Growth |
| Minimum SIP for HDFC Mid Cap Fund Direct Growth | ₹100 | HDFC Mid Cap Fund Direct Growth |
| Exit load of HDFC Flexi Cap | 1% if redeemed within 1 year | HDFC Equity Fund Direct Growth |
| Benchmark of HDFC Large Cap | NIFTY 100 Total Return Index | HDFC Large Cap Fund Direct Growth |
| AUM of HDFC Large Cap Fund | ₹9,34,076 Cr | HDFC Large Cap Fund Direct Growth |
| NAV of HDFC Large Cap Fund | ₹1,233.61 as of 05 Nov 2026 | HDFC Large Cap Fund Direct Growth |

---

## 2. What failed

1. The source ZIP did not contain a `.env` file, so no live LLM credentials were configured initially.
2. The originally configured model, `qwen/qwen3-32b`, was retired on the Groq account; generation failed until it was changed to `qwen/qwen3.8-27b`.
3. The ELSS lock-in question produced an invented answer of “3 years,” even though the retrieved chunk only contained “3Y annualised,” which is a return figure.
4. When the model said a fact was not on the sourced pages, the result could still cite a scheme URL instead of the educational link.
5. The custom HTML answer card did not wrap the Streamlit content, producing a malformed layout.
6. Documentation was stale: `README.md` named the retired model, and `sample_qa.md` contained old figures and old lock-in behavior.

---

## 3. What was fixed

| File | Fix |
|---|---|
| `src/generate.py` | Added a deterministic not-found post-check that converts the response to `out_of_corpus` with the educational link |
| `src/generate.py` | Added a deterministic lock-in post-check that refuses a duration not explicitly stated near “lock-in” in the retrieved text |
| `src/generate.py` | Strengthened the system prompt to forbid inferring numbers, durations, or percentages from unrelated values |
| `src/app.py` | Replaced the broken HTML wrapper with `st.container(border=True)` |
| `tests/test_generate.py` | Added regression tests for not-found answers, “not explicitly stated” wording, invented lock-in refusal, and supported lock-in retention |
| `README.md` | Updated model ID, setup/run commands, packaged-data notes, post-check behavior, and ELSS limitation |
| `sample_qa.md` | Refreshed figures and updated lock-in, capital-gains-download, and riskometer behavior |

---

## 4. What remains incomplete

1. **ELSS lock-in duration is not answerable.** The retrieved chunk contains the section label but not the duration. The assistant now refuses instead of inventing one. Better chunking could retain the “3Y Lock-in” label.
2. **Riskometer is out of corpus.** The question returns `out_of_corpus` because the value is not present in the retrieved chunks.
3. **Scope remains exactly five pages.** Other schemes, statements, KYC, and account actions are unsupported.
4. **Data freshness depends on scraping.** NAV and AUM change; the last-updated line reflects the scrape date.
5. **The package uses a local `.env`.** A Groq key must be supplied by the reviewer; it is not included for security.
6. **No Git push was performed.** No repository URL or commit identity was provided.

---

## 5. Commands used for verification

```powershell
cd "C:\Users\shiva\AppData\Local\Temp\opencode\mf_review_updated"

& "C:\Users\shiva\OneDrive\Desktop\New folder\demo\.venv\Scripts\Activate.ps1"

python -m src.ingest

python -m pytest -q

streamlit run src/app.py --server.port 8502
```

Verification results:

- Full ingest: all 5 pages HTTP 200, 201 chunks, 201 × 384 vectors, Chroma index built.
- Test suite: `67 passed`.
- Server health: `ok`.
- Page response: HTTP 200.
- Factual, advice, returns, PII, and unsupported-question paths all behaved as documented.

---

## 6. Notes for reviewers

- Deployment update (07 November 2026): the suite now has 67 tests. The added tests cover `GROQ_API_KEY`/`LLM_MODEL` resolution from the environment, `.env`, and `st.secrets`, plus UI rendering of the source list, sample Q&A, and disclaimer.
- The packager intentionally excluded `.env`, `.env.txt`, `.venv`, caches, and `data/traces/`.
- The package includes the built corpus and ChromaDB index under `data/`, so ingestion can be skipped.
- If the index does not open on another machine, run `python -m src.ingest` to rebuild it. This requires internet access to Groww.
- Generated wording can vary slightly between Groq calls; citations, refusal behavior, and source dates are deterministic post-checks.
