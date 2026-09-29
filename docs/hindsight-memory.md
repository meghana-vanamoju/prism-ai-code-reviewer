# Hindsight Memory in PRISM

## Why PRISM Uses Hindsight

PRISM (Persistent Review Intelligence & Standards Memory) is an AI code-review agent that learns from a team's historical knowledge. Normal AI code reviewers only see the current input (diff/PR). PRISM retrieves relevant memories from Hindsight — previous reviews, team standards, architecture decisions, recurring bugs, incidents, and accepted fixes — and uses them to produce context-aware code reviews.

Hindsight provides:
- **Semantic memory storage** — memories are stored with embeddings for similarity search
- **Automatic fact extraction** — converts raw text into structured facts (observations, experiences, opinions, world facts)
- **Temporal awareness** — tracks when memories were created and their relevance over time
- **Reflection/reasoning** — `reflect` endpoint synthesizes answers from stored memories
- **Persistent bank** — stable identifier (`prism-demo-team`) for the team's collective memory

## What Is a Memory Bank?

A **memory bank** is a named namespace in Hindsight that holds a collection of memories. In PRISM, we use a single stable bank:

```
prism-demo-team
```

All memories — team standards, previous reviews, architecture decisions, incidents — are stored in this bank. The bank persists across sessions and accumulates knowledge over time.

## Hindsight Operations in PRISM

### Retain (Store Memory)

**API:** `POST /api/memory/retain`

Stores a new memory in the bank. PRISM uses this to:
- Save team coding standards
- Record previous review findings
- Document architecture decisions
- Log incidents and their fixes

**Example:**
```json
{
  "content": "Financial calculations must use Decimal rather than floating-point arithmetic.",
  "context": "Team coding standard for monetary calculations",
  "metadata": { "source": "team-standard", "category": "financial" }
}
```

### Recall (Retrieve Memories)

**API:** `POST /api/memory/recall`

Retrieves relevant memories using semantic similarity search. PRISM uses this during code review to find memories related to the code being reviewed.

**Example Request:**
```json
{
  "query": "What should our team use for financial calculations?",
  "budget": "mid"
}
```

**Example Response:**
```json
{
  "query": "What should our team use for financial calculations?",
  "memories": [
    {
      "id": "mem-1",
      "text": "Financial calculations must use Decimal rather than floating-point arithmetic.",
      "type": "observation",
      "context": "Team coding standard for monetary calculations",
      "metadata": { "source": "team-standard", "category": "financial" },
      "document_id": "doc-1"
    }
  ]
}
```

### Reflect (Reason Over Memories)

**API:** `POST /api/memory/reflect`

Generates a synthesized answer by reasoning over the bank's memories. PRISM can use this for higher-level questions about team practices.

**Example Request:**
```json
{
  "query": "What should I know about this team's coding standards for financial calculations?",
  "budget": "low"
}
```

**Example Response:**
```json
{
  "query": "What should I know about this team's coding standards for financial calculations?",
  "answer": "Based on team standards, financial calculations must use Decimal rather than floating-point arithmetic. A previous incident in the billing service was caused by floating-point precision issues. The team also has an existing money utility at src/utils/money.py that should be used.",
  "based_on": [
    { "text": "Financial calculations must use Decimal..." },
    { "text": "A billing service bug was caused by floating-point precision..." }
  ]
}
```

## PRISM's Bank ID

```
prism-demo-team
```

This is configured via `HINDSIGHT_BANK_ID` environment variable (default in `.env.example`).

## Seed Data

The demo includes 6 seed memories in `demo-data/seed_memories.json`:

1. **Team Standard** — Financial calculations must use Decimal
2. **Previous Review** — PR #42 floating-point precision issue
3. **Architecture Decision** — Use existing money utility (src/utils/money.py)
4. **Team Standard** — Service-layer functions use Result<T, Error> pattern
5. **Previous Incident** — Billing service bug from floating-point precision
6. **Previous Review** — Prefer existing shared utilities before creating duplicates

## Local Configuration

### Environment Variables

```bash
HINDSIGHT_BASE_URL=http://localhost:8888
HINDSIGHT_BANK_ID=prism-demo-team
HINDSIGHT_API_KEY=  # optional for local dev
```

### Running Hindsight Locally (Docker)

```bash
# Requires an LLM API key (e.g., OpenAI, Groq, or local Ollama)
export OPENAI_API_KEY=sk-xxx  # or GROQ_API_KEY, or configure local LLM

docker run -it --pull always --name hindsight --restart unless-stopped -p 8888:8888 -p 9999:9999 \
  -e HINDSIGHT_API_LLM_API_KEY=$OPENAI_API_KEY \
  -v hindsight-data:/home/hindsight/.pg0 \
  ghcr.io/vectorize-io/hindsight:latest
```

The server will be available at `http://localhost:8888`.

### Running the Seed Script

```bash
cd backend
PYTHONPATH=. .venv/bin/python scripts/seed_memory.py
```

Expected output:
```
Seeding PRISM memory bank: prism-demo-team
Hindsight URL: http://localhost:8888
Loading 6 memories from demo-data/seed_memories.json

[1/6] Retaining: Financial calculations must use Decimal rather than floating-point ar...
      ✓ Success (items: 1)
[2/6] Retaining: PR #42 introduced a floating-point precision issue in billing calculations...
      ✓ Success (items: 1)
...
Memory seeding complete: 6/6 succeeded
```

## Testing the Memory API

### Retain a Memory
```bash
curl -X POST http://localhost:8000/api/memory/retain \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Financial calculations must use Decimal rather than floating-point arithmetic.",
    "context": "Team coding standard",
    "metadata": {"source": "demo"}
  }'
```

### Recall Memories
```bash
curl -X POST http://localhost:8000/api/memory/recall \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What does our team require for financial calculations?",
    "budget": "mid"
  }'
```

### Reflect on Memories
```bash
curl -X POST http://localhost:8000/api/memory/reflect \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What should I know about this team's coding standards for financial calculations?",
    "budget": "low"
  }'
```

## Verification Steps

1. Start Hindsight (Docker)
2. Run seed script: `PYTHONPATH=. .venv/bin/python scripts/seed_memory.py`
3. Test recall: `curl -X POST http://localhost:8000/api/memory/recall -d '{"query": "financial calculations"}'`
4. Verify the stored memories are returned
5. Test reflect: `curl -X POST http://localhost:8000/api/memory/reflect -d '{"query": "financial calculation standards"}'`

## Files

- `backend/app/services/hindsight_service.py` — Hindsight client wrapper
- `backend/app/api/memory.py` — REST endpoints
- `backend/app/models/memory.py` — Request/response models
- `backend/scripts/seed_memory.py` — Seed script
- `demo-data/seed_memories.json` — Demo memories
- `backend/tests/test_hindsight_service.py` — Unit tests (mocked)
- `backend/tests/test_memory_api.py` — API tests (mocked)