# PRISM — Persistent Review Intelligence & Standards Memory

PRISM is an AI code review agent that uses [Hindsight](https://github.com/vectorize-io/hindsight)
as a **persistent memory bank** for a team's standards, past decisions, incidents, and review feedback.

Most AI code review tools are stateless: they see the current code (or diff) and nothing else. PRISM
remembers what your team has already decided, so every future review is informed by your team's
history rather than by generic best practices.

---

## 1. Project overview

PRISM runs a closed learning loop over a single shared memory bank:

```
RETAIN  →  RECALL  →  REVIEW  →  FEEDBACK  →  RETAIN
   ▲                                                  │
   └──────────────────────────────────────────────────┘
```

| Stage | What happens |
| --- | --- |
| **RETAIN** | Team standards, past reviews, incidents, and architecture decisions are written into the Hindsight bank (`prism-demo-team` by default). |
| **RECALL** | For every new review, PRISM semantically searches the bank for memories relevant to the submitted code. |
| **REVIEW** | Recalled memories are injected into the Groq LLM prompt alongside the code, producing a context-aware review. |
| **FEEDBACK** | A reviewer accepts or rejects individual issues, with an optional reason. |
| **RETAIN** | Those decisions are written back into the bank, so the next related review recalls the decision. |

The final arrow is the point of the project: the loop is what makes the memory compound over time.

---

## 2. Why PRISM

- **Conventional review agents are context-free.** They review the snippet in front of them and
  cannot know that this team rejected `Decimal` two reviews ago, that a shared money helper already
  exists, or that a past incident started exactly here.
- **PRISM recalls the team's history.** It stores previous reviews, coding standards, architecture
  decisions, recurring issues, incidents, and accepted/rejected review feedback.
- **Future reviews are grounded in that memory.** Recalled items appear in the prompt and are shown
  in a **Memories Used** panel so the reviewer can see *why* a recommendation was made. Individual
  issues can cite a specific memory via `memory_reference`.

An empty issues array therefore means *"nothing here requires a change against our standards"* — not
*"this code is good"*. The review summary can still call out an observation, and a remembered
decision can be the reason no change is needed.

---

## 3. Architecture

```
┌──────────────────────────────┐
│  Frontend (React 19 + Vite)  │   code editor, summary, issues, memories
│  dev server :5173            │   API health indicator
└──────────────┬───────────────┘
               │  same-origin /api + /health
               │  (proxied by Vite)
               ▼
┌──────────────────────────────┐
│  FastAPI Backend  :8000      │   /api/review, /api/review/feedback
│  ReviewService               │   /api/memory/{retain,recall,reflect}
│  LLMService ─────┐           │   /health
│  HindsightService│           │
└─────────┬────────┴───────────┘
          │                │
          │  REST          │  REST
          ▼                ▼
┌──────────────────────┐   ┌──────────────────────────┐
│  Groq LLM            │   │  Hindsight  :8888       │
│  (review generation) │   │  bank: prism-demo-team   │
└──────────┬───────────┘   │  persistent Docker vol  │
           │               └──────────────────────────┘
           ▼
┌──────────────────────────────────────┐
│  Context-aware review:               │
│  summary + issues + suggestions      │
│  + memories used, with references    │
└──────────────────────────────────────┘
```

Only components that exist in this repository are shown: the React/Vite frontend, the FastAPI
backend, the Hindsight memory server, and the Groq-hosted LLM.

---

## 4. Features

Implemented and verified in this repository:

- **AI code review** — Groq-hosted LLM (`openai/gpt-oss-20b` by default) returns a JSON summary,
  issues, and suggestions. Severity levels: `critical`, `high`, `medium`, `low`, `suggestion`.
- **Hindsight memory recall** — semantic recall against the team bank on every review, with a
  configurable budget (`low`/`mid`/`high`) and memory cap.
- **Persistent review feedback** — accept/reject decisions plus optional reasons are retained to the
  bank and can be recalled by later reviews.
- **Memory references in review results** — each issue may carry a `memory_reference` (e.g. `[1]`)
  and the UI renders it as **Based on:**.
- **Memories Used UI** — a panel listing every recalled memory with its context and collapsible
  metadata, stating they informed the recommendations.
- **Accept/reject issue feedback** — per-issue radio decision with an optional free-text reason.
- **Hindsight retention using the configured retention extraction mode** — the bank is aligned to
  `HINDSIGHT_RETAIN_EXTRACTION_MODE` (`chunks` by default) at backend startup, so retention does not
  depend on the Hindsight server reaching its own LLM.
- **Hindsight memory API** — direct `retain` / `recall` / `reflect` endpoints for exploring the bank.
- **API health indicator** — the header shows `API: Checking… / Connected / Disconnected` based on
  the real `GET /health` result, with the failure reason in the tooltip.
- **CWD-independent backend `.env` loading** — the root `.env` is resolved from the file's location,
  so the backend works whether uvicorn starts from the repo root or from `backend/`.
- **Optional review focus** — a "Specific review focus" field is passed to recall and the prompt.
- **Language selection** — JavaScript, TypeScript, Python, Go, Rust, Java, C++, Other.

---

## 5. Tech stack

**Frontend** (`frontend/package.json`)

| | |
| --- | --- |
| UI | React 19, React DOM 19 |
| Build / dev server | Vite 8, `@vitejs/plugin-react` |
| Language | TypeScript ~6.0 |
| Lint | oxlint 1.81 |
| Tests | Vitest 5, React Testing Library 16, `@testing-library/jest-dom` 7, jsdom 30 |

**Backend** (`backend/requirements.txt`)

| | |
| --- | --- |
| API framework | FastAPI 0.141.1 |
| ASGI server | uvicorn 0.54.0 (`uvicorn[standard]`) |
| Settings / models | pydantic 2.13.5, pydantic-settings 2.15.0 |
| Env loading | python-dotenv 1.2.3 |
| HTTP client | httpx 0.28.1 |
| LLM | groq 1.7.0 |
| Memory | hindsight-client 0.1.0 |
| Tests | pytest 8.3.2, pytest-asyncio 0.23.7 |

**Memory server:** Hindsight via Docker (`ghcr.io/vectorize-io/hindsight:latest`).

---

## 6. Prerequisites

- **Python 3.11+** — the repo does not pin a version in `requirements.txt`; it is developed and
  tested on **Python 3.13.5**. (3.10 may work, 3.11+ is the safe floor.)
- **Node.js 18+ with npm** — no `engines` field is declared. Verified on **Node v24.21.0 / npm 11.19.0**.
- **Docker** — required to run Hindsight.
- **A Groq API key** — used both for review generation and by the Hindsight container.
- **A Hindsight server** — started via Docker in step 9.

---

## 7. Repository setup

```bash
git clone https://github.com/meghana-vanamoju/prism-ai-code-reviewer.git
cd prism-ai-code-reviewer
```

**Backend virtual environment and dependencies** (run from `backend/`):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Frontend dependencies** (run from `frontend/`):

```bash
cd frontend
npm install
```

**Environment file** (from the repository root — see section 8):

```bash
cp .env.example .env
# then edit .env and set GROQ_API_KEY
```

---

## 8. Environment configuration

`.env` belongs at the **repository root**, next to `README.md` and `.env.example`.

- `.env` is **gitignored** (see `.gitignore`, the `.env` rule) and must **never** be committed.
- `.env.example` is the committed template and documents every supported variable.
- The backend resolves the root `.env` from the location of `config.py`, not the process working
  directory, so the backend behaves the same whether it is started from the repo root or from
  `backend/`. An optional `backend/.env` is loaded **after** the root file if you need to override a
  single value locally.

Copy the template and fill in the key:

```bash
cp .env.example .env
$EDITOR .env
```

### Variables (names and defaults only — never commit real values)

| Variable | Default | Required | Purpose |
| --- | --- | --- | --- |
| `HINDSIGHT_BASE_URL` | `http://localhost:8888` | yes | Base URL of the Hindsight API |
| `HINDSIGHT_BANK_ID` | `prism-demo-team` | yes | Name of the persistent memory bank |
| `HINDSIGHT_RETAIN_EXTRACTION_MODE` | `chunks` | yes | How Hindsight stores retained content (see section 9) |
| `GROQ_API_KEY` | *(empty)* | **yes** | Groq API key for review generation. Empty ⇒ `/api/review` returns HTTP 400 `GROQ_API_KEY not configured` |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | no | Model used for reviews and by the Hindsight container |
| `API_HOST` | `0.0.0.0` | no | Backend bind host |
| `API_PORT` | `8000` | no | Backend bind port |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | no | Comma-separated allowed browser origins |

The same key is used in two places: PRISM's own `GROQ_API_KEY` for reviews, and
`HINDSIGHT_API_LLM_API_KEY` inside the Hindsight container (section 9).

---

## 9. Hindsight setup

Hindsight is the memory server. It is a single Docker container exposing an HTTP API on
**port 8888** (API) and **port 9999** (control plane), backed by a **named Docker volume** so the
bank survives restarts and reboots.

The following is the exact configuration this project runs with:

```bash
export GROQ_API_KEY=your-groq-key   # your real key; never commit it

docker run -d --pull always --name hindsight --restart unless-stopped \
  -p 8888:8888 \
  -p 9999:9999 \
  -e HINDSIGHT_API_LLM_PROVIDER=groq \
  -e HINDSIGHT_API_LLM_API_KEY="$GROQ_API_KEY" \
  -e HINDSIGHT_API_LLM_MODEL=openai/gpt-oss-20b \
  -e HINDSIGHT_API_LLM_GROQ_SERVICE_TIER=on_demand \
  -e HINDSIGHT_API_WORKER_ID=prism-hindsight \
  -v hindsight-data:/home/hindsight/.pg0 \
  ghcr.io/vectorize-io/hindsight:latest
```

| Item | Value |
| --- | --- |
| Image | `ghcr.io/vectorize-io/hindsight:latest` |
| Ports | `8888:8888` (API, what PRISM talks to) and `9999:9999` (control plane) |
| Restart policy | `unless-stopped` |
| Persistent volume | `hindsight-data:/home/hindsight/.pg0` |
| LLM provider | `HINDSIGHT_API_LLM_PROVIDER=groq` |
| LLM API key | `HINDSIGHT_API_LLM_API_KEY=$GROQ_API_KEY` (the same Groq key) |
| LLM model | `HINDSIGHT_API_LLM_MODEL=openai/gpt-oss-20b` (keep in sync with `GROQ_MODEL`) |
| Groq service tier | `HINDSIGHT_API_LLM_GROQ_SERVICE_TIER=on_demand` |
| Worker id | `HINDSIGHT_API_WORKER_ID=prism-hindsight` |

First run pulls the image and may take a few minutes. The image ships **no Docker healthcheck**, so
verify readiness with the API directly:

```bash
curl http://localhost:8888/health          # expect HTTP 200
curl http://localhost:8888/v1/default/banks # expect HTTP 200
```

`prism-demo-team` does not exist until something writes to it. The backend creates and configures it
lazily on first startup (see `ensure_bank_configuration` in
`backend/app/services/hindsight_service.py`), and section 15's seed script populates it.

### Retention extraction mode

`HINDSIGHT_RETAIN_EXTRACTION_MODE` (default `chunks`) controls how Hindsight turns submitted content
into stored memory:

- `chunks` stores the submitted content directly. Retention is fast and does **not** require the
  Hindsight server to reach its own LLM. Content stays fully recallable through normal semantic
  recall. **This is the default and what you should use locally.**
- `concise` asks the Hindsight server to summarise every chunk into atomic facts using the LLM it was
  started with. If the container cannot reach that provider, summarisation fails and *every* retain
  request fails, even though the database and recall paths are healthy.

PRISM applies this setting to the bank at backend startup via `PATCH
/v1/default/banks/{bank_id}/config`. It is best-effort: if Hindsight is unreachable, the backend logs
a warning and continues rather than failing to start.

---

## 10. Backend startup

Run from the **`backend/`** directory:

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For development with auto-reload:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

`--host 0.0.0.0 --port 8000` matches the `API_HOST` / `API_PORT` defaults in `.env.example`.

**Health endpoint:**

```bash
curl http://localhost:8000/health
# {"status":"healthy","service":"prism-api"}
```

Interactive API docs (FastAPI): <http://localhost:8000/docs>

Startup also calls `ensure_bank_configuration()` to align the bank's retention mode, and closes the
Hindsight client on shutdown.

---

## 11. Frontend startup

Run from the **`frontend/`** directory:

```bash
cd frontend
npm run dev
```

Vite prints the URL; the default is <http://localhost:5173>.

Other scripts: `npm run build` (Type-check + production build to `dist/`), `npm run preview`
(serves the production build with the same proxy).

### Vite proxy and API configuration

The frontend does **not** call `http://localhost:8000` directly. `frontend/src/services/api.ts` uses
same-origin relative paths, and `frontend/vite.config.ts` proxies them to the backend:

| Path | Proxied to |
| --- | --- |
| `/health` | `VITE_API_PROXY_TARGET` or `http://localhost:8000` |
| `/api` | `VITE_API_PROXY_TARGET` or `http://localhost:8000` |

Because the browser only ever talks to its own origin, the backend's CORS allowlist is never
involved. Point the proxy elsewhere with:

```bash
VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
```

`VITE_API_BASE` remains supported in `api.ts` as an explicit absolute-URL override if you need it.

---

## 12. Running the application

Start everything, in this order:

1. **Hindsight** — `docker run ... ghcr.io/vectorize-io/hindsight:latest` (section 9), then confirm
   `curl http://localhost:8888/health` returns 200.
2. **Backend** — `cd backend && source .venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
   (section 10). Confirm `curl http://localhost:8000/health` returns `{"status":"healthy",...}`.
3. **Frontend** — `cd frontend && npm run dev` (section 11).
4. **Seed demo memories** (optional but recommended for the demo) — section 15.
5. **Open** <http://localhost:5173> and check the header shows **API: Connected**.

---

## 13. API endpoints

All routes are defined in `backend/app/api/` and `backend/app/main.py`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness check. Returns `{"status":"healthy","service":"prism-api"}` |
| `POST` | `/api/review` | Recall memories for the submitted code, then generate a context-aware review. **200** on success, **400** if `GROQ_API_KEY` is unset, **500** if recall or generation fails |
| `POST` | `/api/review/feedback` | Persist per-issue accept/reject decisions (and optional free text) to the memory bank. **201** on success |
| `POST` | `/api/memory/retain` | Store a memory directly in the bank. **201** on success |
| `POST` | `/api/memory/recall` | Semantic search of the bank by query. **200** |
| `POST` | `/api/memory/reflect` | Reason over the bank and return a synthesized answer with `based_on` evidence. **200** |

`/api/review/feedback` and `/api/memory/reflect` are the two most useful for a demo: the first is
what closes the learning loop, the second shows the memory reasoning on its own.

Example — review:

```bash
curl -X POST http://localhost:8000/api/review \
  -H "Content-Type: application/json" \
  -d '{
    "code": "function calculateTotal(items) { let total = 0; for (const item of items) { total += item.price; } return total; }",
    "language": "javascript",
    "query": "financial calculation issues"
  }'
```

---

## 14. Demo flow

Takes 2–3 minutes. The editor is pre-filled with exactly the code the seed memories cover, so this
works with no typing.

1. **Start everything** and open <http://localhost:5173>. Point out **API: Connected** in the header.
2. **Show the memories up front.** Point at the 🧠 Memories Used panel and say these came from
   Hindsight, not from a prompt. Note the seeded team standards about `Decimal` and
   `src/utils/money.py`.
3. **Submit the code.** The editor already contains a `calculateTotal` that sums `item.price` into a
   JS `number`. Optionally set *Specific review focus* to `financial calculation issues`, then click
   **Review Code**.
4. **Show the review.** The floating-point money bug should be flagged, with a **Based on:** reference
   back to the recalled `Decimal` memory, and the summary shows how many memories were used.
5. **Give feedback.** Expand **Provide Feedback** on the issue, choose **Accept** or **Reject**, add
   a reason (e.g. "we now use the shared money utility"), and submit. The success toast confirms it
   was stored in Hindsight.
6. **Explain retention.** That decision was just written into the bank — this is the RETAIN leg of
   the loop.
7. **Prove it recalls.** Modify the code to use a second float helper (or re-submit the same snippet
   with a focus like `duplicate money helpers`) and review again. The new **Memories Used** panel now
   includes the feedback record, so PRISM's recommendation reflects your decision rather than
   re-litigating it.

That is RECALL → REVIEW → FEEDBACK → RETAIN → RECALL, visible end to end.

---

## 15. Demo data

`demo-data/seed_memories.json` contains **6** seed memories:

1. Team standard — financial calculations must use `Decimal`
2. Previous review — PR #42 floating-point precision issue in billing
3. Architecture decision — use the existing `src/utils/money.py` utility
4. Team standard — service layer returns `Result<T, Error>` instead of throwing
5. Previous incident — billing service bug from floating-point precision
6. Previous review guidance — prefer existing shared utilities over duplicates

### Seed script

`backend/scripts/seed_memory.py` reads that file, prints the target bank and Hindsight URL, retains
each memory one at a time, and **exits non-zero if any memory fails** so CI and humans notice.

```bash
cd backend
PYTHONPATH=. .venv/bin/python scripts/seed_memory.py
```

Expected shape of output:

```
Seeding PRISM memory bank: prism-demo-team
Hindsight URL: http://localhost:8888
Loading 6 memories from demo-data/seed_memories.json

[1/6] Retaining: Financial calculations must use Decimal rather than floating-point ar...
      ✓ Success (items: 1)
...
Memory seeding complete: 6/6 succeeded
```

**Prerequisites:** Hindsight must be running and reachable at `HINDSIGHT_BASE_URL`, and `.env` must be
configured. The script does not need Groq for the retain call when
`HINDSIGHT_RETAIN_EXTRACTION_MODE=chunks`, but `concise` mode would require Hindsight to reach its
LLM provider.

The script is **not** idempotent-safe to run repeatedly against the same bank — it appends, so you
will get duplicates. To start over, remove the volume and the container, then re-run:

```bash
docker rm -f hindsight
docker volume rm hindsight-data
```

---

## 16. Troubleshooting

### Hindsight not healthy

```bash
curl http://localhost:8888/health
docker ps --filter name=hindsight
docker logs hindsight --tail 50
```

- `curl: (7) Failed to connect` → the container is not running. `docker ps -a --filter name=hindsight`
  and `docker logs` to see why; the first start also pulls a large image, so wait for it to finish.
- Container is running but Hindsight is slow on first use → the initial image pull and model
  warm-up can take several minutes.

### Retain / feedback hangs or fails with a timeout

If `HINDSIGHT_RETAIN_EXTRACTION_MODE` is `concise`, Hindsight calls its own LLM on every retain. If
the container cannot resolve or reach the provider, summarisation fails and every retain request
fails after a long delay even though recall works. **Set `HINDSIGHT_RETAIN_EXTRACTION_MODE=chunks`**
and restart the backend. Confirm the bank took the setting:

```bash
curl http://localhost:8888/v1/default/banks/prism-demo-team/config
```

Note that `GET /v1/default/banks/prism-demo-team` on its own returns **405 Method Not Allowed** — that
path only accepts `PUT`/`PATCH`/`DELETE`. Use the `/config` sub-path to read the bank's settings.

You should also see a startup log line `Hindsight bank prism-demo-team retain_extraction_mode set to
chunks`, or a warning naming the failure.

### `GROQ_API_KEY not configured` (HTTP 400)

`GROQ_API_KEY` is empty or missing from `.env`. Confirm the file is at the **repository root** and
contains a non-empty value. pydantic-settings strips surrounding whitespace, but the value must
still be there — check for a stray newline or leading space in the key. The same key must also be
passed to the Hindsight container as `HINDSIGHT_API_LLM_API_KEY`.

### Frontend cannot reach the backend

- The header shows **API: Disconnected**. Hover it: the tooltip carries the real reason (network
  error vs. HTTP status).
- Verify the backend directly: `curl http://localhost:8000/health`.
- The frontend proxies `/api` and `/health` to `VITE_API_PROXY_TARGET` (default
  `http://localhost:8000`). If your backend runs elsewhere, restart the dev server with
  `VITE_API_PROXY_TARGET=http://<host>:<port> npm run dev`.
- Check `CORS_ORIGINS` in `.env` includes the origin the browser is actually using. A mismatch
  between `localhost` and `127.0.0.1` counts as a different origin. The proxy usually sidesteps CORS
  entirely, so prefer it.
- A blank `Disconnected` with a network error usually means the backend is not running or the port is
  wrong.

### Port already in use

- `8000` (backend): stop the other process, or start PRISM on a different port *and* update
  `VITE_API_PROXY_TARGET` to match. `lsof -i :8000` finds the owner.
- `8888` (Hindsight): `docker stop hindsight` if a stale container holds it.
- `5173` (frontend): Vite will offer the next free port; use the URL it prints. If you need a fixed
  one, `npm run dev -- --port 5174`.

### Backend started from the wrong directory

Run the backend from `backend/` so `app.main:app` is importable:

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Starting from the repository root fails with `ModuleNotFoundError: No module named 'app'`. The `.env`
location is *not* the problem — it is resolved from the source file's location, so it is found either
way.

### Memories come back empty

- The bank was never seeded — run the seed script (section 15).
- `HINDSIGHT_BANK_ID` differs between the seed run and the backend, so memories went to another bank.
- Recall is semantic: an unrelated snippet will legitimately return nothing. Try the demo code, or
  probe the bank directly with `POST /api/memory/recall` using a query like `financial calculations`.

### `ModuleNotFoundError: No module named 'uvicorn'`

The virtual environment is not active. Re-run `source .venv/bin/activate` from `backend/`, or call
the interpreter directly: `.venv/bin/python -m uvicorn app.main:app`.

---

## 17. Project structure

```
prism-ai-code-reviewer/
├── .env.example                    # committed template — copy to .env
├── .gitignore                      # ignores .env
├── README.md
├── demo-data/
│   └── seed_memories.json          # 6 seed memories
├── docs/
│   └── hindsight-memory.md         # deeper Hindsight notes
├── backend/
│   ├── requirements.txt
│   ├── scripts/
│   │   └── seed_memory.py          # loads demo-data into the bank
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, lifespan, /health
│   │   ├── config.py               # Settings + CWD-independent .env resolution
│   │   ├── api/
│   │   │   ├── review.py           # /api/review, /api/review/feedback
│   │   │   └── memory.py           # /api/memory/{retain,recall,reflect}
│   │   ├── models/
│   │   │   ├── review.py           # request/response models
│   │   │   └── memory.py
│   │   └── services/
│   │       ├── review_service.py   # RETAIN/RECALL/REVIEW/FEEDBACK orchestration
│   │       ├── llm_service.py      # Groq prompt + response parsing
│   │       └── hindsight_service.py# Hindsight client + bank configuration
│   └── tests/                      # 54 pytest tests (mocked, no network)
│       ├── test_health.py
│       ├── test_config.py
│       ├── test_review_api.py
│       ├── test_memory_api.py
│       ├── test_review_service.py
│       └── test_hindsight_service.py
└── frontend/
    ├── package.json
    ├── vite.config.ts              # dev/preview proxy for /api and /health
    ├── tsconfig.json
    ├── .oxlintrc.json
    ├── public/
    └── src/
        ├── main.tsx
        ├── App.tsx                 # layout, health indicator, review state
        ├── App.css
        ├── types/review.ts
        ├── services/api.ts         # same-origin fetch wrapper
        ├── components/
        │   ├── CodeEditor.tsx
        │   ├── SummaryPanel.tsx
        │   ├── IssuesPanel.tsx
        │   ├── MemoriesPanel.tsx
        │   └── SeverityBadge.tsx
        └── test/                   # 17 vitest + RTL tests
            ├── setup.ts
            ├── apiStatus.test.tsx
            └── issuesPanel.test.tsx
```

### Running the tests

```bash
cd backend && source .venv/bin/activate && python -m pytest tests/ -q   # 54 tests
cd frontend && npm test                                                  # 17 tests
cd frontend && npm run lint
cd frontend && npm run build
```

Backend tests mock both Hindsight and Groq, so they need no network, no Docker, and no API key.

---

## 18. How PRISM uses Hindsight

**What PRISM retains.** Everything lives in one named bank (`prism-demo-team`):

- **Seed / team knowledge** — coding standards, architecture decisions, previous review findings,
  incident reports.
- **Review feedback records.** On `POST /api/review/feedback`, `ReviewService.store_review_feedback`
  composes a plain-text record containing the code snippet, the review summary, the issue count, each
  per-issue `accepted` / `rejected` decision with its reason, any free-text feedback, and a
  *Related memories* line listing the `memory_reference` values from that review. It is retained with
  `context="Code review feedback"` and metadata `{"source": "review-feedback", "type": "feedback",
  "review_topic", "issues_count", "accepted_count", "rejected_count"}`. That metadata is what lets a
  later review reason about prior decisions rather than just raw text.

**How PRISM recalls memories.** Before any LLM call, `ReviewService.review_code` issues
`POST /api/memory/recall` against the bank. The query is the user's *Specific review focus* if
provided, otherwise an auto-built one (`"code review standards and best practices for: <first 200
chars of code>"`). The request uses `max_tokens=4096` and the `recall_budget` level
(`low` / `mid` / `high`, default `mid`), then truncates to `max_memories` (default **5**). Hindsight
performs the semantic similarity search; PRISM does no filtering of its own beyond the cap.

**How memories reach the review prompt.** `LLMService.generate_review` receives the recalled
`MemoryUsed` list and `_build_review_prompt` renders it as a numbered block above the code:

```
RELEVANT TEAM MEMORIES (from Hindsight):

[1] <memory text> (Context: <context>) [Metadata: <metadata>]
[2] ...

SPECIFIC REVIEW FOCUS: <user query, when provided>
```

The system prompt then instructs the model to *reference specific memories when they apply to issues
you find* and to only flag genuine problems or standard violations. The model is called with
`temperature=0.1`, `max_tokens=2048`, and `response_format={"type": "json_object"}` so the reply
parses into a validated `ReviewResponse`. The same recalled list is attached to the response as
`memories_used` and rendered in the 🧠 panel, so the reviewer can audit the grounding. An issue's
`memory_reference` ties a specific recommendation back to a specific memory.

**How feedback is retained, and recalled later.** Feedback goes to the *same* bank through the same
`retain` path, so it is retrievable by the same semantic recall. The loop closes because recall is
query-driven: submitting similar code — or asking a related question — retrieves the feedback record
alongside the original standards, so the model can apply the decision the team already made instead
of proposing the change again. That is why the demo in section 14 ends by re-reviewing related code
and showing the new memory in the panel.

**Reflection.** `POST /api/memory/reflect` exposes Hindsight's higher-level `reflect` operation, which
synthesizes an answer from the bank and returns `based_on` evidence. It is available via the API for
exploration; the frontend review flow uses `recall` rather than `reflect`.

---

## 19. Note on Hindsight

Hindsight is **core to PRISM, not an optional integration.** Removing it removes the product: the
RETAIN → RECALL → REVIEW → FEEDBACK → RETAIN loop, the Memories Used panel, memory references on
issues, and persistent feedback all depend on it. The backend is designed around the Hindsight client
and configures the bank at startup, and the seed data is a Hindsight bank.

This is why retention reliability is handled explicitly. The backend aligns the bank's
`retain_extraction_mode` to `HINDSIGHT_RETAIN_EXTRACTION_MODE` (`chunks`) on startup so that storing a
memory does not silently depend on the Hindsight server being able to reach its own LLM — recall,
feedback, and the closed loop keep working on a laptop or a fresh clone.

---

## 20. Security

- **Never commit `.env`.** It is gitignored at the repository root and contains your Groq API key.
  Verify with `git status` before committing; a staged `.env` means something went wrong.
- **Never put Groq or Hindsight credentials in source code, tests, fixtures, or the README.** The
  only place a real key belongs is `.env` (for PRISM) and the Hindsight container's
  `HINDSIGHT_API_LLM_API_KEY` environment variable.
- **Use `.env.example` for documentation.** It is the committed, secret-free template. When you add
  a variable, add it there with an empty or placeholder value — never the real one.
- **The seed data is synthetic.** `demo-data/seed_memories.json` contains invented standards and an
  invented PR number; it carries no real customer or production information.
- **The backend binds `0.0.0.0` by default**, which exposes it beyond localhost. That is convenient
  for containers; on a shared or public machine set `API_HOST=127.0.0.1`.
- **`CORS_ORIGINS` is an allowlist.** Do not widen it to `*` — the proxy design means it normally
  does not need to include the frontend origin at all.
- If a key is ever committed or shared, treat it as compromised and rotate it in the Groq console.
