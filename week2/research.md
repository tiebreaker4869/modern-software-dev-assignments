# Week 2 — Research Report: Action Item Extractor

## Overview

Week 2 is a web application called the **Action Item Extractor**. It is a FastAPI + SQLite + vanilla-JS app that extracts actionable tasks from meeting notes or free-form text. It ships with a working heuristic extractor, a full REST API, and a minimal browser UI, with hooks for a future LLM-based extractor via Ollama.

---

## File Structure

```
week2/
├── __init__.py                   ← top-level package marker (empty)
├── assignment.md                 ← assignment instructions
├── writeup.md                    ← student documentation template
├── data/
│   └── app.db                    ← live SQLite database
├── frontend/
│   └── index.html                ← single-file HTML/CSS/JS frontend
├── app/
│   ├── __init__.py
│   ├── main.py                   ← FastAPI app factory + router wiring
│   ├── db.py                     ← raw sqlite3 database layer
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── notes.py              ← POST /notes, GET /notes/{id}
│   │   └── action_items.py       ← POST /extract, GET /action-items, POST /{id}/done
│   └── services/
│       └── extract.py            ← heuristic extractor + ollama placeholder
└── tests/
    ├── __init__.py
    └── test_extract.py           ← single pytest test for heuristic extractor
```

---

## How the System Works End-to-End

### Startup Sequence

```
uvicorn imports week2.app.main
  → init_db() is called at module level (side-effect on import)
      → ensure_data_directory_exists()  ← creates week2/data/ if missing
      → CREATE TABLE IF NOT EXISTS notes (...)
      → CREATE TABLE IF NOT EXISTS action_items (...)
  → FastAPI app object created
  → include_router(notes.router)          ← /notes/* routes
  → include_router(action_items.router)   ← /action-items/* routes
  → app.mount("/static", StaticFiles(...))  ← serves frontend/ directory
```

Start command: `poetry run uvicorn week2.app.main:app --reload`

### Request Lifecycle — Extract Action Items

```
1. User pastes text into <textarea> and clicks "Extract"
2. JS: POST /action-items/extract  { text: "...", save_note: true }

3. Router: action_items.extract()
   a. Validates text is non-empty (HTTP 400 otherwise)
   b. save_note=true → db.insert_note(text) → INSERT INTO notes → note_id
   c. extract_action_items(text) → heuristic parser → ["item1", "item2", ...]
   d. db.insert_action_items(items, note_id) → batch INSERT → [id1, id2, ...]
   e. Returns { note_id: 1, items: [{ id: 1, text: "item1" }, ...] }

4. JS renders each item as a labelled checkbox with data-id attribute

5. User checks a checkbox
6. JS: POST /action-items/1/done  { done: true }
7. Router: mark_done(1) → db.mark_action_item_done(1, True)
   → UPDATE action_items SET done=1 WHERE id=1
```

---

## Component Deep-Dives

### `app/main.py` — FastAPI Entry Point

Calls `init_db()` at module import time (not inside a lifespan event — a simplification that makes isolated testing harder). Serves `frontend/index.html` by reading the file from disk on every `GET /` request. Wires in two routers and mounts `/static` pointing to the same `frontend/` directory, meaning every file in `frontend/` is accessible via both `/` and `/static/<filename>`.

---

### `app/db.py` — Database Layer

All SQLite access in a single flat file using raw `sqlite3`. SQLAlchemy is installed as a project dependency but is not used here.

**Schema:**

`notes`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | |
| content | TEXT NOT NULL | |
| created_at | TEXT | DEFAULT datetime('now') |

`action_items`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | |
| note_id | INTEGER | FK → notes(id), nullable |
| text | TEXT NOT NULL | |
| done | INTEGER | 0=false, 1=true |
| created_at | TEXT | DEFAULT datetime('now') |

**Public functions:**

| Function | Returns | Description |
|---|---|---|
| `ensure_data_directory_exists()` | None | Creates `data/` dir if missing |
| `get_connection()` | `sqlite3.Connection` | Opens DB with `row_factory = sqlite3.Row` |
| `init_db()` | None | CREATE TABLE IF NOT EXISTS both tables |
| `insert_note(content)` | `int` | Inserts note, returns new ID |
| `list_notes()` | `list[Row]` | All notes, newest first |
| `get_note(note_id)` | `Row \| None` | Single note by ID |
| `insert_action_items(items, note_id=None)` | `list[int]` | Batch insert, returns list of IDs |
| `list_action_items(note_id=None)` | `list[Row]` | All items or filtered by note_id |
| `mark_action_item_done(id, done)` | None | UPDATE done flag |

**Connection pattern**: every function opens and closes its own connection via `with get_connection()`. No pooling, no shared session. `sqlite3.Row` as row_factory allows dict-style access (`row["id"]`). `note_id` is nullable — items can be saved without an associated note.

---

### `app/services/extract.py` — Heuristic Extractor

The core logic. Has a placeholder import of `ollama.chat` and calls `load_dotenv()` at import time in anticipation of a future LLM extractor.

**Pattern constants:**
```python
BULLET_PREFIX_PATTERN = re.compile(r"^\s*([-*•]|\d+\.)\s+")
KEYWORD_PREFIXES = ("todo:", "action:", "next:")
```

**`_is_action_line(line: str) -> bool`** — Classifies a single line:
- `False` if blank
- `True` if starts with `-`, `*`, `•`, or a numbered item (`1.`, `2.`, ...)
- `True` if starts with keyword prefix (`todo:`, `action:`, `next:`)
- `True` if contains `[ ]` or `[todo]` (markdown unchecked checkbox)

**`extract_action_items(text: str) -> List[str]`** — Main extractor:
1. Splits text into lines, skips blanks
2. For each line where `_is_action_line()` is True: strips bullet prefix, strips `[ ]` / `[todo]`, appends cleaned text
3. **Fallback**: if zero lines matched, splits text by `.!?` into sentences and applies `_looks_imperative()` to each
4. **Deduplication**: case-insensitive comparison; first occurrence wins; original casing preserved in output

**`_looks_imperative(sentence: str) -> bool`** — Sentence-level fallback heuristic. Returns True if the first word is one of:
`add, create, implement, fix, update, write, check, verify, refactor, document, design, investigate`

**Edge cases:**
- Unicode bullet `•` is explicitly handled
- Numbered lists (`1.`, `2.`) matched by `\d+\.`
- The sentence fallback only fires when the **entire** text has zero recognized action lines — not partially
- `[todo]` recognized alongside `[ ]`

---

### `app/routers/notes.py` — Notes Endpoints

Router prefix: `/notes`

| Method | Path | Description |
|---|---|---|
| POST | `/notes` | Creates a note from `{content}` JSON body |
| GET | `/notes/{note_id}` | Returns a single note by ID (HTTP 404 if missing) |

Request bodies are typed as `Dict[str, Any]` with manual field extraction — FastAPI's Pydantic validation is not used here.

---

### `app/routers/action_items.py` — Action Items Endpoints

Router prefix: `/action-items`

| Method | Path | Description |
|---|---|---|
| POST | `/action-items/extract` | Extracts items from text; optionally saves note |
| GET | `/action-items` | Lists all items; accepts `?note_id=` query param |
| POST | `/action-items/{id}/done` | Marks an item done or undone |

The `extract` endpoint performs the full pipeline: validate → optionally save note → extract → insert items → return. The `mark_done` endpoint defaults `done` to `True` if not supplied in the payload.

---

### `frontend/index.html` — Vanilla JS Frontend

A single-file, no-build-step frontend. No framework, no TypeScript, no bundler.

**UI elements:**
- `<textarea id="text">` for note input
- `<input type="checkbox" id="save_note" checked>` — toggles note persistence
- **"Extract" button** — calls `POST /action-items/extract`
- `<div id="items">` — dynamically populated with checkboxes per item

**JS behavior:**
1. On "Extract": POSTs `{ text, save_note }` → renders each returned item as a labelled checkbox with `data-id`; shows "No action items found." on empty result; shows "Error extracting items" on failure
2. On checkbox change: POSTs `{ done: true/false }` to `/action-items/{id}/done`

---

### `tests/test_extract.py` — Test Suite

One pytest test covering the three main bullet patterns:

```python
def test_extract_bullets_and_checkboxes():
    text = """
    Notes from meeting:
    - [ ] Set up database
    * implement API extract endpoint
    1. Write tests
    Some narrative sentence.
    """.strip()

    items = extract_action_items(text)
    assert "Set up database" in items
    assert "implement API extract endpoint" in items
    assert "Write tests" in items
```

Tests: `- [ ] ...` checkbox bullet, `* ...` asterisk bullet, `1. ...` numbered list item. Does not test keyword prefixes, fallback imperative detection, empty input, or deduplication.

Run with: `poetry run pytest week2/tests/`

---

## Architecture & Design Decisions

| Decision | Detail |
|---|---|
| **DB init as side-effect** | `init_db()` at module top-level — simpler but couples app startup to module import, making unit testing harder |
| **Raw sqlite3** | No ORM despite SQLAlchemy being installed; each function opens its own connection |
| **No Pydantic request models** | All endpoints use `Dict[str, Any]` with manual field extraction |
| **`ollama` import without implementation** | `from ollama import chat` in `extract.py` is a scaffolding placeholder; `load_dotenv()` anticipates env vars like `OLLAMA_HOST` |
| **`note_id` nullable** | Action items can be saved without persisting the source note |
| **Deduplication preserves casing** | Lowercase for comparison, original string stored; first occurrence wins |
| **Frontend served from disk** | `open(file).read()` on every `GET /` request — simple, no templating overhead |
| **`done` as INTEGER** | SQLite has no native boolean; 0/1 used |
| **No auth, no CORS** | Local development tool only |

---

## Configuration & Environment

| Item | Detail |
|---|---|
| Conda env | `cs146s` |
| Package manager | Poetry |
| Python | 3.12 |
| DB path | `week2/data/app.db` (auto-created on first run) |
| `.env` file | Not present; `load_dotenv()` is called — anticipated for `OLLAMA_HOST` |
| Server start | `poetry run uvicorn week2.app.main:app --reload` |
| App URL | http://127.0.0.1:8000/ |
| Tests | `poetry run pytest week2/tests/` |

**Runtime dependencies active in week2:**

| Package | Usage |
|---|---|
| `fastapi` | Web framework |
| `uvicorn[standard]` | ASGI server |
| `python-dotenv` | `.env` loading in `extract.py` |
| `ollama ^0.5.3` | LLM client (imported, not yet invoked) |
| `sqlite3` | DB (stdlib) |
| `sqlalchemy` | Installed but unused |
| `pydantic` | Installed but unused |
| `openai` | Installed but unused |

---

## Live Database State (`data/app.db`)

The database contains real data from a test session on 2026-02-23:

**1 note** (id=1): A Chinese-language Q1 product iteration meeting summary mentioning a 42% onboarding completion rate, with tasks assigned to Alice, Bob, and Carol.

**5 action items** linked to note id=1:

| ID | Text | Status |
|---|---|---|
| 1 | Alice — compile user research data by Feb 28 | done |
| 2 | Bob — complete performance analysis report | done |
| 3 | Carol — design two onboarding variants | done |
| 4 | Bob + Carol — create A/B test experiment plan by March 5 | pending |
| 5 | All members — update OKR progress in Feishu | pending |

These were extracted from the note's `## Action Items` section formatted as `- [ ] **Name** — task`, confirming the heuristic extractor correctly handles markdown bullet+checkbox lines.
