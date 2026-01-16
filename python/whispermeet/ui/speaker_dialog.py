"""Speaker name assignment dialog using PyObjC."""

from pathlib import Path
from typing import Optional
import subprocess

try:
    from AppKit import (
        NSApplication,
        NSWindow,
        NSTextField,
        NSButton,
        NSView,
        NSFont,
        NSColor,
        NSWindowStyleMaskTitled,
        NSWindowStyleMaskClosable,
        NSBackingStoreBuffered,
        NSMakeRect,
        NSApp,
    )
    HAS_APPKIT = True
except ImportError:
    HAS_APPKIT = False


class SpeakerNamesDialog:
    """Dialog for assigning names to detected speakers."""

    def __init__(
        self,
        speakers: list[str],
        audio_path: Optional[Path] = None,
        speaker_samples: Optional[dict[str, tuple[float, float]]] = None,
    ):
        """
        Args:
            speakers: List of speaker IDs (e.g., ["SPEAKER_00", "SPEAKER_01"])
            audio_path: Path to audio file for playback
            speaker_samples: Dict mapping speaker ID to (start, end) time range
        """
        self.speakers = speakers
        self.audio_path = audio_path
        self.speaker_samples = speaker_samples or {}
        self.result: Optional[dict[str, str]] = None
        self._text_fields: dict[str, "NSTextField"] = {}

    def show(self) -> Optional[dict[str, str]]:
        """Show dialog and return speaker name assignments.

        Returns:
            Dict mapping speaker IDs to names, or None if cancelled
        """
        if not HAS_APPKIT:
            return self._show_fallback()

        return self._show_native()

    def _show_fallback(self) -> Optional[dict[str, str]]:
        """Fallback using rumps for simple input."""
        import rumps

        names = {}
        for i, speaker_id in enumerate(self.speakers, 1):
            response = rumps.Window(
                title=f"Speaker {i}",
                message=f"Enter name for {speaker_id}:",
                default_text=f"Speaker {i}",
                ok="Save",
                cancel="Skip",
            ).run()

            if response.clicked:
                names[speaker_id] = response.text or f"Speaker {i}"
            else:
                names[speaker_id] = f"Speaker {i}"

        return names

    def _show_native(self) -> Optional[dict[str, str]]:
        """Show native macOS dialog using PyObjC."""
        # Calculate window size
        row_height = 40
        window_height = 120 + (len(self.speakers) * row_height)
        window_width = 400

        # Create window
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, window_width, window_height),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        window.setTitle_("Assign Speaker Names")
        window.center()

        content_view = window.contentView()

        # Title label
        title_label = NSTextField.labelWithString_("Who was speaking?")
        title_label.setFont_(NSFont.boldSystemFontOfSize_(14))
        title_label.setFrame_(NSMakeRect(20, window_height - 50, window_width - 40, 25))
        content_view.addSubview_(title_label)

        # Speaker rows
        y_offset = window_height - 90
        for i, speaker_id in enumerate(self.speakers):
            # Label
            label = NSTextField.labelWithString_(f"Speaker {i + 1}:")
            label.setFrame_(NSMakeRect(20, y_offset, 80, 25))
            content_view.addSubview_(label)

            # Text field
            text_field = NSTextField.alloc().initWithFrame_(
                NSMakeRect(110, y_offset, 180, 25)
            )
            text_field.setStringValue_(f"Speaker {i + 1}")
            text_field.setPlaceholderString_("Enter name")
            content_view.addSubview_(text_field)
            self._text_fields[speaker_id] = text_field

            # Play button (if we have samples)
            if speaker_id in self.speaker_samples and self.audio_path:
                play_btn = NSButton.alloc().initWithFrame_(
                    NSMakeRect(300, y_offset, 80, 25)
                )
                play_btn.setTitle_("▶ Play")
                play_btn.setBezelStyle_(1)  # Rounded
                play_btn.setTarget_(self)
                play_btn.setAction_("playSample:")
                play_btn.setTag_(i)
                content_view.addSubview_(play_btn)

            y_offset -= row_height

        # Checkbox for "Remember"
        remember_checkbox = NSButton.alloc().initWithFrame_(
            NSMakeRect(20, 50, 250, 20)
        )
        remember_checkbox.setButtonType_(3)  # Switch/Checkbox
        remember_checkbox.setTitle_("Remember for future calls")
        remember_checkbox.setState_(1)  # Checked by default
        content_view.addSubview_(remember_checkbox)
        self._remember_checkbox = remember_checkbox

        # Buttons
        save_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(window_width - 100, 15, 80, 30)
        )
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(1)
        save_btn.setKeyEquivalent_("\r")  # Enter key
        save_btn.setTarget_(self)
        save_btn.setAction_("saveClicked:")
        content_view.addSubview_(save_btn)

        skip_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(window_width - 190, 15, 80, 30)
        )
        skip_btn.setTitle_("Skip")
        skip_btn.setBezelStyle_(1)
        skip_btn.setTarget_(self)
        skip_btn.setAction_("skipClicked:")
        content_view.addSubview_(skip_btn)

        # Store window reference and show
        self._window = window
        self._should_save = False

        # Run modal
        window.makeKeyAndOrderFront_(None)
        NSApp.runModalForWindow_(window)

        if self._should_save:
            return {
                speaker_id: tf.stringValue() or f"Speaker {i + 1}"
                for i, (speaker_id, tf) in enumerate(self._text_fields.items())
            }
        return None

    def saveClicked_(self, sender):
        """Handle Save button click."""
        self._should_save = True
        NSApp.stopModal()
        self._window.close()

    def skipClicked_(self, sender):
        """Handle Skip button click."""
        self._should_save = False
        NSApp.stopModal()
        self._window.close()

    def playSample_(self, sender):
        """Play voice sample for speaker."""
        if not self.audio_path:
            return

        speaker_idx = sender.tag()
        speaker_id = self.speakers[speaker_idx]

        if speaker_id not in self.speaker_samples:
            return

        start, end = self.speaker_samples[speaker_id]

        # Use ffplay to play sample
        try:
            subprocess.Popen(
                [
                    "ffplay",
                    "-nodisp",
                    "-autoexit",
                    "-ss", str(start),
                    "-t", str(end - start),
                    str(self.audio_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            # ffplay not available, try afplay with temp file
            pass


def show_speaker_names_dialog(
    speakers: list[str],
    audio_path: Optional[Path] = None,
    speaker_samples: Optional[dict[str, tuple[float, float]]] = None,
) -> Optional[dict[str, str]]:
    """Convenience function to show speaker names dialog.

    Returns:
        Dict mapping speaker IDs to names, or None if cancelled
    """
    dialog = SpeakerNamesDialog(speakers, audio_path, speaker_samples)
    return dialog.show()
