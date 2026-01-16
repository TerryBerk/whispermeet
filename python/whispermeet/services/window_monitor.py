"""Window monitoring service using macOS Accessibility API."""

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from AppKit import NSWorkspace
from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
    kAXWindowsAttribute,
    kAXTitleAttribute,
)

from whispermeet.models.config import AppConfig, MonitoredApp


@dataclass
class DetectedMeeting:
    """Represents a detected meeting."""

    app: MonitoredApp
    window_title: str
    timestamp: datetime


class WindowMonitor:
    """Monitors windows for meeting detection."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or AppConfig.default()
        self.is_monitoring = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[DetectedMeeting], None]] = None
        self._detected_meeting: Optional[DetectedMeeting] = None

    def start(self, callback: Callable[[DetectedMeeting], None]):
        """Start monitoring for meetings."""
        self._callback = callback
        self.is_monitoring = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop monitoring."""
        self.is_monitoring = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.is_monitoring:
            meeting = self._check_for_meetings()
            if meeting and self._callback:
                self._callback(meeting)
            time.sleep(2.0)

    def _check_for_meetings(self) -> Optional[DetectedMeeting]:
        """Check running apps for meeting windows."""
        workspace = NSWorkspace.sharedWorkspace()
        running_apps = workspace.runningApplications()

        for monitored_app in self.config.apps:
            for app in running_apps:
                if app.bundleIdentifier() == monitored_app.bundle_id:
                    title = self._get_window_title(app.processIdentifier())
                    if title and self.matches_pattern(title, monitored_app.window_patterns):
                        return DetectedMeeting(
                            app=monitored_app,
                            window_title=title,
                            timestamp=datetime.now(),
                        )
        return None

    def _get_window_title(self, pid: int) -> Optional[str]:
        """Get the title of the frontmost window for a process."""
        app_ref = AXUIElementCreateApplication(pid)

        err, windows = AXUIElementCopyAttributeValue(app_ref, kAXWindowsAttribute, None)
        if err or not windows:
            return None

        if len(windows) == 0:
            return None

        err, title = AXUIElementCopyAttributeValue(windows[0], kAXTitleAttribute, None)
        if err:
            return None

        return title

    def matches_pattern(self, title: str, patterns: list[str]) -> bool:
        """Check if window title matches any pattern (case insensitive)."""
        title_lower = title.lower()
        return any(pattern.lower() in title_lower for pattern in patterns)
