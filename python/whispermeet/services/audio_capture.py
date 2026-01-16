"""Audio capture service using ScreenCaptureKit."""

import wave
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

try:
    import ScreenCaptureKit
    from ScreenCaptureKit import (
        SCShareableContent,
        SCContentFilter,
        SCStreamConfiguration,
        SCStream,
    )
    from CoreMedia import (
        CMSampleBufferGetNumSamples,
        CMSampleBufferGetDataBuffer,
        CMBlockBufferGetDataLength,
        CMBlockBufferCopyDataBytes,
    )
    HAS_SCREENCAPTUREKIT = True
except ImportError:
    HAS_SCREENCAPTUREKIT = False


@dataclass
class RecordingState:
    """Current recording state."""
    is_recording: bool = False
    duration: float = 0.0
    output_path: Optional[Path] = None


class AudioCapture:
    """Captures audio from applications using ScreenCaptureKit."""

    SAMPLE_RATE = 16000
    CHANNELS = 1
    SAMPLE_WIDTH = 2  # 16-bit

    def __init__(self, output_directory: Optional[Path] = None):
        self.output_directory = output_directory or (Path.home() / "Transcripts")
        self.output_directory.mkdir(parents=True, exist_ok=True)

        self._state = RecordingState()
        self._stream: Optional["SCStream"] = None
        self._wave_file: Optional[wave.Wave_write] = None
        self._start_time: Optional[datetime] = None
        self._duration_timer: Optional[threading.Timer] = None
        self._on_duration_update: Optional[Callable[[float], None]] = None

    @property
    def is_recording(self) -> bool:
        return self._state.is_recording

    @property
    def duration(self) -> float:
        return self._state.duration

    @property
    def output_path(self) -> Optional[Path]:
        return self._state.output_path

    def _create_output_url(self, app_name: str) -> Path:
        """Create timestamped output file path."""
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        safe_name = app_name.replace(" ", "-").lower()
        return self.output_directory / f"{timestamp}-{safe_name}.wav"

    async def start_recording(
        self,
        app_bundle_id: str,
        on_duration_update: Optional[Callable[[float], None]] = None,
    ) -> Path:
        """Start recording audio from specified application."""
        if not HAS_SCREENCAPTUREKIT:
            raise RuntimeError("ScreenCaptureKit not available. Requires macOS 12.3+")

        if self._state.is_recording:
            raise RuntimeError("Already recording")

        self._on_duration_update = on_duration_update

        # Get shareable content using completion handler pattern
        content = await self._get_shareable_content()

        # Find the target application
        target_app = None
        for app in content.applications():
            if app.bundleIdentifier() == app_bundle_id:
                target_app = app
                break

        if not target_app:
            raise ValueError(f"Application not found: {app_bundle_id}")

        # Find a window for the app
        target_window = None
        for window in content.windows():
            owning_app = window.owningApplication()
            if owning_app and owning_app.bundleIdentifier() == app_bundle_id:
                target_window = window
                break

        if not target_window:
            raise ValueError(f"No window found for: {app_bundle_id}")

        # Create content filter
        filter = SCContentFilter.alloc().initWithDesktopIndependentWindow_(target_window)

        # Configure stream for audio only
        config = SCStreamConfiguration.alloc().init()
        config.setCapturesAudio_(True)
        config.setExcludesCurrentProcessAudio_(True)
        config.setSampleRate_(self.SAMPLE_RATE)
        config.setChannelCount_(self.CHANNELS)

        # Create output file
        output_path = self._create_output_url(target_app.applicationName())
        self._wave_file = wave.open(str(output_path), 'wb')
        self._wave_file.setnchannels(self.CHANNELS)
        self._wave_file.setsampwidth(self.SAMPLE_WIDTH)
        self._wave_file.setframerate(self.SAMPLE_RATE)

        # Create and start stream
        self._stream = SCStream.alloc().initWithFilter_configuration_delegate_(
            filter, config, self
        )

        # Add stream output
        self._stream.addStreamOutput_type_sampleHandlerQueue_error_(
            self,
            ScreenCaptureKit.SCStreamOutputTypeAudio,
            None,  # Use main queue
            None,
        )

        await self._start_capture()

        # Update state
        self._state.is_recording = True
        self._state.output_path = output_path
        self._start_time = datetime.now()
        self._start_duration_timer()

        return output_path

    async def _get_shareable_content(self):
        """Get shareable content using asyncio."""
        import asyncio

        loop = asyncio.get_event_loop()
        future = loop.create_future()

        def completion_handler(content, error):
            if error:
                loop.call_soon_threadsafe(
                    future.set_exception,
                    RuntimeError(f"Failed to get shareable content: {error}")
                )
            else:
                loop.call_soon_threadsafe(future.set_result, content)

        SCShareableContent.getShareableContentWithCompletionHandler_(completion_handler)
        return await future

    async def _start_capture(self):
        """Start capture using asyncio."""
        import asyncio

        loop = asyncio.get_event_loop()
        future = loop.create_future()

        def completion_handler(error):
            if error:
                loop.call_soon_threadsafe(
                    future.set_exception,
                    RuntimeError(f"Failed to start capture: {error}")
                )
            else:
                loop.call_soon_threadsafe(future.set_result, None)

        self._stream.startCaptureWithCompletionHandler_(completion_handler)
        return await future

    async def _stop_capture(self):
        """Stop capture using asyncio."""
        import asyncio

        loop = asyncio.get_event_loop()
        future = loop.create_future()

        def completion_handler(error):
            if error:
                loop.call_soon_threadsafe(
                    future.set_exception,
                    RuntimeError(f"Failed to stop capture: {error}")
                )
            else:
                loop.call_soon_threadsafe(future.set_result, None)

        self._stream.stopCaptureWithCompletionHandler_(completion_handler)
        return await future

    async def stop_recording(self) -> Optional[Path]:
        """Stop recording and return output file path."""
        if not self._state.is_recording:
            return None

        output_path = self._state.output_path

        # Stop stream
        if self._stream:
            await self._stop_capture()
            self._stream = None

        # Close wave file
        if self._wave_file:
            self._wave_file.close()
            self._wave_file = None

        # Stop duration timer
        self._stop_duration_timer()

        # Reset state
        self._state = RecordingState()
        self._start_time = None

        return output_path

    def _start_duration_timer(self):
        """Start timer to update duration every second."""
        def update_duration():
            if self._state.is_recording and self._start_time:
                self._state.duration = (datetime.now() - self._start_time).total_seconds()
                if self._on_duration_update:
                    self._on_duration_update(self._state.duration)
                self._duration_timer = threading.Timer(1.0, update_duration)
                self._duration_timer.daemon = True
                self._duration_timer.start()

        update_duration()

    def _stop_duration_timer(self):
        """Stop duration update timer."""
        if self._duration_timer:
            self._duration_timer.cancel()
            self._duration_timer = None

    # SCStreamOutput protocol
    def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buffer, output_type):
        """Handle audio samples from stream."""
        if not HAS_SCREENCAPTUREKIT:
            return

        if output_type != ScreenCaptureKit.SCStreamOutputTypeAudio:
            return

        if not self._wave_file:
            return

        # Extract audio data from sample buffer
        try:
            # Get audio buffer list
            num_samples = CMSampleBufferGetNumSamples(sample_buffer)
            if num_samples == 0:
                return

            # Get raw audio data
            audio_data = self._extract_audio_data(sample_buffer)
            if audio_data:
                self._wave_file.writeframes(audio_data)
        except Exception as e:
            print(f"Error processing audio: {e}")

    def _extract_audio_data(self, sample_buffer) -> Optional[bytes]:
        """Extract raw audio bytes from CMSampleBuffer."""
        if not HAS_SCREENCAPTUREKIT:
            return None

        try:
            data_buffer = CMSampleBufferGetDataBuffer(sample_buffer)
            if not data_buffer:
                return None

            length = CMBlockBufferGetDataLength(data_buffer)
            if length == 0:
                return None

            data = bytearray(length)
            CMBlockBufferCopyDataBytes(data_buffer, 0, length, data)
            return bytes(data)
        except Exception:
            return None

    # SCStreamDelegate protocol
    def stream_didStopWithError_(self, stream, error):
        """Handle stream stop."""
        if error:
            print(f"Stream stopped with error: {error}")
        self._state.is_recording = False
