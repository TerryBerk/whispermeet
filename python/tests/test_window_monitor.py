"""Tests for WindowMonitor service."""

import pytest
from whispermeet.models.config import MonitoredApp, AppConfig
from whispermeet.services.window_monitor import WindowMonitor


def test_config_default_apps():
    """Default config should include Zoom, Telegram, Telemost."""
    config = AppConfig.default()
    app_names = [app.name for app in config.apps]

    assert "Zoom" in app_names
    assert "Telegram" in app_names
    assert "Telemost (Arc)" in app_names


def test_pattern_matching():
    """Window titles should match configured patterns."""
    monitor = WindowMonitor()

    assert monitor.matches_pattern("Zoom Meeting - My Call", ["Zoom Meeting"])
    assert monitor.matches_pattern("Voice Chat with John", ["Voice Chat"])
    assert not monitor.matches_pattern("Safari", ["Zoom Meeting"])


def test_case_insensitive_matching():
    """Pattern matching should be case insensitive."""
    monitor = WindowMonitor()

    assert monitor.matches_pattern("zoom meeting", ["Zoom Meeting"])
    assert monitor.matches_pattern("TELEMOST Conference", ["telemost"])
