# Architecture

**Product:** Groww Mutual Fund FAQ Assistant  
**Style:** Small-corpus RAG, inspectable by stage  
**Source:** `PRD.md`

---

## 1. Purpose

A facts-only FAQ prototype over **five public Groww pages**. Ingestion is offline and inspectable. Query time is retrieve-then-generate with a single citation, length and safety rules, and no investment advice.

The architecture is **phase-wise** so each RAG stage writes artifacts to disk (and/or Chroma) for demo review.

---

## 2. High-level design

```
                    ┌─────────────────────────────────────────┐
                    │              config.yaml + .env         │
                    │  URLs, embed model, Chroma, LLM, top-k  │
                    └────────────────────┬────────────────────┘
                                         │
     INGEST (offline)                    │              QUERY (online)
                                         │
  [5 Groww URLs]                         │           [Tiny UI]
         │                               │                │
         ▼                               │                ▼
  P1 Loader ──► data/raw/                │     PII / intent gate
         │                               │                │
         ▼                               │                ▼
  P2 Chunker ──► data/chunks/            │     Embed query (same model)
         │                               │                │
         ▼                               │                ▼
  P3 Embedder                            │     P5 Retrieve (Chroma top-k)
         │                               │                │
         ▼                               │                ▼
  P4 Chroma persist dir                  │     Persist retrieval trace
                                         │                │
                                         │                ▼
                                         │     P6 LLM (Groq / swap)
                                         │                │
                                         │                ▼
                                         │     Answer | Refuse + 1 URL
                                         │     + last-updated
```

**Invariant:** ingest embedding model ≡ query embedding model. Ingest collection ≡ query collection. Both come from config.

---

## 3. Logical components

| Component | Responsibility |
|-----------|----------------|
| **Config loader** | Read `config.yaml` (paths, models, Chroma, chunking, allowed URLs, educational links). Read secrets and `LLM_MODEL` from `.env`. |
| **Loader (P1)** | HTTP GET only the five allowlisted URLs. Strip to text. Write raw HTML + cleaned docs + fetch timestamp. **Do not follow in-page links.** |
| **Chunker (P2)** | Split cleaned docs with a structure-aware strategy (headings / labeled fields such as expense ratio, SIP, exit load, lock-in, riskometer, benchmark). Fallback: overlapping character/token windows. Write chunk JSONL. |
| **Embedder (P3)** | `sentence-transformers/all-MiniLM-L6-v2`. Produce vectors for chunks. |
| **Vector store (P4)** | ChromaDB persistent client. One collection. Metadata: `chunk_id`, `source_url`, `title`, `fetched_at`, optional `section`. |
| **Retriever (P5)** | Embed question; similarity search; return top-k + distances. Write a retrieval trace file per query (demo). |
| **Policy gate** | Before generation: detect PII → reject and do not log the raw query. Detect advice / returns-compute intent → refuse path (educational link, no RAG answer as advice). |
| **Generator (P6)** | Groq chat completion grounded **only** in retrieved chunks. Enforce ≤3 sentences, one citation URL, last-updated. Provider interface allows Gemini / OpenAI / Anthropic / Mistral later. |
| **UI** | Welcome, 3 example questions, disclaimer, Q&A. No account features. |

---

## 4. Repository layout (target)

```
demo/
  PRD.md
  architecture.md
  config.yaml
  .env.example
  README.md
  sources.md | sources.csv
  sample_qa.md
  src/
    config.py
    ingest/
      load.py
      chunk.py
      embed.py
      index.py
    retrieve.py
    generate.py
    policy.py
    llm/
      base.py
      groq_client.py
    app.py                 # Streamlit (or equivalent)
  data/
    raw/                   # P1
    cleaned/               # P1
    chunks/                # P2
    embeddings/            # P3 optional dump (ids + dim) for demo
    chroma/                # P4 persist path
    traces/                # P5 retrieval JSON per query
```

Secrets never live under `data/` or git. `.env` is gitignored.

---

## 5. Configuration

### 5.1 `config.yaml` (changeable without code)

| Key | Role |
|-----|------|
| `sources.urls` | Exactly the 5 Groww pages |
| `chunking.strategy` | `structure` \| `fixed` |
| `chunking.size` / `overlap` | Used when strategy is fixed or as fallback |
| `embedding.model` | Default `sentence-transformers/all-MiniLM-L6-v2` |
| `chroma.persist_dir` | e.g. `data/chroma` |
| `chroma.collection` | Collection name |
| `retrieval.top_k` | Integer |
| `llm.provider` | `groq` (default) |
| `paths.*` | Artifact directories |
| `ui.examples` | Three example questions |
| `ui.disclaimer` | Facts-only copy |
| `policy.educational_link` | URL used on polite refuse |

### 5.2 `.env`

| Variable | Role |
|----------|------|
| `GROQ_API_KEY` | Groq auth |
| `LLM_MODEL` | Groq model id (e.g. Qwen 3.8 / 27B class as available) |
| Optional later | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY` |

`config.yaml` points at provider name; `.env` holds key + model id.

---

## 6. Data contracts (stage artifacts)

Each stage writes **explicit files** so the demo can show RAG without opening Chroma internals only.

### P1 — Load

`data/raw/{slug}.html`  
`data/cleaned/{slug}.json`

```json
{
  "url": "https://groww.in/...",
  "title": "...",
  "fetched_at": "ISO-8601",
  "text": "cleaned visible text"
}
```

### P2 — Chunks

`data/chunks/chunks.jsonl` — one object per line:

```json
{
  "chunk_id": "hdfc-large-cap-003",
  "url": "https://groww.in/...",
  "title": "...",
  "section": "exit_load",
  "text": "...",
  "fetched_at": "ISO-8601"
}
```

**Chunking strategy (chosen for this corpus):**

1. Prefer **section / label chunks**: Groww scheme pages mix key-value facts and short narrative. Split on headings and on known labels (Expense ratio, Exit load, Min SIP, Lock-in, Riskometer, Benchmark, AMC about).
2. If a section exceeds `chunking.size`, split with overlap so a number and its label stay together.
3. Keep `url` on every chunk so citation is a lookup, not an LLM guess.

### P3 — Embeddings

Vectors stored in Chroma. Optional demo dump: `data/embeddings/manifest.json` (`chunk_id`, dim, model name, count). Do not require a huge numpy dump for the demo.

### P4 — Chroma

- Persistent client, `persist_dir` from config.
- Document = chunk text.
- Embedding function = same SentenceTransformer model.
- Id = `chunk_id`.

### P5 — Retrieval trace

`data/traces/{query_hash}.json`

```json
{
  "asked_at": "ISO-8601",
  "query_redacted": true,
  "intent": "fact | refuse_advice | refuse_returns | refuse_pii | out_of_corpus",
  "top_k": 4,
  "hits": [
    { "chunk_id": "...", "url": "...", "score": 0.42, "text": "..." }
  ]
}
```

Queries containing PII are **not** written. Store a stub: `{ "intent": "refuse_pii" }` only.

### P6 — Generation input

Prompt = system policy + retrieved chunk texts + user question (if allowed). Output JSON internally, then render:

- `answer` (≤3 sentences)
- `source_url` (exactly one; must be in retrieved hit URLs or configured educational URL on refuse)
- `last_updated_from_sources` (max `fetched_at` among used chunks, or ingest run time)

---

## 7. Query-time flow

```
1. User submits question in UI.
2. Policy.scan(text)
     - PII pattern (PAN, Aadhaar, account, OTP, email, phone) → refuse; do not persist query.
     - Advice / buy-sell / portfolio → refuse + educational_link; optional light retrieve is not required.
     - Returns / performance compare → refuse compute; if a factsheet-like chunk exists, cite that URL only as “see official page”, no numbers invented.
3. Else embed query with config embedding model.
4. Chroma query top_k.
5. If empty / low similarity → out-of-corpus refuse (still one educational or closest allowed URL if policy says so).
6. Write retrieval trace.
7. LLM generate grounded in hits only.
8. Post-check: trim to 3 sentences; force source_url ∈ {hit.urls ∪ educational}; append last-updated.
9. Render in UI with disclaimer.
```

The LLM must **not** be the only safety layer. Policy runs first; generation is constrained after.

---

## 8. LLM provider interface

```
LLMClient.complete(system: str, user: str) -> str
```

- `GroqClient` is the only implementation in v1.
- `provider` in config selects the class.
- Model id always from `LLM_MODEL` in `.env`.
- Swap path: add `OpenAIClient` / `GeminiClient` / `AnthropicClient` / `MistralClient` behind the same interface. Retrieval and chunking stay unchanged.

**System prompt (behavior, not copy-paste product text):**

- Answer only from provided chunks.
- Identify the exact fact; if missing, say it is not on the sourced pages.
- No buy/sell/switch; no return math.
- ≤3 sentences; one URL; facts-only tone.

---

## 9. UI architecture

Minimal single-page app (Streamlit recommended for speed of demo):

| Element | Binding |
|---------|---------|
| Welcome line | static / config |
| Disclaimer | `ui.disclaimer` |
| 3 example chips | `ui.examples` → fill the question box |
| Question input | no file upload, no KYC fields |
| Answer panel | text, source link, last-updated |
| Optional “pipeline” expander | last trace path + chunk ids (demo of RAG stages) |

No auth. No cookies beyond session. Do not log full questions if they fail PII scan.

---

## 10. Security and compliance (architecture)

| Concern | Control |
|---------|---------|
| Crawl scope | Hard allowlist of 5 URLs in config; loader raises if asked to fetch anything else |
| PII | Regex/heuristic gate; no storage of matching inputs |
| Advice | Intent classifier or keyword/LLM-classify **before** answer; refuse template |
| Secrets | `.env` only; never in traces |
| Citations | URL taken from chunk metadata or refuse-link config, not free-typed by the model without allowlist check |
| Performance claims | Policy + prompt; no calculator over NAV/returns |

---

## 11. Runtime views

**Ingest CLI** (run when sources change):

`python -m src.ingest.load` → `chunk` → `embed` / `index`

**Serve:**

`streamlit run src/app.py` (or equivalent)

Ingest does not need Groq. Serve needs Groq key + existing Chroma directory.

---

## 12. Mapping to PRD

| PRD | Architecture |
|-----|----------------|
| G4 inspectable RAG | `data/raw`, `cleaned`, `chunks`, Chroma, `traces` |
| G5 configurable stack | `config.yaml` + `.env` |
| FR-1–FR-8 | Policy + generator post-check + UI |
| P1–P6 | Components in §3 and §6 |
| Deliverables | README, `sources.*`, `sample_qa.md`, disclaimer in config/UI |

---

## 13. Non-goals in this design

- Crawlers, sitemaps, or recursive Groww navigation
- Hybrid search / rerankers (optional later; not required for five pages)
- Fine-tuning
- User accounts, statement download APIs, or any Groww private API
- Computing CAGR, XIRR, or scheme ranking
