"""Tests for Summary service."""

import pytest
from whispermeet.services.summary import SummaryGenerator, MeetingSummary
from whispermeet.services.transcriber import TranscriptSegment


def test_summary_generator_init():
    """SummaryGenerator should initialize with default prompt."""
    generator = SummaryGenerator()
    assert generator.prompt_template is not None


def test_meeting_summary_to_markdown():
    """MeetingSummary should convert to markdown."""
    summary = MeetingSummary(
        title="Test Meeting",
        date="2026-01-16",
        duration="45 minutes",
        participants=["Terry", "John"],
        tldr="Brief overview",
        key_decisions=["Decision 1"],
        action_items=["Terry: Do task"],
        discussion_points=["Topic 1 discussed"],
    )

    md = summary.to_markdown()

    assert "# Meeting Summary: Test Meeting" in md
    assert "Terry, John" in md
    assert "## TL;DR" in md
    assert "## Key Decisions" in md
    assert "## Action Items" in md
