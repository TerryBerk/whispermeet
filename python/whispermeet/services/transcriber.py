"""Transcription service using whisper.cpp."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterator

try:
    from pywhispercpp.model import Model
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False
    Model = None


@dataclass
class TranscriptSegment:
    """A segment of transcribed text."""

    start: float  # seconds
    end: float  # seconds
    text: str
    speaker: Optional[str] = None

    def format(self) -> str:
        """Format segment with timestamp."""
        start_str = self._format_time(self.start)
        end_str = self._format_time(self.end)

        if self.speaker:
            return f"[{start_str} - {end_str}] {self.speaker}: {self.text}"
        return f"[{start_str} - {end_str}] {self.text}"

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as MM:SS."""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"


class Transcriber:
    """Transcription service using whisper.cpp."""

    MODELS_DIR = Path.home() / ".cache" / "whisper"

    def __init__(self, model: str = "base"):
        self.model_name = model
        self._model: Optional["Model"] = None

    def _ensure_model(self):
        """Load model if not already loaded."""
        if not HAS_WHISPER:
            raise ImportError("pywhispercpp not installed")

        if self._model is None:
            model_path = self.MODELS_DIR / f"ggml-{self.model_name}.bin"
            if not model_path.exists():
                self._download_model()
            self._model = Model(str(model_path))

    def _download_model(self):
        """Download whisper model."""
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        # whisper.cpp provides download script
        # For now, assume model exists or raise error
        raise FileNotFoundError(
            f"Model {self.model_name} not found. "
            f"Please download to {self.MODELS_DIR}"
        )

    def transcribe(self, audio_path: Path) -> list[TranscriptSegment]:
        """Transcribe an audio file."""
        self._ensure_model()

        segments = []
        result = self._model.transcribe(str(audio_path))

        for seg in result:
            segments.append(
                TranscriptSegment(
                    start=seg.t0 / 100.0,  # centiseconds to seconds
                    end=seg.t1 / 100.0,
                    text=seg.text.strip(),
                )
            )

        return segments

    def transcribe_realtime(self, audio_path: Path) -> Iterator[TranscriptSegment]:
        """Transcribe audio file with streaming output."""
        self._ensure_model()

        for seg in self._model.transcribe(str(audio_path)):
            yield TranscriptSegment(
                start=seg.t0 / 100.0,
                end=seg.t1 / 100.0,
                text=seg.text.strip(),
            )


class TwoStageTranscriber:
    """Two-stage transcriber: fast for realtime, large for final."""

    def __init__(
        self,
        realtime_model: str = "base",
        final_model: str = "large-v3",
    ):
        self.realtime = Transcriber(model=realtime_model)
        self.final = Transcriber(model=final_model)

    def transcribe_realtime(self, audio_path: Path) -> Iterator[TranscriptSegment]:
        """Get realtime transcription (draft quality)."""
        return self.realtime.transcribe_realtime(audio_path)

    def transcribe_final(self, audio_path: Path) -> list[TranscriptSegment]:
        """Get final high-quality transcription."""
        return self.final.transcribe(audio_path)
