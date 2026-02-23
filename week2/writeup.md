# Week 2 Write-up
Tip: To preview this markdown file
- On Mac, press `Command (⌘) + Shift + V`
- On Windows/Linux, press `Ctrl + Shift + V`

## INSTRUCTIONS

Fill out all of the `TODO`s in this file.

## SUBMISSION DETAILS

Name: **TODO** \
SUNet ID: **TODO** \
Citations: **TODO**

This assignment took me about **TODO** hours to do. 


## YOUR RESPONSES
For each exercise, please include what prompts you used to generate the answer, in addition to the location of the generated response. Make sure to clearly add comments in your code documenting which parts are generated.

### Exercise 1: Scaffold a New Feature

The goal was to implement `extract_action_items_llm()` — an LLM-backed extractor using Ollama that understands natural language, as opposed to the existing heuristic approach which only matches bullet prefixes and keyword patterns.

Key design decisions:
- Used `ollama.chat()` with a JSON schema passed via the `format` parameter. This forces **constrained decoding** at the model's token-sampling level, making malformed JSON structurally impossible — more reliable than prompting alone.
- The system prompt defines "action item" explicitly (concrete tasks only, not observations or decisions) to reduce false positives.
- Added a one-shot `<input>/<output>` example in the prompt alongside the `format` schema to anchor the expected output shape.
- `OLLAMA_MODEL` defaults to `llama3.1:8b` but is overridable via `.env` so the model can be swapped without code changes.
- Errors (Ollama unreachable, malformed JSON) are raised as `RuntimeError` from the service function, letting the router decide the HTTP status code.

Prompt:
```
I want to build a feature that leverage llm with ollama to extract action items
to substitute the current heuristic based extraction. Write a detailed plan.md
document outlining how to implement this. include code snippets.
```

Generated Code Snippets:
```
app/services/extract.py
  Line 92:        OLLAMA_MODEL constant (reads OLLAMA_MODEL env var, defaults to llama3.1:8b)
  Lines 94–133:   LLM_SYSTEM_PROMPT — extraction rules + one-shot <input>/<output> example
  Lines 136–177:  extract_action_items_llm() — ollama.chat() with JSON schema format,
                  json.loads() parsing, RuntimeError on failure, case-insensitive dedup
```

### Exercise 2: Add Unit Tests

Tests use `unittest.mock.patch` to mock `ollama.chat`, so they run without a live Ollama instance and are fully deterministic. The `SAMPLE_NOTE` fixture is a realistic meeting note (markdown headers, prose summary, `- [ ] Name — task` bullets) rather than trivial one-liners, testing against real-world input shapes.

Four cases covered:
1. **Happy path** — all 5 items from `SAMPLE_NOTE` appear in output
2. **No tasks** — LLM returns `{"items": []}`, function returns `[]`
3. **Deduplication** — 3 case variants of the same string collapse to 1
4. **Malformed JSON** — non-JSON response raises `RuntimeError` matching `"non-JSON"`

Prompt:
```
implement it all. when you're done with a task or phase, mark it as completed
in the plan document. do not stop until all tasks and phases are completed.
```

Generated Code Snippets:
```
week2/tests/test_extract_llm.py  (new file)
  Lines 1–5:   imports (MagicMock, patch, pytest, extract_action_items_llm)
  Lines 8–26:  SAMPLE_NOTE fixture — realistic kickoff meeting note
  Lines 28–34: SAMPLE_NOTE_ITEMS — 5 expected extracted strings
  Lines 37–40: _mock_response() helper — MagicMock with .message.content attribute
  Lines 43–51: test_llm_extracts_from_meeting_note()
  Lines 54–58: test_llm_returns_empty_for_no_tasks()
  Lines 61–67: test_llm_deduplicates_items()
  Lines 70–74: test_llm_raises_on_malformed_json()
```

### Exercise 3: Refactor Existing Code for Clarity

Two separate refactors were performed: a frontend JS cleanup (done as part of Exercise 4 implementation) and a full backend refactor targeting API contracts, DB layer, app lifecycle, and error handling.

#### Part A: Frontend refactor (`index.html`)

The original `index.html` had all fetch logic and item-rendering inlined inside a single click handler. Adding a second button would have required duplicating all of it. Refactored into two shared helpers so both buttons share the same code path.

Changes made:
- Extracted `runExtract(endpoint)` — handles fetch, error surfacing, and calls `renderItems`
- Extracted `renderItems(items)` — handles DOM rendering and checkbox event binding
- Both buttons call `runExtract()` with a different endpoint string; everything else is shared
- Error display now shows the server's `detail` field (e.g. `"LLM returned non-JSON output"`) instead of the generic `"Error extracting items"`

Prompt:
```
implement it all. when you're done with a task or phase, mark it as completed
in the plan document. do not stop until all tasks and phases are completed.
```

Generated/Modified Code Snippets:
```
week2/frontend/index.html
  Line 27:      <button id="extract-llm">Extract with LLM</button> added
  Lines 36–56:  runExtract(endpoint) — shared async fetch + error handler
  Lines 58–76:  renderItems(items) — shared DOM renderer + checkbox wiring
  Lines 78–79:  event listeners: #extract → /extract, #extract-llm → /extract-llm
```

#### Part B: Backend refactor

Four categories of issues found and fixed: no Pydantic schemas (all endpoints used `Dict[str, Any]`), connection leaks in the DB layer (`get_connection()` never closed), side-effects at module import time (`init_db()` and `load_dotenv()` ran on every test import), and incomplete error handling (silent 200 for missing action items, orphaned notes on LLM failure, Ollama connection errors propagating as unhandled 500s).

Changes made:
- Created `app/schemas.py` with 8 typed Pydantic request/response models; all endpoints now validate input and serialize output via these models
- Replaced `get_connection()` with a `get_db()` context manager that commits and always closes in `finally`; added `PRAGMA foreign_keys = ON` on every connection; made `DB_PATH` configurable via `DATABASE_URL` env var
- Moved `init_db()` into a FastAPI `lifespan` handler and centralized `load_dotenv()` in `main.py`; removed all dead imports
- Wrapped `ollama.chat()` in broad `try/except Exception → RuntimeError` so connection errors are caught by the router's `except RuntimeError → 502`; moved note insertion to after extraction succeeds to prevent orphaned DB rows
- Added 404 response to `mark_done` via `cursor.rowcount` check in `mark_action_item_done()`; added missing `GET /notes` endpoint exposing `db.list_notes()`

Prompts:
```
Perform a refactor of the code in the backend, focusing in particular on
well-defined API contracts/schemas, database layer cleanup, app
lifecycle/configuration, error handling. give a refactor-plan.md first
```
```
implement them all without stop
```

Generated/Modified Code Snippets:
```
week2/app/schemas.py  (new file)
  Lines 1–51:   NoteCreate, NoteResponse, ExtractRequest, ActionItemOut,
                ExtractResponse, ActionItemResponse, MarkDoneRequest, MarkDoneResponse

week2/app/db.py
  Lines 10–12:  DB_PATH reads from DATABASE_URL env var
  Lines 15–34:  get_db() contextmanager — commit/rollback/close + FK pragma
  Lines 99–105: get_action_item() — new helper for 404 check
  Lines 123–130: mark_action_item_done() — returns bool via cursor.rowcount

week2/app/main.py
  Line 14:      load_dotenv() — single call at app entry point
  Line 16:      FRONTEND_DIR constant defined once
  Lines 19–22:  lifespan handler — init_db() runs only at server start

week2/app/services/extract.py
  Lines 139–158: chat() wrapped in try/except Exception → RuntimeError

week2/app/routers/notes.py
  Lines 12–16:  create_note — NoteCreate/NoteResponse, status_code=201
  Lines 19–22:  list_notes — new GET /notes endpoint
  Lines 25–30:  get_single_note — NoteResponse, explicit 404

week2/app/routers/action_items.py
  Lines 8–15:   imports updated to use schemas
  Lines 22–34:  extract — ExtractRequest/ExtractResponse; note saved after extraction
  Lines 37–53:  extract_llm — same atomicity fix
  Lines 56–68:  list_all — ActionItemResponse typed return
  Lines 71–76:  mark_done — MarkDoneRequest/MarkDoneResponse, 404 on missing ID
```


### Exercise 4: Use Agentic Mode to Automate a Small Task

Added `POST /action-items/extract-llm` — intentionally identical in interface to the existing `POST /action-items/extract` (same request/response shape) so the frontend can call both uniformly. The only behavioral difference: it calls `extract_action_items_llm()` and wraps it in `try/except RuntimeError` → HTTP 502, which correctly signals an upstream dependency failure.

The full implementation (service function, endpoint, frontend, tests, `.env`, phased todo tracking in `plan.md`) was completed end-to-end through a single agentic prompt.

Prompt:
```
implement it all. when you're done with a task or phase, mark it as completed
in the plan document. do not stop until all tasks and phases are completed.
```

Generated Code Snippets:
```
week2/app/routers/action_items.py
  Line 8:       import updated to include extract_action_items_llm
  Lines 29–45:  POST /action-items/extract-llm handler (extract_llm)
                — validates text (400), optionally saves note, calls LLM extractor,
                  catches RuntimeError → 502, inserts items, returns {note_id, items}

week2/.env  (new file)
  Line 1:  OLLAMA_MODEL=llama3.1:8b
```


### Exercise 5: Generate a README from the Codebase

Generated a `README.md` from the live codebase state after all prior exercises were complete, so it accurately reflects the refactored backend, the two extraction endpoints, and the full test suite.

Sections included:
- **Overview** — project purpose and the two extraction strategies (heuristic vs. LLM)
- **Setup** — prerequisites, `poetry install`, `.env` configuration, Ollama model pull
- **Running** — `uvicorn` command, links to UI and `/docs`
- **API reference** — all 7 endpoints in tables with example request/response JSON, error codes (502, 404, 422)
- **Tests** — `pytest` command, what each test file covers, note that LLM tests run offline

Prompt:
```
now generate a README.md for week2 folder. the file should at a minimum have:
- a brief overview of the project
- how to setup and run
- api endpoint and functionality
- instructions for running the test suite
```

Generated Code Snippets:
```
week2/README.md  (new file)
  Lines 1–3:    Title and one-sentence project description
  Lines 5–14:   Overview section — heuristic vs. LLM extraction strategies
  Lines 18–46:  Setup section — prerequisites, poetry install, .env config, ollama pull
  Lines 50–53:  Running section — uvicorn command and docs URL
  Lines 57–109: API Endpoints section — Notes table, Action Items table, request/response examples
  Lines 113–129: Running the Tests section — pytest command, test file descriptions, offline note
```


## SUBMISSION INSTRUCTIONS
1. Hit a `Command (⌘) + F` (or `Ctrl + F`) to find any remaining `TODO`s in this file. If no results are found, congratulations – you've completed all required fields. 
2. Make sure you have all changes pushed to your remote repository for grading.
3. Submit via Gradescope. 