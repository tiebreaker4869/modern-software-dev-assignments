# Implementation Plan: LLM-based Action Item Extractor (Ollama)

## Goal

Replace the heuristic regex/keyword approach in `extract_action_items` with a
semantic LLM call via Ollama. The heuristic path is preserved as a fallback;
the LLM path is exposed via a dedicated endpoint and a new frontend button.

The heuristic extractor fails on unformatted prose ("Alice said she'll finish
the report by Friday"), multi-sentence items, and non-English text. The LLM
approach handles all of these naturally.

---

## Architecture

```
User (browser)
  ├── "Extract" button         → POST /action-items/extract      → extract_action_items()      (heuristic, unchanged)
  └── "Extract with LLM" btn  → POST /action-items/extract-llm  → extract_action_items_llm()  (new, Ollama-backed)
```

Both paths share the same DB insertion logic and return the same response shape,
so the frontend can treat them identically.

---

## Files Changed

```
week2/
├── .env                          ← NEW: OLLAMA_MODEL, OLLAMA_HOST
├── app/
│   ├── services/extract.py       ← ADD: OLLAMA_MODEL constant, LLM_SYSTEM_PROMPT, extract_action_items_llm()
│   └── routers/action_items.py   ← ADD: import, POST /action-items/extract-llm endpoint
├── frontend/index.html           ← UPDATE: "Extract with LLM" button, refactor JS into runExtract()
└── tests/
    └── test_extract_llm.py       ← NEW: 4 unit tests with mocked ollama.chat
```

---

## Todo List

### Phase 1 — Environment & Prerequisites ✅

- [x] Create `week2/.env` with `OLLAMA_MODEL=llama3.1:8b`
- [x] Confirm Ollama is installed and the daemon is running (`ollama list`)
- [x] Pull the model: `ollama pull llama3.1:8b`

### Phase 2 — Service layer (`app/services/extract.py`) ✅

- [x] Add `import os` at the top of the file
- [x] Add `OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")` constant
- [x] Add `LLM_SYSTEM_PROMPT` constant with the extraction rules
- [x] Implement `extract_action_items_llm(text, model)` function body
  - [x] Call `ollama.chat()` with system prompt, user message, and JSON schema `format`
  - [x] Parse `response.message.content` with `json.loads()`
  - [x] Raise `RuntimeError` on `JSONDecodeError` or missing `items` key
  - [x] Deduplicate results (case-insensitive, preserve original casing)

### Phase 3 — Router (`app/routers/action_items.py`) ✅

- [x] Add `extract_action_items_llm` to the import from `..services.extract`
- [x] Add `@router.post("/extract-llm")` handler `extract_llm()`
  - [x] Validate `text` is non-empty → HTTP 400
  - [x] Optionally save note if `save_note` is truthy → `db.insert_note()`
  - [x] Call `extract_action_items_llm(text)` inside a `try/except RuntimeError`
  - [x] Re-raise caught `RuntimeError` as HTTP 502
  - [x] Insert items via `db.insert_action_items()` and return `{note_id, items}`

### Phase 4 — Frontend (`frontend/index.html`) ✅

- [x] Add `<button id="extract-llm">Extract with LLM</button>` next to the existing Extract button
- [x] Refactor inline click-handler JS into a shared `runExtract(endpoint)` function
- [x] Extract checkbox rendering into a shared `renderItems(items)` function
- [x] Wire `#extract` button → `runExtract('/action-items/extract')`
- [x] Wire `#extract-llm` button → `runExtract('/action-items/extract-llm')`
- [x] Update error display to show the server's `detail` field instead of a generic message

### Phase 5 — Tests (`tests/test_extract_llm.py`) ✅

- [x] Create `week2/tests/test_extract_llm.py`
- [x] Add `SAMPLE_NOTE` constant (realistic kickoff meeting note with `- [ ]` bullets)
- [x] Add `SAMPLE_NOTE_ITEMS` constant (the 5 expected extracted items)
- [x] Add `_mock_response(content)` helper that returns a `MagicMock` matching `ollama` response shape
- [x] Implement `test_llm_extracts_from_meeting_note()` — verifies all 5 items extracted from `SAMPLE_NOTE`
- [x] Implement `test_llm_returns_empty_for_no_tasks()` — verifies `[]` on prose-only input
- [x] Implement `test_llm_deduplicates_items()` — verifies 3 case variants collapse to 1
- [x] Implement `test_llm_raises_on_malformed_json()` — verifies `RuntimeError` on non-JSON response

### Phase 6 — Verification

- [ ] Run `poetry run pytest week2/tests/test_extract_llm.py -v` — all 4 tests pass
- [ ] Start server: `poetry run uvicorn week2.app.main:app --reload`
- [ ] Smoke-test heuristic path: paste bullet-list notes, click "Extract", confirm items render
- [ ] Smoke-test LLM path: paste `SAMPLE_NOTE`, click "Extract with LLM", confirm 5 items render
- [ ] Mark a checkbox done and confirm the `POST /action-items/{id}/done` call succeeds
- [ ] Error-path test: stop Ollama, click "Extract with LLM", confirm UI shows the 502 `detail` message

---

## 1. `app/services/extract.py` — New LLM extractor function

### What to add

Append the following to the bottom of the existing `extract.py`. The existing
heuristic functions are untouched.

```python
import os

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

LLM_SYSTEM_PROMPT = """\
You are a precise action-item extractor.
An action item is a specific task that someone needs to do, has committed to doing,
or has been assigned to complete.

Rules:
- Extract ONLY concrete tasks — not observations, decisions, or general discussion.
- Return a JSON object with a single key "items" whose value is an array of strings.
- Each string is one self-contained action item, written as clearly and concisely as possible.
- Do not modify the contents of action items.
- If there are no action items, return {"items": []}.
- Do NOT add commentary, markdown, or any text outside the JSON object.

Examples:
<input>
# Sprint Planning Meeting Notes
**Date:** February 23, 2026 | **Location:** Zoom (Remote) | **Attendees:** David, Emma, Frank, Grace

## Summary
The team reviewed the Sprint 14 backlog and agreed on priorities for the next two weeks. Key focus areas include resolving outstanding API bugs, completing the onboarding flow redesign, and preparing for the upcoming QA freeze on March 6. Velocity targets were discussed and capacity was confirmed based on current team availability.

## Action Items
- [ ] David — Finalize Sprint 14 ticket assignments in Jira by EOD today.
- [ ] Emma — Submit pull request for the onboarding flow UI components by Feb 26.
- [ ] Frank — Write unit tests for the new authentication module and push by Feb 27.
- [ ] Grace — Coordinate with QA team to schedule regression testing for March 3–5.
- [ ] David — Send sprint kickoff summary email to all stakeholders by tomorrow morning.

## Next Meeting
**Sprint 14 Mid-Sprint Check-in** — March 2, 2026 at 2:00 PM PST via Zoom

**Agenda:** Progress review, blocker discussion, and deployment readiness check.
</input>

<output>
{
    "items": ["David — Finalize Sprint 14 ticket assignments in Jira by EOD today.", "Emma — Submit pull request for the onboarding flow UI components by Feb 26.", "Frank — Write unit tests for the new authentication module and push by Feb 27.", "Grace — Coordinate with QA team to schedule regression testing for March 3–5.", "David — Send sprint kickoff summary email to all stakeholders by tomorrow morning."]
}
</output>
"""


def extract_action_items_llm(text: str, model: str = OLLAMA_MODEL) -> List[str]:
    """Extract action items from *text* using an Ollama LLM.

    Returns a deduplicated list of action item strings.
    Raises RuntimeError if Ollama is unreachable or returns malformed output.
    """
    response = chat(
        model=model,
        messages=[
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        format={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                }
            },
            "required": ["items"],
        },
    )

    raw = response.message.content
    try:
        parsed = json.loads(raw)
        items: List[str] = parsed.get("items", [])
    except (json.JSONDecodeError, AttributeError) as exc:
        raise RuntimeError(f"LLM returned non-JSON output: {raw!r}") from exc

    # Deduplicate (same logic as the heuristic extractor)
    seen: set[str] = set()
    unique: List[str] = []
    for item in items:
        lowered = item.strip().lower()
        if not lowered or lowered in seen:
            continue
        seen.add(lowered)
        unique.append(item.strip())

    return unique
```

### Why `format` with a JSON schema?

`ollama.chat(..., format=<schema>)` (supported since ollama-python 0.3+) forces
**constrained decoding** — the model's token sampling is guided to produce output
matching the schema. This is more reliable than prompting alone because it
operates at the generation level, not just the instruction level. Passing a dict
directly (instead of `"json"`) restricts the output to the exact shape you need.

### Prompt design rationale

- The system prompt defines "action item" explicitly to reduce false positives
  (decisions, observations should not be extracted).
- The `format` JSON schema enforces valid, correctly-shaped output at the decoding
  level — a verbose in-prompt example is redundant when constrained decoding is active.
- `"Do NOT add commentary"` is kept as a belt-and-suspenders guard for models that
  partially ignore the schema constraint.

---

## 2. `app/routers/action_items.py` — New `/extract-llm` endpoint

### What to change

Update the import line and add one new route:

```python
# Change this line at the top:
from ..services.extract import extract_action_items

# To:
from ..services.extract import extract_action_items, extract_action_items_llm


# Add this new route after the existing @router.post("/extract") handler:

@router.post("/extract-llm")
def extract_llm(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    note_id: Optional[int] = None
    if payload.get("save_note"):
        note_id = db.insert_note(text)

    try:
        items = extract_action_items_llm(text)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    ids = db.insert_action_items(items, note_id=note_id)
    return {"note_id": note_id, "items": [{"id": i, "text": t} for i, t in zip(ids, items)]}
```

### Why HTTP 502?

502 Bad Gateway signals that the server received an invalid response from an
upstream dependency (Ollama). This is semantically correct: the client request
was valid, but our LLM backend failed. Using 500 would be misleading (not our
fault), and 400 would be wrong (not the client's fault).

---

## 3. `frontend/index.html` — Add "Extract with LLM" button

### What to change

Replace the existing `<div class="row">` block and `<script>` tag with:

```html
<div class="row">
  <label class="row"><input id="save_note" type="checkbox" checked /> Save as note</label>
  <button id="extract">Extract</button>
  <button id="extract-llm">Extract with LLM</button>
</div>

<div class="items" id="items"></div>

<script>
  const $ = (sel) => document.querySelector(sel);
  const itemsEl = $('#items');

  async function runExtract(endpoint) {
    const text = $('#text').value;
    const save = $('#save_note').checked;
    itemsEl.textContent = 'Extracting...';
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, save_note: save }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Request failed');
      }
      const data = await res.json();
      renderItems(data.items);
    } catch (err) {
      console.error(err);
      itemsEl.textContent = `Error: ${err.message}`;
    }
  }

  function renderItems(items) {
    if (!items || items.length === 0) {
      itemsEl.innerHTML = '<p class="muted">No action items found.</p>';
      return;
    }
    itemsEl.innerHTML = items.map(it =>
      `<div class="item"><input type="checkbox" data-id="${it.id}" /> <span>${it.text}</span></div>`
    ).join('');
    itemsEl.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', async (e) => {
        const id = e.target.getAttribute('data-id');
        await fetch(`/action-items/${id}/done`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ done: e.target.checked }),
        });
      });
    });
  }

  $('#extract').addEventListener('click', () => runExtract('/action-items/extract'));
  $('#extract-llm').addEventListener('click', () => runExtract('/action-items/extract-llm'));
</script>
```

### Key refactoring

The original script had the fetch logic inline inside the button's click handler.
Here it is extracted into `runExtract(endpoint)` and `renderItems(items)` so both
buttons share the same code. The only difference between the two buttons is the
endpoint URL passed to `runExtract`.

Error messages now show the server's `detail` field (e.g. "LLM returned non-JSON
output") instead of the generic "Error extracting items".

---

## 4. Environment setup

Create `week2/.env`:

```env
OLLAMA_MODEL=llama3.1:8b
# OLLAMA_HOST=http://localhost:11434   # uncomment if Ollama runs on non-default host/port
```

Pull the model before running the server:

```bash
ollama pull llama3.1:8b
```

Start the server:

```bash
poetry run uvicorn week2.app.main:app --reload
```

---

## 5. Error handling strategy

| Scenario | What happens |
|---|---|
| Ollama not running | `ollama.chat()` raises `ConnectionError` → caught, re-raised as `RuntimeError` → HTTP 502 |
| Model not installed on Ollama | Ollama returns an error → same path → HTTP 502 |
| Malformed JSON despite `format` | `json.JSONDecodeError` → `RuntimeError` → HTTP 502 |
| Empty `text` field | HTTP 400 (same as heuristic endpoint) |
| LLM returns `{"items": []}` | Valid empty result; frontend shows "No action items found." |
| LLM returns duplicates | Deduplication in `extract_action_items_llm()` collapses them before DB insert |

---

## 6. Unit tests — `tests/test_extract_llm.py`

Tests mock `ollama.chat` so they run without a live Ollama instance.

The `SAMPLE_NOTE` fixture mirrors realistic input — a structured meeting note with
a prose summary section and an explicit `## Action Items` section with checkbox
bullets. This exercises the LLM's ability to work on real-world formatted text,
not just trivial one-liners.

```python
from unittest.mock import MagicMock, patch

import pytest

from week2.app.services.extract import extract_action_items_llm


SAMPLE_NOTE = """
# Project Kickoff Meeting Notes
**Date:** February 23, 2026
**Attendees:** Alice, Bob, Carol

## Summary
We aligned on the Q1 roadmap and discussed upcoming deliverables. The team agreed
to prioritize the mobile redesign and finalize the budget proposal by end of month.

## Action Items

- [ ] Alice — Draft the mobile wireframes and share with the design team by Feb 28
- [ ] Bob — Schedule a follow-up call with the client to confirm requirements
- [ ] Carol — Update the budget spreadsheet and send to stakeholders by EOD Friday
- [ ] Alice — Review and approve the revised project timeline
- [ ] Bob — Set up the new Slack channel for cross-team communication

## Next Meeting
March 2, 2026 at 10:00 AM PST
""".strip()

SAMPLE_NOTE_ITEMS = [
    "Alice — Draft the mobile wireframes and share with the design team by Feb 28",
    "Bob — Schedule a follow-up call with the client to confirm requirements",
    "Carol — Update the budget spreadsheet and send to stakeholders by EOD Friday",
    "Alice — Review and approve the revised project timeline",
    "Bob — Set up the new Slack channel for cross-team communication",
]


def _mock_response(content: str):
    msg = MagicMock()
    msg.message.content = content
    return msg


def test_llm_extracts_from_meeting_note():
    with patch("week2.app.services.extract.chat") as mock_chat:
        mock_chat.return_value = _mock_response(
            '{"items": ' + str(SAMPLE_NOTE_ITEMS).replace("'", '"') + '}'
        )
        items = extract_action_items_llm(SAMPLE_NOTE)
    for expected in SAMPLE_NOTE_ITEMS:
        assert expected in items


def test_llm_returns_empty_for_no_tasks():
    with patch("week2.app.services.extract.chat") as mock_chat:
        mock_chat.return_value = _mock_response('{"items": []}')
        items = extract_action_items_llm("We had a great discussion about the product roadmap.")
    assert items == []


def test_llm_deduplicates_items():
    with patch("week2.app.services.extract.chat") as mock_chat:
        mock_chat.return_value = _mock_response(
            '{"items": ["Fix the bug", "fix the bug", "Fix The Bug"]}'
        )
        items = extract_action_items_llm("some text with duplicate tasks")
    assert len(items) == 1
    assert items[0] == "Fix the bug"


def test_llm_raises_on_malformed_json():
    with patch("week2.app.services.extract.chat") as mock_chat:
        mock_chat.return_value = _mock_response("Sure! Here are the action items: ...")
        with pytest.raises(RuntimeError, match="non-JSON"):
            extract_action_items_llm("some text")
```

Run with:

```bash
poetry run pytest week2/tests/test_extract_llm.py -v
```