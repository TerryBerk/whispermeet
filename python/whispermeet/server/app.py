"""FastAPI application for WhisperMeet backend."""

import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from whispermeet.services import (
    TwoStageTranscriber,
    SpeakerDiarizer,
    SummaryGenerator,
    TranscriptSegment,
)
from whispermeet.services.voice_db import VoiceDatabase

app = FastAPI(
    title="WhisperMeet Backend",
    description="Audio processing backend for WhisperMeet",
    version="0.1.0",
)

# Global service instances (initialized lazily)
_transcriber: Optional[TwoStageTranscriber] = None
_diarizer: Optional[SpeakerDiarizer] = None
_summary_generator: Optional[SummaryGenerator] = None
_voice_db: Optional[VoiceDatabase] = None


def get_transcriber() -> TwoStageTranscriber:
    global _transcriber
    if _transcriber is None:
        _transcriber = TwoStageTranscriber()
    return _transcriber


def get_diarizer() -> SpeakerDiarizer:
    global _diarizer
    if _diarizer is None:
        _diarizer = SpeakerDiarizer()
    return _diarizer


def get_summary_generator() -> SummaryGenerator:
    global _summary_generator
    if _summary_generator is None:
        _summary_generator = SummaryGenerator()
    return _summary_generator


def get_voice_db() -> VoiceDatabase:
    global _voice_db
    if _voice_db is None:
        _voice_db = VoiceDatabase()
    return _voice_db


# Request/Response Models

class TranscribeResponse(BaseModel):
    segments: list[dict]
    duration_seconds: float


class DiarizeResponse(BaseModel):
    speakers: list[str]
    segments: list[dict]
    speaker_samples: dict[str, list[float]]


class SummarizeRequest(BaseModel):
    transcript: str
    title: str
    date: str
    duration: str
    participants: list[str]


class SummarizeResponse(BaseModel):
    markdown: str
    title: str
    tldr: str
    key_decisions: list[str]
    action_items: list[str]


class IdentifyRequest(BaseModel):
    speaker_samples: dict[str, list[float]]  # speaker_id -> [start, end]


class IdentifyResponse(BaseModel):
    suggestions: dict[str, Optional[str]]


class SaveVoiceRequest(BaseModel):
    name: str
    start: float
    end: float


class ProcessRequest(BaseModel):
    title: Optional[str] = None
    save_voices: bool = False
    speaker_names: Optional[dict[str, str]] = None


class ProcessResponse(BaseModel):
    transcript: str
    summary_markdown: str
    speakers: list[str]
    duration_seconds: float


# Health check

@app.get("/health")
async def health_check():
    """Check if server is running."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# Transcription endpoint

@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...)):
    """Transcribe audio file."""
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        transcriber = get_transcriber()
        segments = transcriber.transcribe_final(tmp_path)

        duration = segments[-1].end if segments else 0.0

        return TranscribeResponse(
            segments=[
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "speaker": s.speaker,
                }
                for s in segments
            ],
            duration_seconds=duration,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


# Diarization endpoint

@app.post("/diarize", response_model=DiarizeResponse)
async def diarize(file: UploadFile = File(...)):
    """Identify speakers in audio file."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        diarizer = get_diarizer()
        segments = diarizer.diarize(tmp_path)
        speakers = diarizer.get_unique_speakers()
        samples = diarizer.get_speaker_samples(tmp_path)

        return DiarizeResponse(
            speakers=speakers,
            segments=[
                {
                    "speaker": s.speaker,
                    "start": s.start,
                    "end": s.end,
                }
                for s in segments
            ],
            speaker_samples={
                speaker: [start, end]
                for speaker, (start, end) in samples.items()
            },
        )
    finally:
        tmp_path.unlink(missing_ok=True)


# Summary endpoint

@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(request: SummarizeRequest):
    """Generate meeting summary from transcript."""
    generator = get_summary_generator()

    try:
        summary = generator.generate(
            transcript=request.transcript,
            title=request.title,
            date=request.date,
            duration=request.duration,
            participants=request.participants,
        )

        return SummarizeResponse(
            markdown=summary.to_markdown(),
            title=summary.title,
            tldr=summary.tldr,
            key_decisions=summary.key_decisions,
            action_items=summary.action_items,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Voice identification endpoint

@app.post("/identify-speakers", response_model=IdentifyResponse)
async def identify_speakers(
    file: UploadFile = File(...),
    speaker_samples: str = "",  # JSON string of {speaker_id: [start, end]}
):
    """Identify known speakers from voice samples."""
    import json

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        samples = json.loads(speaker_samples) if speaker_samples else {}
        samples_tuples = {k: tuple(v) for k, v in samples.items()}

        voice_db = get_voice_db()
        suggestions = voice_db.suggest_names(tmp_path, samples_tuples)

        return IdentifyResponse(suggestions=suggestions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)


# Save voice profile endpoint

@app.post("/save-voice")
async def save_voice(
    file: UploadFile = File(...),
    name: str = "",
    start: float = 0.0,
    end: float = 0.0,
):
    """Save voice profile for future identification."""
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        voice_db = get_voice_db()
        voice_db.add_profile(name, tmp_path, start if start > 0 else None, end if end > 0 else None)
        return {"status": "ok", "name": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)


# Full processing endpoint (combines all steps)

@app.post("/process", response_model=ProcessResponse)
async def process_audio(
    file: UploadFile = File(...),
    title: str = "Meeting",
    save_voices: bool = False,
    speaker_names: str = "",  # JSON string
):
    """Full audio processing: diarize, transcribe, summarize."""
    import json

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        # Parse speaker names if provided
        names = json.loads(speaker_names) if speaker_names else {}

        # Step 1: Diarize
        diarizer = get_diarizer()
        diarizer.diarize(tmp_path)
        speakers = diarizer.get_unique_speakers()

        # Apply provided names or use defaults
        if names:
            diarizer.assign_names(names)

        # Step 2: Transcribe with speaker labels
        transcriber = get_transcriber()
        segments = transcriber.transcribe_with_diarization(tmp_path, diarizer)

        transcript_text = "\n".join(seg.format() for seg in segments)
        duration = segments[-1].end if segments else 0.0

        # Step 3: Get participant names
        participant_names = [diarizer.get_name(s) for s in speakers]

        # Step 4: Generate summary
        generator = get_summary_generator()
        summary = generator.generate(
            transcript=transcript_text,
            title=title,
            date=datetime.now().strftime("%Y-%m-%d"),
            duration=f"{int(duration // 60)} minutes",
            participants=participant_names,
        )

        # Step 5: Save voice profiles if requested
        if save_voices and names:
            voice_db = get_voice_db()
            samples = diarizer.get_speaker_samples(tmp_path)
            for speaker_id, name in names.items():
                if speaker_id in samples:
                    start, end = samples[speaker_id]
                    try:
                        voice_db.add_profile(name, tmp_path, start, end)
                    except Exception:
                        pass  # Ignore voice save errors

        return ProcessResponse(
            transcript=transcript_text,
            summary_markdown=summary.to_markdown(),
            speakers=participant_names,
            duration_seconds=duration,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def start_server(host: str = "127.0.0.1", port: int = 8765):
    """Start the FastAPI server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
