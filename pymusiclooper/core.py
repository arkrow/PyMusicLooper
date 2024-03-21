"""Contains the core MusicLooper class that can be
used for programmatic access to the CLI's main features."""

import os
import shutil
from math import ceil
from typing import List, Optional, Tuple, Union

import lazy_loader as lazy
import numpy as np

from pymusiclooper.analysis import LoopPair, find_best_loop_points
from pymusiclooper.audio import MLAudio
from pymusiclooper.playback import PlaybackHandler

# Lazy-load external libraries when they're needed
soundfile = lazy.load("soundfile")

class MusicLooper:
    """High-level API access to PyMusicLooper's main functions."""
    def __init__(self, filepath: str):
        """Initializes the MusicLooper object with the provided audio track.

        Args:
            filepath (str): path to the audio track to use.
        """
        self.mlaudio = MLAudio(filepath=filepath)

    def find_loop_pairs(
        self,
        min_duration_multiplier: float = 0.35,
        min_loop_duration: Optional[float] = None,
        max_loop_duration: Optional[float] = None,
        approx_loop_start: Optional[float] = None,
        approx_loop_end: Optional[float] = None,
        brute_force: bool = False,
        disable_pruning: bool = False,
    ) -> List[LoopPair]:
        """Finds the best loop points for the track, according to the parameters specified.

        Args:
            min_duration_multiplier (float, optional): The minimum duration of a loop as a multiplier of track duration. Defaults to 0.35.
            min_loop_duration (float, optional): The minimum duration of a loop (in seconds). Defaults to None.
            max_loop_duration (float, optional): The maximum duration of a loop (in seconds). Defaults to None.
            approx_loop_start (float, optional): The approximate location of the desired loop start (in seconds). If specified, must specify approx_loop_end as well. Defaults to None.
            approx_loop_end (float, optional): The approximate location of the desired loop end (in seconds). If specified, must specify approx_loop_start as well. Defaults to None.
            brute_force (bool, optional): Checks the entire track instead of the detected beats (disclaimer: runtime may be significantly longer). Defaults to False.
            disable_pruning (bool, optional): Returns all the candidate loop points without filtering. Defaults to False.
        
        Raises:
            LoopNotFoundError: raised in case no loops were found

        Returns:
            List[LoopPair]: A list of `LoopPair` objects containing the loop points related data. See the `LoopPair` class for more info.
        """
        return find_best_loop_points(
            mlaudio=self.mlaudio,
            min_duration_multiplier=min_duration_multiplier,
            min_loop_duration=min_loop_duration,
            max_loop_duration=max_loop_duration,
            approx_loop_start=approx_loop_start,
            approx_loop_end=approx_loop_end,
            brute_force=brute_force,
            disable_pruning=disable_pruning
        )

    @property
    def filename(self) -> str:
        return self.mlaudio.filename

    @property
    def filepath(self) -> str:
        return self.mlaudio.filepath

    def samples_to_frames(self, samples: int) -> int:
        return self.mlaudio.samples_to_frames(samples)
    
    def samples_to_seconds(self, samples: int) -> float:
        return self.mlaudio.samples_to_seconds(samples)

    def frames_to_samples(self, frame: int) -> int:
        return self.mlaudio.frames_to_samples(frame)

    def seconds_to_frames(self, seconds: float) -> int:
        return self.mlaudio.seconds_to_frames(seconds)

    def seconds_to_samples(self, seconds: float) -> int:
        return self.mlaudio.seconds_to_samples(seconds)

    def frames_to_ftime(self, frame: int) -> str:
        return self.mlaudio.frames_to_ftime(frame)
    
    def samples_to_ftime(self, samples: int) -> str:
        return self.mlaudio.samples_to_ftime(samples)

    def play_looping(self, loop_start: int, loop_end: int, start_from: int = 0):
        """Plays an audio file with a loop active at the points specified

        Args:
            loop_start (int): Index of the loop start (in samples)
            loop_end (int): Index of the loop end (in samples)
            start_from (int, optional): Index of the sample point to start from. Defaults to 0.
        """
        playback_handler = PlaybackHandler()
        playback_handler.play_looping(
            self.mlaudio.playback_audio,
            self.mlaudio.rate,
            self.mlaudio.n_channels,
            loop_start,
            loop_end,
            start_from,
        )

    def export(
        self,
        loop_start: int,
        loop_end: int,
        format: str = "WAV",
        output_dir: Optional[str] = None
    ):
        """Exports the audio into three files: intro, loop and outro.

        Args:
            loop_start (int): Loop start in samples.
            loop_end (int): Loop end in samples.
            format (str, optional): Audio format of the exported files (formats available depend on the `soundfile` library). Defaults to "WAV".
            output_dir (str, optional): Path to the output directory. Defaults to the same diretcory as the source audio file.
        """
        if output_dir is not None:
            out_path = os.path.join(output_dir, self.mlaudio.filename)
        else:
            out_path = os.path.abspath(self.mlaudio.filepath)

        soundfile.write(
            f"{out_path}-intro.{format.lower()}",
            self.mlaudio.playback_audio[:loop_start],
            self.mlaudio.rate,
            format=format,
        )
        soundfile.write(
            f"{out_path}-loop.{format.lower()}",
            self.mlaudio.playback_audio[loop_start:loop_end],
            self.mlaudio.rate,
            format=format,
        )
        soundfile.write(
            f"{out_path}-outro.{format.lower()}",
            self.mlaudio.playback_audio[loop_end:],
            self.mlaudio.rate,
            format=format,
        )

    def extend(
        self,
        loop_start: int,
        loop_end: int,
        extended_length: float,
        fade_length: float = 5,
        disable_fade_out: bool = False,
        format: str = "WAV",
        output_dir: Optional[str] = None,
    ) -> str:
        """Extends the audio by looping to at least the specified length.
        Returns the path to the extended audio file. 

        Args:
            loop_start (int): Loop start in samples.
            loop_end (int): Loop end in samples.
            extended_length (float): Desired length of the extended audio in seconds.
            fade_length (float, optional): Desired length of the extended audio's fade out in seconds.
            disable_fade_out (bool, optional): Disable fading out from the loop section, and instead, includes the audio outro section . If `True`, `extended_length` will be treated as an 'at least' constraint.
            format (str, optional): Audio format of the exported files (formats available depend on the `soundfile` library). Defaults to "WAV".
            output_dir (str, optional): Path to the output directory. Defaults to the same directory as the source audio file.
        """
        if output_dir is not None:
            out_path = os.path.join(output_dir, self.mlaudio.filename)
        else:
            out_path = os.path.abspath(self.mlaudio.filepath)

        if extended_length < self.mlaudio.total_duration:
            raise ValueError(
                "Extended length must be greater than the audio's original length."
            )

        intro = self.mlaudio.playback_audio[:loop_start]
        loop = self.mlaudio.playback_audio[loop_start:loop_end]
        outro = self.mlaudio.playback_audio[loop_end:]

        loop_extended_length = self.mlaudio.seconds_to_samples(extended_length) - intro.shape[0]

        # If the outro will be included, account for its length when calculating the new loop duration
        if disable_fade_out:
            loop_extended_length -= outro.shape[0]

        loop_factor = loop_extended_length / loop.shape[0]
        left_over_multiplier = loop_factor - int(loop_factor)
        extend_end_idx = loop_start + int(
            (loop_end - loop_start) * left_over_multiplier
        )

        # Modify the extended track's final loop section based on the fade out parameter
        final_loop = self.mlaudio.playback_audio[loop_start:extend_end_idx].copy()
        if disable_fade_out:
            final_loop = loop
        else:
            samples_to_fade = min(
                self.mlaudio.seconds_to_samples(fade_length), final_loop.shape[0]
            )
            final_loop[-samples_to_fade:] = (
                final_loop[-samples_to_fade:]
                * np.linspace(1, 0, samples_to_fade)[:, np.newaxis]
            )

        # Format extended file name with its duration suffixed
        extended_loop_length = final_loop.shape[0] + (
            loop.shape[0] * (int(loop_factor))
        )
        extended_audio_length = (
            intro.shape[0]
            + extended_loop_length
            + (outro.shape[0] if disable_fade_out else 0)
        )
        total_length_seconds = self.mlaudio.samples_to_seconds(extended_audio_length)
        duration_sec = ceil(total_length_seconds%60)
        duration_mins = int(total_length_seconds//60)
        if duration_sec == 60:
            duration_sec = 0
            duration_mins += 1
        extended_audio_length_fmt = (
            f"{duration_mins:d}m{duration_sec:02d}s"
        )
        output_file_path = (
            f"{out_path}-extended-{extended_audio_length_fmt}.{format.lower()}"
        )

        # Export with buffered write logic to avoid storing the entire extended audio in-memory
        with soundfile.SoundFile(
            output_file_path,
            mode="w",
            samplerate=self.mlaudio.rate,
            channels=self.mlaudio.n_channels,
            format=format,
        ) as sf:
            dtype = str(self.mlaudio.playback_audio.dtype)
            sf.buffer_write(intro.tobytes(order="C"), dtype)
            for _ in range(int(loop_factor)):
                sf.buffer_write(loop.tobytes(order="C"), dtype)
            sf.buffer_write(final_loop.tobytes(order="C"), dtype)
            if disable_fade_out:
                sf.buffer_write(outro.tobytes(order="C"), dtype)
        return output_file_path

    def export_txt(
        self,
        loop_start: Union[int, float, str],
        loop_end: Union[str, int, float, str],
        txt_name: str = "loops",
        output_dir: Optional[str] = None
    ):
        """Exports the given loop points to a text file named `loop.txt` in append mode with the format:
        `{loop_start} {loop_end} {filename}`

        Args:
            loop_start (Union[int, float, str]): Loop start in samples, seconds or ftime.
            loop_end (Union[int, float, str]): Loop end in samples, seconds or ftime.
            txt_name (str, optional): Filename of the text file to export to. Defaults to "loops".
            output_dir (str, optional): Path to the output directory. Defaults to the same directory as the source audio file.
        """
        if output_dir is not None:
            out_path = os.path.join(output_dir, f"{txt_name}.txt")
        else:
            out_path = os.path.join(os.path.dirname(self.mlaudio.filepath), f"{txt_name}.txt")

        with open(out_path, "a") as file:
            file.write(f"{loop_start} {loop_end} {self.mlaudio.filename}\n")

    def export_tags(
        self,
        loop_start: int,
        loop_end: int,
        loop_start_tag: str,
        loop_end_tag: str,
        output_dir: Optional[str] = None
    ):
        """Adds metadata tags of loop points to a copy of the source audio file.

        Args:
            loop_start (int): Loop start in samples.
            loop_end (int): Loop end in samples.
            loop_start_tag (str): Name of the loop_start metadata tag.
            loop_end_tag (str): Name of the loop_end metadata tag.
            output_dir (str, optional): Path to the output directory. Defaults to the same diretcory as the source audio file.
        """
        # Workaround for taglib import issues on Apple silicon devices
        # Import taglib only when needed to isolate ImportErrors
        import taglib
            
        if output_dir is None:
            output_dir = os.path.abspath(self.mlaudio.filepath)

        track_name, file_extension = os.path.splitext(self.mlaudio.filename)

        exported_file_path = os.path.join(
            output_dir, f"{track_name}-tagged{file_extension}"
        )
        shutil.copyfile(self.mlaudio.filepath, exported_file_path)

        with taglib.File(exported_file_path, save_on_exit=True) as audio_file:
            audio_file.tags[loop_start_tag] = [str(loop_start)]
            audio_file.tags[loop_end_tag] = [str(loop_end)]


    def read_tags(self, loop_start_tag: str, loop_end_tag: str) -> Tuple[int, int]:
        """Reads the tags provided from the file and returns the read loop points

        Args:
            loop_start_tag (str): The name of the metadata tag containing the loop_start value
            loop_end_tag (str): The name of the metadata tag containing the loop_end value

        Returns:
            Tuple[int, int]: A tuple containing (loop_start, loop_end)
        """
        # Workaround for taglib import issues on Apple silicon devices
        # Import taglib only when needed to isolate ImportErrors
        import taglib

        loop_start = None
        loop_end = None

        with taglib.File(self.filepath) as audio_file:
            if loop_start_tag not in audio_file.tags:
                raise ValueError(f"The tag \"{loop_start_tag}\" is not present in the metadata of \"{self.filename}\".")
            if loop_end_tag not in audio_file.tags:
                raise ValueError(f"The tag \"{loop_end_tag}\" is not present in the metadata of \"{self.filename}\".")
            try:
                loop_start = int(audio_file.tags[loop_start_tag][0])
                loop_end = int(audio_file.tags[loop_end_tag][0])
            except Exception as e:
                raise TypeError(
                    "One of the tags provided has invalid (non-integer or empty) values"
                ) from e

        # Re-order the loop points in case
        real_loop_start = min(loop_start, loop_end)
        real_loop_end = max(loop_start, loop_end)

        return real_loop_start, real_loop_end
