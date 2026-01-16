"""Tests for Transcriber service."""

import pytest
from pathlib import Path
from whispermeet.services.transcriber import Transcriber, TranscriptSegment


def test_transcriber_init():
    """Transcriber should initialize with model name."""
    transcriber = Transcriber(model="base")
    assert transcriber.model_name == "base"


def test_transcript_segment_format():
    """TranscriptSegment should format with timestamp."""
    segment = TranscriptSegment(
        start=0.0,
        end=5.5,
        text="Hello world",
        speaker=None,
    )

    formatted = segment.format()
    assert "[00:00 - 00:05]" in formatted
    assert "Hello world" in formatted


def test_transcript_segment_with_speaker():
    """TranscriptSegment with speaker should include speaker label."""
    segment = TranscriptSegment(
        start=10.0,
        end=15.0,
        text="Test message",
        speaker="Speaker 1",
    )

    formatted = segment.format()
    assert "Speaker 1:" in formatted
