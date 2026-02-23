from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db
from ..schemas import NoteCreate, NoteResponse


router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("", response_model=NoteResponse, status_code=201)
def create_note(body: NoteCreate) -> NoteResponse:
    note_id = db.insert_note(body.content.strip())
    note = db.get_note(note_id)
    return NoteResponse(**dict(note))


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
