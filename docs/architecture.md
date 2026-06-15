# Architecture Documentation

## System Overview

The Autonomous Research Agent is built on a **directed acyclic graph (DAG)** architecture powered by LangGraph. Each phase of the research process is implemented as an independent, testable node that communicates through a shared typed state.

## Core Design Principles

### 1. Graceful Degradation
Every node has conditional edges that skip to report generation if insufficient data is available. A research job will always produce *some* output, even if individual phases fail.

### 2. Immutable State
Nodes return partial state updates rather than mutating the input state. List fields use `Annotated[list[T], operator.add]` reducers to accumulate values.

### 3. Async-First
All I/O operations (search, scraping, LLM calls, database access) use `async/await`. CPU-bound work (PDF parsing, PDF rendering) is offloaded to thread pools.

### 4. Tool Isolation
Each tool (search, scraper, PDF reader, etc.) is a standalone class that can be tested and used independently of the LangGraph workflow.

## Data Flow

```
ResearchQuery
    │
    ▼
┌──────────┐     ┌───────────┐     ┌──────────┐
│ Planner  │────▶│ Discoverer│────▶│  Ranker  │
│ (LLM)   │     │ (Tavily)  │     │ (Scoring)│
└──────────┘     └───────────┘     └──────────┘
                                         │
    ┌────────────────────────────────────┘
    ▼
┌──────────┐     ┌───────────┐     ┌──────────┐
│Retriever │────▶│ Extractor │────▶│ Verifier │
│(httpx/BS)│     │ (LLM)    │     │ (LLM)   │
└──────────┘     └───────────┘     └──────────┘
                                         │
    ┌────────────────────────────────────┘
    ▼
┌──────────┐     ┌───────────┐
│Synthesize│────▶│ Reporter  │────▶ Report (MD + PDF)
│ (LLM)   │     │ (LLM)    │
└──────────┘     └───────────┘
```

## Key Components

### LLM Service (`app/services/llm_service.py`)
- Factory pattern supporting Gemini and Groq providers
- Structured output via `llm.with_structured_output(PydanticModel)`
- Separate "fast" and "strong" model presets

### Vector Store (`app/memory/vector_store.py`)
- ChromaDB PersistentClient with sentence-transformers embeddings
- Per-session collections for isolation
- Cosine similarity search for fact grouping

### Source Ranking (`app/agents/nodes/ranker.py`)
- 4-dimensional scoring: authority, relevance, freshness, domain trust
- 40+ hardcoded domain trust scores
- Content type bonuses/penalties
- Weighted composite: `0.25·auth + 0.35·rel + 0.20·fresh + 0.20·trust`

### Confidence Scoring (`app/agents/nodes/verifier.py`)
- Single source: 0.2–0.4
- Two independent sources: 0.5–0.7
- Three+ independent sources: 0.7–0.9
- Academic/government source bonus: +0.1
- Contradicting source penalty: -0.1 to -0.2

## Error Handling Strategy

| Layer | Strategy |
|-------|----------|
| Search | Retry 3× with exponential backoff, return empty on failure |
| Scraping | Per-URL try/catch, mark failed sources, continue |
| LLM | Retry via tenacity, fall back to heuristic scoring |
| Nodes | Catch all exceptions, add to `errors` list, continue |
| Graph | Conditional edges skip to report if data is missing |
