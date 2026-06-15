# 🔬 Autonomous Research Agent

A production-grade AI research agent that autonomously searches the web, collects and verifies information across sources, synthesizes findings, and generates professional research reports with inline citations.

![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-0.4+-purple.svg)

---

## ✨ Features

- **8-Phase Research Pipeline**: Plan → Discover → Rank → Retrieve → Extract → Verify → Synthesize → Report
- **Autonomous Web Search**: Tavily-powered search with intelligent query generation
- **Multi-Source Verification**: Cross-references claims across sources with confidence scoring
- **Genuine Knowledge Synthesis**: Pattern recognition, trend analysis, and contradiction detection
- **Professional Reports**: Academic-style Markdown + PDF output with IEEE/APA/MLA/Chicago citations
- **FastAPI Backend**: Full REST API with async job management and real-time status
- **Streamlit Frontend**: Beautiful UI with real-time progress tracking
- **Vector Memory**: ChromaDB-powered semantic search for fact retrieval
- **Production-Ready**: Async I/O, retry logic, rate limiting, structured logging, Docker deployment

---

## 🏗️ Architecture

```
┌──────────────┐     ┌──────────────────────────────────────────────────┐
│  Streamlit   │────▶│                FastAPI Backend                   │
│  Frontend    │     │                                                  │
└──────────────┘     │  ┌────────────────────────────────────────────┐  │
                     │  │          LangGraph Workflow                 │  │
                     │  │                                            │  │
                     │  │  Plan → Discover → Rank → Retrieve →       │  │
                     │  │  Extract → Verify → Synthesize → Report    │  │
                     │  └────────────────────────────────────────────┘  │
                     │                                                  │
                     │  ┌──────────┐ ┌──────────┐ ┌───────────────┐   │
                     │  │  Tavily  │ │  httpx   │ │   Gemini /    │   │
                     │  │  Search  │ │  Scraper │ │   Groq LLM    │   │
                     │  └──────────┘ └──────────┘ └───────────────┘   │
                     │                                                  │
                     │  ┌──────────┐ ┌──────────┐ ┌───────────────┐   │
                     │  │ ChromaDB │ │  SQLite  │ │  LangGraph    │   │
                     │  │ Vectors  │ │  Cache   │ │  Checkpoints  │   │
                     │  └──────────┘ └──────────┘ └───────────────┘   │
                     └──────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- API Keys: Gemini (required), Tavily (recommended), Groq (optional)

### 1. Clone & Setup

```bash
cd autonomous-research-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys:
#   GEMINI_API_KEY=your-key-here
#   TAVILY_API_KEY=your-key-here  (get free at https://tavily.com)
```

### 3. Run the API Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Run the Streamlit Frontend (optional)

```bash
streamlit run frontend/streamlit_app.py
```

### 5. Submit a Research Job

```bash
# Start research
curl -X POST http://localhost:8000/api/v1/research \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Research the impact of AI agents on software engineering productivity in 2025",
    "depth": "standard"
  }'

# Poll status (replace JOB_ID)
curl http://localhost:8000/api/v1/research/{JOB_ID}/status

# Get report
curl http://localhost:8000/api/v1/research/{JOB_ID}/report

# Download Markdown
curl http://localhost:8000/api/v1/research/{JOB_ID}/report/download?format=md -o report.md
```

---

## 📁 Project Structure

```
autonomous-research-agent/
├── app/
│   ├── agents/           # LangGraph workflow
│   │   ├── state.py      # AgentState TypedDict
│   │   ├── graph.py      # StateGraph builder & runner
│   │   └── nodes/        # 8 workflow phase implementations
│   ├── tools/            # Agent tools (search, scraper, PDF, citations, report writer)
│   ├── models/           # Pydantic data models
│   ├── memory/           # ChromaDB vector store, SQLite cache, checkpointer
│   ├── prompts/          # LLM prompt templates
│   ├── services/         # LLM service, research orchestrator
│   ├── api/              # FastAPI routes & schemas
│   ├── config.py         # Pydantic Settings (from .env)
│   └── main.py           # FastAPI application entry point
├── frontend/
│   └── streamlit_app.py  # Streamlit UI
├── tests/                # pytest test suite
├── docker/               # Dockerfile + docker-compose.yml
├── reports/              # Generated reports output
├── data/                 # Persistent data (ChromaDB, cache)
└── docs/                 # Documentation
```

---

## 🔧 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/research` | Start a new research job |
| `GET` | `/api/v1/research/{id}/status` | Poll job status |
| `GET` | `/api/v1/research/{id}/report` | Get completed report |
| `GET` | `/api/v1/research/{id}/report/download` | Download report (MD/PDF) |
| `GET` | `/api/v1/research/{id}/sources` | List discovered sources |
| `GET` | `/api/v1/research/{id}/claims` | List verified claims |

Full interactive docs at: `http://localhost:8000/docs`

---

## ⚙️ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google Gemini API key (required) |
| `GROQ_API_KEY` | — | Groq API key (optional, fast inference) |
| `TAVILY_API_KEY` | — | Tavily search API key (recommended) |
| `DEFAULT_LLM_MODEL` | `gemini-2.0-flash` | Default LLM model |
| `STRONG_LLM_MODEL` | `gemini-2.5-flash` | Model for synthesis/reporting |
| `SEARCH_MAX_PER_MINUTE` | `10` | Search rate limit |
| `SCRAPE_CONCURRENCY` | `10` | Concurrent web scraping limit |

---

## 🐳 Docker Deployment

```bash
# Build and run
cd docker
docker-compose up --build

# API: http://localhost:8000
# Frontend: http://localhost:8501
# Docs: http://localhost:8000/docs
```

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_models.py -v
pytest tests/test_tools.py -v
pytest tests/test_api.py -v
```

---

## 📊 Research Workflow Details

### Phase 1: Research Planning
The agent decomposes your question into sub-questions, generates optimized search queries, and identifies information gaps.

### Phase 2: Web Discovery
Executes search queries via Tavily, collecting candidate sources with metadata (URL, title, snippet, domain).

### Phase 3: Source Ranking
Scores sources on 4 dimensions: **authority** (domain reputation), **relevance** (query match), **freshness** (publication date), **domain trust** (hardcoded trust scores for 40+ domains).

### Phase 4: Content Retrieval
Fetches full text from top-ranked sources using async web scraping (httpx + BeautifulSoup). Handles PDFs via PyMuPDF.

### Phase 5: Information Extraction
Chunks content, stores embeddings in ChromaDB, and uses the LLM to extract structured facts (statistics, findings, claims, quotes).

### Phase 6: Cross-Source Verification
Groups related facts, identifies core claims, and calculates confidence scores based on source count and quality.

### Phase 7: Knowledge Synthesis
Organizes verified claims into themes, identifies patterns, trends, contradictions, and emerging insights.

### Phase 8: Report Generation
Produces a professional research report with executive summary, methodology, findings, analysis, conclusions, and IEEE citations.

---

## 📄 License

MIT License
