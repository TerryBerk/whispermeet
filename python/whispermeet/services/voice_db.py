"""Voice fingerprint database for speaker identification."""

import json
import numpy as np
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

try:
    from pyannote.audio import Model, Inference
    HAS_PYANNOTE_EMBEDDING = True
except ImportError:
    HAS_PYANNOTE_EMBEDDING = False


@dataclass
class VoiceProfile:
    """Stored voice profile for a known speaker."""

    name: str
    embedding: list[float]  # Voice embedding vector
    sample_count: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "VoiceProfile":
        return cls(**data)


class VoiceDatabase:
    """Local database of voice fingerprints."""

    DEFAULT_PATH = Path.home() / ".config" / "whispermeet" / "voices.json"
    SIMILARITY_THRESHOLD = 0.7  # Cosine similarity threshold for match

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or self.DEFAULT_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._profiles: dict[str, VoiceProfile] = {}
        self._model: Optional["Model"] = None
        self._inference: Optional["Inference"] = None
        self._load()

    def _load(self):
        """Load profiles from disk."""
        if self.db_path.exists():
            try:
                with open(self.db_path) as f:
                    data = json.load(f)
                self._profiles = {
                    name: VoiceProfile.from_dict(profile)
                    for name, profile in data.get("profiles", {}).items()
                }
            except (json.JSONDecodeError, KeyError):
                self._profiles = {}

    def _save(self):
        """Save profiles to disk."""
        data = {
            "profiles": {
                name: profile.to_dict()
                for name, profile in self._profiles.items()
            }
        }
        with open(self.db_path, "w") as f:
            json.dump(data, f, indent=2)

    def _ensure_model(self):
        """Load embedding model if not loaded."""
        if not HAS_PYANNOTE_EMBEDDING:
            raise ImportError(
                "pyannote.audio embedding model not available. "
                "Install with: pip install pyannote.audio"
            )

        if self._model is None:
            self._model = Model.from_pretrained(
                "pyannote/embedding",
                use_auth_token=True,
            )
            self._inference = Inference(self._model, window="whole")

    def extract_embedding(
        self,
        audio_path: Path,
        start: Optional[float] = None,
        end: Optional[float] = None,
    ) -> np.ndarray:
        """Extract voice embedding from audio.

        Args:
            audio_path: Path to audio file
            start: Start time in seconds (optional)
            end: End time in seconds (optional)

        Returns:
            Voice embedding vector as numpy array
        """
        self._ensure_model()

        if start is not None and end is not None:
            # Extract from specific segment
            from pyannote.core import Segment
            segment = Segment(start, end)
            embedding = self._inference.crop(str(audio_path), segment)
        else:
            embedding = self._inference(str(audio_path))

        return embedding

    def add_profile(
        self,
        name: str,
        audio_path: Path,
        start: Optional[float] = None,
        end: Optional[float] = None,
    ):
        """Add or update voice profile.

        Args:
            name: Speaker name
            audio_path: Path to audio sample
            start: Start time in seconds
            end: End time in seconds
        """
        embedding = self.extract_embedding(audio_path, start, end)

        if name in self._profiles:
            # Average with existing embedding
            old_profile = self._profiles[name]
            old_embedding = np.array(old_profile.embedding)
            count = old_profile.sample_count

            # Weighted average
            new_embedding = (old_embedding * count + embedding) / (count + 1)
            self._profiles[name] = VoiceProfile(
                name=name,
                embedding=new_embedding.tolist(),
                sample_count=count + 1,
            )
        else:
            self._profiles[name] = VoiceProfile(
                name=name,
                embedding=embedding.tolist(),
                sample_count=1,
            )

        self._save()

    def identify(
        self,
        audio_path: Path,
        start: Optional[float] = None,
        end: Optional[float] = None,
    ) -> Optional[tuple[str, float]]:
        """Identify speaker from audio.

        Args:
            audio_path: Path to audio file
            start: Start time in seconds
            end: End time in seconds

        Returns:
            Tuple of (name, confidence) or None if no match
        """
        if not self._profiles:
            return None

        embedding = self.extract_embedding(audio_path, start, end)

        best_match = None
        best_similarity = -1.0

        for name, profile in self._profiles.items():
            stored_embedding = np.array(profile.embedding)

            # Cosine similarity
            similarity = np.dot(embedding, stored_embedding) / (
                np.linalg.norm(embedding) * np.linalg.norm(stored_embedding)
            )

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = name

        if best_similarity >= self.SIMILARITY_THRESHOLD:
            return (best_match, float(best_similarity))

        return None

    def suggest_names(
        self,
        audio_path: Path,
        speaker_samples: dict[str, tuple[float, float]],
    ) -> dict[str, Optional[str]]:
        """Suggest names for speakers based on voice matching.

        Args:
            audio_path: Path to audio file
            speaker_samples: Dict mapping speaker IDs to (start, end) tuples

        Returns:
            Dict mapping speaker IDs to suggested names (or None if no match)
        """
        suggestions = {}

        for speaker_id, (start, end) in speaker_samples.items():
            result = self.identify(audio_path, start, end)
            if result:
                name, confidence = result
                suggestions[speaker_id] = name
            else:
                suggestions[speaker_id] = None

        return suggestions

    def get_all_profiles(self) -> list[str]:
        """Get list of all known speaker names."""
        return list(self._profiles.keys())

    def remove_profile(self, name: str):
        """Remove a voice profile."""
        if name in self._profiles:
            del self._profiles[name]
            self._save()
