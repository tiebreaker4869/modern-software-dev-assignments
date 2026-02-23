from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── Notes ─────────────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    content: str = Field(..., min_length=1, description="Note text content")


class NoteResponse(BaseModel):
    id: int
    content: str
    created_at: str


# ── Action Items ───────────────────────────────────────────────────────────────

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
