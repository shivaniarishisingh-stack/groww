# Product Requirements Document (PRD)

**Product:** Groww Mutual Fund FAQ Assistant  
**Type:** Working RAG prototype (facts-only, no investment advice)  
**Source:** Problem statement  
**Status:** Draft for implementation  

---

## 1. Overview

Build a small FAQ assistant on Groww public pages that answers **factual** questions about selected HDFC Mutual Fund schemes (expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, how to download statements).

Every answer must include **one source link**. The assistant must **not** give investment advice.

This is a **RAG demo**. Each pipeline stage must persist its output so the flow can be inspected: load → chunk → embed → retrieve → generate.

---

## 2. Problem

Retail users and support/content teams repeatedly ask the same mutual-fund facts. Answers should come only from **official public pages**, with a citation, and without mixing in opinion, performance claims, or personal data.

---

## 3. Goals

| ID | Goal |
|----|------|
| G1 | Answer factual MF queries from a small, fixed public corpus. |
| G2 | Cite exactly one source URL on every answer. |
| G3 | Refuse opinionated / portfolio / buy-sell questions politely, with a relevant educational link. |
| G4 | Make the RAG pipeline inspectable: store artifacts for each stage. |
| G5 | Keep models, vector DB, and LLM provider configurable (config + `.env`). |

**Non-goals**

- Investment advice, scheme ranking, or “should I buy/sell?”
- Computing or comparing returns
- Scraping any URL beyond the five allowed pages (no internal/linked pages)
- Accepting or storing PII
- Full Groww app integration or authenticated account features

---

## 4. Users

| Persona | Need |
|---------|------|
| Retail user comparing schemes | Fast, cited facts (SIP min, exit load, lock-in, etc.) |
| Support / content team | Repeatable answers to common MF questions without inventing facts |

---

## 5. Scope

### 5.1 Allowed data sources (exactly these 5 pages)

Do **not** scrape links internal to these pages. Store only content from:

| # | Page | URL |
|---|------|-----|
| 1 | AMC overview — HDFC Mutual Fund | https://groww.in/mutual-funds/amc/hdfc-mutual-funds |
| 2 | Large Cap — HDFC Large Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| 3 | Flexi Cap — HDFC Flexi Cap Direct Plan Growth | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 4 | ELSS (tax saver) — HDFC ELSS Tax Saver Fund Direct Plan Growth | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 5 | Mid Cap — HDFC Mid Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |

**Public sources only.** No app back-end screenshots. No third-party blogs as sources.

### 5.2 In-scope query types (examples)

- Expense ratio of a listed scheme
- ELSS lock-in
- Minimum SIP
- Exit load
- Riskometer / benchmark
- How to download a capital-gains statement (if present on allowed pages; otherwise refuse or point to official educational/source link without inventing steps)

### 5.3 Out-of-scope query types

- Should I buy / sell / switch?
- Portfolio construction
- Return comparison or performance claims (do not compute; if asked, link to official factsheet if available in corpus, else refuse with facts-only message)

---

## 6. Product requirements

### 6.1 FAQ assistant (prototype)

| ID | Requirement |
|----|-------------|
| FR-1 | Answer **factual** queries only from retrieved corpus chunks. |
| FR-2 | Every answer shows **one clear citation link**. |
| FR-3 | Refuse opinionated/portfolio questions with a polite, facts-only message and a relevant educational link. |
| FR-4 | Answers ≤ **3 sentences**. |
| FR-5 | Include **“Last updated from sources: &lt;timestamp/date&gt;”**. |
| FR-6 | Tiny UI: welcome line + **3 example questions** + note: **“Facts-only. No investment advice.”** |
| FR-7 | Do not accept or store PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers. If the user pastes PII, do not persist it; respond that PII is not accepted. |
| FR-8 | No performance claims; do not compute/compare returns. |

### 6.2 RAG pipeline (phase-wise, artifacts stored)

Implement in phases. Persist stage outputs so they can be shown in the demo.

| Phase | Stage | Requirement |
|-------|--------|-------------|
| P1 | **Data loading** | Fetch/scrape only the 5 URLs. Store raw page content (HTML and/or cleaned text) plus URL, title, fetch timestamp. |
| P2 | **Data chunking** | Chunk using a strategy suited to this data (scheme fact sheets / AMC pages: structured fields + prose). Persist chunks with source URL and chunk id. |
| P3 | **Data embedding** | Embed with `sentence-transformers/all-MiniLM-L6-v2`. Persist embeddings (or confirm they live in the vector store with metadata). |
| P4 | **Vector DB** | Use **ChromaDB**. Collection name, persist path, and related settings live in **config**. |
| P5 | **Data retrieval** | Query embedding model **must match** ingestion. Vector DB **must match** ingestion. Return top-k chunks + source URLs. Persist retrieval traces for demo (query, retrieved chunks, scores). |
| P6 | **LLM generation** | Ground answers in retrieved chunks only. Enforce citation, length, refuse, and disclaimer rules. |

### 6.3 Configuration

| Item | Spec |
|------|------|
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` (config; same for ingest and retrieve) |
| Vector DB | ChromaDB (config: path, collection, top-k, etc.) |
| LLM provider | Groq (primary). API key from `.env`. |
| LLM model | `qwen/qwen3-8b` (or the Groq-hosted Qwen 3.8 / 27B id specified at implementation time). **Model name from `.env`.** |
| Future providers | Architecture should allow swapping Gemini, OpenAI, Anthropic, Mistral via config/env without rewriting the pipeline. |

Do **not** commit secrets. `.env` is local only; document required keys in README.

### 6.4 Prompting / model behavior (skills W1–W3)

- Identify the **exact fact** asked; answer or refuse.
- Instruction-style, concise phrasing.
- Polite safe-refusals with citation wording.
- Small-corpus retrieval with **accurate citations** from the allowed Groww pages (AMC/scheme pages). Treat extra official pages (SEBI/AMFI) as out of scrape scope unless they appear on the 5 pages; source list for submission may document the 5 URLs plus any citation URLs shown in the UI.

---

## 7. UX requirements

- Welcome line.
- Three example questions (aligned with in-scope facts).
- Persistent disclaimer: **“Facts-only. No investment advice.”**
- Answer area: short text (≤3 sentences), one source link, last-updated line.
- Refusal path: polite message + educational link, still facts-only.

---

## 8. Data & privacy

| Rule | Detail |
|------|--------|
| Public sources only | The five Groww URLs listed above |
| No extra crawl | Do not follow/scrape internal links from those pages |
| No PII | Do not accept/store PAN, Aadhaar, account numbers, OTPs, emails, phone numbers |
| Stage artifacts | Store load/chunk/embed/retrieve outputs for demo transparency; artifacts must not contain user PII |

---

## 9. Deliverables

| Deliverable | Description |
|-------------|-------------|
| Working prototype | App/notebook link, **or** ≤3-minute demo video if hosting is not possible |
| Source list | CSV or Markdown of **15–25 URLs** used (the 5 scrape targets plus documented citation/educational links as applicable) |
| README | Setup steps, scope (AMC + schemes), known limits |
| Sample Q&A | 5–10 queries with assistant answers + links |
| Disclaimer snippet | The facts-only, no-advice copy used in the UI |
| Stage data | Explicit stored outputs for load, chunk, embed, retrieve (demo of RAG) |

---

## 10. Success criteria

- Factual questions about the five pages return a correct (or clearly sourced) answer, ≤3 sentences, with one link and last-updated line.
- Buy/sell and other advice questions are refused without recommendations.
- Returns questions are not computed; user is pointed to official factsheet if applicable.
- Changing embedding model / Chroma settings / Groq model is possible via config and `.env` without code hunt.
- A reviewer can inspect persisted artifacts for each RAG stage.

---

## 11. Known limits (to document in README)

- Corpus is five pages only; facts not on those pages cannot be answered.
- No live account/statement download; “how to download statements” only if the public pages describe it.
- Embeddings and LLM may miss or slightly paraphrase numbers; citation is mandatory so the user can verify.
- Content can go stale; last-updated reflects last successful source fetch, not Groww’s own publish date unless extracted.

---

## 12. Open decisions (implementation)

- Exact Groq model id string (`qwen/qwen3-8b` vs `qwen/qwen3-32b` / 27B-class) — **read from `.env`**.
- Chunking strategy: prefer structure-aware chunks (per scheme field / section heading) over naive fixed windows, with overlap if sections are long.
- UI stack: keep minimal (e.g. Streamlit/Gradio/simple web) sufficient for welcome, examples, Q&A, disclaimer.
- Source-list of 15–25 URLs: start from the 5 scrape targets; add official Groww/AMFI/SEBI educational URLs used only as refusal/help links, without scraping them into the vector store unless later in-scope.

---

## 13. Implementation phases (build order)

1. Config + `.env` template (embedding, Chroma, Groq model, API key).
2. Data loading for the 5 URLs; persist raw/cleaned docs.
3. Chunking + persist chunks.
4. Embed + upsert to ChromaDB; persist metadata.
5. Retrieval API with traces.
6. LLM answer/refuse layer with citation and length rules.
7. Tiny UI + disclaimer + example questions.
8. Source list, sample Q&A, README, demo.

---

## 14. Disclaimer (UI snippet — draft)

> Facts-only. No investment advice. Answers are based on public Groww pages for the listed HDFC schemes and may be incomplete or out of date. Always verify on the cited source. Mutual fund investments are subject to market risks.
