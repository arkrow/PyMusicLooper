import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import librosa
import numpy as np
from numba import njit

from .audio import MLAudio
from .exceptions import LoopNotFoundError


@dataclass
class LoopPair:
    """A data class that encapsulates the loop point related data.
    Contains:
        loop_start: int (exact loop start position in samples)
        loop_end: int (exact loop end position in samples)
        note_distance: float
        loudness_difference: float
        score: float. Defaults to 0.
    """

    _loop_start_frame_idx: int
    _loop_end_frame_idx: int
    note_distance: float
    loudness_difference: float
    score: float = 0
    loop_start: int = 0
    loop_end: int = 0


def find_best_loop_points(
    mlaudio: MLAudio,
    min_duration_multiplier: float = 0.35,
    min_loop_duration: Optional[float] = None,
    max_loop_duration: Optional[float] = None,
    approx_loop_start: Optional[float] = None,
    approx_loop_end: Optional[float] = None,
    brute_force: bool = False,
    disable_pruning: bool = False,
) -> List[LoopPair]:
    """Finds the best loop points for a given audio track, given the constraints specified

    Args:
        mlaudio (MLAudio): The MLAudio object to use for analysis
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
    runtime_start = time.perf_counter()
    min_loop_duration = (
        mlaudio.seconds_to_frames(min_loop_duration)
        if min_loop_duration is not None
        else mlaudio.seconds_to_frames(
            int(min_duration_multiplier * mlaudio.total_duration)
        )
    )
    max_loop_duration = (
        mlaudio.seconds_to_frames(max_loop_duration)
        if max_loop_duration is not None
        else mlaudio.seconds_to_frames(mlaudio.total_duration)
    )

    # Loop points must be at least 1 frame apart
    min_loop_duration = max(1, min_loop_duration)

    if approx_loop_start is not None and approx_loop_end is not None:
        # Skipping the unnecessary beat analysis (in this case) speeds up the analysis runtime by ~2x
        # and significantly reduces the total memory consumption
        chroma, power_db, _, _ = _analyze_audio(mlaudio, skip_beat_analysis=True)
        # Set bpm to a general average of 120
        bpm = 120.0

        approx_loop_start = mlaudio.seconds_to_frames(
            approx_loop_start, apply_trim_offset=True
        )
        approx_loop_end = mlaudio.seconds_to_frames(
            approx_loop_end, apply_trim_offset=True
        )

        n_frames_to_check = mlaudio.seconds_to_frames(2)

        # Adjust min and max loop duration checks to the specified range
        min_loop_duration = (
            (approx_loop_end - n_frames_to_check)
            - (approx_loop_start + n_frames_to_check)
            - 1
        )
        max_loop_duration = (
            (approx_loop_end + n_frames_to_check)
            - (approx_loop_start - n_frames_to_check)
            + 1
        )

        # Override the beats to check with the specified approx points +/- 2 seconds
        beats = np.concatenate(
            [
                np.arange(
                    start=max(0, approx_loop_start - n_frames_to_check),
                    stop=min(
                        mlaudio.seconds_to_frames(mlaudio.total_duration),
                        approx_loop_start + n_frames_to_check,
                    ),
                ),
                np.arange(
                    start=max(0, approx_loop_end - n_frames_to_check),
                    stop=min(
                        mlaudio.seconds_to_frames(mlaudio.total_duration),
                        approx_loop_end + n_frames_to_check,
                    ),
                ),
            ]
        )
    else:
        chroma, power_db, bpm, beats = _analyze_audio(mlaudio)
        logging.info(f"Detected {beats.size} beats at {bpm:.0f} bpm")
    
    if brute_force:
        beats = np.arange(start=0, stop=chroma.shape[-1], step=1, dtype=int)
        logging.info(f"Overriding number of beats to check with: {beats.size}")
        logging.info(f"Estimated iterations required using brute force: {int(beats.size*beats.size*(1-(min_loop_duration/chroma.shape[-1])))}")
        logging.info("**NOTICE** The program may appear frozen, but it will be continuing processing in the background. This operation may take several minutes to complete.")

    logging.info(
        "Finished initial audio processing in {:.3f}s".format(
            time.perf_counter() - runtime_start
        )
    )

    initial_pairs_start_time = time.perf_counter()

    # Since numba jitclass cannot be cached, the pair data must be stored temporarily in a list of tuple
    # (instead of a list of LoopPairs directly) and then loaded into a list of LoopPair objects using list comprehension
    unproc_candidate_pairs = _find_candidate_pairs(
        chroma, power_db, beats, min_loop_duration, max_loop_duration
    )
    candidate_pairs = [
        LoopPair(
            _loop_start_frame_idx=tup[0],
            _loop_end_frame_idx=tup[1],
            note_distance=tup[2],
            loudness_difference=tup[3],
        )
        for tup in unproc_candidate_pairs
    ]

    n_candidate_pairs = len(candidate_pairs) if candidate_pairs is not None else 0
    logging.info(
        f"Found {n_candidate_pairs} possible loop points in"
        f" {(time.perf_counter() - initial_pairs_start_time):.3f}s"
    )

    if not candidate_pairs:
        raise LoopNotFoundError(
            f"No loop points found for \"{mlaudio.filename}\" with current parameters."
        )

    filtered_candidate_pairs = _assess_and_filter_loop_pairs(
        mlaudio, chroma, bpm, candidate_pairs, disable_pruning
    )

    # prefer longer loops for highly similar sequences
    if len(filtered_candidate_pairs) > 1:
        _prioritize_duration(filtered_candidate_pairs)

    # Set the exact loop start and end in samples and adjust them
    # to the nearest zero crossing. Avoids audio popping/clicking while looping
    # as much as possible.
    for pair in filtered_candidate_pairs:
        if mlaudio.trim_offset > 0:
            pair._loop_start_frame_idx = int(
                mlaudio.apply_trim_offset(pair._loop_start_frame_idx)
            )
            pair._loop_end_frame_idx = int(
                mlaudio.apply_trim_offset(pair._loop_end_frame_idx)
            )
        pair.loop_start = nearest_zero_crossing(
            mlaudio, mlaudio.frames_to_samples(pair._loop_start_frame_idx)
        )
        pair.loop_end = nearest_zero_crossing(
            mlaudio, mlaudio.frames_to_samples(pair._loop_end_frame_idx)
        )

    if not filtered_candidate_pairs:
        raise LoopNotFoundError(
            f"No loop points found for {mlaudio.filename} with current parameters."
        )

    logging.info(
        f"Filtered to {len(filtered_candidate_pairs)} best candidate loop points"
    )
    logging.info(
        f"Total analysis runtime: {time.perf_counter() - runtime_start:.3f}s"
    )

    return filtered_candidate_pairs


def _analyze_audio(
    mlaudio: MLAudio, skip_beat_analysis=False
) -> Tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """Performs the main audio analysis required

    Args:
        mlaudio (MLAudio): the MLAudio object to perform analysis on
        skip_beat_analysis (bool, optional): Skips beat analysis if true and returns None for bpm and beats. Defaults to False.

    Returns:
        Tuple[np.ndarray, np.ndarray, float, np.ndarray]: a tuple containing the (chroma spectrogram, power spectrogram in dB, tempo/bpm, frame indices of detected beats)
    """
    S = librosa.core.stft(y=mlaudio.audio)
    S_power = np.abs(S) ** 2
    S_weighed = librosa.core.perceptual_weighting(
        S=S_power, frequencies=librosa.fft_frequencies(sr=mlaudio.rate)
    )
    mel_spectrogram = librosa.feature.melspectrogram(
        S=S_weighed, sr=mlaudio.rate, n_mels=128, fmax=8000
    )
    chroma = librosa.feature.chroma_stft(S=S_power)
    power_db = librosa.power_to_db(S_weighed, ref=np.median)

    if skip_beat_analysis:
        return chroma, power_db, None, None

    try:
        onset_env = librosa.onset.onset_strength(S=mel_spectrogram)

        pulse = librosa.beat.plp(onset_envelope=onset_env)
        beats_plp = np.flatnonzero(librosa.util.localmax(pulse))
        bpm, beats = librosa.beat.beat_track(onset_envelope=onset_env)

        beats = np.union1d(beats, beats_plp)
        beats = np.sort(beats)
    except Exception as e:
        raise LoopNotFoundError(f"Beat analysis failed for \"{mlaudio.filename}\". Cannot continue.") from e

    return chroma, power_db, bpm, beats


@njit
def _db_diff(power_db_f1: np.ndarray, power_db_f2: np.ndarray) -> float:
    return np.abs(np.max(power_db_f1) - np.max(power_db_f2))


@njit
def _norm(a: np.ndarray) -> float:
    return np.sqrt(np.sum(np.abs(a) ** 2, axis=0))


@njit(cache=True)
def _find_candidate_pairs(
    chroma: np.ndarray,
    power_db: np.ndarray,
    beats: np.ndarray,
    min_loop_duration: int,
    max_loop_duration: int,
) -> List[Tuple[int, int, float, float]]:
    """Generates a list of all valid candidate loop pairs using combinations of beat indices,
    by comparing the notes using the chroma spectrogram and their loudness difference

    Args:
        chroma (np.ndarray): The chroma spectrogram
        power_db (np.ndarray): The power spectrogram in dB
        beats (np.ndarray): The frame indices of detected beats
        min_loop_duration (int): Minimum loop duration (in frames)
        max_loop_duration (int): Maximum loop duration (in frames)

    Returns:
        List[Tuple[int, int, float, float]]: A list of tuples containing each candidate loop pair data in the following format (loop_start, loop_end, note_distance, loudness_difference)
    """
    candidate_pairs = []

    # Magic constants
    ## Mainly found through trial and error,
    ## higher values typically result in the inclusion of musically unrelated beats/notes
    ACCEPTABLE_NOTE_DEVIATION = 0.0875
    ## Since the _db_diff comparison is takes a perceptually weighted power_db frame,
    ## the difference should be imperceptible (ideally, close to 0)
    ## Based on trial and error, values higher than ~0.5 have a perceptible
    ## difference in loudness
    ACCEPTABLE_LOUDNESS_DIFFERENCE = 0.5

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
                loop_pair = (
                    int(loop_start),
                    int(loop_end),
                    note_distance,
                    loudness_difference,
                )
                if loudness_difference <= ACCEPTABLE_LOUDNESS_DIFFERENCE:
                    candidate_pairs.append(loop_pair)

    return candidate_pairs


def _assess_and_filter_loop_pairs(
    mlaudio: MLAudio,
    chroma: np.ndarray,
    bpm: float,
    candidate_pairs: List[LoopPair],
    disable_pruning: bool = False,
) -> List[LoopPair]:
    """Assigns the scores to each loop pair and prunes the list of candidate loop pairs

    Args:
        mlaudio (MLAudio): MLAudio object of the track being analyzed
        chroma (np.ndarray): The chroma spectrogram
        bpm (float): The estimated bpm/tempo of the track
        candidate_pairs (List[LoopPair]): The list of candidate loop pairs found
        disable_pruning (bool, optional): Returns all the candidate loop points without filtering. Defaults to False.

    Returns:
        List[LoopPair]: A scored and filtered list of valid loop candidate pairs
    """
    beats_per_second = bpm / 60
    num_test_beats = 12
    seconds_to_test = num_test_beats / beats_per_second
    test_offset = mlaudio.samples_to_frames(int(seconds_to_test * mlaudio.rate))

    # adjust offset for very short tracks to 25% of its length
    if test_offset > chroma.shape[-1]:
        test_offset = chroma.shape[-1] // 4

    # Prune candidates if there are too many
    if len(candidate_pairs) >= 250 and not disable_pruning:
        pruned_candidate_pairs = _prune_candidates(candidate_pairs)
    else:
        pruned_candidate_pairs = candidate_pairs

    weights = _weights(test_offset, start=max(2, test_offset // num_test_beats), stop=1)

    pair_score_list = [
        _calculate_loop_score(
            int(pair._loop_start_frame_idx),
            int(pair._loop_end_frame_idx),
            chroma,
            test_duration=test_offset,
            weights=weights,
        )
        for pair in pruned_candidate_pairs
    ]
    # Add cosine similarity as score
    for pair, score in zip(pruned_candidate_pairs, pair_score_list):
        pair.score = score

    # re-sort based on new score
    pruned_candidate_pairs = sorted(
        pruned_candidate_pairs, reverse=True, key=lambda x: x.score
    )
    return pruned_candidate_pairs


def _prune_candidates(
    candidate_pairs: List[LoopPair],
    keep_top_notes: float = 75,
    keep_top_loudness: float = 90,
    acceptable_loudness=0.25,
) -> List[LoopPair]:
    db_diff_array = np.array([pair.loudness_difference for pair in candidate_pairs])
    note_dist_array = np.array([pair.note_distance for pair in candidate_pairs])

    # Minimum value used to avoid issues with tracks with lots of silence
    epsilon = 1e-3
    min_adjusted_db_diff_array = db_diff_array[db_diff_array > epsilon]
    min_adjusted_note_dist_array = note_dist_array[note_dist_array > epsilon]

    # Avoid index errors by having at least 3 elements when performing percentile-based pruning
    # Otherwise, skip by setting the value to the highest available
    if min_adjusted_db_diff_array.size > 3:
        db_threshold = np.percentile(
            min_adjusted_db_diff_array, keep_top_notes
        )
    else:
        db_threshold = np.max(db_diff_array)

    if min_adjusted_note_dist_array.size > 3:
        note_dist_threshold = np.percentile(
            min_adjusted_note_dist_array, keep_top_loudness
        )
    else:
        note_dist_threshold = np.max(note_dist_array)

    # Lower values are better
    indices_that_meet_cond = np.flatnonzero(
        (db_diff_array <= max(acceptable_loudness, db_threshold)) & (note_dist_array <= note_dist_threshold)
    )
    return [candidate_pairs[idx] for idx in indices_that_meet_cond]


def _prioritize_duration(pair_list: List[LoopPair]) -> List[LoopPair]:
    db_diff_array = np.array([pair.loudness_difference for pair in pair_list])
    db_threshold = np.median(db_diff_array)

    duration_argmax = 0
    duration_max = 0

    score_array = np.array([pair.score for pair in pair_list])
    score_threshold = np.percentile(score_array, 90)

    # Must be a negligible difference from the top score
    score_threshold = max(score_threshold, pair_list[0].score - 1e-4)

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


def _calculate_loop_score(
    b1: int,
    b2: int,
    chroma: np.ndarray,
    test_duration: int,
    weights: Optional[np.ndarray] = None,
) -> float:
    """Calculates the similarity of two sequences given the starting indices `b1` and `b2` for the period of the `test_duration` specified.
        Returns the best score based on the cosine similarity of subsequent (or preceding) notes.

    Args:
        b1 (int): Frame index of the first beat to compare
        b2 (int): Frame index of the second beat to compare
        chroma (np.ndarray): The chroma spectrogram of the audio
        test_duration (int): How many frames along the chroma spectrogram to test.
        weights (np.ndarray, optional): If specified, will provide a weighted average of the note scores according to the weight array provided. Defaults to None.

    Returns:
        float: the weighted average of the cosine similarity of the notes along the tested region
    """
    lookahead_score = _calculate_subseq_beat_similarity(
        b1, b2, chroma, test_duration, weights=weights
    )
    lookbehind_score = _calculate_subseq_beat_similarity(
        b1, b2, chroma, -test_duration, weights=weights[::-1]
    )

    return max(lookahead_score, lookbehind_score)


def _calculate_subseq_beat_similarity(
    b1_start: int,
    b2_start: int,
    chroma: np.ndarray,
    test_end_offset: int,
    weights: Optional[np.ndarray] = None,
) -> float:
    """Calculates the similarity of subsequent notes of the two specified indices (b1_start, b2_start) using cosine similarity

    Args:
        b1_start (int): Starting frame index of the first beat to compare
        b2_start (int): Starting frame index of the second beat to compare
        chroma (np.ndarray): The chroma spectrogram of the audio
        test_end_offset (int): The number of frames to offset from the starting index. If negative, will be testing the preceding frames instead of the subsequent frames.
        weights (np.ndarray, optional): If specified, will provide a weighted average of the note scores according to the weight array provided. Defaults to None.

    Returns:
        float: the weighted average of the cosine similarity of the notes along the tested region
    """
    chroma_len = chroma.shape[-1]
    test_length = abs(test_end_offset)

    if test_end_offset < 0:
        b1_end = b1_start
        b2_end = b2_start
        max_negative_offset = max(test_end_offset, -b1_start, -b2_start)
        b1_start += max_negative_offset
        b2_start += max_negative_offset
        max_offset = abs(max_negative_offset)
    else:
        # clip to chroma len
        b1_end = min(b1_start + test_length, chroma_len)
        b2_end = min(b2_start + test_length, chroma_len)
        # align testing lengths
        max_offset = min(b1_end - b1_start, b2_end - b2_start)
        b1_end, b2_end = (b1_start + max_offset, b2_start + max_offset)

    dot_prod = np.einsum(
        "ij,ij->j", chroma[..., b1_start:b1_end], chroma[..., b2_start:b2_end]
    )
    b1_norm = np.linalg.norm(chroma[..., b1_start:b1_end], axis=0)
    b2_norm = np.linalg.norm(chroma[..., b2_start:b2_end], axis=0)
    cosine_sim = dot_prod / (b1_norm * b2_norm)

    if max_offset < test_length:
        return np.average(
            np.pad(cosine_sim, pad_width=(0, test_length - max_offset), mode="constant", constant_values=0),
            weights=weights,
        )
    else:
        return np.average(cosine_sim, weights=weights)


def _weights(length: int, start: int = 100, stop: int = 1):
    return np.geomspace(start, stop, num=length)


def nearest_zero_crossing(mlaudio: MLAudio, sample_idx: int) -> int:
    """Implementation of Audacity's `At Zero Crossings` feature. https://manual.audacityteam.org/man/select_menu_at_zero_crossings.html
    Description is based on the relevant Audacity manual page, due to identical behaviour.

    Returns the best closest sample point that is at a rising zero crossing point.
    This is a point where a line joining the audio samples rises from left to right and crosses the zero horizontal line that represents silence.
    The shift in audio position is not itself detectable to the ear, but the fact that the joins in the waveform are now of matching height helps avoid clicks in audio.

    This feature does not necessarily find the nearest zero crossing to the current position. It aims to find the crossing where the average amplitude of samples in the vicinity is lowest.

    Args:
        mlaudio (MLAudio): The MLAudio object which contains the relevant audio
        sample_idx (int): The starting sample point to return the nearest zero crossing to

    Returns:
        int: the index of the best sample point that is at a rising zero crossing point closest to the `sample_idx` provided, returns `sample_idx` if none where found
    """
    # Re-implementation of Audacity's NearestZeroCrossing function in Python
    # https://github.com/audacity/audacity/blob/057bf4ee6f71962cd8ecc6dbccf0852695340758/src/menus/SelectMenus.cpp#L30
    # Original credit goes to the Audacity team and contributors
    audio = mlaudio.playback_audio
    rate = mlaudio.rate
    n_channels = mlaudio.n_channels
    # Window is 1/100th of a second
    window_size = int(max(1, rate / 100))

    sample_window = _slice_centered_around_offset(
        audio, sample_idx, window_size=window_size
    )

    dist = _nb_nearest_zcr_helper(sample_window, n_channels, window_size)

    argmin = np.argmin(dist)
    minimum_dist = dist[argmin]

    # If we're worse than 0.2 on average, on one track, then no good.
    if (n_channels == 1) and (minimum_dist > (0.2 * n_channels)):
        return sample_idx
    # If we're worse than 0.6 on average, on multi-track, then no good.
    if (n_channels > 1) and (minimum_dist > (0.6 * n_channels)):
        return sample_idx

    return int(sample_idx + argmin - (window_size // 2))


@njit(cache=True)
def _nb_nearest_zcr_helper(
    sample_window: np.ndarray, n_channels: int, window_size: int
) -> np.ndarray:
    sample_window_length = sample_window.shape[0]
    dist = np.zeros(sample_window_length)

    for channel in range(n_channels):
        prev = 2.0
        one_dist = sample_window[..., channel].copy()
        for i in range(sample_window_length):
            fdist = np.abs(one_dist[i])
            if prev * one_dist[i] > 0:  # both same sign? No good.
                fdist += 0.4  # No good if same sign.
            elif prev > 0.0:
                fdist += 0.1  # medium penalty for downward crossing.
            prev = one_dist[i]
            one_dist[i] = fdist

        for i in range(sample_window_length):
            dist[i] += one_dist[i]
            dist[i] += 0.1 * abs(i - (window_size // 2)) / (window_size / 2)

    return dist


def _slice_centered_around_offset(audio, index, window_size=256):
    offset = window_size // 2
    neg_offset = max(0, index - offset)
    pos_offset = min(audio.shape[0], index + offset)
    return audio[neg_offset:pos_offset]
