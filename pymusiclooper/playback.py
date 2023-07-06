import logging
import signal
import threading

import numpy as np
import sounddevice as sd

from .console import rich_console


class PlaybackHandler:
    def __init__(self) -> None:
        self.event = threading.Event()

    def play_looping(
        self,
        playback_data: np.ndarray,
        samplerate: int,
        n_channels: int,
        loop_start: int,
        loop_end: int,
        start_from=0,
    ) -> None:
        """Plays an audio track through the terminal with a loop active between the `loop_start` and `loop_end` provided. Ctrl+C to interrupt.

        Args:
            playback_data (np.ndarray): A numpy array containing the playback audio. Must be in the shape (samples, channels).
            samplerate (int): The sample rate of the playback
            n_channels (int): The number of channels for playback
            loop_start (int): The start point of the loop (in samples)
            loop_end (int): The end point of the loop (in samples)
            start_from (int, optional): The offset to start from (in samples). Defaults to 0.
        """
        self.loop_counter = 0
        self.looping = True
        self.current_frame = start_from

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
            or loop_end >= total_samples
            or loop_start >= loop_end
        )

        if is_loop_invalid:
            raise ValueError(
                "Loop parameters are out of bounds. "
                f"Loop start: {loop_start}; "
                f"loop end: {loop_end}; "
                f"total number of samples in audio: {total_samples}."
            )

        try:

            def callback(outdata, frames, time, status):
                chunksize = min(len(playback_data) - self.current_frame, frames)

                # Audio looping logic
                if self.looping and self.current_frame + frames > loop_end:
                    pre_loop_index = loop_end - self.current_frame
                    remaining_frames = frames - (loop_end - self.current_frame)
                    adjusted_next_frame_idx = loop_start + remaining_frames
                    outdata[:pre_loop_index] = playback_data[self.current_frame : loop_end]
                    outdata[pre_loop_index:frames] = playback_data[loop_start:adjusted_next_frame_idx]
                    self.current_frame = adjusted_next_frame_idx
                    self.loop_counter += 1
                    rich_console.print(f"[dim italic yellow]Currently on loop #{self.loop_counter}.[/]", end="\r")
                else:
                    outdata[:chunksize] = playback_data[self.current_frame : self.current_frame + chunksize]
                    self.current_frame += chunksize
                    if chunksize < frames:
                        outdata[chunksize:] = 0
                        raise sd.CallbackStop()

            self.stream = sd.OutputStream(
                samplerate=samplerate,
                channels=n_channels,
                callback=callback,
                finished_callback=self.event.set,
            )

            with self.stream:
                # Override SIGINT/KeyboardInterrupt handler with custom logic for loop handling
                signal.signal(signal.SIGINT, self._loop_interrupt_handler)
                # Workaround for python issue on Windows
                # (threading.Event().wait() not interruptable with Ctrl-C on Windows): https://bugs.python.org/issue35935
                # Set a 0.5 second timeout to handle interrupts in-between
                while not self.event.wait(0.5):
                    pass
                # Restore default SIGINT handler after playback is stopped
                signal.signal(signal.SIGINT, signal.default_int_handler)
        except Exception as e:
            logging.error(e)

    def _loop_interrupt_handler(self, *args):
        if self.looping:
            self.looping = False
            rich_console.print("[dim italic yellow](Looping disabled. [red]Ctrl+C[/] again to stop playback.)[/]")
        else:
            self.event.set()
            self.stream.stop()
            self.stream.close()
            rich_console.print("[dim]Playback interrupted by user.[/]")
            # Restore default SIGINT handler
            signal.signal(signal.SIGINT, signal.default_int_handler)
