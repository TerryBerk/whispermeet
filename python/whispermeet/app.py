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
        safe_name = app_name.replace(" ", "-").lower()
        self.audio_path = self.config.transcripts_dir / f"{timestamp}-{safe_name}.wav"

        # Ensure directory exists
        self.config.transcripts_dir.mkdir(parents=True, exist_ok=True)

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
