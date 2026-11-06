# Groww HDFC Mutual Fund FAQ Assistant

A facts-only RAG prototype over five public Groww pages covering HDFC Mutual Fund and four schemes. It retrieves source chunks from ChromaDB, answers with Groq, and enforces one citation, a three-sentence limit, and a last-updated line.

**Facts-only. No investment advice.**

## Sources

The corpus is limited to these five allowlisted public Groww pages. No links are followed and no extra sources are crawled.

| Scheme | Source |
|---|---|
| HDFC Mutual Fund (AMC overview) | [Groww AMC page](https://groww.in/mutual-funds/amc/hdfc-mutual-funds) |
| HDFC Large Cap Fund Direct Growth | [Groww scheme page](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) |
| HDFC Flexi Cap Direct Plan Growth | [Groww scheme page](https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth) |
| HDFC ELSS Tax Saver Fund Direct Plan Growth | [Groww scheme page](https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth) |
| HDFC Mid Cap Fund Direct Growth | [Groww scheme page](https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth) |

## Stack

| Stage | Implementation |
|---|---|
| Scrape / load / chunk | `src/ingest/` |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store | ChromaDB, collection `groww_hdfc_mf`, cosine distance |
| Retrieval | `src/retrieve.py` with scheme/section filtering and traces |
| Policy | `src/policy.py` (PII, advice, returns) |
| Generation | `src/generate.py` + Groq |
| UI | Streamlit, `src/app.py` |

## Requirements

- Windows PowerShell for the local commands below (Streamlit Cloud uses Linux).
- Python 3.10+ (tested with Python 3.12.10; use 3.12 on Streamlit Cloud).
- Internet access for the first `pip install` and for Groq API calls.
- A Groq API key from <https://console.groq.com/keys>.

Runtime versions in `requirements.txt` are pinned to the versions verified with Python 3.12.10. `sentence-transformers` pulls in `torch`; the first install is therefore the slowest step.

## Setup (packaged ZIP or cloned repo)

The project includes the built corpus and ChromaDB index, so you do **not** need to run ingestion before starting the app.

From the packaged ZIP:

```powershell
Expand-Archive -LiteralPath "$HOME\Desktop\mutual_fund_faq_assistant_final.zip" -DestinationPath "$HOME\Desktop\mutual_fund_faq_assistant_final" -Force
cd "$HOME\Desktop\mutual_fund_faq_assistant_final"
```

Or clone your GitHub repository:

```powershell
git clone https://github.com/shivaniarishisingh-stack/groww.git
cd groww
```

Then create the environment and install dependencies:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

`python` must be on `PATH`. If it is not, use `py -3.12 -m venv .venv` instead. In `.env`, set:

```dotenv
GROQ_API_KEY=your_key_here
LLM_MODEL=qwen/qwen3.8-27b
```

`.env` and `.env.txt` are intentionally excluded from the ZIP and must be created locally. Never commit or share the key.

`config.yaml` holds the allowlisted URLs, Chroma settings, retrieval thresholds, UI examples, disclaimer, and educational link.

## Configure credentials (local and cloud)

The app resolves `GROQ_API_KEY` and `LLM_MODEL` in this order:

1. Real environment variables.
2. `.env` in the project root (loaded by `python-dotenv`).
3. Streamlit secrets (`st.secrets`), used by Streamlit Community Cloud.

For local development, use the `.env` file shown above. For Streamlit Cloud, do **not** upload `.env`; paste the same values into the app's **Settings → Secrets** box:

```toml
GROQ_API_KEY = "your_key_here"
LLM_MODEL = "qwen/qwen3.8-27b"
```

Never commit `.env`, `.env.txt`, `.streamlit/secrets.toml`, or any real key. They are excluded by `.gitignore`. `.env.example` contains placeholders only.


## Run the UI

```powershell
cd "$HOME\Desktop\mutual_fund_faq_assistant_final"
.\.venv\Scripts\Activate.ps1
streamlit run src/app.py
```

Open <http://localhost:8501>. If port 8501 is already in use:

```powershell
streamlit run src/app.py --server.port 8502
```

The page shows a responsive layout, the persistent facts-only disclaimer, three primary example questions plus additional question ideas, a question box, the answer, exactly one source link, and the last-updated line. Additional prompts are question ideas only; they do not add facts to the five-page corpus. Retrieval traces are written under `data/traces/` for inspection but are not shown in the UI.

Ingest and the test suite work without a Groq key. A factual UI answer needs `GROQ_API_KEY` and `LLM_MODEL`; if either is missing the UI shows a clear configuration error.

## Sample Q&A

| Question | Expected behavior |
|---|---|
| What is the expense ratio of HDFC Large Cap Fund Direct Growth? | Answers **1.01%** and cites the Large Cap Groww page. |
| What is the minimum SIP for HDFC Mid Cap Fund Direct Growth? | Answers **₹100** and cites the Mid Cap Groww page. |
| What is the lock-in for HDFC ELSS Tax Saver? | Returns `out_of_corpus`; the sourced chunk does not state a lock-in duration. |
| Should I buy HDFC Flexi Cap? | Returns `refuse_advice`; the assistant is facts-only and gives no recommendation. |
| What was the 1Y return of HDFC ELSS? | Returns `refuse_returns`; returns are never calculated or compared. |

The UI exposes its own source list and sample Q&A under expanders. See `sample_qa.md` for the full 12-row set, including PII and out-of-corpus cases. Generated wording may vary, but citations, refusal behavior, and the last-updated line are deterministic.

## Deploy to GitHub and Streamlit Community Cloud

The repository is ready to deploy without rebuilding the index. `data/chroma/` is about **2.1 MB**, well below GitHub's 100 MB per-file limit, so Git LFS is not required.

### 1. Push the project to GitHub

```powershell
cd "$HOME\Desktop\mutual_fund_faq_assistant_final"
git init
git add .
git status
```

Before committing, confirm that `.env`, `.env.txt`, `.streamlit/secrets.toml`, `.venv/`, `__pycache__/`, and `data/traces/` are **not** staged. `git status` should list `data/chroma/`, `.streamlit/config.toml`, the source, tests, and docs.

```powershell
git commit -m "Prepare Groww HDFC FAQ assistant for deployment"
git branch -M main
git remote add origin https://github.com/shivaniarishisingh-stack/groww.git
git push -u origin main
```

### 2. Create the Streamlit app

1. Sign in at <https://share.streamlit.io> with GitHub.
2. Click **New app** → **Deploy a public app from GitHub**.
3. Repository: `shivaniarishisingh-stack/groww`
4. Branch: `main`
5. Main file path: `src/app.py`
6. Click **Deploy**.

`src/app.py` is the entry point. It adds the project root to `sys.path`, so the `src.*` imports and the relative `data/chroma` path in `config.yaml` resolve on Cloud.

### 3. Add secrets

In the deployed app: **⋮ → Settings → Secrets**, paste the TOML from [Configure credentials](#configure-credentials-local-and-cloud), and save. The app restarts automatically and picks up the values through `st.secrets`.

### Deployment notes

- Select **Python 3.12** in Advanced settings if offered. Tested with 3.12.10.
- The first build installs `torch` through `sentence-transformers`, so it can take several minutes.
- The free tier has limited RAM. The embedding model plus Chroma is small, but if the app is restarted for memory pressure, increase resources rather than changing the pipeline.
- The prebuilt index is read-only at runtime. Do not run `python -m src.ingest` on Cloud unless you intend to rebuild it.
- `data/traces/` is created on demand and is not committed.

## Tests

```powershell
cd "$HOME\Desktop\mutual_fund_faq_assistant_final"
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

Expected result for this package: **58 passed**. The suite covers policy classification, PII trace safety, refusal paths that never call Chroma or Groq, citation and length post-checks, missing-key errors, empty/missing collections, the not-found and invented-lock-in post-checks, and the Streamlit render/refusal paths. See `TESTING_REPORT.md` for the full review report.

## Build or refresh the corpus

The packaged `data/` folder already contains a working index. To rebuild it from the five allowlisted Groww pages:

```powershell
python -m src.ingest
```

Or run stages individually:

```powershell
python -m src.ingest.scrape
python -m src.ingest.load
python -m src.ingest.chunk
python -m src.ingest.embed
python -m src.ingest.index
```

`data/chroma/` is committed intentionally (about 2.1 MB) so Streamlit Community Cloud can use the prebuilt index without re-ingestion. Rebuild Chroma if the scraped pages or chunking settings change.

## Safety behavior

| Input | Behavior |
|---|---|
| PAN, Aadhaar, phone, email, OTP, account/folio | `refuse_pii`; no raw query or value stored, only a safe stub trace |
| Buy/sell/switch, recommendations, portfolio, “best fund” | `refuse_advice`; policy blocks retrieval and the LLM |
| Returns, CAGR, performance comparisons, hypothetical growth | `refuse_returns`; no numbers computed |
| Fact not in the five pages / weak retrieval | `out_of_corpus`; educational link, no invention |
| LLM says the fact is not in the retrieved context | post-check converts to `out_of_corpus`; educational link, no scheme citation |
| LLM invents a lock-in duration not stated in context | post-check converts to `out_of_corpus`; no invented duration |
| LLM returns more than 3 sentences | trimmed to 3 |
| LLM cites a non-allowlisted URL | replaced with the top retrieved URL |
| LLM omits a source | top retrieved URL used |
| Missing/empty Chroma | out-of-corpus refusal, not a crash |

## Inspectable artifacts

```text
data/raw/          scraped HTML + sidecar metadata
data/cleaned/      cleaned JSON per page
data/chunks/       chunks.jsonl + _stats.json
data/embeddings/   vectors.npy + manifest.json
data/chroma/       persistent ChromaDB + index_manifest.json
data/traces/       retrieval traces (redacted; PII gets a stub only)
```

The packaged ZIP includes `raw/`, `cleaned/`, `chunks/`, `embeddings/`, and `chroma/`. It excludes `data/traces/` because traces are runtime diagnostics, not required to answer questions; the app recreates the folder on demand.

## Disclaimer

Facts-only. No investment advice. Answers are based on the five public Groww pages listed under [Sources](#sources) and may be incomplete or out of date. Always verify on the cited source. Mutual fund investments are subject to market risks.

This prototype does not provide investment recommendations, calculate returns, or access personal investment accounts.

## Known limits

- Only the five pages are in scope; other schemes and live account actions are out of corpus.
- No statement download or KYC/account features.
- Returns are never calculated or compared; published figures must be read from the cited page.
- Content may be stale; “Last updated from sources” reflects the last successful fetch, not Groww’s publish date.
- The ELSS page labels a section “3Y Lock-in”, but the retrieved chunk only contains the section label and a “3Y annualised” return figure, not a lock-in duration. A deterministic post-check refuses to invent one and returns `out_of_corpus`.
