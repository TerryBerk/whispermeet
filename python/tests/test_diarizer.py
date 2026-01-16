"""Tests for Speaker Diarization service."""

import pytest
from whispermeet.services.diarizer import SpeakerDiarizer, SpeakerSegment


def test_speaker_segment_creation():
    """SpeakerSegment should store speaker and time info."""
    segment = SpeakerSegment(
        speaker="SPEAKER_00",
        start=0.0,
        end=5.5,
    )

    assert segment.speaker == "SPEAKER_00"
    assert segment.start == 0.0
    assert segment.end == 5.5


def test_speaker_segment_contains_time():
    """contains_time should check if timestamp is within segment."""
    segment = SpeakerSegment(
        speaker="SPEAKER_00",
        start=10.0,
        end=20.0,
    )

    assert segment.contains_time(15.0)
    assert segment.contains_time(10.0)  # inclusive start
    assert not segment.contains_time(9.9)
    assert not segment.contains_time(20.1)


def test_diarizer_init():
    """SpeakerDiarizer should initialize."""
    diarizer = SpeakerDiarizer()
    assert diarizer is not None


def test_speaker_names_assignment():
    """Should be able to assign names to speakers."""
    diarizer = SpeakerDiarizer()
    diarizer.assign_names({
        "SPEAKER_00": "Terry",
        "SPEAKER_01": "John",
    })

    assert diarizer.get_name("SPEAKER_00") == "Terry"
    assert diarizer.get_name("SPEAKER_01") == "John"
    assert diarizer.get_name("SPEAKER_02") == "Speaker 3"  # fallback
