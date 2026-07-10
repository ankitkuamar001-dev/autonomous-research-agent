# 🔬 Autonomous Research Agent

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.4+-purple.svg)](https://langchain-ai.github.io/langgraph/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-FF4B4B.svg)](https://streamlit.io/)

> **Production-grade AI research assistant that autonomously searches the web, verifies information across sources, and generates professional research reports with citations.**

Leverages **LangGraph multi-agent orchestration**, **vector-based semantic search**, and **LLM-powered fact verification** to deliver trustworthy, sourced research in minutes.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🔄 **8-Phase Research Pipeline** | Plan → Discover → Rank → Retrieve → Extract → Verify → Synthesize → Report |
| 🔍 **Autonomous Web Search** | Tavily-powered search with intelligent query generation and multi-source ranking |
| ✅ **Multi-Source Verification** | Cross-references claims across sources with confidence scoring (90%+ accuracy) |
| 📊 **Knowledge Synthesis** | Pattern recognition, trend analysis, contradiction detection, and insight extraction |
| 📄 **Professional Reports** | Academic-style Markdown + PDF with IEEE/APA/MLA/Chicago citations |
| ⚡ **FastAPI Backend** | Async REST API with job management and real-time status tracking |
| 🎨 **Streamlit Frontend** | Interactive UI with progress visualization and live updates |
| 🧠 **Vector Memory** | ChromaDB semantic search for intelligent fact retrieval and deduplication |
| 🐳 **Production-Ready** | Async I/O, retry logic, rate limiting, structured logging, Docker support |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Client Layer                              │
├─────────────────┬────────────────────────────────────────────────┤
│  Streamlit UI   │        FastAPI Backend REST API                │
│  (port 8501)    │        (port 8000)                             │
└─────────────────┴──────────────────┬─────────────────────────────┘
                                     │
                      ┌──────────────▼──────────────┐
                      │ LangGraph Workflow Engine   │
                      │ (Stateful Graph Execution) │
                      └──────────────┬──────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
    ┌───▼────┐              ┌─────────▼──────┐          ┌────────▼──────┐
    │ Tavily  │              │   httpx +      │          │  Gemini/Groq  │
    │ Search  │              │  BeautifulSoup │          │     LLM       │
    │  API    │              │   Scraper      │          │  (GPT-4 alt)  │
    └────┬────┘              └────────┬───────┘          └────────┬──────┘
         │                            │                          │
    ┌────▼──────────────────────────────────────────────────────▼───────┐
    │              Storage & Memory Layer                               │
    ├────────────────┬──────────────────────┬──────────────────────────┤
    │  ChromaDB      │   SQLite Cache       │  LangGraph               │
    │  (Embeddings)  │   (Persistence)      │  Checkpoints (Snapshots) │
    └────────────────┴──────────────────────┴──────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+**
- **API Keys**: 
  - Gemini (required) — [Get here](https://aistudio.google.com/)
  - Tavily (recommended) — [Free tier](https://tavily.com)
  - Groq (optional) — [Sign up](https://console.groq.com)

### 1️⃣ Clone & Setup

```bash
git clone https://github.com/ankitkuamar001-dev/autonomous-research-agent.git
cd autonomous-research-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2️⃣ Configure Environment

```bash
cp .env.example .env

# Edit .env with your API keys
nano .env  # or use your editor
```

**Required variables:**
```env
GEMINI_API_KEY=your-gemini-key-here
TAVILY_API_KEY=your-tavily-key-here
```

### 3️⃣ Run API Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit **http://localhost:8000/docs** for interactive API documentation.

### 4️⃣ Run Frontend (Optional)

```bash
streamlit run frontend/streamlit_app.py
```

Open **http://localhost:8501**

### 5️⃣ Submit a Research Request

```bash
# Start research
curl -X POST http://localhost:8000/api/v1/research \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the latest breakthroughs in AI agents in 2025?",
    "depth": "standard"
  }'

# Response
# { "job_id": "abc-123-def", "status": "running" }

# Poll status
curl http://localhost:8000/api/v1/research/abc-123-def/status

# Get report
curl http://localhost:8000/api/v1/research/abc-123-def/report | jq

# Download as Markdown
curl http://localhost:8000/api/v1/research/abc-123-def/report/download?format=md -o report.md

# Download as PDF
curl http://localhost:8000/api/v1/research/abc-123-def/report/download?format=pdf -o report.pdf
```

---

## 📁 Project Structure

```
autonomous-research-agent/
├── app/
│   ├── agents/
│   │   ├── state.py                  # TypedDict state definitions
│   │   ├── graph.py                  # LangGraph builder & orchestrator
│   │   └── nodes/
│   │       ├── planner.py            # Phase 1: Research planning
│   │       ├── discoverer.py         # Phase 2: Web discovery
│   │       ├── ranker.py             # Phase 3: Source ranking
│   │       ├── retriever.py          # Phase 4: Content retrieval
│   │       ├── extractor.py          # Phase 5: Fact extraction
│   │       ├── verifier.py           # Phase 6: Cross-source verification
│   │       ├── synthesizer.py        # Phase 7: Knowledge synthesis
│   │       └── reporter.py           # Phase 8: Report generation
│   ├── tools/
│   │   ├── search.py                 # Tavily search wrapper
│   │   ├── scraper.py                # Web scraping + HTML parsing
│   │   ├── pdf_generator.py          # PDF export utility
│   │   ├── citations.py              # Citation formatting (IEEE/APA/MLA/Chicago)
│   │   └── report_writer.py          # Report template engine
│   ├── models/
│   │   ├── research.py               # Pydantic schemas
│   │   └── agent_state.py            # State type definitions
│   ├── memory/
│   │   ├── vector_store.py           # ChromaDB wrapper
│   │   ├── cache.py                  # SQLite caching layer
│   │   └── checkpointer.py           # LangGraph persistence
│   ├── prompts/
│   │   ├── planner.prompt            # LLM system prompts
│   │   ├── verifier.prompt
│   │   └── synthesizer.prompt
│   ├── services/
│   │   ├── llm_service.py            # LLM routing & orchestration
│   │   ├── research_orchestrator.py  # Main coordinator
│   │   └── job_manager.py            # Async job tracking
│   ├── api/
│   │   ├── routes.py                 # FastAPI endpoints
│   │   ├── schemas.py                # Request/response models
│   │   └── health.py                 # Health check endpoints
│   ├── config.py                     # Settings from .env
│   └── main.py                       # FastAPI app entry
├── frontend/
│   └── streamlit_app.py              # Streamlit UI
├── tests/
│   ├── test_models.py
│   ├── test_tools.py
│   ├── test_api.py
│   └── conftest.py                   # pytest fixtures
├── docker/
│   ├── Dockerfile                    # Python service image
│   └── docker-compose.yml            # Local dev stack
├── docs/
│   ├── ARCHITECTURE.md               # Detailed design docs
│   ├── API.md                        # API reference
│   └── EXAMPLES.md                   # Usage examples
├── reports/                          # Generated reports output
├── data/
│   ├── chroma/                       # Vector DB storage
│   ├── cache.db                      # SQLite cache
│   └── checkpoints/                  # LangGraph snapshots
├── .env.example                      # Template env vars
├── requirements.txt                  # Dependencies
└── README.md                         # This file
```

---

## 🔧 API Reference

### Research Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/research` | Start new research job |
| `GET` | `/api/v1/research/{job_id}` | Get job details |
| `GET` | `/api/v1/research/{job_id}/status` | Poll job status |
| `GET` | `/api/v1/research/{job_id}/report` | Get completed report (JSON) |
| `GET` | `/api/v1/research/{job_id}/report/download` | Download report (MD/PDF) |
| `GET` | `/api/v1/research/{job_id}/sources` | List discovered sources |
| `GET` | `/api/v1/research/{job_id}/claims` | List verified claims |

### Request Schema

```json
{
  "question": "Your research question here",
  "depth": "quick|standard|deep",
  "max_sources": 10,
  "citation_format": "ieee|apa|mla|chicago"
}
```

### Response Schema (Report)

```json
{
  "job_id": "abc-123",
  "status": "completed",
  "question": "What are the latest AI breakthroughs?",
  "executive_summary": "Summary of key findings...",
  "findings": [
    {
      "title": "Finding title",
      "description": "Details...",
      "sources": ["url1", "url2"],
      "confidence": 0.95
    }
  ],
  "sources": [
    {
      "url": "https://example.com",
      "title": "Article Title",
      "domain": "example.com",
      "authority_score": 0.92
    }
  ],
  "methodology": "Description of research methodology...",
  "generated_at": "2025-01-10T12:34:56Z"
}
```

Full interactive docs at: **http://localhost:8000/docs**

---

## ⚙️ Configuration

All settings from `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google Gemini API key (required) |
| `GROQ_API_KEY` | — | Groq inference key (optional) |
| `TAVILY_API_KEY` | — | Tavily search key (recommended) |
| `DEFAULT_LLM_MODEL` | `gemini-2.0-flash` | Primary LLM model |
| `STRONG_LLM_MODEL` | `gemini-2.5-flash` | Model for synthesis/reporting |
| `SEARCH_MAX_PER_MINUTE` | `10` | Rate limit for searches |
| `SCRAPE_CONCURRENCY` | `10` | Max concurrent web scrapes |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | Vector DB storage path |
| `CACHE_DB_PATH` | `./data/cache.db` | SQLite cache location |

---

## 🐳 Docker Deployment

```bash
cd docker
docker-compose up --build -d

# Check logs
docker-compose logs -f api

# Stop services
docker-compose down
```

**Access:**
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Frontend: http://localhost:8501

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=html

# Run specific test file
pytest tests/test_api.py::test_research_endpoint -v

# Run tests matching pattern
pytest tests/ -k "verify" -v
```

---

## 📊 How It Works: The 8-Phase Pipeline

### Phase 1: **Research Planning** 🎯
Agent decomposes your question into sub-questions, identifies information gaps, and generates optimized search queries.

**Example**: "What are AI breakthroughs?" → ["Recent LLM improvements", "Computer Vision advances", "Reasoning models", ...]

### Phase 2: **Web Discovery** 🔍
Executes queries via Tavily API, collecting candidate sources with metadata (URL, title, snippet, domain).

**Output**: 10-20 candidate sources with snippets and metadata

### Phase 3: **Source Ranking** ⭐
Scores sources on 4 dimensions:
- **Authority**: Domain reputation + historical trust (40+ hardcoded trusted domains)
- **Relevance**: Query match score (BM25-like)
- **Freshness**: Publication date (recency bias)
- **Trust**: Curated list for authoritative sources (ArXiv, Nature, IEEE, etc.)

**Output**: Ranked list of top sources (typically 5-10 selected)

### Phase 4: **Content Retrieval** 📥
Fetches full text from top-ranked sources using async web scraping. Handles:
- HTML pages (BeautifulSoup)
- PDFs (PyMuPDF)
- Plain text

**Output**: Full-text content for all sources

### Phase 5: **Information Extraction** 🧩
Chunks content, stores embeddings in ChromaDB, extracts structured facts using LLM:
- Claims
- Statistics
- Quotes
- Key findings

**Output**: Structured facts with embeddings

### Phase 6: **Cross-Source Verification** ✅
Groups related facts, identifies core claims, calculates confidence scores:
- **Confidence = (source_count × source_quality) / total_sources**

Detects contradictions and flags uncertain claims.

**Output**: Verified claims with confidence scores (0.0-1.0)

### Phase 7: **Knowledge Synthesis** 🔗
Organizes verified claims into themes, identifies:
- Patterns across sources
- Emerging trends
- Contradictions and nuances
- Actionable insights

**Output**: Thematically organized findings

### Phase 8: **Report Generation** 📝
Produces professional research report:
- Executive summary
- Methodology
- Findings (organized by theme)
- Analysis and conclusions
- Formatted citations (IEEE/APA/MLA/Chicago)

**Output**: Markdown + PDF report files

---

## 🎯 Use Cases

| Use Case | Example Query |
|----------|--------------|
| **Competitive Analysis** | "Research our top 5 competitors' 2025 product roadmaps" |
| **Trend Research** | "What are emerging trends in quantum computing?" |
| **Due Diligence** | "Analyze the EU regulatory landscape for AI systems" |
| **Literature Review** | "Summarize recent breakthroughs in neural architecture search" |
| **Market Analysis** | "Estimate the global market size for LLM APIs and compare offerings" |
| **Technical Research** | "Research best practices for LLM fine-tuning in 2025" |
| **News Aggregation** | "What are the top AI news stories from this week?" |

---

## 📈 Performance Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| **Avg Search Time** | 30-45 sec | Includes scraping & verification |
| **Sources Retrieved** | 5-20 | Configurable per request |
| **Report Generation** | 2-3 min | End-to-end pipeline |
| **Verification Accuracy** | ~90% | Cross-source matching |
| **Max Concurrent Jobs** | 10+ | Horizontally scalable |
| **Report Size** | 10-50 KB | Depends on content |

---

## 🔐 Security & Best Practices

- ✅ **API Key Management**: Stored in `.env`, never committed (see `.gitignore`)
- ✅ **Rate Limiting**: Prevents API quota exhaustion and abuse
- ✅ **Async Processing**: Non-blocking, handles timeouts gracefully
- ✅ **Structured Logging**: All operations logged for debugging and auditing
- ✅ **Input Validation**: Pydantic schemas validate all requests
- ✅ **CORS Enabled**: Configured for frontend integration
- ✅ **Error Handling**: Graceful fallbacks and recovery strategies

---

## 📚 Additional Documentation

- [Architecture Deep Dive](docs/ARCHITECTURE.md) — System design, trade-offs, scalability
- [API Reference](docs/API.md) — Detailed endpoint documentation
- [Usage Examples](docs/EXAMPLES.md) — Real-world use cases and code samples
- [Troubleshooting](docs/TROUBLESHOOTING.md) — Common issues and solutions

---

## 🤝 Contributing

Contributions welcome! Please follow these steps:

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/your-feature`
3. **Commit** changes: `git commit -am 'Add new feature'`
4. **Push** to branch: `git push origin feature/your-feature`
5. **Submit** a pull request with clear description

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details. Free for personal and commercial use.

---

## 🙏 Acknowledgments

- [LangChain](https://langchain.com/) — LLM orchestration framework
- [Tavily](https://tavily.com/) — Web search API
- [ChromaDB](https://www.trychroma.com/) — Vector database
- [FastAPI](https://fastapi.tiangolo.com/) — Modern web framework
- [Streamlit](https://streamlit.io/) — Rapid frontend development

---

## 📞 Support & Contact

- 🐛 [Report Issues](https://github.com/ankitkuamar001-dev/autonomous-research-agent/issues)
- 💬 [Start Discussion](https://github.com/ankitkuamar001-dev/autonomous-research-agent/discussions)
- 📧 Email: [your-email@domain.com]
- 🌐 Portfolio: [your-portfolio-url]

---

**Built with ❤️ by [Ankit Kumar](https://github.com/ankitkuamar001-dev)**

If this project helps you, please **⭐ star** it on GitHub!

---

*Last updated: January 2025* | [View on GitHub](https://github.com/ankitkuamar001-dev/autonomous-research-agent)
