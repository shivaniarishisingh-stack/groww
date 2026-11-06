# Package Contents

This archive is a reviewed, fixed, and tested copy of the Mutual Fund FAQ Assistant.

## Included

### Source code
- `src/__init__.py`
- `src/app.py`
- `src/config.py`
- `src/generate.py`
- `src/policy.py`
- `src/retrieve.py`
- `src/llm/` (base client, Groq client, exports)
- `src/ingest/` (scrape, load, chunk, embed, index, entry points)

### Tests
- `tests/test_app.py`
- `tests/test_generate.py`
- `tests/test_policy.py`
- `tests/test_retrieve_policy.py`

### Configuration
- `config.yaml`
- `requirements.txt`
- `.env.example` (key intentionally blank)
- `.gitignore`

### Built data and index
- `data/raw/` — scraped HTML and sidecar metadata
- `data/cleaned/` — cleaned JSON per page
- `data/chunks/` — `chunks.jsonl` and statistics
- `data/embeddings/` — `vectors.npy` and manifest
- `data/chroma/` — persistent ChromaDB index and manifest

The built corpus lets the app run without repeating ingestion.

### Documentation
- `README.md` — setup, run, test, refresh, and safety behavior
- `TESTING_REPORT.md` — full review and test report
- `PACKAGE_CONTENTS.md` — this file
- `sample_qa.md` — sample questions and verified behavior
- `architecture.md`
- `implementation.md`
- `PRD.md`
- `Problem statement`

## Excluded

- `.env` — contains the live Groq API key
- `.env.txt` — local environment backup
- `.venv/`, `venv/` — local virtual environments
- `.pytest_cache/`, `__pycache__/`, `*.py[cod]` — caches and compiled files
- `data/traces/` — runtime diagnostics and test query traces
- Any API keys, passwords, tokens, credentials, or secrets
- OS-generated temporary files

## Recreate the excluded local environment

```powershell
cd "$HOME\Desktop\mutual_fund_faq_assistant_final"
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Set `GROQ_API_KEY` and `LLM_MODEL=qwen/qwen3.8-27b` in `.env`, then run:

```powershell
streamlit run src/app.py
```
