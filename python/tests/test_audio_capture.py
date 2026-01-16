"""Tests for AudioCapture service."""

import pytest
from pathlib import Path
from whispermeet.services.audio_capture import AudioCapture


def test_audio_capture_init():
    """AudioCapture should initialize with output directory."""
    capture = AudioCapture()
    assert capture.output_directory == Path.home() / "Transcripts"


def test_audio_capture_custom_directory():
    """AudioCapture should accept custom output directory."""
    custom_dir = Path("/tmp/test_transcripts")
    capture = AudioCapture(output_directory=custom_dir)
    assert capture.output_directory == custom_dir


def test_create_output_url():
    """Should create timestamped output file path."""
    capture = AudioCapture()
    url = capture._create_output_url("Zoom")

    assert url.parent == capture.output_directory
    assert "zoom" in url.name.lower()
    assert url.suffix == ".wav"
