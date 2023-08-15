"""Contains the core MusicLooper class that can be
used for programmatic access to the CLI's main features."""

import os
import shutil
from typing import Tuple, List, Optional

import lazy_loader as lazy

from .analysis import find_best_loop_points, LoopPair
from .audio import MLAudio
from .playback import PlaybackHandler

# Lazy-load external libraries when they're needed
soundfile = lazy.load("soundfile")
taglib = lazy.load("taglib")

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
        min_duration_multiplier=0.35,
        min_loop_duration=None,
        max_loop_duration=None,
        approx_loop_start=None,
        approx_loop_end=None,
        brute_force=False,
        disable_pruning=False,
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
    def filename(self):
        return self.mlaudio.filename

    @property
    def filepath(self):
        return self.mlaudio.filepath

    def samples_to_frames(self, samples):
        return self.mlaudio.samples_to_frames(samples)
    
    def samples_to_seconds(self, samples):
        return self.mlaudio.samples_to_seconds(samples)

    def frames_to_samples(self, frame):
        return self.mlaudio.frames_to_samples(frame)

    def seconds_to_frames(self, seconds):
        return self.mlaudio.seconds_to_frames(seconds)

    def seconds_to_samples(self, seconds):
        return self.mlaudio.seconds_to_samples(seconds)

    def frames_to_ftime(self, frame):
        return self.mlaudio.frames_to_ftime(frame)
    
    def samples_to_ftime(self, samples):
        return self.mlaudio.samples_to_ftime(samples)

    def play_looping(self, loop_start: int, loop_end: int, start_from=0):
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

    def export_txt(
        self,
        loop_start: int,
        loop_end: int,
        txt_name: str = "loops",
        output_dir: Optional[str] = None
    ):
        """Exports the given loop points to a text file named `loop.txt` in append mode with the format:
        `{loop_start} {loop_end} {filename}`

        Args:
            loop_start (int): _description_
            loop_end (int): _description_
            txt_name (str, optional): Filename of the text file to export to. Defaults to "loops".
            output_dir (str, optional): _description_. Defaults to None.
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
