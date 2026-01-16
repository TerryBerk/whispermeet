"""Speaker diarization service using pyannote.audio."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# PyTorch 2.6+ workaround for pyannote model loading
os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")

try:
    from pyannote.audio import Pipeline
    HAS_PYANNOTE = True
except ImportError:
    HAS_PYANNOTE = False
    Pipeline = None


@dataclass
class SpeakerSegment:
    """A segment of speech from a specific speaker."""

    speaker: str  # e.g., "SPEAKER_00"
    start: float  # seconds
    end: float  # seconds

    def contains_time(self, time: float) -> bool:
        """Check if timestamp falls within this segment."""
        return self.start <= time < self.end


class SpeakerDiarizer:
    """Speaker diarization using pyannote.audio."""

    def __init__(self, model: str = "pyannote/speaker-diarization-3.1"):
        """Initialize diarizer with model name.

        Args:
            model: HuggingFace model name for diarization pipeline
        """
        self.model_name = model
        self._pipeline: Optional["Pipeline"] = None
        self._speaker_names: dict[str, str] = {}
        self._segments: list[SpeakerSegment] = []

    def _ensure_pipeline(self):
        """Load pipeline if not already loaded."""
        if not HAS_PYANNOTE:
            raise ImportError(
                "pyannote.audio not installed. "
                "Install with: pip install pyannote.audio"
            )

        if self._pipeline is None:
            # Note: Requires HuggingFace token for some models
            # Set HF_TOKEN environment variable or use huggingface-cli login
            self._pipeline = Pipeline.from_pretrained(self.model_name)

    def diarize(self, audio_path: Path) -> list[SpeakerSegment]:
        """Perform speaker diarization on audio file.

        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)

        Returns:
            List of SpeakerSegment with speaker labels and timestamps
        """
        self._ensure_pipeline()

        # Run diarization
        diarization = self._pipeline(str(audio_path))

        # Convert to SpeakerSegments
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(SpeakerSegment(
                speaker=speaker,
                start=turn.start,
                end=turn.end,
            ))

        self._segments = segments
        return segments

    def assign_names(self, names: dict[str, str]):
        """Assign human-readable names to speakers.

        Args:
            names: Mapping of speaker IDs to names
                   e.g., {"SPEAKER_00": "Terry", "SPEAKER_01": "John"}
        """
        self._speaker_names = names

    def get_name(self, speaker_id: str) -> str:
        """Get human-readable name for speaker ID.

        Args:
            speaker_id: Speaker ID like "SPEAKER_00"

        Returns:
            Assigned name or fallback like "Speaker 1"
        """
        if speaker_id in self._speaker_names:
            return self._speaker_names[speaker_id]

        # Generate fallback name from ID
        try:
            num = int(speaker_id.split("_")[-1]) + 1
            return f"Speaker {num}"
        except (ValueError, IndexError):
            return speaker_id

    def get_speaker_at_time(self, time: float) -> Optional[str]:
        """Get speaker ID for a given timestamp.

        Args:
            time: Timestamp in seconds

        Returns:
            Speaker ID or None if no speaker at that time
        """
        for segment in self._segments:
            if segment.contains_time(time):
                return segment.speaker
        return None

    def get_unique_speakers(self) -> list[str]:
        """Get list of unique speaker IDs in order of first appearance."""
        seen = set()
        unique = []
        for segment in self._segments:
            if segment.speaker not in seen:
                seen.add(segment.speaker)
                unique.append(segment.speaker)
        return unique

    def get_speaker_samples(self, audio_path: Path, duration: float = 5.0) -> dict[str, tuple[float, float]]:
        """Get sample time ranges for each speaker (for voice preview).

        Args:
            audio_path: Path to audio file
            duration: Max duration for each sample

        Returns:
            Mapping of speaker IDs to (start, end) tuples
        """
        samples = {}
        for speaker in self.get_unique_speakers():
            # Find first segment for this speaker
            for segment in self._segments:
                if segment.speaker == speaker:
                    end = min(segment.end, segment.start + duration)
                    samples[speaker] = (segment.start, end)
                    break
        return samples
