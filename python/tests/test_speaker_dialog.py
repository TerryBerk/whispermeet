"""Tests for Speaker Names Dialog."""

import pytest
from whispermeet.ui.speaker_dialog import SpeakerNamesDialog


def test_dialog_init():
    """Dialog should initialize with speakers list."""
    dialog = SpeakerNamesDialog(
        speakers=["SPEAKER_00", "SPEAKER_01"],
    )
    assert dialog.speakers == ["SPEAKER_00", "SPEAKER_01"]
    assert dialog.result is None


def test_dialog_with_samples():
    """Dialog should accept speaker samples."""
    samples = {
        "SPEAKER_00": (0.0, 5.0),
        "SPEAKER_01": (10.0, 15.0),
    }
    dialog = SpeakerNamesDialog(
        speakers=["SPEAKER_00", "SPEAKER_01"],
        speaker_samples=samples,
    )
    assert dialog.speaker_samples == samples
