#!/usr/bin/python3
# coding=utf-8

import os
import shutil

import soundfile
import taglib

from .playback import PlaybackHandler
from .audio import MLAudio
from .analysis import find_best_loop_points

class MusicLooper:

    def __init__(self,
                 filepath,
                 min_duration_multiplier=0.35,
                 min_loop_duration=None,
                 max_loop_duration=None,
                 approx_loop_start=None,
                 approx_loop_end=None):
        self.min_duration_multiplier = min_duration_multiplier
        self.min_loop_duration = min_loop_duration
        self.max_loop_duration = max_loop_duration
        self.approx_loop_start = approx_loop_start
        self.approx_loop_end = approx_loop_end
        self.mlaudio = MLAudio(filepath=filepath)

    def find_loop_pairs(self):
        return find_best_loop_points(mlaudio=self.mlaudio,
                                     min_duration_multiplier=self.min_duration_multiplier,
                                     min_loop_duration=self.min_loop_duration,
                                     max_loop_duration=self.max_loop_duration,
                                     approx_loop_start=self.approx_loop_start,
                                     approx_loop_end=self.approx_loop_end)
    
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

    def play_looping(self, loop_start, loop_end, start_from=0):
        playback_handler = PlaybackHandler()
        playback_handler.play_looping(
            self.mlaudio.playback_audio,
            self.mlaudio.rate,
            self.mlaudio.channels,
            self.frames_to_samples(loop_start),
            self.frames_to_samples(loop_end),
            self.frames_to_samples(start_from)
        )

    def export(self,
               loop_start,
               loop_end,
               format="WAV",
               output_dir=None):

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

    def export_tags(self, loop_start, loop_end, loop_start_tag, loop_end_tag, output_dir=None):
        if output_dir is None:
            output_dir = os.path.abspath(self.mlaudio.filepath)
        
        track_name, file_extension = os.path.splitext(self.mlaudio.filename)

        exported_file_path = os.path.join(output_dir, f"{track_name}-tagged{file_extension}")
        shutil.copyfile(self.mlaudio.filepath, exported_file_path)

        loop_start = int(self.frames_to_samples(loop_start))
        loop_end = int(self.frames_to_samples(loop_end))

        with taglib.File(exported_file_path, save_on_exit=True) as audio_file:
            audio_file.tags[loop_start_tag] = [str(loop_start)]
            audio_file.tags[loop_end_tag] = [str(loop_end)]
