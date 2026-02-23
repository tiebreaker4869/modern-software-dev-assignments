# Action Item Extractor

A FastAPI + SQLite web application that extracts action items from meeting notes or freeform text. Supports two extraction strategies: a fast regex/heuristic approach and an LLM-backed approach via Ollama.

## Overview

- **Backend**: FastAPI with SQLite storage. Notes and action items are persisted across restarts.
- **Frontend**: Single-page HTML/JS UI served directly by FastAPI.
- **Extraction strategies**:
  - **Heuristic** (`POST /action-items/extract`): regex-based, matches bullet lists, checkbox markers (`- [ ]`), and keyword prefixes (`TODO:`, `Action:`, `Next:`). No external dependencies.
  - **LLM** (`POST /action-items/extract-llm`): sends the text to a local [Ollama](https://ollama.com) instance. Uses constrained JSON decoding so the model is forced to return a valid `{"items": [...]}` object regardless of phrasing.

---

## Setup

### Prerequisites

- Python 3.10+
- [Poetry](https://python-poetry.org/docs/#installation)
- [Ollama](https://ollama.com) (only required for the `/extract-llm` endpoint)

### Install dependencies

From the **repository root** (not the `week2/` folder):

```bash
poetry install
```

### Configure environment

Copy or create `week2/.env`:

```bash
# week2/.env
OLLAMA_MODEL=llama3.1:8b          # Ollama model to use (default)
# OLLAMA_HOST=http://localhost:11434  # Override if Ollama runs on a different host
# DATABASE_URL=/path/to/custom.db     # Override default SQLite path (week2/data/app.db)
```

The `.env` file is loaded automatically at startup. All variables are optional.

### Pull the Ollama model (LLM endpoint only)

```bash
ollama pull llama3.1:8b
```

---

## Running the App

From the **repository root**:

```bash
poetry run uvicorn week2.app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser. The interactive API docs are at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## API Endpoints

All endpoints accept and return JSON.

### Notes

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/notes` | Create and persist a new note |
| `GET` | `/notes` | List all notes (newest first) |
| `GET` | `/notes/{note_id}` | Retrieve a single note by ID |

**`POST /notes`** request body:
```json
{ "content": "Meeting notes text here" }
```

**`POST /notes`** response (`201 Created`):
```json
{ "id": 1, "content": "Meeting notes text here", "created_at": "2026-02-23 10:00:00" }
```

---

### Action Items

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/action-items/extract` | Extract action items using the heuristic extractor |
| `POST` | `/action-items/extract-llm` | Extract action items using the Ollama LLM |
| `GET` | `/action-items` | List all action items (optionally filtered by `?note_id=`) |
| `POST` | `/action-items/{id}/done` | Mark an action item as done or undone |

**`POST /action-items/extract`** and **`POST /action-items/extract-llm`** share the same request/response shape:

Request body:
```json
{
  "text": "- [ ] Alice — send the report\n- [ ] Bob — schedule follow-up",
  "save_note": true
}
```

Response (`200 OK`):
```json
{
  "note_id": 3,
  "items": [
    { "id": 7, "text": "Alice — send the report" },
    { "id": 8, "text": "Bob — schedule follow-up" }
  ]
}
```

- `save_note: false` (default) extracts items without persisting the input text.
- `save_note: true` saves the input as a note first; the returned `note_id` links items to that note.
- The LLM endpoint returns `502 Bad Gateway` if Ollama is unreachable or returns malformed output.

**`POST /action-items/{id}/done`** request body:
```json
{ "done": true }
```

Response (`200 OK`):
```json
{ "id": 7, "done": true }
```

Returns `404` if the action item ID does not exist.

---

## Running the Tests

From the **repository root**:

```bash
poetry run pytest week2/tests/ -v
```

### Test files

| File | What it tests |
|------|---------------|
| `tests/test_extract.py` | Heuristic extractor — bullet lists, checkbox markers, numbered items |
| `tests/test_extract_llm.py` | LLM extractor — happy path, empty response, deduplication, malformed JSON |

The LLM tests mock `ollama.chat` with `unittest.mock.patch` and run fully offline — no Ollama instance is needed.

To run only one file:

```bash
poetry run pytest week2/tests/test_extract_llm.py -v
```
