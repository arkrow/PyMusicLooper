import logging
import time

import librosa
import numpy as np
from numba import njit

from .audio import MLAudio
from .exceptions import LoopNotFoundError


class LoopPair:
    loop_start:int
    loop_end:int
    note_distance:float
    loudness_difference:float
    score:float

    def __init__(self, loop_start:int, loop_end:int, note_distance:float, loudness_difference:float, score:float=None):
        self.loop_start = loop_start
        self.loop_end = loop_end
        self.note_distance = note_distance
        self.loudness_difference = loudness_difference
        self.score = score


def find_best_loop_points(mlaudio: MLAudio,
                          min_duration_multiplier:float=0.35,
                          min_loop_duration:int=None,
                          max_loop_duration:int=None,
                          approx_loop_start=None,
                          approx_loop_end=None) -> list[LoopPair]:
    runtime_start = time.perf_counter()
    min_loop_duration = (mlaudio.seconds_to_frames(min_loop_duration)
                        if min_loop_duration is not None else
                        mlaudio.seconds_to_frames(
                            int(min_duration_multiplier *
                                mlaudio.total_duration)))
    max_loop_duration = (mlaudio.seconds_to_frames(max_loop_duration)
                            if max_loop_duration is not None else
                            mlaudio.seconds_to_frames(mlaudio.total_duration))

    if approx_loop_start is not None and approx_loop_end is not None:
        # Skipping the unncessary beat analysis (in this case) speeds up the analysis runtime by ~2x
        # and significantly reduces the total memory consumption
        chroma, power_db, _, _ = _analyze_audio(mlaudio, skip_beat_analysis=True)
        # Set bpm to a general average of 120
        bpm = 120
        approx_loop_start = mlaudio.seconds_to_frames(approx_loop_start, apply_trim_offset=True)
        approx_loop_end = mlaudio.seconds_to_frames(approx_loop_end, apply_trim_offset=True)
        n_frames_to_check = mlaudio.seconds_to_frames(2)

        # Correct min and max loop duration checks to the specified range
        min_loop_duration = (approx_loop_end - n_frames_to_check) - (approx_loop_start + n_frames_to_check) - 1
        max_loop_duration = (approx_loop_end + n_frames_to_check) - (approx_loop_start - n_frames_to_check) + 1

        # Override the beats to check with the specified approx points +/- 2 seconds
        beats = np.concatenate([
            np.arange(start=max(0, approx_loop_start - n_frames_to_check),
                      stop=min(mlaudio.seconds_to_frames(mlaudio.total_duration), approx_loop_start + n_frames_to_check)),
            np.arange(start=max(0, approx_loop_end - n_frames_to_check),
                      stop=min(mlaudio.seconds_to_frames(mlaudio.total_duration), approx_loop_end + n_frames_to_check))
            ])
    else:
        chroma, power_db, bpm, beats = _analyze_audio(mlaudio)
        logging.info("Detected {} beats at {:.0f} bpm".format(beats.size, bpm))

    logging.info("Finished initial audio processing in {:.3}s".format(time.perf_counter() - runtime_start))

    initial_pairs_start_time = time.perf_counter()


    # Since numba jitclass cannot be cached, the pair data must be stored temporarily in a list of tuple
    # (instead of a list of LoopPairs directly) and then loaded into a list of LoopPair objects using list comprehension
    unproc_candidate_pairs = _find_candidate_pairs(chroma, power_db, beats, min_loop_duration, max_loop_duration)
    candidate_pairs = [
        LoopPair(loop_start=tup[0], loop_end=tup[1], note_distance=tup[2], loudness_difference=tup[3]) for tup in unproc_candidate_pairs
    ]

    n_candidate_pairs = len(candidate_pairs) if candidate_pairs is not None else 0
    logging.info(f"Found {n_candidate_pairs} possible loop points in {(time.perf_counter() - initial_pairs_start_time):.3}s")

    if not candidate_pairs:
        raise LoopNotFoundError(f'No loop points found for {mlaudio.filename} with current parameters.')

    filtered_candidate_pairs = _assess_and_filter_loop_pairs(mlaudio, chroma, bpm, candidate_pairs)

    # prefer longer loops for highly similar sequences
    if len(filtered_candidate_pairs) > 1:
        _prioritize_duration(filtered_candidate_pairs)

    if mlaudio.trim_offset > 0:
        for pair in filtered_candidate_pairs:
            pair.loop_start = int(mlaudio.apply_trim_offset(
                pair.loop_start
            ))
            pair.loop_end = int(mlaudio.apply_trim_offset(
                pair.loop_end
            ))
    logging.info(f"Filtered to {len(filtered_candidate_pairs)} best candidate loop points")
    logging.info("Total analysis runtime: {:.3}s".format(time.perf_counter()-runtime_start))

    if not filtered_candidate_pairs:
        raise LoopNotFoundError(f'No loop points found for {mlaudio.filename} with current parameters.')
    else:
        return filtered_candidate_pairs


def _analyze_audio(mlaudio: MLAudio, skip_beat_analysis=False) -> tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    S = librosa.core.stft(y=mlaudio.audio)
    S_power = np.abs(S) ** 2
    S_weighed = librosa.core.perceptual_weighting(
        S=S_power, frequencies=librosa.fft_frequencies(sr=mlaudio.rate)
    )
    mel_spectrogram = librosa.feature.melspectrogram(S=S_weighed, sr=mlaudio.rate, n_mels=128, fmax=8000)
    chroma = librosa.feature.chroma_stft(S=S_power)
    power_db = librosa.power_to_db(S_weighed, ref=np.median)

    if skip_beat_analysis:
        return chroma, power_db, None, None

    onset_env = librosa.onset.onset_strength(S=mel_spectrogram)

    pulse = librosa.beat.plp(onset_envelope=onset_env)
    beats_plp = np.flatnonzero(librosa.util.localmax(pulse))
    bpm, beats = librosa.beat.beat_track(onset_envelope=onset_env)

    beats = np.union1d(beats, beats_plp)
    beats = np.sort(beats)
    return chroma, power_db, bpm, beats


@njit
def _db_diff(power_db_f1: np.ndarray, power_db_f2: np.ndarray) -> float:
    f1_max = np.max(power_db_f1)
    f2_max = np.max(power_db_f2)
    return max(f1_max, f2_max) - min(f1_max, f2_max)


@njit
def _norm(a: np.ndarray) -> float:
    return np.sqrt(np.sum(np.abs(a)**2, axis=0))


@njit(cache=True)
def _find_candidate_pairs(chroma: np.ndarray, power_db: np.ndarray, beats: np.ndarray, min_loop_duration: int, max_loop_duration: int) -> list[tuple[int,int,float,float]]:
    candidate_pairs = []

    # Magic constants
    ## Mainly found through trial and error,
    ## higher values typically result in the inclusion of musically unrelated beats/notes
    ACCEPTABLE_NOTE_DEVIATION = 0.0875
    ## Since the _db_diff comparison is takes a perceptually weighted power_db frame,
    ## the difference should be imperceptible (ideally, close to 0), but the min threshold is set to 0.75
    ## Based on trial and error, values higher than ~1 have a jarring difference in loudness
    ACCEPTABLE_LOUDNESS_DIFFERENCE = 0.75

    deviation = _norm(chroma[..., beats] * ACCEPTABLE_NOTE_DEVIATION)

    for idx, loop_end in enumerate(beats):
        for loop_start in beats:
            loop_length = loop_end - loop_start
            if loop_length < min_loop_duration:
                break
            if loop_length > max_loop_duration:
                continue
            note_distance = _norm(chroma[..., loop_end] - chroma[..., loop_start])
            
            if note_distance <= deviation[idx]:
                loudness_difference = _db_diff(
                    power_db[..., loop_end], power_db[..., loop_start]
                )
                loop_pair = (int(loop_start), int(loop_end), note_distance, loudness_difference)
                if loudness_difference <= ACCEPTABLE_LOUDNESS_DIFFERENCE:
                    candidate_pairs.append(loop_pair)

    return candidate_pairs


def _assess_and_filter_loop_pairs(mlaudio: MLAudio, chroma: np.ndarray, bpm:float, candidate_pairs: list[LoopPair]):
    beats_per_second = bpm / 60
    num_test_beats = 12
    seconds_to_test = num_test_beats / beats_per_second
    test_offset = librosa.samples_to_frames(int(seconds_to_test * mlaudio.rate))

    # adjust offset for very short tracks to 25% of its length
    if test_offset > chroma.shape[-1]:
        test_offset = chroma.shape[-1] // 4

    # Prune candidates if there are too many
    if len(candidate_pairs) >= 100:
        pruned_candidate_pairs = _prune_candidates(candidate_pairs)
    else:
        pruned_candidate_pairs = candidate_pairs

    weights = _weights(test_offset, start=test_offset // num_test_beats)
    
    pair_score_list = [
        _calculate_loop_score(
            int(pair.loop_start),
            int(pair.loop_end),
            chroma,
            test_duration=test_offset,
            weights=weights,
        ) for pair in pruned_candidate_pairs
    ]
    # Add cosine similarity as score
    for pair, score in zip(pruned_candidate_pairs, pair_score_list):
        pair.score = score

    if len(pruned_candidate_pairs) >= 50:
        score_pruned_candidate_pairs = _prune_by_score(pruned_candidate_pairs)
    else:
        score_pruned_candidate_pairs = pruned_candidate_pairs

    # re-sort based on new score
    score_pruned_candidate_pairs = sorted(score_pruned_candidate_pairs, reverse=True, key=lambda x: x.score)
    return score_pruned_candidate_pairs

def _prune_candidates(candidate_pairs, drop_bottom_x_percentile=50):
    db_diff_array = np.array(
        [pair.loudness_difference for pair in candidate_pairs]
    )
    note_dist_array = np.array(
        [pair.note_distance for pair in candidate_pairs]
    )

    # Minimum value used to avoid issues with tracks with lots of silence
    epsilon = 1e-3

    db_threshold = np.percentile(db_diff_array[db_diff_array > epsilon], drop_bottom_x_percentile) # lower is better
    note_dist_threshold = np.percentile(note_dist_array[note_dist_array > epsilon], drop_bottom_x_percentile) # lower is better

    indicies_that_meet_cond = np.flatnonzero((db_diff_array < db_threshold) & (note_dist_array < note_dist_threshold))
    return [candidate_pairs[idx] for idx in indicies_that_meet_cond]

def _prune_by_score(candidate_pairs, percentile=25, acceptable_score=80):
    candidate_pairs = sorted(candidate_pairs, key=lambda x: x.score)

    score_array = np.array(
        [pair.score for pair in candidate_pairs]
    )

    score_threshold = np.percentile(score_array, percentile)
    percentile_idx = np.searchsorted(score_array, score_threshold, side="left")
    acceptable_idx = np.searchsorted(score_array, acceptable_score, side="left")

    return candidate_pairs[min(percentile_idx, acceptable_idx):]


def _prioritize_duration(pair_list):
    db_diff_array = np.array(
        [pair.loudness_difference for pair in pair_list]
    )
    db_threshold = np.median(db_diff_array)

    duration_argmax = 0
    duration_max = 0

    score_array = np.array(
        [pair.score for pair in pair_list]
    )
    score_threshold = np.percentile(score_array, 90)

    score_threshold = max(score_threshold, pair_list[0].score - 1e-4) # Must be a negligible difference from the top score 

    # Since pair_list is already sorted
    # Break the loop if the condition is not met 
    for idx, pair in enumerate(pair_list):
        if pair.score < score_threshold:
            break
        duration = pair.loop_end - pair.loop_start
        if duration > duration_max and pair.loudness_difference <= db_threshold:
            duration_max, duration_argmax = duration, idx

    if duration_argmax:
        pair_list.insert(0, pair_list.pop(duration_argmax))

def _calculate_loop_score(b1, b2, chroma, test_duration, weights=None):
    lookahead_score = _calculate_subseq_beat_similarity(
        b1, b2, chroma, test_duration, weights=weights
    )
    lookbehind_score = _calculate_subseq_beat_similarity(
        b1, b2, chroma, -test_duration, weights=weights[::-1]
    )

    return max(lookahead_score, lookbehind_score)


def _calculate_subseq_beat_similarity(b1_start, b2_start, chroma, test_duration, weights=None):
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
    
def _weights(length:int, start:int=100, stop:int=1):
    return np.geomspace(start, stop, num=length)
