"""
DOCex core data models.

Canonical Pydantic models for the extraction engine.
Field names here must stay in sync with api/schemas.py and web/types/index.ts.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel


class Question(BaseModel):
    """A single question the user wants answered from the documents."""
    id: str
    text: str  # plain language, e.g. "What states does this organisation work in?"


class ExtractionAnswer(BaseModel):
    """The AI's answer to one question for one applicant."""
    question_id: str
    question_text: str
    answer: Optional[str] = None
    # found     — explicitly stated in a document
    # inferred  — reasonably concluded from context
    # not_found — not mentioned anywhere
    confidence: Literal["found", "inferred", "not_found"]
    source_document: Optional[str] = None  # filename the answer came from
    source_page: Optional[int] = None      # page number (from === PAGE N === markers in PDFs)
    quote: Optional[str] = None            # verbatim excerpt supporting the answer
    search_notes: Optional[str] = None     # reasoning trail — what was searched, what was found/not found


class ApplicantExtraction(BaseModel):
    """Full extraction result for one applicant (who may have submitted many docs)."""
    applicant_id: str
    applicant_name: str
    documents: list[str]       # filenames that were read
    answers: list[ExtractionAnswer]
    error: Optional[str] = None
