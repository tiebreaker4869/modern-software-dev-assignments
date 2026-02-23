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
            '{"items": ' + str(SAMPLE_NOTE_ITEMS).replace("'", '"') + "}"
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
