"""Module for playback through the terminal"""
import importlib
import logging
import signal
import threading

import numpy as np
from rich.progress import BarColumn, Progress, TextColumn

from pymusiclooper.console import rich_console

# Use a generous fixed blocksize (~46 ms at 44.1 kHz) so Python's GIL and
# terminal updates do not starve the PortAudio callback on tight audio periods.
DEFAULT_BLOCKSIZE = 2048

# Lazy-load sounddevice: call `sd()` to return the module.
# (We use this instead of `lazy-loader`, to get clearer error messages when
# sounddevice is missing dependencies like PortAudio.)
_sd = None
def sd():
    global _sd
    _sd = _sd or importlib.import_module("sounddevice")
    return _sd

class PlaybackHandler:
    """Handler class for initiating looping playback through the terminal."""
    def __init__(self) -> None:
        self.event = threading.Event()
        self.progressbar = Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.fields[time_field]}"),
            TextColumn("{task.fields[loop_field]}"),
            console=rich_console,
            transient=True,
            auto_refresh=False,
        )

    def play_looping(
        self,
        playback_data: np.ndarray,
        samplerate: int,
        n_channels: int,
        loop_start: int,
        loop_end: int,
        start_from: int = 0,
        blocksize: int = DEFAULT_BLOCKSIZE,
    ) -> None:
        """Plays an audio track through the terminal with a loop active between the `loop_start` and `loop_end` provided. Ctrl+C to interrupt.

        Args:
            playback_data (np.ndarray): A numpy array containing the playback audio. Must be in the shape (samples, channels).
            samplerate (int): The sample rate of the playback
            n_channels (int): The number of channels for playback
            loop_start (int): The start point of the loop (in samples)
            loop_end (int): The end point of the loop (in samples)
            start_from (int, optional): The offset to start from (in samples). Defaults to 0.
            blocksize (int, optional): Number of frames per audio callback block. Defaults to 2048.
        """
        self.event.clear()
        self.loop_counter = 0
        self.looping = True
        self.current_frame = max(0, start_from)
        self.underflow_count = 0
        self._stop_requested = False
        self._disable_loop_announced = False

        total_samples = playback_data.shape[0]

        if loop_start > loop_end:
            raise ValueError(
                "Loop parameters are in the wrong order. "
                f"Loop start: {loop_start}; loop end: {loop_end}."
            )

        is_loop_invalid = (
            loop_start < 0
            or loop_start >= total_samples
            or loop_end < 0
            or loop_end > total_samples
            or loop_start >= loop_end
        )

        if is_loop_invalid:
            raise ValueError(
                "Loop parameters are out of bounds. "
                f"Loop start: {loop_start}; "
                f"loop end: {loop_end}; "
                f"total number of samples in audio: {total_samples}."
            )

        # Ensure C-contiguous float32 layout once upfront so the real-time audio
        # callback copies raw bytes directly via RawOutputStream. This avoids
        # per-callback NumPy wrapper creation and sounddevice's deprecated
        # `data.shape = -1, channels` mutation under NumPy 2.5+.
        contiguous_audio = np.ascontiguousarray(playback_data, dtype=np.float32)
        if contiguous_audio.ndim == 1:
            contiguous_audio = contiguous_audio[:, np.newaxis]
        audio_bytes = memoryview(contiguous_audio).cast("B")
        frame_bytes = n_channels * contiguous_audio.dtype.itemsize
        silence = bytes(max(blocksize, 1) * frame_bytes)

        sd_mod = sd()
        callback_stop = sd_mod.CallbackStop

        def callback(outdata, frames, time, status):
            if status:
                self.underflow_count += 1

            total_bytes = frames * frame_bytes
            if self._stop_requested:
                outdata[:total_bytes] = (
                    silence[:total_bytes]
                    if total_bytes <= len(silence)
                    else b"\x00" * total_bytes
                )
                raise callback_stop()

            written = 0
            remaining = frames
            out_offset = 0

            while remaining > 0:
                if self.looping and self.current_frame < loop_end:
                    available = loop_end - self.current_frame
                    to_copy = min(available, remaining)
                    src_start = self.current_frame * frame_bytes
                    copy_bytes = to_copy * frame_bytes
                    outdata[out_offset : out_offset + copy_bytes] = audio_bytes[
                        src_start : src_start + copy_bytes
                    ]
                    self.current_frame += to_copy
                    out_offset += copy_bytes
                    written += to_copy
                    remaining -= to_copy
                    if self.current_frame >= loop_end:
                        self.current_frame = loop_start
                        self.loop_counter += 1
                else:
                    available = total_samples - self.current_frame
                    if available <= 0:
                        break
                    to_copy = min(available, remaining)
                    src_start = self.current_frame * frame_bytes
                    copy_bytes = to_copy * frame_bytes
                    outdata[out_offset : out_offset + copy_bytes] = audio_bytes[
                        src_start : src_start + copy_bytes
                    ]
                    self.current_frame += to_copy
                    out_offset += copy_bytes
                    written += to_copy
                    remaining -= to_copy
                    if self.current_frame >= total_samples:
                        break

            if written < frames:
                zero_bytes = (frames - written) * frame_bytes
                outdata[out_offset : out_offset + zero_bytes] = (
                    silence[:zero_bytes]
                    if zero_bytes <= len(silence)
                    else b"\x00" * zero_bytes
                )
                raise callback_stop()

        is_main_thread = threading.current_thread() is threading.main_thread()
        prev_sigint_handler = signal.getsignal(signal.SIGINT) if is_main_thread else None

        try:
            self.stream = sd_mod.RawOutputStream(
                samplerate=samplerate,
                blocksize=blocksize,
                channels=n_channels,
                dtype="float32",
                latency="high",
                callback=callback,
                finished_callback=self.event.set,
            )

            with self.stream, self.progressbar:
                # Initialize playback progress bar
                pbar = self.progressbar.add_task(
                    "Now Playing...",
                    total=total_samples,
                    loop_field="",
                    time_field="",
                )

                # Override SIGINT/KeyboardInterrupt handler with custom logic for loop handling
                if is_main_thread:
                    signal.signal(signal.SIGINT, self._loop_interrupt_handler)

                def _refresh_progress() -> None:
                    time_sec = self.current_frame / samplerate
                    ftime = f"{time_sec // 60:02.0f}:{time_sec % 60:02.0f}"
                    self.progressbar.update(
                        pbar,
                        completed=self.current_frame,
                        time_field=ftime,
                        loop_field=(
                            f"[dim] | Currently on Loop #{self.loop_counter}[/]"
                            if self.loop_counter
                            else ""
                        ),
                        refresh=True,
                    )

                _refresh_progress()

                # Workaround for python issue on Windows
                # (threading.Event().wait() not interruptable with Ctrl-C on Windows): https://bugs.python.org/issue35935
                # Set a 0.25 second timeout to handle interrupts and refresh the progress bar in-between
                while not self.event.wait(0.25):
                    if not self.looping and not self._disable_loop_announced:
                        self._disable_loop_announced = True
                        rich_console.print(
                            "[dim italic yellow](Looping disabled. [red]Ctrl+C[/] again to stop playback.)[/]"
                        )
                    _refresh_progress()

            if self._stop_requested:
                rich_console.print("[dim]Playback interrupted by user.[/]")

            if self.underflow_count:
                logging.info(
                    f"Audio playback experienced {self.underflow_count} output underflow(s)."
                )
        except Exception as e:
            logging.error(e)
        finally:
            if is_main_thread and prev_sigint_handler is not None:
                signal.signal(signal.SIGINT, prev_sigint_handler)

    def _loop_interrupt_handler(self, *args):
        if self.looping:
            self.looping = False
        else:
            self._stop_requested = True
            self.event.set()
