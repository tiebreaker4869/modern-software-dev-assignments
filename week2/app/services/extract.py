from __future__ import annotations

import json
import os
import re
from typing import Any, List

from dotenv import load_dotenv
from ollama import chat

load_dotenv()

BULLET_PREFIX_PATTERN = re.compile(r"^\s*([-*•]|\d+\.)\s+")
KEYWORD_PREFIXES = (
    "todo:",
    "action:",
    "next:",
)


def _is_action_line(line: str) -> bool:
    stripped = line.strip().lower()
    if not stripped:
        return False
    if BULLET_PREFIX_PATTERN.match(stripped):
        return True
    if any(stripped.startswith(prefix) for prefix in KEYWORD_PREFIXES):
        return True
    if "[ ]" in stripped or "[todo]" in stripped:
        return True
    return False


def extract_action_items(text: str) -> List[str]:
    lines = text.splitlines()
    extracted: List[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if _is_action_line(line):
            cleaned = BULLET_PREFIX_PATTERN.sub("", line)
            cleaned = cleaned.strip()
            # Trim common checkbox markers
            cleaned = cleaned.removeprefix("[ ]").strip()
            cleaned = cleaned.removeprefix("[todo]").strip()
            extracted.append(cleaned)
    # Fallback: if nothing matched, heuristically split into sentences and pick imperative-like ones
    if not extracted:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            if _looks_imperative(s):
                extracted.append(s)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: List[str] = []
    for item in extracted:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(item)
    return unique


def _looks_imperative(sentence: str) -> bool:
    words = re.findall(r"[A-Za-z']+", sentence)
    if not words:
        return False
    first = words[0]
    # Crude heuristic: treat these as imperative starters
    imperative_starters = {
        "add",
        "create",
        "implement",
        "fix",
        "update",
        "write",
        "check",
        "verify",
        "refactor",
        "document",
        "design",
        "investigate",
    }
    return first.lower() in imperative_starters


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
