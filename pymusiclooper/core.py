#!/usr/bin/python3
# coding=utf-8

import os
import shutil

import soundfile
import taglib

from .analysis import find_best_loop_points
from .audio import MLAudio
from .playback import PlaybackHandler


class MusicLooper:
    def __init__(
        self,
        filepath,
        min_duration_multiplier=0.35,
        min_loop_duration=None,
        max_loop_duration=None,
        approx_loop_start=None,
        approx_loop_end=None,
    ):
        self.min_duration_multiplier = min_duration_multiplier
        self.min_loop_duration = min_loop_duration
        self.max_loop_duration = max_loop_duration
        self.approx_loop_start = approx_loop_start
        self.approx_loop_end = approx_loop_end
        self.mlaudio = MLAudio(filepath=filepath)

    def find_loop_pairs(self):
        return find_best_loop_points(
            mlaudio=self.mlaudio,
            min_duration_multiplier=self.min_duration_multiplier,
            min_loop_duration=self.min_loop_duration,
            max_loop_duration=self.max_loop_duration,
            approx_loop_start=self.approx_loop_start,
            approx_loop_end=self.approx_loop_end,
        )

    @property
    def filename(self):
        return self.mlaudio.filename

    @property
    def filepath(self):
        return self.mlaudio.filepath

    def samples_to_frames(self, samples):
        return self.mlaudio.samples_to_frames(samples)

    def frames_to_samples(self, frame):
        return self.mlaudio.frames_to_samples(frame)

    def seconds_to_frames(self, seconds):
        return self.mlaudio.seconds_to_frames(seconds)

    def frames_to_ftime(self, frame):
        return self.mlaudio.frames_to_ftime(frame)
    
    def samples_to_ftime(self, samples):
        return self.mlaudio.samples_to_ftime(samples)

    def play_looping(self, loop_start: int, loop_end: int, start_from=0, is_sample_units=False):
        """Plays an audio file with a loop active at the points specified

        Args:
            loop_start (int): Index of the loop start (in frames)
            loop_end (int): Index of the loop end (in frames)
            start_from (int, optional): Index of the frame to start from. Defaults to 0.
            is_sample_units (bool, optional): If True, will handle all parameters as raw sample units instead of frame indices. Defaults to False.
        """
        playback_handler = PlaybackHandler()
        if not is_sample_units:
            loop_start = self.frames_to_samples(loop_start)
            loop_end = self.frames_to_samples(loop_end)
            start_from = self.frames_to_samples(start_from)

        playback_handler.play_looping(
            self.mlaudio.playback_audio,
            self.mlaudio.rate,
            self.mlaudio.channels,
            loop_start,
            loop_end,
            start_from,
        )

    def export(self, loop_start, loop_end, format="WAV", output_dir=None):
        if output_dir is not None:
            out_path = os.path.join(output_dir, self.mlaudio.filename)
        else:
            out_path = os.path.abspath(self.mlaudio.filepath)

        loop_start = self.frames_to_samples(loop_start)
        loop_end = self.frames_to_samples(loop_end)

        soundfile.write(
            f"{out_path}-intro.{format.lower()}",
            self.mlaudio.playback_audio[..., :loop_start].T,
            self.mlaudio.rate,
            format=format,
        )
        soundfile.write(
            f"{out_path}-loop.{format.lower()}",
            self.mlaudio.playback_audio[..., loop_start:loop_end].T,
            self.mlaudio.rate,
            format=format,
        )
        soundfile.write(
            f"{out_path}-outro.{format.lower()}",
            self.mlaudio.playback_audio[..., loop_end:].T,
            self.mlaudio.rate,
            format=format,
        )

    def export_txt(self, loop_start, loop_end, output_dir=None):
        if output_dir is not None:
            out_path = os.path.join(output_dir, "loop.txt")
        else:
            out_path = os.path.join(os.path.dirname(self.mlaudio.filepath), "loop.txt")

        loop_start = int(self.frames_to_samples(loop_start))
        loop_end = int(self.frames_to_samples(loop_end))

        with open(out_path, "a") as file:
            file.write(f"{loop_start} {loop_end} {self.mlaudio.filename}\n")

    def export_tags(
        self, loop_start, loop_end, loop_start_tag, loop_end_tag, output_dir=None
    ):
        if output_dir is None:
            output_dir = os.path.abspath(self.mlaudio.filepath)

        track_name, file_extension = os.path.splitext(self.mlaudio.filename)

        exported_file_path = os.path.join(
            output_dir, f"{track_name}-tagged{file_extension}"
        )
        shutil.copyfile(self.mlaudio.filepath, exported_file_path)

        loop_start = int(self.frames_to_samples(loop_start))
        loop_end = int(self.frames_to_samples(loop_end))

        with taglib.File(exported_file_path, save_on_exit=True) as audio_file:
            audio_file.tags[loop_start_tag] = [str(loop_start)]
            audio_file.tags[loop_end_tag] = [str(loop_end)]


    def read_tags(self, loop_start_tag: str, loop_end_tag: str) -> tuple[int, int]:
        """Reads the tags provided from the file and returns the read loop points

        Args:
            loop_start_tag (str): The name of the metadata tag containing the loop_start value
            loop_end_tag (str): The name of the metadata tag containing the loop_end value

        Returns:
            tuple[int, int]: A tuple containing (loop_start, loop_end)
        """
        loop_start = None
        loop_end = None

        with taglib.File(self.filepath) as audio_file:
            if loop_start_tag not in audio_file.tags:
                raise ValueError(f"The tag '{loop_start_tag}' is not present in {self.filename}'s tags.")
            if loop_end_tag not in audio_file.tags:
                raise ValueError(f"The tag '{loop_end_tag}' is not present in {self.filename}'s tags.")
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
