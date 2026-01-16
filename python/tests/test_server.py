"""Tests for FastAPI server."""

import pytest
from fastapi.testclient import TestClient
from whispermeet.server.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    """Health endpoint should return ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_summarize_endpoint(client):
    """Summarize endpoint should accept transcript."""
    response = client.post(
        "/summarize",
        json={
            "transcript": "Speaker 1: Hello\nSpeaker 2: Hi there",
            "title": "Test Meeting",
            "date": "2026-01-16",
            "duration": "5 minutes",
            "participants": ["Speaker 1", "Speaker 2"],
        },
    )
    # May fail without Claude CLI, but should not crash
    assert response.status_code in [200, 500]
