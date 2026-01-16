# WhisperMeet Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a macOS menubar app that automatically detects meetings, records audio, transcribes with speaker diarization, and generates AI summaries.

**Architecture:** Two parallel implementations (Swift and Python) that can later be integrated. Swift handles native macOS UI, ScreenCaptureKit, and window monitoring. Python handles whisper.cpp transcription, pyannote diarization, and Claude CLI integration.

**Tech Stack:**
- Swift: SwiftUI, ScreenCaptureKit, Accessibility API, AVFoundation
- Python: rumps, pyobjc, pywhispercpp, pyannote-audio, subprocess

---

## Phase 1: Swift — Core Infrastructure

### Task 1.1: Create Xcode Project Structure

**Files:**
- Create: `swift/WhisperMeet/WhisperMeet.xcodeproj`
- Create: `swift/WhisperMeet/Sources/App/WhisperMeetApp.swift`
- Create: `swift/WhisperMeet/Sources/App/AppDelegate.swift`

**Step 1: Create directory structure**

```bash
cd ~/git/whispermeet/.worktrees/swift
mkdir -p swift/WhisperMeet/Sources/{App,Views,Services,Models}
mkdir -p swift/WhisperMeet/Resources
```

**Step 2: Create SwiftUI App entry point**

Create `swift/WhisperMeet/Sources/App/WhisperMeetApp.swift`:

```swift
import SwiftUI

@main
struct WhisperMeetApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        Settings {
            SettingsView()
        }
    }
}
```

**Step 3: Create AppDelegate for menubar**

Create `swift/WhisperMeet/Sources/App/AppDelegate.swift`:

```swift
import Cocoa
import SwiftUI

class AppDelegate: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem?
    var popover: NSPopover?

    func applicationDidFinishLaunching(_ notification: Notification) {
        setupMenuBar()
    }

    private func setupMenuBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)

        if let button = statusItem?.button {
            button.image = NSImage(systemSymbolName: "mic.circle", accessibilityDescription: "WhisperMeet")
            button.action = #selector(togglePopover)
        }

        popover = NSPopover()
        popover?.contentSize = NSSize(width: 300, height: 400)
        popover?.behavior = .transient
        popover?.contentViewController = NSHostingController(rootView: MenuBarView())
    }

    @objc func togglePopover() {
        if let button = statusItem?.button {
            if popover?.isShown == true {
                popover?.performClose(nil)
            } else {
                popover?.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            }
        }
    }
}
```

**Step 4: Create placeholder MenuBarView**

Create `swift/WhisperMeet/Sources/Views/MenuBarView.swift`:

```swift
import SwiftUI

struct MenuBarView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("WhisperMeet")
                .font(.headline)

            Divider()

            Button("Start Manual Recording") {
                // TODO: Implement
            }

            Divider()

            Text("Recent Transcripts")
                .font(.subheadline)
                .foregroundColor(.secondary)

            Text("No recordings yet")
                .foregroundColor(.secondary)
                .padding(.vertical, 8)

            Divider()

            HStack {
                Button("Settings") {
                    NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
                }
                Spacer()
                Button("Quit") {
                    NSApplication.shared.terminate(nil)
                }
            }
        }
        .padding()
        .frame(width: 280)
    }
}

struct SettingsView: View {
    var body: some View {
        Text("Settings")
            .frame(width: 400, height: 300)
    }
}
```

**Step 5: Create Package.swift for SPM**

Create `swift/WhisperMeet/Package.swift`:

```swift
// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "WhisperMeet",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "WhisperMeet", targets: ["WhisperMeet"])
    ],
    targets: [
        .executableTarget(
            name: "WhisperMeet",
            path: "Sources"
        )
    ]
)
```

**Step 6: Build and verify**

```bash
cd ~/git/whispermeet/.worktrees/swift/swift/WhisperMeet
swift build
```

Expected: Build succeeds

**Step 7: Commit**

```bash
git add .
git commit -m "feat(swift): add menubar app skeleton with SwiftUI

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.2: Window Monitor Service

**Files:**
- Create: `swift/WhisperMeet/Sources/Services/WindowMonitor.swift`
- Create: `swift/WhisperMeet/Sources/Models/AppConfig.swift`

**Step 1: Create app configuration model**

Create `swift/WhisperMeet/Sources/Models/AppConfig.swift`:

```swift
import Foundation

struct MonitoredApp: Codable, Identifiable {
    var id: String { bundleId }
    let name: String
    let bundleId: String
    let windowPatterns: [String]
    var autoStart: AutoStartMode

    enum AutoStartMode: String, Codable {
        case auto = "true"
        case prompt = "prompt"
        case disabled = "false"
    }
}

struct AppConfig: Codable {
    var apps: [MonitoredApp]

    static let `default` = AppConfig(apps: [
        MonitoredApp(
            name: "Zoom",
            bundleId: "us.zoom.xos",
            windowPatterns: ["Zoom Meeting", "Zoom Webinar"],
            autoStart: .prompt
        ),
        MonitoredApp(
            name: "Telegram",
            bundleId: "ru.keepcoder.Telegram",
            windowPatterns: ["Voice Chat", "Video Chat"],
            autoStart: .prompt
        ),
        MonitoredApp(
            name: "Telemost (Arc)",
            bundleId: "company.thebrowser.Browser",
            windowPatterns: ["Telemost", "telemost.yandex"],
            autoStart: .prompt
        )
    ])
}
```

**Step 2: Create WindowMonitor service**

Create `swift/WhisperMeet/Sources/Services/WindowMonitor.swift`:

```swift
import Cocoa
import Combine

class WindowMonitor: ObservableObject {
    @Published var detectedMeeting: DetectedMeeting?
    @Published var isMonitoring = false

    private var timer: Timer?
    private var config: AppConfig

    struct DetectedMeeting {
        let app: MonitoredApp
        let windowTitle: String
        let timestamp: Date
    }

    init(config: AppConfig = .default) {
        self.config = config
    }

    func startMonitoring() {
        isMonitoring = true
        timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.checkForMeetings()
        }
    }

    func stopMonitoring() {
        isMonitoring = false
        timer?.invalidate()
        timer = nil
    }

    private func checkForMeetings() {
        let runningApps = NSWorkspace.shared.runningApplications

        for monitoredApp in config.apps {
            guard let app = runningApps.first(where: { $0.bundleIdentifier == monitoredApp.bundleId }) else {
                continue
            }

            if let windowTitle = getActiveWindowTitle(for: app),
               matchesPattern(windowTitle, patterns: monitoredApp.windowPatterns) {
                let meeting = DetectedMeeting(
                    app: monitoredApp,
                    windowTitle: windowTitle,
                    timestamp: Date()
                )

                DispatchQueue.main.async {
                    self.detectedMeeting = meeting
                }
                return
            }
        }
    }

    private func getActiveWindowTitle(for app: NSRunningApplication) -> String? {
        let appElement = AXUIElementCreateApplication(app.processIdentifier)

        var windowsRef: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(appElement, kAXWindowsAttribute as CFString, &windowsRef)

        guard result == .success,
              let windows = windowsRef as? [AXUIElement],
              let firstWindow = windows.first else {
            return nil
        }

        var titleRef: CFTypeRef?
        AXUIElementCopyAttributeValue(firstWindow, kAXTitleAttribute as CFString, &titleRef)

        return titleRef as? String
    }

    private func matchesPattern(_ title: String, patterns: [String]) -> Bool {
        let lowercasedTitle = title.lowercased()
        return patterns.contains { lowercasedTitle.contains($0.lowercased()) }
    }
}
```

**Step 3: Build and verify**

```bash
cd ~/git/whispermeet/.worktrees/swift/swift/WhisperMeet
swift build
```

Expected: Build succeeds

**Step 4: Commit**

```bash
git add .
git commit -m "feat(swift): add WindowMonitor with Accessibility API

- Polls running apps every 2 seconds
- Matches window titles against patterns
- Supports Zoom, Telegram, Telemost (Arc)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.3: ScreenCaptureKit Audio Capture

**Files:**
- Create: `swift/WhisperMeet/Sources/Services/AudioCapture.swift`
- Modify: `swift/WhisperMeet/Sources/App/AppDelegate.swift`

**Step 1: Create AudioCapture service**

Create `swift/WhisperMeet/Sources/Services/AudioCapture.swift`:

```swift
import ScreenCaptureKit
import AVFoundation
import Combine

class AudioCapture: NSObject, ObservableObject {
    @Published var isRecording = false
    @Published var duration: TimeInterval = 0

    private var stream: SCStream?
    private var audioFile: AVAudioFile?
    private var startTime: Date?
    private var durationTimer: Timer?

    private let outputDirectory: URL

    override init() {
        let transcriptsPath = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Transcripts")
        self.outputDirectory = transcriptsPath

        super.init()

        try? FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
    }

    func startRecording(appBundleId: String) async throws -> URL {
        let content = try await SCShareableContent.current

        guard let app = content.applications.first(where: { $0.bundleIdentifier == appBundleId }) else {
            throw CaptureError.appNotFound
        }

        let filter = SCContentFilter(desktopIndependentWindow: content.windows.first { $0.owningApplication?.bundleIdentifier == appBundleId }!)

        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.sampleRate = 16000
        config.channelCount = 1

        let outputURL = createOutputURL(for: app.applicationName)
        audioFile = try createAudioFile(at: outputURL)

        stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream?.addStreamOutput(self, type: .audio, sampleHandlerQueue: .main)
        try await stream?.startCapture()

        startTime = Date()
        isRecording = true
        startDurationTimer()

        return outputURL
    }

    func stopRecording() async throws {
        try await stream?.stopCapture()
        stream = nil
        audioFile = nil
        isRecording = false
        stopDurationTimer()
        duration = 0
    }

    private func createOutputURL(for appName: String) -> URL {
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd-HHmmss"
        let timestamp = dateFormatter.string(from: Date())
        let safeName = appName.replacingOccurrences(of: " ", with: "-").lowercased()
        return outputDirectory.appendingPathComponent("\(timestamp)-\(safeName).wav")
    }

    private func createAudioFile(at url: URL) throws -> AVAudioFile {
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: 16000,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false
        ]
        return try AVAudioFile(forWriting: url, settings: settings)
    }

    private func startDurationTimer() {
        durationTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            guard let self, let start = self.startTime else { return }
            self.duration = Date().timeIntervalSince(start)
        }
    }

    private func stopDurationTimer() {
        durationTimer?.invalidate()
        durationTimer = nil
    }

    enum CaptureError: Error {
        case appNotFound
        case audioFileCreationFailed
    }
}

extension AudioCapture: SCStreamDelegate {
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        print("Stream stopped with error: \(error)")
        isRecording = false
    }
}

extension AudioCapture: SCStreamOutput {
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio,
              let audioFile,
              let samples = sampleBuffer.asPCMBuffer else { return }

        try? audioFile.write(from: samples)
    }
}

extension CMSampleBuffer {
    var asPCMBuffer: AVAudioPCMBuffer? {
        guard let formatDescription = formatDescription,
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(formatDescription) else {
            return nil
        }

        let format = AVAudioFormat(streamDescription: asbd)!
        let numSamples = CMSampleBufferGetNumSamples(self)

        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(numSamples)) else {
            return nil
        }

        buffer.frameLength = AVAudioFrameCount(numSamples)
        CMSampleBufferCopyPCMDataIntoAudioBufferList(self, at: 0, frameCount: Int32(numSamples), into: buffer.mutableAudioBufferList)

        return buffer
    }
}
```

**Step 2: Add entitlements file**

Create `swift/WhisperMeet/Resources/WhisperMeet.entitlements`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.app-sandbox</key>
    <false/>
    <key>com.apple.security.device.audio-input</key>
    <true/>
</dict>
</plist>
```

**Step 3: Build and verify**

```bash
cd ~/git/whispermeet/.worktrees/swift/swift/WhisperMeet
swift build
```

Expected: Build succeeds

**Step 4: Commit**

```bash
git add .
git commit -m "feat(swift): add ScreenCaptureKit audio capture

- Captures app audio at 16kHz mono WAV
- Saves to ~/Transcripts with timestamp
- Tracks recording duration

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 2: Python — Core Infrastructure

### Task 2.1: Create Python Project Structure

**Files:**
- Create: `python/pyproject.toml`
- Create: `python/whispermeet/__init__.py`
- Create: `python/whispermeet/app.py`

**Step 1: Create directory structure**

```bash
cd ~/git/whispermeet/.worktrees/python
mkdir -p python/whispermeet/{services,models}
mkdir -p python/tests
```

**Step 2: Create pyproject.toml**

Create `python/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "whispermeet"
version = "0.1.0"
description = "macOS meeting transcription app"
requires-python = ">=3.10"
dependencies = [
    "rumps>=0.4.0",
    "pyobjc-framework-ScreenCaptureKit>=10.0",
    "pyobjc-framework-AVFoundation>=10.0",
    "pywhispercpp>=1.0.0",
    "pyannote.audio>=3.0.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]

[project.scripts]
whispermeet = "whispermeet.app:main"
```

**Step 3: Create main app entry point**

Create `python/whispermeet/__init__.py`:

```python
"""WhisperMeet - macOS meeting transcription app."""

__version__ = "0.1.0"
```

Create `python/whispermeet/app.py`:

```python
"""Main application entry point."""

import rumps
from pathlib import Path


class WhisperMeetApp(rumps.App):
    """Menubar application for meeting transcription."""

    def __init__(self):
        super().__init__(
            name="WhisperMeet",
            icon=None,  # Will use default
            template=True,  # For dark/light mode
        )
        self.recording = False
        self.menu = [
            rumps.MenuItem("Start Manual Recording", callback=self.start_recording),
            None,  # Separator
            rumps.MenuItem("Recent Transcripts"),
            None,
            rumps.MenuItem("Settings...", callback=self.open_settings),
        ]

    @rumps.clicked("Start Manual Recording")
    def start_recording(self, sender):
        """Toggle recording state."""
        if not self.recording:
            self.recording = True
            sender.title = "Stop Recording"
            self.title = "● WhisperMeet"
            rumps.notification(
                title="WhisperMeet",
                subtitle="Recording started",
                message="Audio capture is now active",
            )
        else:
            self.recording = False
            sender.title = "Start Manual Recording"
            self.title = "WhisperMeet"
            rumps.notification(
                title="WhisperMeet",
                subtitle="Recording stopped",
                message="Processing transcript...",
            )

    def open_settings(self, _):
        """Open settings window."""
        rumps.alert("Settings", "Settings window not yet implemented")


def main():
    """Run the WhisperMeet application."""
    app = WhisperMeetApp()
    app.run()


if __name__ == "__main__":
    main()
```

**Step 4: Create virtual environment and install**

```bash
cd ~/git/whispermeet/.worktrees/python/python
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**Step 5: Test run**

```bash
cd ~/git/whispermeet/.worktrees/python/python
source .venv/bin/activate
python -m whispermeet.app
```

Expected: Menubar icon appears (Ctrl+C to exit)

**Step 6: Commit**

```bash
git add .
git commit -m "feat(python): add menubar app skeleton with rumps

- Basic rumps menubar app structure
- Start/stop recording toggle
- Notification support

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2.2: Window Monitor Service (Python)

**Files:**
- Create: `python/whispermeet/services/window_monitor.py`
- Create: `python/whispermeet/models/config.py`
- Create: `python/tests/test_window_monitor.py`

**Step 1: Write failing test**

Create `python/tests/test_window_monitor.py`:

```python
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
```

**Step 2: Run test to verify it fails**

```bash
cd ~/git/whispermeet/.worktrees/python/python
source .venv/bin/activate
pytest tests/test_window_monitor.py -v
```

Expected: FAIL with ModuleNotFoundError

**Step 3: Create config model**

Create `python/whispermeet/models/__init__.py`:

```python
"""Models package."""

from .config import MonitoredApp, AppConfig

__all__ = ["MonitoredApp", "AppConfig"]
```

Create `python/whispermeet/models/config.py`:

```python
"""Configuration models."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml


class AutoStartMode(Enum):
    """Auto-start behavior for monitored apps."""

    AUTO = "true"
    PROMPT = "prompt"
    DISABLED = "false"


@dataclass
class MonitoredApp:
    """Configuration for a monitored application."""

    name: str
    bundle_id: str
    window_patterns: list[str]
    auto_start: AutoStartMode = AutoStartMode.PROMPT


@dataclass
class AppConfig:
    """Application configuration."""

    apps: list[MonitoredApp] = field(default_factory=list)
    transcripts_dir: Path = field(
        default_factory=lambda: Path.home() / "Transcripts"
    )

    @classmethod
    def default(cls) -> "AppConfig":
        """Create default configuration."""
        return cls(
            apps=[
                MonitoredApp(
                    name="Zoom",
                    bundle_id="us.zoom.xos",
                    window_patterns=["Zoom Meeting", "Zoom Webinar"],
                ),
                MonitoredApp(
                    name="Telegram",
                    bundle_id="ru.keepcoder.Telegram",
                    window_patterns=["Voice Chat", "Video Chat"],
                ),
                MonitoredApp(
                    name="Telemost (Arc)",
                    bundle_id="company.thebrowser.Browser",
                    window_patterns=["Telemost", "telemost.yandex"],
                ),
            ]
        )

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        """Load configuration from YAML file."""
        if not path.exists():
            return cls.default()

        with open(path) as f:
            data = yaml.safe_load(f)

        apps = [
            MonitoredApp(
                name=app["name"],
                bundle_id=app["bundle_id"],
                window_patterns=app["window_patterns"],
                auto_start=AutoStartMode(app.get("auto_start", "prompt")),
            )
            for app in data.get("apps", [])
        ]

        return cls(apps=apps)
```

**Step 4: Create WindowMonitor service**

Create `python/whispermeet/services/__init__.py`:

```python
"""Services package."""

from .window_monitor import WindowMonitor

__all__ = ["WindowMonitor"]
```

Create `python/whispermeet/services/window_monitor.py`:

```python
"""Window monitoring service using macOS Accessibility API."""

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from AppKit import NSWorkspace
from Quartz import (
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
```

**Step 5: Run tests to verify they pass**

```bash
cd ~/git/whispermeet/.worktrees/python/python
source .venv/bin/activate
pytest tests/test_window_monitor.py -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add .
git commit -m "feat(python): add WindowMonitor with Accessibility API

- Config model with default apps (Zoom, Telegram, Telemost)
- Case-insensitive pattern matching
- Background thread monitoring

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2.3: Transcription Service (Python)

**Files:**
- Create: `python/whispermeet/services/transcriber.py`
- Create: `python/tests/test_transcriber.py`

**Step 1: Write failing test**

Create `python/tests/test_transcriber.py`:

```python
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
```

**Step 2: Run test to verify it fails**

```bash
cd ~/git/whispermeet/.worktrees/python/python
source .venv/bin/activate
pytest tests/test_transcriber.py -v
```

Expected: FAIL with ModuleNotFoundError

**Step 3: Create Transcriber service**

Create `python/whispermeet/services/transcriber.py`:

```python
"""Transcription service using whisper.cpp."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterator

from pywhispercpp.model import Model


@dataclass
class TranscriptSegment:
    """A segment of transcribed text."""

    start: float  # seconds
    end: float  # seconds
    text: str
    speaker: Optional[str] = None

    def format(self) -> str:
        """Format segment with timestamp."""
        start_str = self._format_time(self.start)
        end_str = self._format_time(self.end)

        if self.speaker:
            return f"[{start_str} - {end_str}] {self.speaker}: {self.text}"
        return f"[{start_str} - {end_str}] {self.text}"

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as MM:SS."""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"


class Transcriber:
    """Transcription service using whisper.cpp."""

    MODELS_DIR = Path.home() / ".cache" / "whisper"

    def __init__(self, model: str = "base"):
        self.model_name = model
        self._model: Optional[Model] = None

    def _ensure_model(self):
        """Load model if not already loaded."""
        if self._model is None:
            model_path = self.MODELS_DIR / f"ggml-{self.model_name}.bin"
            if not model_path.exists():
                self._download_model()
            self._model = Model(str(model_path))

    def _download_model(self):
        """Download whisper model."""
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        # whisper.cpp provides download script
        # For now, assume model exists or raise error
        raise FileNotFoundError(
            f"Model {self.model_name} not found. "
            f"Please download to {self.MODELS_DIR}"
        )

    def transcribe(self, audio_path: Path) -> list[TranscriptSegment]:
        """Transcribe an audio file."""
        self._ensure_model()

        segments = []
        result = self._model.transcribe(str(audio_path))

        for seg in result:
            segments.append(
                TranscriptSegment(
                    start=seg.t0 / 100.0,  # centiseconds to seconds
                    end=seg.t1 / 100.0,
                    text=seg.text.strip(),
                )
            )

        return segments

    def transcribe_realtime(self, audio_path: Path) -> Iterator[TranscriptSegment]:
        """Transcribe audio file with streaming output."""
        self._ensure_model()

        for seg in self._model.transcribe(str(audio_path)):
            yield TranscriptSegment(
                start=seg.t0 / 100.0,
                end=seg.t1 / 100.0,
                text=seg.text.strip(),
            )


class TwoStageTranscriber:
    """Two-stage transcriber: fast for realtime, large for final."""

    def __init__(
        self,
        realtime_model: str = "base",
        final_model: str = "large-v3",
    ):
        self.realtime = Transcriber(model=realtime_model)
        self.final = Transcriber(model=final_model)

    def transcribe_realtime(self, audio_path: Path) -> Iterator[TranscriptSegment]:
        """Get realtime transcription (draft quality)."""
        return self.realtime.transcribe_realtime(audio_path)

    def transcribe_final(self, audio_path: Path) -> list[TranscriptSegment]:
        """Get final high-quality transcription."""
        return self.final.transcribe(audio_path)
```

**Step 4: Update services __init__.py**

Edit `python/whispermeet/services/__init__.py`:

```python
"""Services package."""

from .window_monitor import WindowMonitor
from .transcriber import Transcriber, TranscriptSegment, TwoStageTranscriber

__all__ = [
    "WindowMonitor",
    "Transcriber",
    "TranscriptSegment",
    "TwoStageTranscriber",
]
```

**Step 5: Run tests to verify they pass**

```bash
cd ~/git/whispermeet/.worktrees/python/python
source .venv/bin/activate
pytest tests/test_transcriber.py -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add .
git commit -m "feat(python): add Transcriber service with whisper.cpp

- TranscriptSegment with timestamp formatting
- Two-stage transcription (realtime + final)
- Model path management

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2.4: Claude Summary Service (Python)

**Files:**
- Create: `python/whispermeet/services/summary.py`
- Create: `python/tests/test_summary.py`
- Create: `python/whispermeet/prompts/summary.md`

**Step 1: Write failing test**

Create `python/tests/test_summary.py`:

```python
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
```

**Step 2: Run test to verify it fails**

```bash
cd ~/git/whispermeet/.worktrees/python/python
source .venv/bin/activate
pytest tests/test_summary.py -v
```

Expected: FAIL with ModuleNotFoundError

**Step 3: Create summary prompt template**

Create `python/whispermeet/prompts/summary.md`:

```markdown
Generate a meeting summary from the following transcript.

IMPORTANT:
- Headers MUST be in English
- Content should be in the same language as the transcript
- Extract action items with assignee names
- Identify key decisions made
- Keep TL;DR to 2-3 sentences

Transcript:
{transcript}

Participants: {participants}
Duration: {duration}

Output format (use exactly these headers):

# Meeting Summary: {title}
**Date:** {date}
**Duration:** {duration}
**Participants:** {participants}

## TL;DR
[2-3 sentence overview]

## Key Decisions
- [Decision with context]

## Action Items
- [ ] [Name]: [Task description]

## Discussion Points
1. **[Topic]** — [Brief summary]
```

**Step 4: Create Summary service**

Create `python/whispermeet/services/summary.py`:

```python
"""Meeting summary generation using Claude Code CLI."""

import subprocess
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MeetingSummary:
    """Structured meeting summary."""

    title: str
    date: str
    duration: str
    participants: list[str]
    tldr: str
    key_decisions: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    discussion_points: list[str] = field(default_factory=list)
    notable_quotes: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert summary to markdown format."""
        participants_str = ", ".join(self.participants)

        lines = [
            f"# Meeting Summary: {self.title}",
            f"**Date:** {self.date}",
            f"**Duration:** {self.duration}",
            f"**Participants:** {participants_str}",
            "",
            "## TL;DR",
            self.tldr,
            "",
        ]

        if self.key_decisions:
            lines.extend(["## Key Decisions"])
            for decision in self.key_decisions:
                lines.append(f"- {decision}")
            lines.append("")

        if self.action_items:
            lines.extend(["## Action Items"])
            for item in self.action_items:
                if item.startswith("[ ]") or item.startswith("[x]"):
                    lines.append(f"- {item}")
                else:
                    lines.append(f"- [ ] {item}")
            lines.append("")

        if self.discussion_points:
            lines.extend(["## Discussion Points"])
            for i, point in enumerate(self.discussion_points, 1):
                lines.append(f"{i}. {point}")
            lines.append("")

        if self.notable_quotes:
            lines.extend(["## Notable Quotes"])
            for quote in self.notable_quotes:
                lines.append(f"> {quote}")
            lines.append("")

        return "\n".join(lines)


class SummaryGenerator:
    """Generate meeting summaries using Claude Code CLI."""

    PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

    def __init__(self, prompt_path: Optional[Path] = None):
        if prompt_path:
            self.prompt_template = prompt_path.read_text()
        else:
            default_prompt = self.PROMPTS_DIR / "summary.md"
            if default_prompt.exists():
                self.prompt_template = default_prompt.read_text()
            else:
                self.prompt_template = self._default_prompt()

    def _default_prompt(self) -> str:
        """Return default prompt if file not found."""
        return """Generate a meeting summary from the transcript.
Use English headers, content in transcript language.

Transcript:
{transcript}

Format as markdown with sections:
- TL;DR
- Key Decisions
- Action Items
- Discussion Points
"""

    def generate(
        self,
        transcript: str,
        title: str,
        date: str,
        duration: str,
        participants: list[str],
    ) -> MeetingSummary:
        """Generate summary using Claude Code CLI."""
        prompt = self.prompt_template.format(
            transcript=transcript,
            title=title,
            date=date,
            duration=duration,
            participants=", ".join(participants),
        )

        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI failed: {result.stderr}")

        # Parse the markdown response
        return self._parse_response(
            result.stdout,
            title=title,
            date=date,
            duration=duration,
            participants=participants,
        )

    def _parse_response(
        self,
        response: str,
        title: str,
        date: str,
        duration: str,
        participants: list[str],
    ) -> MeetingSummary:
        """Parse Claude's markdown response into structured summary."""
        # Basic parsing - extract sections
        tldr = ""
        key_decisions = []
        action_items = []
        discussion_points = []

        current_section = None

        for line in response.split("\n"):
            line = line.strip()

            if "## TL;DR" in line:
                current_section = "tldr"
            elif "## Key Decisions" in line:
                current_section = "decisions"
            elif "## Action Items" in line:
                current_section = "actions"
            elif "## Discussion Points" in line:
                current_section = "discussion"
            elif line.startswith("## "):
                current_section = None
            elif line and current_section:
                if current_section == "tldr":
                    tldr += line + " "
                elif current_section == "decisions" and line.startswith("-"):
                    key_decisions.append(line[1:].strip())
                elif current_section == "actions" and line.startswith("-"):
                    action_items.append(line[1:].strip())
                elif current_section == "discussion":
                    discussion_points.append(line)

        return MeetingSummary(
            title=title,
            date=date,
            duration=duration,
            participants=participants,
            tldr=tldr.strip(),
            key_decisions=key_decisions,
            action_items=action_items,
            discussion_points=discussion_points,
        )
```

**Step 5: Update services __init__.py**

Edit `python/whispermeet/services/__init__.py`:

```python
"""Services package."""

from .window_monitor import WindowMonitor
from .transcriber import Transcriber, TranscriptSegment, TwoStageTranscriber
from .summary import SummaryGenerator, MeetingSummary

__all__ = [
    "WindowMonitor",
    "Transcriber",
    "TranscriptSegment",
    "TwoStageTranscriber",
    "SummaryGenerator",
    "MeetingSummary",
]
```

**Step 6: Run tests to verify they pass**

```bash
cd ~/git/whispermeet/.worktrees/python/python
source .venv/bin/activate
pytest tests/test_summary.py -v
```

Expected: All tests PASS

**Step 7: Commit**

```bash
git add .
git commit -m "feat(python): add SummaryGenerator with Claude Code CLI

- MeetingSummary dataclass with markdown output
- Claude CLI integration via subprocess
- Customizable prompt template

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 3: Integration

### Task 3.1: Integrate Services into Python App

**Files:**
- Modify: `python/whispermeet/app.py`

**Step 1: Update app with full integration**

Update `python/whispermeet/app.py`:

```python
"""Main application entry point."""

import rumps
import threading
from datetime import datetime
from pathlib import Path

from whispermeet.models.config import AppConfig
from whispermeet.services.window_monitor import WindowMonitor, DetectedMeeting
from whispermeet.services.transcriber import TwoStageTranscriber, TranscriptSegment
from whispermeet.services.summary import SummaryGenerator


class WhisperMeetApp(rumps.App):
    """Menubar application for meeting transcription."""

    def __init__(self):
        super().__init__(
            name="WhisperMeet",
            icon=None,
            template=True,
        )

        self.config = AppConfig.default()
        self.window_monitor = WindowMonitor(self.config)
        self.transcriber = TwoStageTranscriber()
        self.summary_generator = SummaryGenerator()

        self.recording = False
        self.current_meeting: DetectedMeeting | None = None
        self.audio_path: Path | None = None

        self._setup_menu()
        self._start_monitoring()

    def _setup_menu(self):
        """Configure menu items."""
        self.menu = [
            rumps.MenuItem("Start Manual Recording", callback=self.toggle_recording),
            None,
            rumps.MenuItem("Recent Transcripts"),
            None,
            rumps.MenuItem("Settings...", callback=self.open_settings),
        ]

    def _start_monitoring(self):
        """Start window monitoring for meetings."""
        self.window_monitor.start(self._on_meeting_detected)

    def _on_meeting_detected(self, meeting: DetectedMeeting):
        """Handle detected meeting."""
        if self.recording:
            return

        if meeting.app.auto_start.value == "true":
            self._start_recording_for_meeting(meeting)
        else:
            rumps.notification(
                title="WhisperMeet",
                subtitle=f"{meeting.app.name} detected",
                message="Click to start recording",
            )
            self.current_meeting = meeting

    def toggle_recording(self, sender):
        """Toggle recording state."""
        if not self.recording:
            self._start_recording_for_meeting(self.current_meeting)
            sender.title = "Stop Recording"
        else:
            self._stop_recording()
            sender.title = "Start Manual Recording"

    def _start_recording_for_meeting(self, meeting: DetectedMeeting | None):
        """Start recording for a meeting."""
        self.recording = True
        self.title = "● REC"

        # TODO: Integrate with AudioCapture service
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        app_name = meeting.app.name if meeting else "manual"
        self.audio_path = self.config.transcripts_dir / f"{timestamp}-{app_name}.wav"

        rumps.notification(
            title="WhisperMeet",
            subtitle="Recording started",
            message=f"Recording {meeting.app.name if meeting else 'manual session'}",
        )

    def _stop_recording(self):
        """Stop recording and process transcript."""
        self.recording = False
        self.title = "WhisperMeet"

        rumps.notification(
            title="WhisperMeet",
            subtitle="Recording stopped",
            message="Processing transcript...",
        )

        # Process in background
        if self.audio_path:
            threading.Thread(
                target=self._process_recording,
                args=(self.audio_path, self.current_meeting),
                daemon=True,
            ).start()

        self.audio_path = None
        self.current_meeting = None

    def _process_recording(self, audio_path: Path, meeting: DetectedMeeting | None):
        """Process recording: transcribe and generate summary."""
        try:
            # Final transcription
            segments = self.transcriber.transcribe_final(audio_path)
            transcript_text = "\n".join(seg.format() for seg in segments)

            # Generate summary
            summary = self.summary_generator.generate(
                transcript=transcript_text,
                title=meeting.app.name if meeting else "Manual Recording",
                date=datetime.now().strftime("%Y-%m-%d"),
                duration="Unknown",  # TODO: Calculate from segments
                participants=["Unknown"],  # TODO: From diarization
            )

            # Save files
            base_path = audio_path.parent / audio_path.stem
            base_path.mkdir(parents=True, exist_ok=True)

            (base_path / "transcript.md").write_text(transcript_text)
            (base_path / "summary.md").write_text(summary.to_markdown())

            rumps.notification(
                title="WhisperMeet",
                subtitle="Transcript ready",
                message=f"Saved to {base_path}",
            )
        except Exception as e:
            rumps.notification(
                title="WhisperMeet",
                subtitle="Error",
                message=str(e),
            )

    def open_settings(self, _):
        """Open settings window."""
        rumps.alert("Settings", "Settings window coming soon")


def main():
    """Run the WhisperMeet application."""
    app = WhisperMeetApp()
    app.run()


if __name__ == "__main__":
    main()
```

**Step 2: Test the integrated app**

```bash
cd ~/git/whispermeet/.worktrees/python/python
source .venv/bin/activate
python -m whispermeet.app
```

Expected: App runs with window monitoring active

**Step 3: Commit**

```bash
git add .
git commit -m "feat(python): integrate all services into main app

- Window monitoring with meeting detection
- Two-stage transcription pipeline
- Claude summary generation
- Background processing

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Execution Checklist

- [ ] Phase 1: Swift Core (Tasks 1.1-1.3)
- [ ] Phase 2: Python Core (Tasks 2.1-2.4)
- [ ] Phase 3: Integration (Task 3.1)
- [ ] Merge feature branches to main
- [ ] Test end-to-end flow
