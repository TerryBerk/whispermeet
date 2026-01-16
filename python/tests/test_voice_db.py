"""Tests for Voice Database service."""

import pytest
from pathlib import Path
from whispermeet.services.voice_db import VoiceDatabase, VoiceProfile


def test_voice_profile_creation():
    """VoiceProfile should store name and embedding."""
    profile = VoiceProfile(
        name="Terry",
        embedding=[0.1, 0.2, 0.3],
        sample_count=1,
    )

    assert profile.name == "Terry"
    assert profile.embedding == [0.1, 0.2, 0.3]
    assert profile.sample_count == 1


def test_voice_profile_to_dict():
    """VoiceProfile should serialize to dict."""
    profile = VoiceProfile(
        name="John",
        embedding=[0.5, 0.5],
        sample_count=2,
    )

    data = profile.to_dict()
    assert data["name"] == "John"
    assert data["embedding"] == [0.5, 0.5]
    assert data["sample_count"] == 2


def test_voice_profile_from_dict():
    """VoiceProfile should deserialize from dict."""
    data = {
        "name": "Alex",
        "embedding": [0.1, 0.2],
        "sample_count": 3,
    }

    profile = VoiceProfile.from_dict(data)
    assert profile.name == "Alex"
    assert profile.embedding == [0.1, 0.2]
    assert profile.sample_count == 3


def test_voice_database_init(tmp_path):
    """VoiceDatabase should initialize with custom path."""
    db_path = tmp_path / "voices.json"
    db = VoiceDatabase(db_path=db_path)

    assert db.db_path == db_path


def test_voice_database_get_all_profiles(tmp_path):
    """Should return empty list for new database."""
    db_path = tmp_path / "voices.json"
    db = VoiceDatabase(db_path=db_path)

    assert db.get_all_profiles() == []
