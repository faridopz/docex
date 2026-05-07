"""
DOCex FastAPI schemas.

Input schemas live here (QuestionIn for validation).
Output schemas re-export the core models directly — no duplication.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel

# Re-export core models as the API response types
# This keeps field names in sync automatically
from sys import path
from pathlib import Path
path.insert(0, str(Path(__file__).parent.parent))
from models import ExtractionAnswer, ApplicantExtraction  # noqa: E402


class QuestionIn(BaseModel):
    """Input validation for a single question."""
    id: str
    text: str


class SingleExtractionResponse(BaseModel):
    """Response for POST /extract/single."""
    applicant_name: str
    documents: list[str]
    answers: list[ExtractionAnswer]
    error: Optional[str] = None


class BatchExtractionResponse(BaseModel):
    """Response for POST /extract/batch."""
    total: int
    succeeded: int
    failed: int
    applicants: list[ApplicantExtraction]


class HealthOut(BaseModel):
    status: str = "ok"
    version: str = "2.0.0"
