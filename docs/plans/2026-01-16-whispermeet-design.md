# WhisperMeet Design Document

**Date:** 2026-01-16
**Status:** Approved
**Author:** Terry + Claude

## Overview

macOS menubar application for automatic meeting transcription with speaker diarization and AI-powered summaries.

**Target apps:** Zoom, Telegram, Yandex Telemost (including browser via Arc)

## Requirements Summary

- macOS menubar app with light/dark theme support
- Auto-detect meeting start via window monitoring
- Audio capture via ScreenCaptureKit (system audio + microphone)
- Two-stage transcription: realtime (tiny/base) + post-processing (large-v3)
- Speaker diarization with name assignment
- Automatic summary generation via Claude Code CLI
- Storage as Markdown files in configurable directory (`~/Transcripts`)
- Optional export to Obsidian/Notion
- Parallel development: Swift/SwiftUI and Python versions
- UI language: English
- Transcript/summary content: language of the conversation

---

## Architecture

```
┌─────────────────────────────────────────┐
│           UI Layer (Menubar)            │
│  - Recording status indicator           │
│  - Transcript history                   │
│  - Settings                             │
└─────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────┐
│          Core Services                   │
│  - WindowMonitor (meeting detection)    │
│  - AudioCapture (ScreenCaptureKit)      │
│  - Transcriber (whisper.cpp)            │
│  - SpeakerDiarizer (pyannote/whisperX)  │
│  - SummaryGenerator (Claude Code CLI)   │
└─────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────┐
│          Storage Layer                   │
│  - ~/Transcripts/                       │
│  - Markdown files                       │
│  - Audio files (optional)               │
└─────────────────────────────────────────┘
```

**Recording lifecycle:**

1. WindowMonitor detects meeting window → notification "Start recording?"
2. User confirms → ScreenCaptureKit requests permission
3. Recording + realtime transcription (tiny/base model)
4. Meeting window closed → stop recording
5. Background re-transcription (large-v3) + diarization
6. Claude Code CLI generates summary
7. Save Markdown + optional export

---

## Meeting Detection (WindowMonitor)

Uses macOS Accessibility API (`AXUIElement`) to monitor windows. Polling every 2-3 seconds.

### App Configuration

```yaml
# ~/.config/whispermeet/apps.yaml
apps:
  - name: Zoom
    bundle_id: us.zoom.xos
    window_patterns:
      - "Zoom Meeting"
      - "Zoom Webinar"
    auto_start: true

  - name: Telegram
    bundle_id: ru.keepcoder.Telegram
    window_patterns:
      - "Voice Chat"
      - "Video Chat"
    auto_start: prompt

  - name: Telemost (Web)
    bundle_id: company.thebrowser.Browser  # Arc
    window_patterns:
      - "Telemost"
      - "telemost.yandex"
    capture_mode: window

  - name: Google Meet
    bundle_id: company.thebrowser.Browser
    window_patterns:
      - "Meet -"
      - "meet.google.com"
    auto_start: prompt
```

### Start modes

- `auto_start: true` — recording starts automatically
- `auto_start: prompt` — shows notification with "Record" / "Skip" buttons

---

## Audio Capture (ScreenCaptureKit)

### Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Zoom/Arc/     │────▶│ ScreenCaptureKit│
│   Telegram      │     │  (System Audio) │
└─────────────────┘     └────────┬────────┘
                                 │
┌─────────────────┐              │
│   Microphone    │──────────────┼────────┐
│   (your voice)  │              │        │
└─────────────────┘              ▼        ▼
                        ┌─────────────────┐
                        │   AudioMixer    │
                        │   (combine)     │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  WAV/M4A file   │
                        │  + Transcriber  │
                        └─────────────────┘
```

### Two audio streams

1. **System audio** — participants' voices (via ScreenCaptureKit)
2. **Microphone** — your voice (via AVAudioEngine)

Both streams are mixed into a single file for transcription.

### Recording format

- **During call:** WAV 16kHz mono (optimal for Whisper)
- **After call:** optionally save original as M4A (~10x compression)

---

## Transcription and Speaker Diarization

### Two-stage transcription

```
During call                     After call
─────────────                   ──────────
     │                               │
     ▼                               ▼
┌─────────────┐               ┌─────────────┐
│ tiny/base   │               │  large-v3   │
│ ~150MB      │               │  ~3GB       │
│ realtime    │               │  quality    │
└──────┬──────┘               └──────┬──────┘
       │                             │
       ▼                             ▼
  Preview in UI               Final transcript
  (draft)                     + timestamps
```

### Speaker Diarization

Using `pyannote-audio` or `whisperX` to identify speaker segments.

```
[00:00 - 00:15] Speaker 1: "Let's discuss the roadmap..."
[00:15 - 00:42] Speaker 2: "I think we should focus on..."
[00:42 - 01:03] Speaker 1: "Agreed, and also..."
```

### Name Assignment (post-call UI)

```
┌─────────────────────────────────────────────┐
│  Assign Speaker Names                       │
│                                             │
│  Speaker 1: [Terry_____________]  ▶ Play    │
│  Speaker 2: [John______________]  ▶ Play    │
│  Speaker 3: [___________________] ▶ Play    │
│                                             │
│  ☑ Remember for future calls                │
│                                             │
│            [Skip]        [Save]             │
└─────────────────────────────────────────────┘
```

**Voice Fingerprinting (optional):** If "Remember" is enabled, app saves voice fingerprint for automatic name suggestions in future calls.

---

## Summary Generation (Claude Code CLI)

### Integration

```python
subprocess.run([
    "claude",
    "-p", f"Generate meeting summary from transcript:\n\n{transcript}",
    "--output-format", "text"
], capture_output=True)
```

Uses existing Claude Code authorization — no separate API key needed.

### Summary Structure

```markdown
# Meeting Summary: Zoom call with John, Alex
**Date:** 2026-01-16 14:30
**Duration:** 45 minutes
**Participants:** Terry, John, Alex

## TL;DR
Brief 2-3 sentence overview of the meeting.

## Key Decisions
- Decision 1 with context
- Decision 2 with context

## Action Items
- [ ] Terry: Complete the design doc by Friday
- [ ] John: Review PR #234
- [ ] Alex: Schedule follow-up with client

## Discussion Points
1. **Topic 1** — brief summary of discussion
2. **Topic 2** — brief summary of discussion

## Notable Quotes
> "We should ship this before the deadline" — John

---
*Full transcript: [[2026-01-16-zoom-john-alex-transcript]]*
```

**Note:** Headers in English, content in conversation language.

### Settings

```
┌─────────────────────────────────────────────┐
│  Summary Settings                           │
│                                             │
│  Language:    [English ▼]                   │
│  Detail level: ○ Brief  ● Standard  ○ Full  │
│                                             │
│  Include:                                   │
│  ☑ Action items                             │
│  ☑ Key decisions                            │
│  ☐ Notable quotes                           │
│  ☑ Discussion points                        │
│                                             │
│  Model: Claude Opus                         │
└─────────────────────────────────────────────┘
```

---

## File Storage

### Base directory (configurable)

```
~/Transcripts/
├── 2026/
│   └── 01/
│       ├── 2026-01-16-zoom-john-alex/
│       │   ├── summary.md
│       │   ├── transcript.md
│       │   ├── audio.m4a (optional)
│       │   └── metadata.json
│       └── 2026-01-16-telegram-mike/
│           └── ...
├── templates/
│   └── summary-prompt.md
└── config.yaml
```

### metadata.json

```json
{
  "id": "uuid-here",
  "date": "2026-01-16T14:30:00",
  "duration_seconds": 2700,
  "app": "Zoom",
  "participants": ["Terry", "John", "Alex"],
  "language": "ru",
  "models": {
    "realtime": "ggml-base",
    "final": "ggml-large-v3"
  },
  "exported_to": ["obsidian"]
}
```

### Settings UI

```
┌─────────────────────────────────────────────┐
│  Storage Settings                           │
│                                             │
│  Base directory:                            │
│  [~/Transcripts____________________] [Browse]│
│                                             │
│  ☑ Organize by year/month                   │
│  ☑ Keep original audio files                │
│  ☐ Compress audio (M4A)                     │
└─────────────────────────────────────────────┘
```

### Integrations

- **Obsidian:** Point vault to `~/Transcripts` or symlink
- **Notion:** Export via Notion API to specified database

---

## UI Design

### Menubar Icon States

```
○ — idle (gray)
● — recording (red, pulsing)
◐ — processing (blue)
```

### Dropdown Menu (idle)

```
┌─────────────────────────────────┐
│  WhisperMeet                    │
├─────────────────────────────────┤
│  ▶ Start Manual Recording       │
├─────────────────────────────────┤
│  Recent Transcripts             │
│    Today                        │
│      ├ Zoom: John, Alex  14:30  │
│      └ Telegram: Mike    11:00  │
│    Yesterday                    │
│      └ Telemost: Team    16:00  │
│    → View All...                │
├─────────────────────────────────┤
│  ⚙ Settings...                  │
│  ⍰ Help                         │
│  ⎋ Quit                         │
└─────────────────────────────────┘
```

### Dropdown Menu (recording)

```
┌─────────────────────────────────┐
│  ● Recording: Zoom              │
│    Duration: 00:12:34           │
├─────────────────────────────────┤
│  ⏸ Pause Recording              │
│  ⏹ Stop Recording               │
├─────────────────────────────────┤
│  Live Preview:                  │
│  "...and I think we should..."  │
└─────────────────────────────────┘
```

### Notifications

**Meeting detected:**
```
┌─────────────────────────────────────────┐
│ 🎙 WhisperMeet                          │
│                                         │
│ Zoom Meeting detected                   │
│ Start recording?                        │
│                                         │
│ [Skip]  [Record]                        │
└─────────────────────────────────────────┘
```

**Transcript ready:**
```
┌─────────────────────────────────────────┐
│ ✓ WhisperMeet                           │
│                                         │
│ Transcript ready                        │
│ "Zoom: John, Alex" — 45 min             │
│                                         │
│ [View Summary]                          │
└─────────────────────────────────────────┘
```

### Theme Support

Follows system appearance (light/dark mode).

```
Light Mode                    Dark Mode
┌─────────────────┐          ┌─────────────────┐
│ bg: #FFFFFF     │          │ bg: #1E1E1E     │
│ text: #000000   │          │ text: #FFFFFF   │
│ accent: #007AFF │          │ accent: #0A84FF │
│ recording: #FF3B30│        │ recording: #FF453A│
└─────────────────┘          └─────────────────┘
```

---

## Implementation: Swift vs Python

### Parallel Development

| Aspect | Swift/SwiftUI | Python |
|--------|---------------|--------|
| **Menubar** | Native `NSStatusItem` | `rumps` library |
| **ScreenCaptureKit** | Native Swift API | `pyobjc-framework-ScreenCaptureKit` |
| **Whisper.cpp** | Swift bindings / C interop | `pywhispercpp` or subprocess |
| **Diarization** | Harder (no pyannote) | `pyannote-audio` native |
| **Claude CLI** | `Process()` subprocess | `subprocess.run()` |
| **App size** | ~15-20 MB | ~200+ MB (Python runtime) |
| **Autostart** | `LaunchAgent` plist | `LaunchAgent` plist |

### Development Phases

```
Phase 1 (parallel):
├── Swift: UI + ScreenCaptureKit + WindowMonitor
└── Python: Transcription + Diarization + Claude CLI

Phase 2 (integration):
└── Swift calls Python backend for heavy tasks
    OR
    Python app with native macOS bindings
```

### Repository Structure

```
whispermeet/
├── swift/
│   ├── WhisperMeet.xcodeproj
│   └── Sources/
├── python/
│   ├── whispermeet/
│   ├── pyproject.toml
│   └── requirements.txt
├── shared/
│   └── prompts/
│       └── summary-prompt.md
└── docs/
    └── plans/
```

---

## Code Signing for Development

### Problem

macOS requires signing and entitlements for:
- ScreenCaptureKit (screen/audio capture)
- Microphone
- Accessibility API (window monitoring)

### Swift Solution

```
Xcode → Signing & Capabilities

☑ Automatically manage signing
Team: [Personal Team]  ← Free Apple ID
Signing Certificate: Development (NOT Distribution)
```

### Entitlements (WhisperMeet.entitlements)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>com.apple.security.app-sandbox</key>
    <false/>

    <key>com.apple.security.device.audio-input</key>
    <true/>

    <key>com.apple.security.screen-capture.allow</key>
    <true/>
</dict>
</plist>
```

### Info.plist — Permission Descriptions

```xml
<key>NSMicrophoneUsageDescription</key>
<string>WhisperMeet needs microphone access to record your voice during calls.</string>

<key>NSScreenCaptureUsageDescription</key>
<string>WhisperMeet needs screen capture to record meeting audio.</string>
```

### Python — Ad-hoc Signing

```bash
codesign --sign - --force --deep ./WhisperMeet.app
```

### Troubleshooting

| Problem | Solution |
|---------|----------|
| "App is damaged" | `xattr -cr ./WhisperMeet.app` |
| "Not notarized" | System Settings → Privacy → Open Anyway |
| Entitlements not working | Disable "Hardened Runtime" in Debug |
| Rebuild loses permissions | Use `make dev-sign` script |

### Makefile

```makefile
dev-sign:
	codesign --sign - --force --deep --entitlements dev.entitlements ./build/WhisperMeet.app
	xattr -cr ./build/WhisperMeet.app

dev-run: dev-sign
	./build/WhisperMeet.app/Contents/MacOS/WhisperMeet
```

---

## Future Enhancements (Backlog)

- [ ] MCP server for Claude Code integration
- [ ] Voice fingerprint database for automatic speaker identification
- [ ] Calendar integration (auto-detect scheduled meetings)
- [ ] Real-time translation
- [ ] Custom summary prompts per meeting type

---

## Next Steps

1. Set up git repository with structure above
2. Create isolated worktrees for Swift and Python development
3. Write detailed implementation plan
4. Begin parallel development with subagents
