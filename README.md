# Regulatory-Change-Autopilot-AI-Powered-Compliance-Intelligence-System🔍
### Autonomous Regulatory Compliance Monitor for Indian FinTech

> **Status: 🚧 Actively Under Development** — Core RAG pipeline and gap analysis engine are complete. MCP server integration is Done and analyst dashboard and deployment is in progress.

---

## What is This? 

Indian FinTech companies — NBFCs, payment aggregators, co-operative banks — receive 40-60 new regulatory circulars every year from RBI, SEBI, and IRDAI. A compliance team today reads each circular manually, compares it against internal policies, writes a gap analysis, and creates remediation tasks. This takes 2-3 days per circular.

** Regulatory-Change AI collapses that to under 10 minutes — autonomously.**

The system watches regulatory feeds, extracts text from new PDFs, semantically compares them against your internal policy documents, and outputs a structured compliance gap report — with severity ratings, cited policy clauses, and suggested actions.

---

## Demo

```
New RBI Circular Detected → RBI/2026-27/143 (Interest Rate on Deposits)
Extracting text... 5242 chars
Running gap analysis against internal policies...

Gap Analysis Result:
┌─────────────────────────────────────────────────────┐
│ Total Gaps: 4  │  High: 2  │  Medium: 1  │  Low: 1  │
└─────────────────────────────────────────────────────┘

[HIGH] Interest Rate Cap Conflict
  New Requirement : RBI mandates revised floor rate for deposits
  Existing Policy : Section 1.3 caps interest at 8% p.a. — no floor defined
  Action          : Update deposit policy and get board approval within 30 days

[HIGH] No Framework for New Financial Services
  New Requirement : Circular mandates a formal approval framework
  Existing Policy : Section 3.3 — no formal framework exists
  Action          : Draft and ratify a financial services framework immediately
...
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  LAYER 1 — DATA INGESTION               │
│   RBI Circular Index — scraped LIVE via Playwright      │
│   (real headless browser, bypasses Cloudflare)          │
│   PyMuPDF extracts text from downloaded PDFs            │
│   Internal Policy Docs — manually uploaded for now      │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│                  LAYER 2 — RAG CORE                     │
│   Chunker → HuggingFace (embed, local, free)            │
│   Qdrant Vector Store → Semantic Retrieval              │
│   LangChain + Groq LLaMA 3 → Gap Analysis Engine        │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│                  LAYER 3 — MCP ACTION LAYER  ✅         │
│   watch_regulator_feed   → triggers Playwright scraper  │
│   run_gap_analysis       → Groq-powered gap detection   │
│   list_pending_circulars → queue of unanalysed circulars│
│   get_circular_summary   → plain English briefing       │
│   Connected live to Claude Desktop                      │
└─────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Component | Tool | Cost |
|---|---|---|
| LLM Inference | Groq (LLaMA 3 8B) | Free tier |
| Embeddings | HuggingFace `all-MiniLM-L6-v2` | Free, runs locally |
| Vector Store | Qdrant (local mode) | Free, no cloud |
| PDF Extraction | PyMuPDF (fitz) | Free |
| Web Scraping | httpx + BeautifulSoup | Free |
| RAG Framework | LangChain | Free |
| Data Models | Pydantic | Free |
| Database | SQLite | Free |
| CLI Output | Rich | Free |

**Total infrastructure cost: ₹0**

---

## Project Structure

```
regulatory-autopilot/
├── src/
│   ├── watcher/
│   │   ├── scrapers.py       # RBI, SEBI, IRDAI scrapers
│   │   ├── extractor.py      # PDF text extraction via PyMuPDF
│   │   ├── database.py       # SQLite storage layer
│   │   └── models.py         # Pydantic data models
│   ├── rag/
│   │   ├── ingestor.py       # Chunking + embedding + Qdrant
│   │   └── gap_analyser.py   # LangChain + Groq gap analysis chain
│   ├── mcp_servers/          # 🚧 In progress
│   │   ├── watcher_server.py # MCP tools for regulatory watching
│   │   └── gap_server.py     # MCP tools for gap analysis
│   └── dashboard/            # 🚧 In progress
├── data/
│   ├── circulars/            # Downloaded PDFs + SQLite DB
│   └── vectors/              # Local Qdrant storage
├── tests/
│   ├── test_scraper.py       # Phase 1 scraper test
│   ├── test_local_pdf.py     # Phase 1 local PDF ingestion
│   └── test_gap_analyser.py  # Phase 2 gap analysis test
├── .env                      # API keys (not committed)
├── requirements.txt
└── README.md
```

---

## Getting Started

### Prerequisites
- Python 3.12+
- Groq API key (free at [console.groq.com](https://console.groq.com))

### Installation

```bash
# Clone the repo
git clone https://github.com/Manas-singh14/Regulatory-Change-Autopilot-AI-Powered-Compliance-Intelligence-System.git
cd regwatch-ai

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the root:

```env
GROQ_API_KEY=gsk_your-key-here
QDRANT_PATH=./data/vectors
DB_PATH=./data/circulars/circulars.db
LOG_LEVEL=INFO
```

### Run

```bash
# Phase 1 — Scrape RBI circulars
python tests/test_scraper.py

# Phase 1 — Ingest local PDFs into vector store
python tests/test_local_pdf.py

# Phase 2 — Run gap analysis on a circular
python tests/test_gap_analyser.py
```

---

## How It Works

### 1. Document Ingestion
The scraper hits RBI's circular index page, extracts PDF links, and downloads them. PyMuPDF extracts clean text page by page. Each document is stored in SQLite with metadata: regulator, date, circular number, effective date.

### 2. Chunking Strategy
Legal documents have a specific challenge — clause numbers like `4.2(a)(iii)` must stay together semantically. We use 512-token chunks with 50-token overlap, splitting on word boundaries to preserve clause context. This is intentionally different from naive character splitting.

### 3. Embedding & Retrieval
Chunks are embedded using `all-MiniLM-L6-v2` — a 384-dimension model that runs entirely on CPU. Vectors are stored in Qdrant's local mode (no server needed). Semantic search retrieves the top-K most relevant existing policy chunks for any given query.

### 4. Gap Analysis
The core prompt asks Groq (LLaMA 3) to reason in a specific direction: *"What does the new circular require that existing policy does NOT address?"* — not a generic comparison. This precision reduces hallucinations significantly. Output is forced to a Pydantic-validated JSON schema with severity, cited clauses, and remediation steps.

### 5. MCP Integration (In Progress)
Each capability is being exposed as an MCP tool so any AI agent (Claude, LangChain agent, etc.) can call them. The `watch_regulator_feed` tool polls RSS feeds; `run_policy_diff` triggers gap analysis; `create_jira_epic` creates tasks from gaps automatically.

---

## Roadmap

- [x] Phase 1 — RBI/SEBI/IRDAI scraper
- [x] Phase 1 — PDF text extraction pipeline
- [x] Phase 1 — HuggingFace embeddings + Qdrant vector store
- [x] Phase 2 — LangChain + Groq gap analysis engine
- [x] Phase 2 — Structured JSON output with Pydantic validation
- [ ] Phase 3 — MCP server (watcher + gap analyser tools)
- [ ] Phase 3 — Jira integration (auto-create tasks from gaps)
- [ ] Phase 3 — Slack notifications
- [ ] Phase 4 — Analyst dashboard (Next.js)
- [ ] Phase 4 — Confidence scoring per gap
- [ ] Phase 4 — Multi-regulator support (SEBI + IRDAI ingestion)

---

## Why This Matters

Every NBFC and payment aggregator in India has a compliance team of 3-8 people manually tracking 3 regulators. At ₹1-2L/month per compliance analyst, automating the first-pass gap analysis saves significant time and reduces the risk of missing a critical circular. This system is designed to be that first-pass — flagging gaps for human review, not replacing human judgment.

---

## Key Design Decisions

**Why Qdrant over Pinecone?** Local mode requires zero configuration, no API key, and no cost. Same query API as the cloud version — easy to upgrade later.

**Why Groq over OpenAI?** Free tier with LLaMA 3 is sufficient for structured JSON extraction tasks. No billing risk during development.

**Why SQLite over PostgreSQL?** Single-file DB is perfect for this stage — zero ops overhead, easy to inspect with DB Browser, trivial to migrate later.

**Why MCP?** Makes every capability pluggable into any LLM agent. The gap analyser becomes a tool Claude, GPT-4, or any LangChain agent can call without knowing the internals.

---

## Author

Built by Manas singh as part of an AI engineering portfolio project.

Currently actively developing Phase 3 (MCP integration) and Phase 4 (dashboard).

Feel free to reach out or raise issues — feedback welcome.

---

*This project is for educational and portfolio purposes. Always verify AI-generated compliance analysis with qualified legal professionals before acting on it.*
