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
