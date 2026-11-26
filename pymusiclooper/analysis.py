import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import librosa
import numpy as np
from numba import njit

from pymusiclooper.audio import MLAudio
from pymusiclooper.exceptions import LoopNotFoundError

# Boundary loudness-jump penalty parameters (true A-weighted dB over ~200 ms)
_BOUNDARY_LOUDNESS_WINDOW_S = 0.20
_BOUNDARY_LOUDNESS_PENALTY_CAP = 0.08
_BOUNDARY_LOUDNESS_REF_DB = 3.5

# Macroscopic across-boundary loudness-cliff penalty (true A-weighted dB over ~1.0 s)
# Catches loud-body -> quiet-intro cliffs that slip past 200 ms lookbehind matching.
_MACRO_LOUDNESS_WINDOW_S = 1.0
_MACRO_LOUDNESS_PENALTY_CAP = 0.12
_MACRO_LOUDNESS_REF_DB = 5.0

# Small bidirectional continuity blend so mid-loop transitions matching on both
# sides outscore one-sided cold-start / partial-phrase matches without
# penalizing unique-intro or fade-out tracks.
_BIDIRECTIONAL_BLEND_WEIGHT = 0.03

# Fallback sample-level transition crackle penalty (applied after transition
# refinement if an audible step or slope-kink discontinuity still remains).
_CRACKLE_PENALTY_CAP = 0.05
_CRACKLE_REF_EXCESS = 0.15
_CRACKLE_CONTEXT_SAMPLES = 64

# Proximity window (in seconds) for deduplicating exact and near-identical
# loop candidates after transition refinement (applies to beat-tracked,
# approximate, and brute-force searches).
_DEDUP_PROXIMITY_S = 0.05


@dataclass
class LoopPair:
    """A data class that encapsulates the loop point related data.

    Attributes:
        loop_start (int): Exact loop start position in samples.
        loop_end (int): Exact loop end position in samples.
        note_distance (float): Spectral note distance between loop points.
        loudness_difference (float): A-weighted peak loudness difference in dB between loop points.
        score (float): Overall loop quality score in `[0, 1]`, combining bidirectional weighted chroma cosine similarity with penalties for boundary loudness jumps and residual sample-level transition crackles. Defaults to 0.
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
        List[LoopPair]: A list of deduplicated, transition-refined `LoopPair` objects ordered by loop quality. See the `LoopPair` class for more info.
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
    elif brute_force:
        # Similarly skip beat analysis, as the results will not be used
        chroma, power_db, _, _ = _analyze_audio(mlaudio, skip_beat_analysis=True)
        bpm = 120.0
        beats = np.arange(start=0, stop=chroma.shape[-1], step=1, dtype=int)
        logging.info(f"Overriding number of frames to check with: {beats.size}")
        logging.info(f"Estimated iterations required using brute force: {int(beats.size*beats.size*(1-(min_loop_duration/chroma.shape[-1])))}")
        logging.info("**NOTICE** The program may appear frozen, but processing will continue in the background. This operation may take several minutes to complete.")
    else: # normal mode of operation
        chroma, power_db, bpm, beats = _analyze_audio(mlaudio)
        logging.info(f"Detected {beats.size} beats at {bpm:.0f} bpm")

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
        mlaudio, chroma, bpm, candidate_pairs, disable_pruning, power_db=power_db
    )

    # Set the exact loop start and end in samples and refine both endpoints
    # jointly to eliminate sample-level amplitude steps and slope kinks
    # across all channels.
    for pair in filtered_candidate_pairs:
        if mlaudio.trim_offset > 0:
            pair._loop_start_frame_idx = int(
                mlaudio.apply_trim_offset(pair._loop_start_frame_idx)
            )
            pair._loop_end_frame_idx = int(
                mlaudio.apply_trim_offset(pair._loop_end_frame_idx)
            )
        pair.loop_start, pair.loop_end = refine_loop_transition(
            mlaudio.playback_audio,
            mlaudio.rate,
            mlaudio.frames_to_samples(pair._loop_start_frame_idx),
            mlaudio.frames_to_samples(pair._loop_end_frame_idx),
        )

    # Penalize any residual sample-level crackle that transition refinement could not eliminate
    playback_peak = float(np.max(np.abs(mlaudio.playback_audio)))
    if playback_peak > 1e-8:
        for pair in filtered_candidate_pairs:
            crackle_excess = _transition_crackle_excess(
                mlaudio.playback_audio,
                playback_peak,
                pair.loop_start,
                pair.loop_end,
            )
            if crackle_excess > 0.0:
                pair.score = max(0.0, pair.score - _crackle_penalty(crackle_excess))
        filtered_candidate_pairs.sort(key=lambda x: x.score, reverse=True)

    # Deduplicate exact and near-identical (loop_start, loop_end) candidates
    # (e.g. adjacent frames converging during transition refinement or brute-force search)
    filtered_candidate_pairs = _deduplicate_loop_pairs(
        filtered_candidate_pairs,
        tolerance_samples=max(1, int(round(_DEDUP_PROXIMITY_S * mlaudio.rate))),
    )

    # prefer longer loops for highly similar sequences
    if len(filtered_candidate_pairs) > 1:
        _prioritize_duration(filtered_candidate_pairs)

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
        Tuple[np.ndarray, np.ndarray, float, np.ndarray]: a tuple containing the (chroma spectrogram, A-weighted power spectrogram in dB, tempo/bpm, frame indices of detected beats)
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
    # `perceptual_weighting` already converts `S_power` to A-weighted decibels.
    power_db = S_weighed

    if skip_beat_analysis:
        return chroma, power_db, None, None

    try:
        onset_env = librosa.onset.onset_strength(S=mel_spectrogram)

        pulse = librosa.beat.plp(onset_envelope=onset_env)
        beats_plp = np.flatnonzero(librosa.util.localmax(pulse))
        bpm, beats = librosa.beat.beat_track(onset_envelope=onset_env)

        beats = np.union1d(beats, beats_plp)
        beats = np.sort(beats)

        if isinstance(bpm, np.ndarray):
            bpm = bpm[0]
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
        power_db (np.ndarray): The A-weighted power spectrogram in dB
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
    ## Maximum A-weighted peak loudness difference in true decibels (3.5 dB).
    ## Calibrated against the legacy double-dB threshold (0.5), which admitted
    ## ~3.0-4.0 dB of true A-weighted loudness difference on normalized music.
    ACCEPTABLE_LOUDNESS_DIFFERENCE = 3.5

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
    power_db: Optional[np.ndarray] = None,
) -> List[LoopPair]:
    """Assigns the scores to each loop pair and prunes the list of candidate loop pairs

    Args:
        mlaudio (MLAudio): MLAudio object of the track being analyzed
        chroma (np.ndarray): The chroma spectrogram
        bpm (float): The estimated bpm/tempo of the track
        candidate_pairs (List[LoopPair]): The list of candidate loop pairs found
        disable_pruning (bool, optional): Returns all the candidate loop points without filtering. Defaults to False.
        power_db (np.ndarray, optional): A-weighted power spectrogram in dB used for boundary loudness-jump penalties. Defaults to None.

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
    if len(candidate_pairs) >= 100 and not disable_pruning:
        pruned_candidate_pairs = _prune_candidates(candidate_pairs)
    else:
        pruned_candidate_pairs = candidate_pairs

    weights = _weights(test_offset, start=max(2, test_offset // num_test_beats), stop=1)

    loudness_csum = (
        _boundary_loudness_csum(power_db) if power_db is not None else None
    )
    boundary_window_frames = max(
        2, int(mlaudio.seconds_to_frames(_BOUNDARY_LOUDNESS_WINDOW_S))
    )
    macro_window_frames = max(
        4, int(mlaudio.seconds_to_frames(_MACRO_LOUDNESS_WINDOW_S))
    )

    pair_score_list = [
        _calculate_loop_score(
            int(pair._loop_start_frame_idx),
            int(pair._loop_end_frame_idx),
            chroma,
            test_duration=test_offset,
            weights=weights,
            loudness_csum=loudness_csum,
            boundary_window_frames=boundary_window_frames,
            fallback_db=pair.loudness_difference,
            macro_window_frames=macro_window_frames,
        )
        for pair in pruned_candidate_pairs
    ]
    # Assign loop transition scores
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
    keep_top_loudness: float = 50,
    acceptable_loudness: float = 2.0,
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
            min_adjusted_db_diff_array, keep_top_loudness
        )
    else:
        db_threshold = np.max(db_diff_array)

    if min_adjusted_note_dist_array.size > 3:
        note_dist_threshold = np.percentile(
            min_adjusted_note_dist_array, keep_top_notes
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


def _boundary_loudness_csum(power_db: np.ndarray) -> np.ndarray:
    """Computes a 1D float64 cumulative sum of per-frame linear A-weighted energy."""
    frame_power = np.sum(10.0 ** (power_db.astype(np.float64) / 10.0), axis=0)
    return np.cumsum(np.insert(frame_power, 0, 0.0))


def _window_mean_db(loudness_csum: np.ndarray, start: int, end: int) -> Optional[float]:
    n = loudness_csum.shape[0] - 1
    start = max(0, min(n, start))
    end = max(start, min(n, end))
    if end <= start:
        return None
    mean_power = (loudness_csum[end] - loudness_csum[start]) / (end - start)
    return float(10.0 * np.log10(max(mean_power, 1e-12)))


def _boundary_loudness_diff_db(
    b1: int,
    b2: int,
    loudness_csum: np.ndarray,
    window_frames: int,
    use_lookahead: bool,
    fallback_db: float = 0.0,
) -> float:
    """Measures the perceptual A-weighted broadband loudness jump (in dB) across
    a short window adjacent to the loop boundary in the chosen direction."""
    n = loudness_csum.shape[0] - 1
    min_avail = max(1, window_frames // 2)

    d_post: Optional[float] = None
    if (n - b2) >= min_avail and (n - b1) >= min_avail:
        l1 = _window_mean_db(loudness_csum, b1, b1 + window_frames)
        l2 = _window_mean_db(loudness_csum, b2, b2 + window_frames)
        if l1 is not None and l2 is not None:
            d_post = abs(l1 - l2)

    d_pre: Optional[float] = None
    if b1 >= min_avail and b2 >= min_avail:
        l1 = _window_mean_db(loudness_csum, b1 - window_frames, b1)
        l2 = _window_mean_db(loudness_csum, b2 - window_frames, b2)
        if l1 is not None and l2 is not None:
            d_pre = abs(l1 - l2)

    if use_lookahead:
        if d_post is not None:
            return d_post
        if d_pre is not None:
            return d_pre
    else:
        if d_pre is not None:
            return d_pre
        if d_post is not None:
            return d_post
    return float(fallback_db)


def _loudness_jump_penalty(
    jump_db: float,
    max_penalty: float = _BOUNDARY_LOUDNESS_PENALTY_CAP,
    ref_db: float = _BOUNDARY_LOUDNESS_REF_DB,
) -> float:
    """Quadratic bounded penalty for audible boundary loudness jumps.

    Negligible below human JND (~0.5 dB) and capped at `max_penalty` once
    `jump_db` reaches `ref_db`.
    """
    ratio = min(1.0, max(0.0, jump_db) / ref_db)
    return max_penalty * (ratio * ratio)


def _macro_loudness_cliff_db(
    b1: int,
    b2: int,
    loudness_csum: np.ndarray,
    window_frames: int,
) -> float:
    """Measures the macroscopic (~1 s) across-boundary loudness cliff at `b2 -> b1`
    as `min(|L(b2 - W .. b2) - L(b1 .. b1 + W)|, |L(b2 .. b2 + W) - L(b1 .. b1 + W)|)`.

    Taking the minimum of across-boundary (`d_cross`) and post-boundary (`d_post`) ensures:
    - OST fade-outs (`b2` before outro fade) have `d_cross ~= 0 dB` (unpenalized).
    - Synchronized quiet -> loud drops at both `b1` and `b2` have `d_post ~= 0 dB` (unpenalized).
    - False loud-body -> quiet-intro cliffs have both `d_cross` and `d_post` large (penalized).
    """
    n = loudness_csum.shape[0] - 1
    min_avail = max(1, window_frames // 2)
    if (n - b1) < min_avail or b2 < min_avail:
        return 0.0

    l_s_post = _window_mean_db(loudness_csum, b1, b1 + window_frames)
    l_e_pre = _window_mean_db(loudness_csum, b2 - window_frames, b2)
    if l_s_post is None or l_e_pre is None:
        return 0.0

    d_cross = abs(l_e_pre - l_s_post)
    if (n - b2) >= min_avail:
        l_e_post = _window_mean_db(loudness_csum, b2, b2 + window_frames)
        if l_e_post is not None:
            return min(d_cross, abs(l_e_post - l_s_post))
    return d_cross


def _macro_loudness_cliff_penalty(
    cliff_db: float,
    max_penalty: float = _MACRO_LOUDNESS_PENALTY_CAP,
    ref_db: float = _MACRO_LOUDNESS_REF_DB,
) -> float:
    """Quadratic bounded penalty for macroscopic (~1 s) loudness cliffs across a loop transition."""
    ratio = min(1.0, max(0.0, cliff_db) / ref_db)
    return max_penalty * (ratio * ratio)


def _calculate_loop_score(
    b1: int,
    b2: int,
    chroma: np.ndarray,
    test_duration: int,
    weights: Optional[np.ndarray] = None,
    loudness_csum: Optional[np.ndarray] = None,
    boundary_window_frames: int = 0,
    fallback_db: float = 0.0,
    macro_window_frames: int = 0,
) -> float:
    """Calculates the loop transition score for two frame indices `b1` and `b2` over `test_duration` frames.

    Computes weighted chroma cosine similarity for both lookahead (subsequent) and lookbehind
    (preceding) windows, optionally subtracts a bounded quadratic penalty for audible boundary
    loudness jumps in each direction, blends the stronger and weaker directions to favor
    bidirectional continuity, and optionally applies a macroscopic (~1 s) across-boundary
    loudness-cliff penalty.

    Args:
        b1 (int): Frame index of the first beat to compare
        b2 (int): Frame index of the second beat to compare
        chroma (np.ndarray): The chroma spectrogram of the audio
        test_duration (int): How many frames along the chroma spectrogram to test.
        weights (np.ndarray, optional): If specified, will provide a weighted average of the note scores according to the weight array provided. Defaults to None.
        loudness_csum (np.ndarray, optional): Cumulative sum of per-frame linear A-weighted energy. Defaults to None.
        boundary_window_frames (int, optional): Short window length (in frames) for boundary loudness comparison. Defaults to 0.
        fallback_db (float, optional): Fallback single-frame loudness difference in dB if both boundary windows are clipped. Defaults to 0.0.
        macro_window_frames (int, optional): Macroscopic window length (in frames) for across-boundary loudness-cliff detection. Defaults to 0.

    Returns:
        float: Combined loop transition score in `[0, 1]`
    """
    lookahead_score = _calculate_subseq_beat_similarity(
        b1, b2, chroma, test_duration, weights=weights
    )
    lookbehind_score = _calculate_subseq_beat_similarity(
        b1, b2, chroma, -test_duration, weights=weights[::-1]
    )

    if loudness_csum is not None and boundary_window_frames > 0:
        post_jump_db = _boundary_loudness_diff_db(
            b1,
            b2,
            loudness_csum,
            boundary_window_frames,
            use_lookahead=True,
            fallback_db=fallback_db,
        )
        pre_jump_db = _boundary_loudness_diff_db(
            b1,
            b2,
            loudness_csum,
            boundary_window_frames,
            use_lookahead=False,
            fallback_db=fallback_db,
        )
        lookahead_score = max(
            0.0, lookahead_score - _loudness_jump_penalty(post_jump_db)
        )
        lookbehind_score = max(
            0.0, lookbehind_score - _loudness_jump_penalty(pre_jump_db)
        )

    best_dir = max(lookahead_score, lookbehind_score)
    other_dir = min(lookahead_score, lookbehind_score)
    score = (
        (1.0 - _BIDIRECTIONAL_BLEND_WEIGHT) * best_dir
        + _BIDIRECTIONAL_BLEND_WEIGHT * other_dir
    )
    if loudness_csum is not None and macro_window_frames > 0:
        cliff_db = _macro_loudness_cliff_db(
            b1, b2, loudness_csum, macro_window_frames
        )
        if cliff_db > 0.0:
            score = max(0.0, score - _macro_loudness_cliff_penalty(cliff_db))
    return score


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

    if max_offset == 0:
        return 0.0

    dot_prod = np.einsum(
        "ij,ij->j", chroma[..., b1_start:b1_end], chroma[..., b2_start:b2_end]
    )
    b1_norm = np.linalg.norm(chroma[..., b1_start:b1_end], axis=0)
    b2_norm = np.linalg.norm(chroma[..., b2_start:b2_end], axis=0)
    cosine_sim = dot_prod / (np.maximum(b1_norm * b2_norm, 1e-10))

    if max_offset < test_length:
        # Avoid penalizing valid loop points near track boundaries where the
        # comparison window is clipped by start/end of audio, while still
        # guarding against tiny boundary fragments (< 25% of test_length)
        # receiving spurious high scores.
        min_frames = max(1, test_length // 4)
        is_lookbehind = test_end_offset < 0
        if max_offset >= min_frames:
            eff_weights = (
                None
                if weights is None
                else (weights[-max_offset:] if is_lookbehind else weights[:max_offset])
            )
            return float(np.average(cosine_sim, weights=eff_weights))

        pad_len = min_frames - max_offset
        pad_width = (pad_len, 0) if is_lookbehind else (0, pad_len)
        eff_weights = (
            None
            if weights is None
            else (weights[-min_frames:] if is_lookbehind else weights[:min_frames])
        )
        return float(
            np.average(
                np.pad(
                    cosine_sim,
                    pad_width=pad_width,
                    mode="constant",
                    constant_values=0,
                ),
                weights=eff_weights,
            )
        )
    else:
        return float(np.average(cosine_sim, weights=weights))


def _weights(length: int, start: int = 100, stop: int = 1):
    return np.geomspace(start, stop, num=length)


@njit(cache=True)
def nearest_zero_crossing(audio: np.ndarray, rate: int, sample_idx: int) -> int:
    """Implementation of Audacity's `At Zero Crossings` feature. https://manual.audacityteam.org/man/select_menu_at_zero_crossings.html
    Description is based on the relevant Audacity manual page, due to identical behaviour.

    Returns the best closest sample point that is at a rising zero crossing point.
    This is a point where a line joining the audio samples rises from left to right and crosses the zero horizontal line that represents silence.
    The shift in audio position is not itself detectable to the ear, but the fact that the joins in the waveform are now of matching height helps avoid clicks in audio.

    This feature does not necessarily find the nearest zero crossing to the current position. It aims to find the crossing where the average amplitude of samples in the vicinity is lowest.

    Args:
        audio (np.ndarray): Numpy array containing the playback audio; must be in the shape `(samples, n_channels)`
        rate (int): Sample rate of the provided audio
        sample_idx (int): The index of the sample point to return the nearest zero crossing of

    Returns:
        int: the index of the best sample point that is at a rising zero crossing point closest to the `sample_idx` provided, returns `sample_idx` if none where found
    """
    # Re-implementation of Audacity's NearestZeroCrossing function in Python
    # https://github.com/audacity/audacity/blob/057bf4ee6f71962cd8ecc6dbccf0852695340758/src/menus/SelectMenus.cpp#L30
    # Original credit goes to the Audacity team and contributors
    n_channels = audio.shape[1]
    sample_idx = min(max(0, sample_idx), audio.shape[0] - 1)

    # Window is 1/100th of a second
    window_size = int(max(1, rate / 100))

    # Create sample window centered around sample_idx
    offset = window_size // 2
    neg_offset = max(0, sample_idx - offset)
    pos_offset = min(audio.shape[0], sample_idx + offset)
    sample_window = audio[neg_offset:pos_offset]

    # Adjusts the indexing offset in case the left side of sample_idx was clipped
    offset_correction = abs(sample_idx - offset) if sample_idx - offset < 0 else 0

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
            dist[i] += 0.1 * abs(i - offset + offset_correction) / (window_size / 2)

    argmin = np.argmin(dist)
    minimum_dist = dist[argmin]

    # If we're worse than 0.2 on average, on one track, then no good.
    if (n_channels == 1) and (minimum_dist > (0.2 * n_channels)):
        return sample_idx
    # If we're worse than 0.6 on average, on multi-track, then no good.
    if (n_channels > 1) and (minimum_dist > (0.6 * n_channels)):
        return sample_idx

    return int(sample_idx + argmin - offset + offset_correction)


@njit(cache=True)
def _transition_discontinuity_cost(audio: np.ndarray, s: int, e: int) -> float:
    """Computes worst-channel transition discontinuity at `audio[e - 1] -> audio[s]`.

    Combines 2nd-order finite-difference curvature impulse (`d2_transition`, which catches
    both 0th-order amplitude steps and 1st-order slope kinks) with direct continuation
    mismatch (`|y[s] - y[e]|` and `|y[s - 1] - y[e - 1]|`), which vanishes at exact
    phase-locked waveform continuation without biasing toward 1-sample flat plateaus.
    """
    n_channels = audio.shape[1]
    worst = 0.0
    for c in range(n_channels):
        ym2 = audio[e - 2, c]
        ym1 = audio[e - 1, c]
        ye = audio[e, c]
        ysm1 = audio[s - 1, c]
        y0 = audio[s, c]
        yp1 = audio[s + 1, c]
        d2_l = abs(y0 - 2.0 * ym1 + ym2)
        d2_r = abs(yp1 - 2.0 * y0 + ym1)
        d2 = d2_l if d2_l > d2_r else d2_r
        cont = 0.5 * (abs(y0 - ye) + abs(ysm1 - ym1))
        val = d2 + cont
        if val > worst:
            worst = val
    return worst


@njit(cache=True)
def _refine_pair_joint(
    audio: np.ndarray,
    s_init: int,
    e_init: int,
    s_anchor: int,
    e_anchor: int,
    radius: int,
    max_rel_drift: int,
) -> Tuple[int, int]:
    """Refines `(loop_start, loop_end)` jointly to minimize multi-channel transition
    crackle while preserving loop duration and rhythmic alignment."""
    n = audio.shape[0]
    best_s = s_init
    best_e = e_init
    best_cost = 1e9

    if best_e >= 2 and best_s >= 1 and best_s + 1 < n and best_e < n:
        best_cost = _transition_discontinuity_cost(audio, best_s, best_e)

    # 1. Equal-duration joint sweep around (s_init, e_init) preserving exact period
    k_lo = max(-radius, 1 - s_init, 2 - e_init)
    k_hi = min(radius, (n - 2) - s_init, (n - 1) - e_init)
    denom_r = radius if radius > 1 else 1
    for k in range(k_lo, k_hi + 1):
        s = s_init + k
        e = e_init + k
        if e <= s:
            continue
        cost = _transition_discontinuity_cost(audio, s, e)
        cost += 1e-4 * (abs(s - s_anchor) + abs(e - e_anchor)) / denom_r
        if cost < best_cost:
            best_cost = cost
            best_s = s
            best_e = e

    # 2. If noticeable discontinuity remains, allow bounded relative adjustment
    #    via coarse stride-4 + fine +/-4 paired search within +/- max_rel_drift.
    if best_cost > 0.01:
        s_lo = max(1, s_init - radius)
        s_hi = min(n - 2, s_init + radius)
        e_lo_global = max(2, e_init - radius)
        e_hi_global = min(n - 1, e_init + radius)
        base_dur = e_init - s_init
        denom_d = max_rel_drift if max_rel_drift > 1 else 1

        coarse_s = best_s
        coarse_e = best_e
        coarse_cost = best_cost

        for s in range(s_lo, s_hi + 1, 4):
            e_lo = max(e_lo_global, s + base_dur - max_rel_drift, s + 1)
            e_hi = min(e_hi_global, s + base_dur + max_rel_drift)
            for e in range(e_lo, e_hi + 1, 4):
                cost = _transition_discontinuity_cost(audio, s, e)
                cost += 2e-3 * abs((e - s) - base_dur) / denom_d
                if cost < coarse_cost:
                    coarse_cost = cost
                    coarse_s = s
                    coarse_e = e

        fs_lo = max(s_lo, coarse_s - 4)
        fs_hi = min(s_hi, coarse_s + 4)
        fe_lo = max(e_lo_global, coarse_e - 4)
        fe_hi = min(e_hi_global, coarse_e + 4)
        for s in range(fs_lo, fs_hi + 1):
            for e in range(fe_lo, fe_hi + 1):
                if e <= s or abs((e - s) - base_dur) > max_rel_drift:
                    continue
                cost = _transition_discontinuity_cost(audio, s, e)
                cost += 2e-3 * abs((e - s) - base_dur) / denom_d
                if cost < best_cost:
                    best_cost = cost
                    best_s = s
                    best_e = e

    return int(best_s), int(best_e)


def refine_loop_transition(
    audio: np.ndarray,
    rate: int,
    start_sample: int,
    end_sample: int,
) -> Tuple[int, int]:
    """Refines `(start_sample, end_sample)` jointly to minimize sample-level transition
    crackle across all channels.

    First performs sub-frame waveform phase alignment (within +/- 1 STFT hop) when
    the waveforms around `start_sample` and `end_sample` are strongly correlated,
    then searches a local +/- 5 ms neighborhood to minimize worst-channel 2nd-order
    curvature impulses (capturing both 0th-order amplitude steps and 1st-order
    slope kinks) and waveform continuation mismatch at the transition.

    Args:
        audio (np.ndarray): Playback audio array with shape `(samples, n_channels)`.
        rate (int): Sample rate in Hz.
        start_sample (int): Initial loop start sample index.
        end_sample (int): Initial loop end sample index.

    Returns:
        Tuple[int, int]: Refined `(loop_start, loop_end)` sample indices.
    """
    n = audio.shape[0]
    if n < 4:
        s_clamped = min(max(0, int(start_sample)), max(0, n - 1))
        e_clamped = min(max(0, int(end_sample)), max(0, n - 1))
        return s_clamped, e_clamped

    s0 = min(max(1, int(start_sample)), n - 2)
    e0 = min(max(2, int(end_sample)), n - 1)
    if e0 <= s0:
        return s0, e0

    # Stage 1: sub-frame waveform phase alignment via FFT cross-correlation (+/- 1 STFT hop)
    max_lag = min(512, max(1, rate // 80))
    half_win = min(512, s0, n - s0, e0 - max_lag, n - e0 - max_lag)
    e_aligned = e0
    if half_win >= 128:
        tpl = np.mean(audio[s0 - half_win : s0 + half_win], axis=1).astype(np.float64)
        src = np.mean(
            audio[e0 - half_win - max_lag : e0 + half_win + max_lag], axis=1
        ).astype(np.float64)
        tpl -= np.mean(tpl)
        tpl_norm = float(np.linalg.norm(tpl))
        if tpl_norm > 1e-6:
            tpl_len = tpl.shape[0]
            n_fft = 1 << (src.shape[0] + tpl_len - 1).bit_length()
            cc = np.fft.irfft(
                np.fft.rfft(src, n_fft) * np.conj(np.fft.rfft(tpl, n_fft)), n_fft
            )
            valid_cc = cc[: 2 * max_lag + 1]
            src_sq = np.cumsum(np.insert(src * src, 0, 0.0))
            win_norms = np.sqrt(
                np.maximum(
                    src_sq[tpl_len : tpl_len + 2 * max_lag + 1]
                    - src_sq[: 2 * max_lag + 1],
                    1e-12,
                )
            )
            corrs = valid_cc / (tpl_norm * win_norms)
            best_idx = int(np.argmax(corrs))
            if corrs[best_idx] >= 0.5:
                lag = best_idx - max_lag
                if e0 + lag > s0:
                    e_aligned = e0 + lag

    # Stage 2: joint multi-channel minimum-crackle transition search (+/- 5 ms radius, +/- 3 ms max relative drift)
    radius = max(1, rate // 200)
    max_rel_drift = max(1, (3 * rate) // 1000)
    return _refine_pair_joint(audio, s0, e_aligned, s0, e0, radius, max_rel_drift)


def _transition_crackle_excess(
    audio: np.ndarray,
    peak: float,
    loop_start: int,
    loop_end: int,
    context_samples: int = _CRACKLE_CONTEXT_SAMPLES,
) -> float:
    """Measures peak-normalized excess 2nd-order finite-difference impulse at the
    transition `audio[loop_end - 1] -> audio[loop_start]` above the local 95th-percentile
    natural curvature across all channels.

    Captures both 0th-order amplitude steps (pops) and 1st-order slope kinks
    (zero-crossing crackles) while ignoring naturally bright/percussive material.
    """
    n, n_channels = audio.shape
    if (
        loop_end < 2
        or loop_start < 1
        or loop_start + 1 >= n
        or loop_end >= n
        or peak <= 1e-8
    ):
        return 0.0

    inv_peak = 1.0 / peak
    d2_left = (
        np.abs(audio[loop_start] - 2.0 * audio[loop_end - 1] + audio[loop_end - 2])
        * inv_peak
    )
    d2_right = (
        np.abs(audio[loop_start + 1] - 2.0 * audio[loop_start] + audio[loop_end - 1])
        * inv_peak
    )
    d2_transition = np.maximum(d2_left, d2_right)

    e0 = max(0, loop_end - context_samples)
    s1 = min(n, loop_start + context_samples)
    nat_e = (
        np.abs(np.diff(audio[e0:loop_end], n=2, axis=0)) * inv_peak
        if (loop_end - e0) >= 3
        else np.zeros((1, n_channels), dtype=np.float64)
    )
    nat_s = (
        np.abs(np.diff(audio[loop_start:s1], n=2, axis=0)) * inv_peak
        if (s1 - loop_start) >= 3
        else np.zeros((1, n_channels), dtype=np.float64)
    )
    nat_p95 = np.percentile(np.vstack([nat_e, nat_s]), 95, axis=0)
    return float(np.max(np.maximum(0.0, d2_transition - nat_p95)))


def _crackle_penalty(
    crackle_excess: float,
    max_penalty: float = _CRACKLE_PENALTY_CAP,
    ref_excess: float = _CRACKLE_REF_EXCESS,
) -> float:
    """Quadratic bounded penalty for residual sample-level transition crackle."""
    ratio = min(1.0, max(0.0, crackle_excess) / ref_excess)
    return max_penalty * (ratio * ratio)


def _deduplicate_loop_pairs(
    pair_list: List[LoopPair],
    tolerance_samples: int = 0,
) -> List[LoopPair]:
    """Deduplicates exact and near-identical `(loop_start, loop_end)` pairs in
    O(N) time using a 2D spatial grid, preserving the highest-scoring occurrence
    from an already score-sorted `pair_list`.

    Two pairs are considered duplicates if both `|s1 - s2| <= tolerance_samples`
    and `|e1 - e2| <= tolerance_samples`.
    """
    if len(pair_list) <= 1:
        return pair_list

    if tolerance_samples <= 0:
        seen = set()
        kept: List[LoopPair] = []
        for pair in pair_list:
            key = (pair.loop_start, pair.loop_end)
            if key not in seen:
                seen.add(key)
                kept.append(pair)
        return kept

    cell = tolerance_samples
    grid: dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    kept = []
    for pair in pair_list:
        s = pair.loop_start
        e = pair.loop_end
        bx = s // cell
        by = e // cell
        is_dup = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for ks, ke in grid.get((bx + dx, by + dy), ()):
                    if abs(s - ks) <= tolerance_samples and abs(e - ke) <= tolerance_samples:
                        is_dup = True
                        break
                if is_dup:
                    break
            if is_dup:
                break
        if not is_dup:
            grid.setdefault((bx, by), []).append((s, e))
            kept.append(pair)
    return kept
