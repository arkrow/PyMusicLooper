#!/usr/bin/python3
# coding=utf-8
""" PyMusicLooper
    Copyright (C) 2020  Hazem Nabil

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>."""

import json
import os
import time
import logging

import librosa
import numpy as np
import soundfile


class MusicLooper:
    def __init__(self, filename, min_duration_multiplier=0.35, trim=True):
        # Load the file if it exists
        if os.path.exists(filename) and os.path.isfile(filename):
            try:
                audio, sampling_rate = librosa.load(filename, sr=None, mono=False)
            except Exception:
                raise TypeError("Unsupported file type.")
        else:
            raise FileNotFoundError("Specified file not found.")

        self.filename = filename
        mono_signal = librosa.core.to_mono(audio)
        self.audio, self.trim_offset = (
            librosa.effects.trim(mono_signal) if trim else (mono_signal, [0, 0])
        )
        self.rate = sampling_rate
        self.playback_audio = audio
        self.min_duration_multiplier = min_duration_multiplier

        # Initialize parameters for playback
        self.channels = self.playback_audio.shape[0]

    def _loop_finding_routine(
        self, beats, i_start, i_stop, chroma, power_db, min_duration, candidate_pairs
    ):
        for i in range(i_start, i_stop):
            deviation = np.linalg.norm(chroma[..., beats[i]] * 0.10)
            for j in range(i):
                # Since the beats array is sorted
                # any j >= current_j will only decrease in duration
                if beats[i] - beats[j] < min_duration:
                    break
                dist = np.linalg.norm(chroma[..., beats[i]] - chroma[..., beats[j]])
                if dist <= deviation:
                    avg_db_diff = self.db_diff(
                        power_db[..., beats[i]], power_db[..., beats[j]]
                    )
                    if avg_db_diff <= 10:
                        candidate_pairs.append(
                            {
                                "loop_start": beats[j],
                                "loop_end": beats[i],
                                "dB_diff": avg_db_diff,
                            }
                        )

    def db_diff(self, power_db_f1, power_db_f2):
        average_diff = np.average(np.abs(power_db_f1 - power_db_f2))
        return average_diff

    def find_loop_pairs(self, combine_beat_plp=False):
        runtime_start = time.time()

        S = librosa.core.stft(y=self.audio)
        S_power = np.abs(S) ** 2
        S_weighed = librosa.core.perceptual_weighting(
            S=S_power, frequencies=librosa.fft_frequencies(sr=self.rate)
        )
        mel_spectrogram = librosa.feature.melspectrogram(S=S_weighed)
        onset_env = librosa.onset.onset_strength(S=mel_spectrogram)
        bpm, beats = librosa.beat.beat_track(onset_envelope=onset_env)

        logging.info("Detected {} beats at {:.0f} bpm".format(beats.size, bpm))

        chroma = librosa.feature.chroma_stft(S=S_power)

        power_db = librosa.power_to_db(mel_spectrogram, ref=np.max)
        min_duration = int(chroma.shape[-1] * self.min_duration_multiplier)

        runtime_end = time.time()
        prep_time = runtime_end - runtime_start
        logging.info("Finished initial prep in {:.3}s".format(prep_time))

        def loop_subroutine(combine_beat_plp=combine_beat_plp, beats=beats):
            if combine_beat_plp:
                pulse = librosa.beat.plp(onset_envelope=onset_env)
                beats_plp = np.flatnonzero(librosa.util.localmax(pulse))
                beats = np.union1d(beats, beats_plp)
                logging.info(
                    "Detected {} total points by combining PLP with existing beats".format(
                        beats.size
                    )
                )
            candidate_pairs = []

            beats = np.sort(beats)

            self._loop_finding_routine(
                beats, 1, beats.size, chroma, power_db, min_duration, candidate_pairs
            )

            if len(candidate_pairs) == 0:
                return candidate_pairs

            pruned_list = self._dB_prune(candidate_pairs)

            beats_per_second = bpm / 60
            num_test_beats = 8
            seconds_to_test = num_test_beats / beats_per_second
            test_offset = librosa.samples_to_frames(int(seconds_to_test * self.rate))

            # adjust offset for very short tracks to half its length
            if test_offset > chroma.shape[-1]:
                test_offset = int(chroma.shape[-1] / 2)

            weights = _weights(test_offset, expo_step=int(test_offset / num_test_beats))
            norm_weights = weights / np.linalg.norm(weights)

            pair_score_list = [
                self.pair_score(
                    pruned_list[i]["loop_start"],
                    pruned_list[i]["loop_end"],
                    chroma,
                    test_duration=test_offset,
                    weights=norm_weights,
                )
                for i in range(len(pruned_list))
            ]

            # Add cosine similarity as score
            for i in range(len(pruned_list)):
                pruned_list[i]["score"] = pair_score_list[i]

            # re-sort based on new score
            pruned_list = sorted(pruned_list, reverse=True, key=lambda x: x["score"])

            # prefer longer loops for highly similar sequences
            self._prioritize_duration(pruned_list)

            # return top 10 scores
            return pruned_list[:10]

        pruned_list = loop_subroutine()

        # Retry will trigger when:
        # (a) there is no beat sequence with <5dB difference and >95% similarity
        # (b) list is empty
        retry = True
        for i in range(len(pruned_list)):
            if pruned_list[i]["dB_diff"] < 5.0 and pruned_list[i]["score"] > 0.975:
                retry = False
                break

        if retry and not combine_beat_plp:
            logging.info(
                "No suitable loop points found with current parameters. Retrying with additional beat points from PLP method."
            )
            pruned_list = loop_subroutine(combine_beat_plp=True)

        if self.trim_offset[0] > 0:
            for i in range(len(pruned_list)):
                pruned_list[i]["loop_start"] = self.apply_trim_offset(
                    pruned_list[i]["loop_start"]
                )
                pruned_list[i]["loop_end"] = self.apply_trim_offset(
                    pruned_list[i]["loop_end"]
                )

        logging.info(f"Found {len(pruned_list)} possible loop points")

        for point in pruned_list:
            logging.info(
                "Found from {} to {}, dB_diff:{}, similarity:{}".format(
                    point["loop_start"],
                    point["loop_end"],
                    point["dB_diff"],
                    point["score"],
                )
            )

        return pruned_list

    def _dB_prune(self, candidate_pairs):
        candidate_pairs = sorted(
            candidate_pairs, reverse=False, key=lambda x: x["dB_diff"]
        )
        db_diff_array = np.array(
            [candidate_pairs[i]["dB_diff"] for i in range(len(candidate_pairs))]
        )

        db_diff_avg = np.average(db_diff_array)
        db_diff_std = np.std(db_diff_array)
        dev_threshold = db_diff_avg - (1 * db_diff_std)
        acceptable_dB_diff = 5

        max_acceptable_idx = np.searchsorted(
            db_diff_array, acceptable_dB_diff, side="right"
        )
        dev_idx = np.searchsorted(db_diff_array, dev_threshold, side="right")
        avg_idx = np.searchsorted(db_diff_array, db_diff_avg, side="right")

        if max_acceptable_idx >= dev_idx:
            return candidate_pairs[:max_acceptable_idx]
        else:
            return candidate_pairs[: dev_idx if dev_idx > 4 else avg_idx]

    def _prioritize_duration(self, pruned_list):
        db_diff_array = np.array(
            [pruned_list[i]["dB_diff"] for i in range(len(pruned_list))]
        )
        db_diff_avg = np.average(db_diff_array)
        db_diff_std = np.std(db_diff_array)
        dev_threshold = db_diff_avg - (1 * db_diff_std)

        duration_argmax = 0
        current_max = 0

        for i in range(len(pruned_list)):
            if pruned_list[i]["score"] < 0.99:
                break
            duration = pruned_list[i]["loop_end"] - pruned_list[i]["loop_start"]
            if duration > current_max and pruned_list[i]["dB_diff"] < dev_threshold:
                current_max = duration
                duration_argmax = i

        best_longest_loop = pruned_list[duration_argmax]
        pruned_list[duration_argmax] = pruned_list[0]
        pruned_list[0] = best_longest_loop

    def pair_score(self, b1, b2, chroma, test_duration, weights=None):
        look_ahead_score = self._subseq_beat_similarity(
            b1, b2, chroma, test_duration, weights=weights
        )
        look_back_score = self._subseq_beat_similarity(
            b1, b2, chroma, -test_duration, weights=weights
        )

        # return highest value
        return (
            look_ahead_score if look_ahead_score > look_back_score else look_back_score
        )

    def _subseq_beat_similarity(self, b1, b2, chroma, test_duration, weights=None):
        if test_duration < 0:
            b1_test_from = b1 + test_duration
            b1_test_to = b1
            b2_test_from = b2 + test_duration
            b2_test_to = b2

            # reflect weights array
            # testing view corresponds to: x.. b
            # weights view corresponds to: b.. x
            if weights is not None:
                weights = weights[::-1]

        else:
            b1_test_from = b1
            b1_test_to = b1 + test_duration
            b2_test_from = b2
            b2_test_to = b2 + test_duration

        # treat the chroma/music array as circular
        # to account for loops that start near the end back to the beginning
        shift = 0
        max_offset = chroma.shape[-1]

        if b1_test_from < 0 or b2_test_from < 0:
            # double negative = positive
            # shift array clockwise
            if b1_test_from < 0:
                shift = -b1_test_from
            else:
                shift = -b2_test_from

        if b1_test_to > max_offset or b2_test_to > max_offset:
            # shift will be positive
            # shift array anti-clockwise
            if b1_test_to > max_offset:
                shift = -(b1_test_to - max_offset)
            else:
                shift = -(b2_test_to - max_offset)

        if shift != 0:
            # apply shift offset
            b1_test_from = b1_test_from + shift
            b2_test_from = b2_test_from + shift
            chroma = np.roll(chroma, shift, axis=1)

        test_offset = np.abs(test_duration)

        cosine_sim = np.zeros(test_offset)

        for i in range(test_offset):
            dot_prod = np.dot(
                chroma[..., b1_test_from + i], chroma[..., b2_test_from + i]
            )
            b1_norm = np.linalg.norm(chroma[..., b1_test_from + i])
            b2_norm = np.linalg.norm(chroma[..., b2_test_from + i])
            cosine_sim[i] = dot_prod / (b1_norm * b2_norm)

        return np.average(cosine_sim, weights=weights)

    def apply_trim_offset(self, frame):
        return (
            librosa.samples_to_frames(
                librosa.frames_to_samples(frame) + self.trim_offset[0]
            )
            if self.trim_offset[0] != 0
            else frame
        )

    def samples_to_frames(self, samples):
        return librosa.core.samples_to_frames(samples)

    def frames_to_samples(self, frame):
        return librosa.core.frames_to_samples(frame)

    def frames_to_ftime(self, frame):
        time_sec = librosa.core.frames_to_time(frame, sr=self.rate)
        return "{:02.0f}:{:06.3f}".format(time_sec // 60, time_sec % 60)

    def play_looping(self, loop_start, loop_end):
        from mpg123 import ENC_FLOAT_32
        from mpg123 import Out123

        out = Out123()
        encoding = ENC_FLOAT_32

        out.start(self.rate, self.channels, encoding)

        playback_frames = librosa.util.frame(self.playback_audio.flatten(order="F"))
        adjusted_loop_start = loop_start * self.channels
        adjusted_loop_end = loop_end * self.channels

        i = 0
        loop_count = 0
        try:
            while True:
                out.play(playback_frames[..., i])
                i += 1
                if i == adjusted_loop_end:
                    i = adjusted_loop_start
                    loop_count += 1
                    print("Currently on loop #{}".format(loop_count), end="\r")

        except KeyboardInterrupt:
            print()  # so that the program ends on a newline

    def export(
        self, loop_start, loop_end, format="WAV", output_dir=None, preserve_tags=False
    ):

        if output_dir is not None:
            filename = os.path.split(self.filename)[1]
            out_path = os.path.join(output_dir, filename)
        else:
            out_path = os.path.abspath(self.filename)

        loop_start = self.frames_to_samples(loop_start)
        loop_end = self.frames_to_samples(loop_end)

        soundfile.write(
            out_path + "-intro." + format.lower(),
            self.playback_audio[..., :loop_start].T,
            self.rate,
            format=format,
        )
        soundfile.write(
            out_path + "-loop." + format.lower(),
            self.playback_audio[..., loop_start:loop_end].T,
            self.rate,
            format=format,
        )
        soundfile.write(
            out_path + "-outro." + format.lower(),
            self.playback_audio[..., loop_end:].T,
            self.rate,
            format=format,
        )

        if preserve_tags:
            import taglib

            track = taglib.File(self.filename)

            intro_file = taglib.File(out_path + "-intro." + format.lower())
            loop_file = taglib.File(out_path + "-loop." + format.lower())
            outro_file = taglib.File(out_path + "-outro." + format.lower())

            try:
                original_title = (
                    track.tags["TITLE"][0]
                    if track.tags is not None and len(track.tags["TITLE"]) > 0
                    else os.path.split(self.filename)[-1]
                )
            except KeyError:
                original_title = os.path.split(self.filename)[-1]

            intro_file.tags = track.tags
            loop_file.tags = track.tags
            outro_file.tags = track.tags

            intro_file.tags["TITLE"] = [original_title + " - Intro"]
            intro_file.save()

            loop_file.tags["TITLE"] = [original_title + " - Loop"]
            loop_file.save()

            outro_file.tags["TITLE"] = [original_title + " - Outro"]
            outro_file.save()

    def export_json(self, loop_start, loop_end, score, output_dir=None):
        if output_dir is not None:
            filename = os.path.split(self.filename)[1]
            out_path = os.path.join(output_dir, filename)
        else:
            out_path = os.path.abspath(self.filename)

        loop_start = self.frames_to_samples(loop_start)
        loop_end = self.frames_to_samples(loop_end)

        out = {
            "loop_start": int(loop_start),
            "loop_end": int(loop_end),
            "score": float(f"{score:.4}"),
        }

        with open(out_path + ".loop_points.json", "w") as file:
            json.dump(out, fp=file)


def _weights(length, expo_step=1):
    weights = np.empty(length)
    weights[0] = length * expo_step
    i = 1
    while i < length:
        if expo_step != 0 and i % expo_step == 0:
            weights[i] = weights[i - 1] / 2
        else:
            weights[i] = weights[i - 1] - 1
        i += 1
    return weights
