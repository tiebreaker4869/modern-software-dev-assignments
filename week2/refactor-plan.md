# Backend Refactor Plan

## Overview

This document describes a structured refactor of the `week2/app/` backend across four areas:

1. **Pydantic schemas** — replace all `Dict[str, Any]` request/response types with typed models
2. **Database layer cleanup** — fix connection lifecycle, enable FK constraints, make DB path configurable
3. **App lifecycle & configuration** — move side-effects out of module scope, centralize config
4. **Error handling** — catch Ollama connection errors, fix silent 404s, fix orphaned-note atomicity

---

## Issues Found

### A. No Pydantic request/response models

All 5 endpoints accept raw `Dict[str, Any]` and return `Dict[str, Any]`. This means:
- FastAPI cannot validate request fields (wrong types, missing required fields accepted silently)
- OpenAPI docs show a generic `object` schema instead of typed fields
- No length/type constraints are enforced at the boundary

Affected files:
- `routers/notes.py` line 14 (`create_note`), line 27 (`get_single_note`)
- `routers/action_items.py` lines 15, 29, 46, 60

### B. Database connection lifecycle

`get_connection()` opens a new `sqlite3.Connection` on every call but never closes it.
The `with conn:` pattern on a `sqlite3.Connection` only manages transactions (commit/rollback) — it does **not** close the connection. Every DB call leaks a connection handle.

```python
# Current — connection opened, never closed
def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def insert_note(content: str) -> int:
    with get_connection() as connection:   # ← only commits, never closes
        ...
```

### C. Side-effect module-level calls

- `main.py` line 14: `init_db()` called at module import time. Importing the module during tests runs DB setup as a side-effect.
- `services/extract.py` line 10: `load_dotenv()` called on every import of the service module, polluting the environment for any test that imports it.

### D. Hardcoded configuration

- `db.py`: `DB_PATH` derived from `__file__`, no env override — impossible to use an in-memory DB for tests
- `main.py`: the string `"frontend"` appears in two separate places
- `services/extract.py`: default model `"llama3.1:8b"` baked into source code

### E. Missing / incomplete error handling

| Location | Issue |
|---|---|
| `services/extract.py:142` | `chat()` not in try/except; Ollama `ConnectionError`/`ResponseError` propagates as unhandled 500 |
| `routers/action_items.py:62` | `mark_done` — no 404 if action item doesn't exist; silently returns success |
| `routers/action_items.py:35-40` | Note inserted before LLM call; if LLM fails, orphaned note remains in DB |
| `routers/action_items.py:21-25` | Same atomicity bug on the heuristic path |
| `db.py:107-114` | `mark_action_item_done` never checks `rowcount` |
| `db.py:44` | `PRAGMA foreign_keys = ON` never issued; FK constraints silently unenforced |

### F. Unused imports / dead code

- `main.py`: `Any`, `Dict`, `Optional`, `HTTPException`, `from . import db` — all unused
- `routers/notes.py`: `List` unused
- `services/extract.py`: `Any` unused
- `db.list_notes()` defined but no router endpoint exposes it (dead DB surface)

---

## Refactor Changes

### 1. New file: `app/schemas.py`

Create a single file with all Pydantic request and response models. This gives the entire API a single source of truth for its contracts.

```python
# app/schemas.py
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ── Notes ────────────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    content: str = Field(..., min_length=1, description="Note text content")


class NoteResponse(BaseModel):
    id: int
    content: str
    created_at: str


# ── Action Items ──────────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to extract action items from")
    save_note: bool = Field(False, description="Whether to persist the input text as a note")


class ActionItemOut(BaseModel):
    id: int
    text: str


class ExtractResponse(BaseModel):
    note_id: Optional[int]
    items: list[ActionItemOut]


class ActionItemResponse(BaseModel):
    id: int
    note_id: Optional[int]
    text: str
    done: bool
    created_at: str


class MarkDoneRequest(BaseModel):
    done: bool = True


class MarkDoneResponse(BaseModel):
    id: int
    done: bool
```

**Why**: FastAPI uses the Pydantic model to auto-validate request payloads (422 on type mismatch or missing required field), generate accurate OpenAPI docs, and serialise responses consistently.

---

### 2. `app/db.py` — Connection lifecycle, FK enforcement, configurable path

**Connection fix** — replace `get_connection()` with a `get_db()` context manager that commits, then closes:

```python
# Before
def get_connection() -> sqlite3.Connection:
    ensure_data_directory_exists()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def insert_note(content: str) -> int:
    with get_connection() as connection:   # leaks — never closed
        cursor = connection.execute(...)
        return int(cursor.lastrowid)

# After
from contextlib import contextmanager

@contextmanager
def get_db():
    ensure_data_directory_exists()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()           # ← always closes

def insert_note(content: str) -> int:
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO notes (content) VALUES (?)", (content,))
        row_id = cursor.lastrowid
        if row_id is None:
            raise RuntimeError("Insert did not return a row ID")
        return int(row_id)
```

**Configurable DB path** — read from environment so tests can use `:memory:`:

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
_default_db = str(BASE_DIR / "data" / "app.db")
DB_PATH = os.getenv("DATABASE_URL", _default_db)
```

**Fix `mark_action_item_done`** — return whether the row existed:

```python
# Before — silent no-op for missing IDs
def mark_action_item_done(action_item_id: int, done: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE action_items SET done=? WHERE id=?", (int(done), action_item_id))

# After — returns False if row not found
def mark_action_item_done(action_item_id: int, done: bool) -> bool:
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE action_items SET done=? WHERE id=?", (int(done), action_item_id)
        )
        return cursor.rowcount > 0
```

**Add `get_action_item()`** — needed for the 404 check in the router:

```python
def get_action_item(action_item_id: int) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM action_items WHERE id=?", (action_item_id,))
        return cursor.fetchone()
```

---

### 3. `app/main.py` — App lifecycle & config

Move `init_db()` into a FastAPI lifespan handler so it only runs when the server actually starts (not on test imports). Move `load_dotenv()` here as the single application entry point.

```python
# Before
from .db import init_db
from . import db          # unused
from fastapi import FastAPI, HTTPException  # HTTPException unused
from typing import Any, Dict, Optional     # all unused

init_db()   # ← runs at import time

app = FastAPI(title="Action Item Extractor")

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html_path = Path(__file__).resolve().parents[1] / "frontend" / "index.html"  # "frontend" ×2
    return html_path.read_text(encoding="utf-8")

static_dir = Path(__file__).resolve().parents[1] / "frontend"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# After
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from .db import init_db

load_dotenv()   # ← single call, at the application entry point

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"  # defined once

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()   # ← only runs when the server starts
    yield

app = FastAPI(title="Action Item Extractor", lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
```

---

### 4. `app/services/extract.py` — Ollama error handling

The `chat()` call can raise `ollama.ResponseError`, `httpx.ConnectError`, or `ConnectionRefusedError` when Ollama is not running. These are **not** `RuntimeError`, so the router's `except RuntimeError` clause does not catch them — they propagate as unhandled 500s. Wrap them:

```python
# Before — only JSON errors caught, connection errors propagate as 500
response = chat(model=model, messages=[...], format={...})

# After — all upstream failures become RuntimeError → caught by router → 502
try:
    response = chat(model=model, messages=[...], format={...})
except Exception as exc:
    raise RuntimeError(f"Ollama request failed: {exc}") from exc
```

Also:
- Remove `load_dotenv()` (moved to `main.py`)
- Remove unused `Any` import
- Validate that `items` list contains only strings:

```python
# Before
items: List[str] = parsed.get("items", [])

# After
raw_items = parsed.get("items", [])
items: List[str] = [str(i) for i in raw_items if isinstance(i, str)]
```

---

### 5. `app/routers/notes.py` — Pydantic models + `GET /notes`

```python
# Before
@router.post("")
def create_note(payload: Dict[str, Any]) -> Dict[str, Any]:
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    ...

# After
from ..schemas import NoteCreate, NoteResponse

@router.post("", response_model=NoteResponse, status_code=201)
def create_note(body: NoteCreate) -> NoteResponse:
    note_id = db.insert_note(body.content.strip())
    note = db.get_note(note_id)
    return NoteResponse(**dict(note))


# Add missing GET /notes endpoint
@router.get("", response_model=list[NoteResponse])
def list_notes() -> list[NoteResponse]:
    rows = db.list_notes()
    return [NoteResponse(**dict(r)) for r in rows]


@router.get("/{note_id}", response_model=NoteResponse)
def get_single_note(note_id: int) -> NoteResponse:
    row = db.get_note(note_id)
    if row is None:
        raise HTTPException(status_code=404, detail="note not found")
    return NoteResponse(**dict(row))
```

---

### 6. `app/routers/action_items.py` — Pydantic models, atomicity fix, 404

**Pydantic models** replace all Dict parameters.

**Atomicity fix** — move note insertion to after extraction succeeds, so a failed LLM call does not orphan a note:

```python
# Before — note saved before LLM call; orphaned on failure
if payload.get("save_note"):
    note_id = db.insert_note(text)      # ← committed here
try:
    items = extract_action_items_llm(text)
except RuntimeError as exc:
    raise HTTPException(status_code=502, detail=str(exc))
    # ↑ note is now orphaned in the DB

# After — note saved only after successful extraction
try:
    items = extract_action_items_llm(text)
except RuntimeError as exc:
    raise HTTPException(status_code=502, detail=str(exc))

note_id: Optional[int] = None
if body.save_note:
    note_id = db.insert_note(body.text)     # ← only runs if extraction succeeded
```

**404 for `mark_done`**:

```python
# Before — silently succeeds for non-existent IDs
def mark_done(action_item_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    done = bool(payload.get("done", True))
    db.mark_action_item_done(action_item_id, done)
    return {"id": action_item_id, "done": done}

# After — returns 404 if item not found
from ..schemas import MarkDoneRequest, MarkDoneResponse

@router.post("/{action_item_id}/done", response_model=MarkDoneResponse)
def mark_done(action_item_id: int, body: MarkDoneRequest) -> MarkDoneResponse:
    found = db.mark_action_item_done(action_item_id, body.done)
    if not found:
        raise HTTPException(status_code=404, detail="action item not found")
    return MarkDoneResponse(id=action_item_id, done=body.done)
```

---

## Files Changed Summary

```
week2/
├── app/
│   ├── schemas.py                ← NEW: all Pydantic request/response models
│   ├── main.py                   ← EDIT: lifespan handler, load_dotenv, FRONTEND_DIR, remove dead imports
│   ├── db.py                     ← EDIT: get_db() contextmanager, FK pragma, configurable DB_PATH,
│   │                                      fix mark_action_item_done, add get_action_item()
│   ├── services/
│   │   └── extract.py            ← EDIT: wrap chat() errors, remove load_dotenv, remove Any import,
│   │                                      validate items list type
│   └── routers/
│       ├── notes.py              ← EDIT: Pydantic models, add GET /notes, remove dead List import
│       └── action_items.py       ← EDIT: Pydantic models, fix atomicity, add 404 to mark_done
```

---

## Verification

After implementing:

```bash
# All existing tests still pass
poetry run pytest week2/tests/ -v

# Server starts cleanly with lifespan handler
poetry run uvicorn week2.app.main:app --reload

# OpenAPI docs show typed schemas (not generic objects)
open http://127.0.0.1:8000/docs

# Confirm 422 on bad input (was silently accepted before)
curl -s -X POST http://localhost:8000/notes \
  -H "Content-Type: application/json" \
  -d '{}' | jq .   # → {"detail": [{"msg": "Field required", "loc": ["body", "content"]}]}

# Confirm 404 for unknown action item (was silently returning 200 before)
curl -s -X POST http://localhost:8000/action-items/9999/done \
  -H "Content-Type: application/json" \
  -d '{"done": true}' | jq .   # → {"detail": "action item not found"}
```
