import numpy as np
import pytest
import soundfile as sf

from pymusiclooper.analysis import (
    LoopPair,
    _analyze_audio,
    _boundary_loudness_csum,
    _boundary_loudness_diff_db,
    _calculate_loop_score,
    _calculate_subseq_beat_similarity,
    _db_diff,
    _loudness_jump_penalty,
    _prioritize_duration,
    _weights,
    find_best_loop_points,
)
from pymusiclooper.audio import MLAudio


def _make_chroma(length: int, period: int, seed: int = 0) -> np.ndarray:
    """Creates a normalized 12-bin chroma spectrogram that repeats every `period` frames."""
    rng = np.random.default_rng(seed)
    base = rng.uniform(0.1, 1.0, size=(12, period))
    base /= np.max(base, axis=0, keepdims=True)
    reps = (length + period - 1) // period
    return np.tile(base, (1, reps))[:, :length]


def test_clipped_lookahead_and_lookbehind_not_penalized_above_min_overlap():
    # Period 200, total length 260 -> only 60 frames of overlap (< test_length=100, >= min_frames=25)
    chroma = _make_chroma(length=260, period=200)
    test_length = 100
    weights = _weights(test_length, start=10, stop=1)

    # Near EOF: 40 frames of identical lookahead available (>= 25)
    la = _calculate_subseq_beat_similarity(20, 220, chroma, test_length, weights=weights)
    assert la == pytest.approx(1.0, abs=1e-6)

    # Near BOF: 40 frames of identical lookbehind available (>= 25)
    lb = _calculate_subseq_beat_similarity(40, 240, chroma, -test_length, weights=weights[::-1])
    assert lb == pytest.approx(1.0, abs=1e-6)


def test_lookahead_and_lookbehind_sub_min_overlap_are_symmetric_and_damped():
    # Identical chroma near boundary with only 5 frames (< min_frames=25 for test_length=100)
    chroma = _make_chroma(length=220, period=200)
    test_length = 100
    weights = _weights(test_length, start=10, stop=1)

    # 5 frames remaining after b2=215 vs 5 frames preceding b1=5
    la_tiny = _calculate_subseq_beat_similarity(15, 215, chroma, test_length, weights=weights)
    lb_tiny = _calculate_subseq_beat_similarity(5, 205, chroma, -test_length, weights=weights[::-1])

    # Mirror symmetry: lookbehind must pad zeros on the far (low-weight) side, matching lookahead
    assert lb_tiny == pytest.approx(la_tiny, abs=1e-6)
    # Guard against spurious ~1.0 scores from tiny boundary fragments
    assert 0.0 < la_tiny < 0.35


def test_zero_overlap_at_boundaries_returns_zero():
    chroma = _make_chroma(length=200, period=100)
    test_length = 80
    weights = _weights(test_length, start=10, stop=1)

    assert _calculate_subseq_beat_similarity(0, 100, chroma, -test_length, weights=weights[::-1]) == 0.0
    assert _calculate_subseq_beat_similarity(100, 200, chroma, test_length, weights=weights) == 0.0


def test_subseq_similarity_without_weights():
    chroma = _make_chroma(length=250, period=200)
    test_length = 100

    # >= min_frames (25): 40 identical frames -> 1.0
    assert _calculate_subseq_beat_similarity(10, 210, chroma, test_length, weights=None) == pytest.approx(1.0)
    assert _calculate_subseq_beat_similarity(40, 240, chroma, -test_length, weights=None) == pytest.approx(1.0)

    # < min_frames (25): 5 identical frames out of 25 -> 0.2
    assert _calculate_subseq_beat_similarity(45, 245, chroma, test_length, weights=None) == pytest.approx(0.2)
    assert _calculate_subseq_beat_similarity(5, 205, chroma, -test_length, weights=None) == pytest.approx(0.2)


def test_loop_score_prefers_exact_short_tail_over_imperfect_interior_loop():
    # True loop has period 300 with 40-frame overlap (< test_length=100, >= min_frames=25)
    # Interior candidate at period 150 has ~0.95 similarity over full 100-frame window
    rng = np.random.default_rng(7)
    base = rng.uniform(0.1, 1.0, size=(12, 300))
    base[:, 150:260] = base[:, 0:110] + rng.uniform(0.0, 0.35, size=(12, 110))
    base /= np.max(base, axis=0, keepdims=True)
    chroma = np.concatenate([base, base[:, :40]], axis=1)

    test_length = 100
    weights = _weights(test_length, start=10, stop=1)

    true_score = _calculate_loop_score(10, 310, chroma, test_length, weights=weights)
    interior_score = _calculate_loop_score(10, 160, chroma, test_length, weights=weights)

    assert true_score == pytest.approx(1.0, abs=1e-6)
    assert true_score > interior_score


def test_prioritize_duration_promotes_longer_near_tied_candidate():
    pairs = [
        LoopPair(0, 100, note_distance=0.02, loudness_difference=0.05, score=0.99995, loop_start=0, loop_end=100_000),
        LoopPair(0, 200, note_distance=0.02, loudness_difference=0.04, score=0.99990, loop_start=0, loop_end=200_000),
    ] + [
        LoopPair(0, 120, note_distance=0.05, loudness_difference=0.20, score=0.90 - i * 0.01, loop_start=0, loop_end=120_000)
        for i in range(10)
    ]
    _prioritize_duration(pairs)
    assert pairs[0].loop_end == 200_000


def test_find_best_loop_points_short_tail_end_to_end(tmp_path):
    """End-to-end test: track with a 24s true loop and only a 2.5s repeated tail
    (shorter than the 12-beat ~6s test window) plus an imperfect 12s interior repeat."""
    sr = 22050

    def chord_bar(freqs, dur=2.0, amp=0.4):
        t = np.arange(int(dur * sr), dtype=np.float32) / sr
        beat_phase = (t % 0.5) / 0.5
        env = 0.25 + 0.75 * np.exp(-5.0 * beat_phase)
        sig = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
        return (amp * env * sig).astype(np.float32)

    C = [261.63, 329.63, 392.00]
    G = [196.00, 246.94, 392.00]
    Am = [220.00, 261.63, 329.63]
    F = [174.61, 220.00, 349.23]
    Dm = [293.66, 349.23, 440.00]
    Em = [329.63, 392.00, 493.88]
    Bb = [233.08, 293.66, 349.23]
    # Slightly altered chord so interior half-repeat is ~95-98% similar, not exact
    C_alt = [261.63, 329.63, 392.00, 493.88]
    G_alt = [196.00, 246.94, 392.00, 440.00]

    bars = [
        chord_bar(C), chord_bar(G), chord_bar(Am), chord_bar(F),
        chord_bar(Em), chord_bar(Dm),
        # Imperfect half-repeat at t=12s
        chord_bar(C_alt), chord_bar(G_alt), chord_bar(Am), chord_bar(F),
        chord_bar(Bb), chord_bar(Dm),
        # Exact 2.5s tail repeat starting at t=24s (shorter than 12-beat ~6s window)
        chord_bar(C, dur=2.0),
        chord_bar(G, dur=0.5),
    ]
    mono = np.concatenate(bars)
    wav_path = tmp_path / "short_tail.wav"
    sf.write(str(wav_path), np.column_stack([mono, mono]), sr)

    mlaudio = MLAudio(str(wav_path))
    pairs = find_best_loop_points(mlaudio)
    best = pairs[0]
    loop_duration_s = (best.loop_end - best.loop_start) / mlaudio.rate

    assert abs(loop_duration_s - 24.0) < 0.2
    assert best.score > 0.99


def test_analyze_audio_power_db_is_true_decibels(tmp_path):
    """Verifies `_analyze_audio` returns true A-weighted dB (no double-dB compression or sign flip)."""
    sr = 22050
    t = np.arange(sr, dtype=np.float32) / sr
    tone = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)

    # First half at 0.5 amplitude, second half +2.0 dB louder, plus a quiet -30 dB section
    gain_2db = 10 ** (2.0 / 20.0)
    gain_m30db = 10 ** (-30.0 / 20.0)
    mono = np.concatenate([0.5 * tone, 0.5 * gain_2db * tone, 0.5 * gain_m30db * tone])
    wav_path = tmp_path / "db_scale.wav"
    sf.write(str(wav_path), np.column_stack([mono, mono]), sr)

    mlaudio = MLAudio(str(wav_path))
    _, power_db, _, _ = _analyze_audio(mlaudio, skip_beat_analysis=True)

    f_ref = mlaudio.seconds_to_frames(0.5)
    f_plus2 = mlaudio.seconds_to_frames(1.5)
    f_minus30 = mlaudio.seconds_to_frames(2.5)

    assert _db_diff(power_db[..., f_ref], power_db[..., f_plus2]) == pytest.approx(2.0, abs=0.15)
    assert _db_diff(power_db[..., f_ref], power_db[..., f_minus30]) == pytest.approx(30.0, abs=0.5)


def test_loudness_jump_penalty_curve_and_cap():
    assert _loudness_jump_penalty(0.0) == 0.0
    assert _loudness_jump_penalty(-1.0) == 0.0
    # Negligible below human loudness JND (~0.5 dB)
    assert _loudness_jump_penalty(0.5) < 0.002
    # Strictly increasing and reaches full 8% cap at 3.5 dB
    assert _loudness_jump_penalty(1.5) < _loudness_jump_penalty(2.5) < _loudness_jump_penalty(3.5)
    assert _loudness_jump_penalty(3.5) == pytest.approx(0.08)
    assert _loudness_jump_penalty(10.0) == pytest.approx(0.08)


def test_boundary_loudness_diff_db_measures_step_and_handles_edges():
    # 100 frames at 10 dB, followed by 100 frames at 13 dB (+3.0 dB step at frame 100)
    power_db = np.full((4, 200), 10.0, dtype=np.float64)
    power_db[:, 100:] = 13.0
    csum = _boundary_loudness_csum(power_db)

    # Lookahead post-boundary comparison: [20..40) at 10 dB vs [120..140) at 13 dB -> 3.0 dB
    assert _boundary_loudness_diff_db(20, 120, csum, window_frames=20, use_lookahead=True) == pytest.approx(
        3.0, abs=1e-6
    )
    # Lookbehind pre-boundary comparison: [20..40) vs [40..60) both at 10 dB -> 0.0 dB
    assert _boundary_loudness_diff_db(40, 60, csum, window_frames=20, use_lookahead=False) == pytest.approx(
        0.0, abs=1e-6
    )
    # When post window is clipped at EOF (< window_frames // 2), falls back to pre window
    assert _boundary_loudness_diff_db(98, 198, csum, window_frames=20, use_lookahead=True) == pytest.approx(
        3.0, abs=1e-6
    )
    # When both pre and post windows are too short, falls back to fallback_db
    tiny_csum = _boundary_loudness_csum(np.full((4, 6), 10.0, dtype=np.float64))
    assert _boundary_loudness_diff_db(
        2, 4, tiny_csum, window_frames=20, use_lookahead=True, fallback_db=1.25
    ) == pytest.approx(1.25)


def test_loop_score_penalizes_audible_boundary_jump():
    # Identical chroma across 300 frames, but frames 150..300 are +3.5 dB louder
    chroma = _make_chroma(length=300, period=100)
    power_db = np.full((8, 300), 10.0, dtype=np.float64)
    power_db[:, 150:] = 13.5
    csum = _boundary_loudness_csum(power_db)
    weights = _weights(60, start=6, stop=1)

    smooth_score = _calculate_loop_score(
        10, 110, chroma, 60, weights=weights, loudness_csum=csum, boundary_window_frames=16
    )
    jumpy_score = _calculate_loop_score(
        80, 180, chroma, 60, weights=weights, loudness_csum=csum, boundary_window_frames=16
    )

    assert smooth_score == pytest.approx(1.0, abs=1e-5)
    assert jumpy_score == pytest.approx(0.92, abs=1e-4)
    assert smooth_score > jumpy_score


def test_find_best_loop_points_preserves_ost_fadeout_loop(tmp_path):
    """End-to-end test: unique intro + 24s loop + 4s fade-out of loop start still picks 24s."""
    sr = 22050

    def chord_bar(freqs, dur=2.0, amp=0.4):
        t = np.arange(int(dur * sr), dtype=np.float32) / sr
        env = 0.25 + 0.75 * np.exp(-5.0 * ((t % 0.5) / 0.5))
        sig = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
        return (amp * env * sig).astype(np.float32)

    C = [261.63, 329.63, 392.00]
    G = [196.00, 246.94, 392.00]
    Am = [220.00, 261.63, 329.63]
    F = [174.61, 220.00, 349.23]
    Dm = [293.66, 349.23, 440.00]
    Em = [329.63, 392.00, 493.88]
    Bb = [233.08, 293.66, 349.23]
    Fs = [185.00, 233.08, 277.18]
    Eb = [311.13, 392.00, 466.16]
    C_alt = [261.63, 329.63, 392.00, 493.88]
    G_alt = [196.00, 246.94, 392.00, 440.00]

    intro = np.concatenate([chord_bar(Fs), chord_bar(Eb), chord_bar(Bb)])
    body = np.concatenate(
        [
            chord_bar(C), chord_bar(G), chord_bar(Am), chord_bar(F),
            chord_bar(Em), chord_bar(Dm),
            chord_bar(C_alt), chord_bar(G_alt), chord_bar(Am), chord_bar(F),
            chord_bar(Bb), chord_bar(Dm),
        ]
    )
    outro_raw = np.concatenate([chord_bar(C), chord_bar(G)])
    outro = outro_raw * np.linspace(1.0, 0.0, len(outro_raw), dtype=np.float32)
    mono = np.concatenate([intro, body, outro])

    wav_path = tmp_path / "ost_fadeout.wav"
    sf.write(str(wav_path), np.column_stack([mono, mono]), sr)

    mlaudio = MLAudio(str(wav_path))
    pairs = find_best_loop_points(mlaudio)
    best = pairs[0]
    loop_duration_s = (best.loop_end - best.loop_start) / mlaudio.rate

    assert abs(loop_duration_s - 24.0) < 0.2
    assert best.score > 0.98


