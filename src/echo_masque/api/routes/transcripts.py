"""Offline transcript import endpoint."""

from fastapi import APIRouter, HTTPException

from echo_masque.api.schemas import TranscriptAnalyzeRequest
from echo_masque.domain import TrialSuiteResult
from echo_masque.transcripts import analyze_transcript, parse_transcript

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])


@router.post("/analyze", response_model=TrialSuiteResult)
def analyze(payload: TranscriptAnalyzeRequest) -> TrialSuiteResult:
    try:
        messages = parse_transcript(payload.content, payload.format)
        return analyze_transcript(
            messages,
            subject_name=payload.subject_name,
            suite=tuple(payload.suite),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
