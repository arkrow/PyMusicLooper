#!/usr/bin/python3
# coding=utf-8

import logging
import os
import time
import shutil

import librosa
import numpy as np
import soundfile
import taglib

from .playback import PlaybackHandler
from .exceptions import LoopNotFoundError, AudioLoadError


class MusicLooper:

    def __init__(self,
                 filepath,
                 min_duration_multiplier=0.35,
                 min_loop_duration=None,
                 max_loop_duration=None,
                 trim=True):
        # Load the file if it exists
        # dtype and subsequent type cast are workarounds for a libsnd bug; see https://github.com/librosa/librosa/issues/1622 and https://github.com/bastibe/python-soundfile/issues/349
        raw_audio, sampling_rate = librosa.load(filepath, sr=None, mono=False, dtype=None)
        raw_audio = raw_audio.astype(np.float32)
        self.total_duration = librosa.get_duration(y=raw_audio,
                                                   sr=sampling_rate)

        if raw_audio.size == 0:
            raise AudioLoadError('The audio file could not be loaded for analysis. The file may be corrupted, or the current environment may be lacking the necessary tools to open this file format.')

        self.filepath = filepath
        self.filename = os.path.basename(filepath)

        mono_signal = librosa.core.to_mono(raw_audio)

        self.audio, self.trim_offset = (
            librosa.effects.trim(mono_signal, top_db=40)
            if trim
            else (mono_signal, (0, 0))
        )
        self.trim_offset = self.trim_offset[0]

        self.rate = sampling_rate
        self.min_loop_duration = (self.seconds_to_frames(min_loop_duration)
                             if min_loop_duration is not None else
                             self.seconds_to_frames(
                                 int(min_duration_multiplier *
                                     self.total_duration)))
        self.max_loop_duration = (self.seconds_to_frames(max_loop_duration)
                             if max_loop_duration is not None else
                             self.seconds_to_frames(self.total_duration))

        # Initialize parameters for playback
        self.playback_audio = raw_audio
        self.channels = self.playback_audio.shape[0]

    def db_diff(self, power_db_f1, power_db_f2):
        f1_max = np.max(power_db_f1)
        f2_max = np.max(power_db_f2)
        return max(f1_max, f2_max) - min(f1_max, f2_max)

    def find_loop_pairs(self):
        runtime_start = time.time()

        S = librosa.core.stft(y=self.audio)
        S_power = np.abs(S) ** 2
        S_weighed = librosa.core.perceptual_weighting(
            S=S_power, frequencies=librosa.fft_frequencies(sr=self.rate)
        )
        mel_spectrogram = librosa.feature.melspectrogram(S=S_weighed, sr=self.rate, n_mels=128, fmax=8000)
        chroma = librosa.feature.chroma_stft(S=S_power)
        power_db = librosa.power_to_db(S_weighed, ref=np.median)

        onset_env = librosa.onset.onset_strength(S=mel_spectrogram)

        pulse = librosa.beat.plp(onset_envelope=onset_env)
        beats_plp = np.flatnonzero(librosa.util.localmax(pulse))
        bpm, beats = librosa.beat.beat_track(onset_envelope=onset_env)

        beats = np.union1d(beats, beats_plp)
        beats = np.sort(beats)

        logging.info("Detected {} beats at {:.0f} bpm".format(beats.size, bpm))

        runtime_end = time.time()
        prep_time = runtime_end - runtime_start
        logging.info("Finished initial audio processing in {:.3}s".format(prep_time))

        candidate_pairs = []

        deviation = np.linalg.norm(chroma[..., beats] * 0.085, axis=0)

        for idx, loop_end in enumerate(beats):
            for loop_start in beats:
                loop_length = loop_end - loop_start
                if loop_length < self.min_loop_duration:
                    break
                if loop_length > self.max_loop_duration:
                    continue
                dist = np.linalg.norm(chroma[..., loop_end] - chroma[..., loop_start])
                if dist <= deviation[idx]:
                    db_diff = self.db_diff(
                        power_db[..., loop_end], power_db[..., loop_start]
                    )
                    if db_diff <= 1.5:
                        candidate_pairs.append(
                            {
                                "loop_start": loop_start,
                                "loop_end": loop_end,
                                "dB_diff": db_diff,
                                "dist": (dist / deviation[idx])
                            }
                        )

        logging.info(f"Found {len(candidate_pairs)} possible loop points")

        if not candidate_pairs:
            raise LoopNotFoundError(f'No loop points found for {self.filename} with current parameters.')

        beats_per_second = bpm / 60
        num_test_beats = 12
        seconds_to_test = num_test_beats / beats_per_second
        test_offset = librosa.samples_to_frames(int(seconds_to_test * self.rate))

        # adjust offset for very short tracks to 25% of its length
        if test_offset > chroma.shape[-1]:
            test_offset = chroma.shape[-1] // 4

        candidate_pairs = self._prune_by_dB_diff(candidate_pairs)

        weights = _geometric_weights(test_offset, start=test_offset // num_test_beats)
        pair_score_list = [
            self._calculate_loop_score(
                pair["loop_start"],
                pair["loop_end"],
                chroma,
                test_duration=test_offset,
                weights=weights,
            ) for pair in candidate_pairs
        ]

        # Add cosine similarity as score
        for pair, score in zip(candidate_pairs, pair_score_list):
            pair["score"] = score

        candidate_pairs = self._prune_by_score(candidate_pairs)

        # re-sort based on new score
        candidate_pairs = sorted(candidate_pairs, reverse=True, key=lambda x: x["score"])

        # prefer longer loops for highly similar sequences
        if len(candidate_pairs) > 1:
            self._prioritize_duration(candidate_pairs)

        if self.trim_offset:
            for pair in candidate_pairs:
                pair["loop_start"] = self.apply_trim_offset(
                    pair["loop_start"]
                )
                pair["loop_end"] = self.apply_trim_offset(
                    pair["loop_end"]
                )

        for pair in candidate_pairs:
            logging.info(
                "Found from {} to {}, dB_diff:{}, similarity:{}".format(
                    pair["loop_start"],
                    pair["loop_end"],
                    pair["dB_diff"],
                    pair["score"],
                )
            )

        if not candidate_pairs:
            raise LoopNotFoundError(f'No loop points found for {self.filename} with current parameters.')
        else:
            return candidate_pairs

    def _prune_by_score(self, candidate_pairs, percentile=10, acceptable_score=80):
        candidate_pairs = sorted(candidate_pairs, key=lambda x: x["score"])

        score_array = np.array(
            [pair["score"] for pair in candidate_pairs]
        )

        score_threshold = np.percentile(score_array, percentile, interpolation='lower')
        percentile_idx = np.searchsorted(score_array, score_threshold, side="left")
        acceptable_idx = np.searchsorted(score_array, acceptable_score, side="left")

        return candidate_pairs[min(percentile_idx, acceptable_idx):]

    def _prune_by_dB_diff(self, candidate_pairs, percentile=90, acceptable_db_diff=0.125):
        candidate_pairs = sorted(candidate_pairs, key=lambda x: x["dB_diff"])

        db_diff_array = np.array(
            [pair["dB_diff"] for pair in candidate_pairs]
        )

        db_threshold = np.percentile(db_diff_array, percentile, interpolation='higher')
        percentile_idx = np.searchsorted(db_diff_array, db_threshold, side="right")
        acceptable_idx = np.searchsorted(db_diff_array, acceptable_db_diff, side="right")

        return candidate_pairs[:max(percentile_idx, acceptable_idx)]

    def _prioritize_duration(self, pair_list):
        db_diff_array = np.array(
            [pair["dB_diff"] for pair in pair_list]
        )
        db_threshold = np.median(db_diff_array)

        duration_argmax = 0
        duration_max = 0

        score_array = np.array(
            [pair["score"] for pair in pair_list]
        )
        score_threshold = np.percentile(score_array, 90, interpolation="lower")

        score_threshold = max(score_threshold, pair_list[0]["score"] - 0.005)

        for idx, pair in enumerate(pair_list):
            if pair["score"] < score_threshold:
                break
            duration = pair["loop_end"] - pair["loop_start"]
            if duration > duration_max and pair["dB_diff"] <= db_threshold:
                duration_max, duration_argmax = duration, idx

        if duration_argmax:
            pair_list.insert(0, pair_list.pop(duration_argmax))

    def _calculate_loop_score(self, b1, b2, chroma, test_duration, weights=None):
        lookahead_score = self._calculate_subseq_beat_similarity(
            b1, b2, chroma, test_duration, weights=weights
        )
        lookbehind_score = self._calculate_subseq_beat_similarity(
            b1, b2, chroma, -test_duration, weights=weights[::-1]
        )

        return max(lookahead_score, lookbehind_score)

    def _calculate_subseq_beat_similarity(self, b1_start, b2_start, chroma, test_duration, weights=None):
        if test_duration < 0:
            max_negative_offset = max(test_duration, -b1_start, -b2_start)
            b1_start = b1_start + max_negative_offset
            b2_start = b2_start + max_negative_offset

        chroma_len = chroma.shape[-1]
        test_offset = np.abs(test_duration)

        # clip to chroma len
        b1_end = min(b1_start + test_offset, chroma_len)
        b2_end = min(b2_start + test_offset, chroma_len)

        # align testing lengths
        max_offset = min(b1_end - b1_start, b2_end - b2_start)
        b1_end, b2_end = (b1_start + max_offset, b2_start + max_offset)

        dot_prod = np.einsum('ij,ij->j', 
            chroma[..., b1_start:b1_end], chroma[..., b2_start:b2_end]
        )

        b1_norm = np.linalg.norm(chroma[..., b1_start:b1_end], axis=0)
        b2_norm = np.linalg.norm(chroma[..., b2_start:b2_end], axis=0)
        cosine_sim = dot_prod / (b1_norm * b2_norm)

        if max_offset < test_offset:
            return np.average(np.pad(cosine_sim, (0, test_offset - max_offset), 'minimum'), weights=weights)
        else:
            return np.average(cosine_sim, weights=weights)

    def apply_trim_offset(self, frame):
        return (
            librosa.samples_to_frames(
                librosa.frames_to_samples(frame) + self.trim_offset
            )
            if self.trim_offset
            else frame
        )

    def samples_to_frames(self, samples):
        return librosa.core.samples_to_frames(samples)

    def frames_to_samples(self, frame):
        return librosa.core.frames_to_samples(frame)

    def seconds_to_frames(self, seconds):
        return librosa.core.time_to_frames(seconds, sr=self.rate)

    def frames_to_ftime(self, frame):
        time_sec = librosa.core.frames_to_time(frame, sr=self.rate)
        return "{:02.0f}:{:06.3f}".format(time_sec // 60, time_sec % 60)

    def play_looping(self, loop_start, loop_end, start_from=0):
        playback_handler = PlaybackHandler()
        playback_handler.play_looping(
            self.playback_audio,
            self.rate,
            self.frames_to_samples(loop_start),
            self.frames_to_samples(loop_end),
            self.frames_to_samples(start_from)
        )

    def export(
        self, loop_start, loop_end, format="WAV", output_dir=None
    ):

        if output_dir is not None:
            out_path = os.path.join(output_dir, self.filename)
        else:
            out_path = os.path.abspath(self.filepath)

        loop_start = self.frames_to_samples(loop_start)
        loop_end = self.frames_to_samples(loop_end)

        soundfile.write(
            f"{out_path}-intro.{format.lower()}",
            self.playback_audio[..., :loop_start].T,
            self.rate,
            format=format,
        )
        soundfile.write(
            f"{out_path}-loop.{format.lower()}",
            self.playback_audio[..., loop_start:loop_end].T,
            self.rate,
            format=format,
        )
        soundfile.write(
            f"{out_path}-outro.{format.lower()}",
            self.playback_audio[..., loop_end:].T,
            self.rate,
            format=format,
        )

    def export_txt(self, loop_start, loop_end, output_dir=None):
        if output_dir is not None:
            out_path = os.path.join(output_dir, "loop.txt")
        else:
            out_path = os.path.join(os.path.dirname(self.filepath), "loop.txt")

        loop_start = int(self.frames_to_samples(loop_start))
        loop_end = int(self.frames_to_samples(loop_end))

        with open(out_path, "a") as file:
            file.write(f"{loop_start} {loop_end} {self.filename}\n")

    def export_tags(self, loop_start, loop_end, loop_start_tag, loop_end_tag, output_dir=None):
        if output_dir is None:
            output_dir = os.path.abspath(self.filepath)
        
        track_name, file_extension = os.path.splitext(self.filename)

        exported_file_path = os.path.join(output_dir, f"{track_name}-tagged{file_extension}")
        shutil.copyfile(self.filepath, exported_file_path)

        loop_start = int(self.frames_to_samples(loop_start))
        loop_end = int(self.frames_to_samples(loop_end))

        with taglib.File(exported_file_path, save_on_exit=True) as audio_file:
            audio_file.tags[loop_start_tag] = [str(loop_start)]
            audio_file.tags[loop_end_tag] = [str(loop_end)]

    def print(self, loop_start, loop_end):
        loop_start = int(self.frames_to_samples(loop_start))
        loop_end = int(self.frames_to_samples(loop_end))
        print(loop_start, loop_end)


def _geometric_weights(length, start=100, stop=1):
    return np.geomspace(start, stop, num=length)
