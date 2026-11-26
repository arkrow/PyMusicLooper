import types
import warnings

import numpy as np
import pytest

from pymusiclooper.playback import DEFAULT_BLOCKSIZE, PlaybackHandler


class _CallbackStop(Exception):
    pass


def _make_fake_sd(captured_stream_kwargs, drive_callback):
    class FakeRawOutputStream:
        def __init__(self, **kwargs):
            captured_stream_kwargs.update(kwargs)
            self._callback = kwargs["callback"]
            self._finished_callback = kwargs["finished_callback"]
            self._frames_size = kwargs["channels"] * np.dtype(kwargs["dtype"]).itemsize

        def __enter__(self):
            drive_callback(self._callback, self._finished_callback, self._frames_size)
            return self

        def __exit__(self, *args):
            return False

    return types.SimpleNamespace(
        RawOutputStream=FakeRawOutputStream,
        CallbackStop=_CallbackStop,
    )


def _read_blocks(callback, frame_counts, frame_bytes, status_seq=None):
    chunks = []
    stopped = False
    for idx, frames in enumerate(frame_counts):
        buf = bytearray(frames * frame_bytes)
        status = status_seq[idx] if status_seq is not None else 0
        try:
            callback(buf, frames, None, status)
        except _CallbackStop:
            chunks.append(np.frombuffer(bytes(buf), dtype=np.float32).copy())
            stopped = True
            break
        chunks.append(np.frombuffer(bytes(buf), dtype=np.float32).copy())
    return chunks, stopped


def test_raw_output_stream_config_and_no_warnings(monkeypatch):
    audio = np.arange(20, dtype=np.float32).reshape(10, 2)
    captured = {}

    def driver(cb, finished_cb, frame_bytes):
        handler._loop_interrupt_handler()  # disable looping
        _, stopped = _read_blocks(cb, [4, 4, 4], frame_bytes)
        assert stopped
        finished_cb()

    monkeypatch.setattr(
        "pymusiclooper.playback.sd", lambda: _make_fake_sd(captured, driver)
    )

    handler = PlaybackHandler()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        handler.play_looping(audio, samplerate=44100, n_channels=2, loop_start=2, loop_end=8)

    assert captured["samplerate"] == 44100
    assert captured["channels"] == 2
    assert captured["blocksize"] == DEFAULT_BLOCKSIZE
    assert captured["dtype"] == "float32"
    assert captured["latency"] == "high"


def test_looping_sample_exact_including_short_loop_and_outro(monkeypatch):
    # 10 stereo frames: frame i has values [i, -i]
    audio = np.column_stack(
        [np.arange(10, dtype=np.float32), -np.arange(10, dtype=np.float32)]
    )
    # Use a Fortran-contiguous float64 copy to verify upfront conversion too.
    non_contig_f64 = np.asfortranarray(audio.astype(np.float64))

    collected = []
    captured = {}

    def driver(cb, finished_cb, frame_bytes):
        # Frames 0..4 (5 frames) hit loop_end=5 -> wrap to 2 (loop #1), then 2, 3 (2 frames)
        chunks, stopped = _read_blocks(cb, [7], frame_bytes)
        assert not stopped
        collected.extend(chunks)
        assert handler.loop_counter == 1

        # Disable looping via first Ctrl+C; remaining audio should play to end and zero-pad
        handler._loop_interrupt_handler()
        chunks2, stopped2 = _read_blocks(cb, [10], frame_bytes)
        assert stopped2
        collected.extend(chunks2)
        finished_cb()

    monkeypatch.setattr(
        "pymusiclooper.playback.sd", lambda: _make_fake_sd(captured, driver)
    )

    handler = PlaybackHandler()
    handler.play_looping(
        non_contig_f64,
        samplerate=44100,
        n_channels=2,
        loop_start=2,
        loop_end=5,
        start_from=0,
        blocksize=7,
    )

    expected_block1 = np.array(
        [[0, 0], [1, -1], [2, -2], [3, -3], [4, -4], [2, -2], [3, -3]],
        dtype=np.float32,
    )
    assert np.array_equal(collected[0].reshape(-1, 2), expected_block1)

    # Block 2 (10 frames, looping disabled, current_frame=4): frames 4..9 (6 frames) + 4 zero frames
    expected_block2 = np.vstack(
        [audio[4:10], np.zeros((4, 2), dtype=np.float32)]
    )
    assert np.array_equal(collected[1].reshape(-1, 2), expected_block2)


def test_short_loop_wraps_multiple_times_in_single_block(monkeypatch):
    audio = np.arange(10, dtype=np.float32)  # 1D mono input
    collected = []
    captured = {}

    def driver(cb, finished_cb, frame_bytes):
        # Loop [2, 4) has length 2; block of 7 frames from start_from=2 wraps 3 times
        chunks, stopped = _read_blocks(cb, [7], frame_bytes)
        assert not stopped
        collected.extend(chunks)
        assert handler.loop_counter == 3
        finished_cb()

    monkeypatch.setattr(
        "pymusiclooper.playback.sd", lambda: _make_fake_sd(captured, driver)
    )

    handler = PlaybackHandler()
    handler.play_looping(
        audio,
        samplerate=44100,
        n_channels=1,
        loop_start=2,
        loop_end=4,
        start_from=2,
        blocksize=7,
    )

    expected = np.array([2, 3, 2, 3, 2, 3, 2], dtype=np.float32)
    assert np.array_equal(collected[0], expected)


def test_second_interrupt_stops_with_silence_and_tracks_underflows(monkeypatch):
    audio = np.ones((16, 2), dtype=np.float32)
    collected = []
    captured = {}

    def driver(cb, finished_cb, frame_bytes):
        # First block reports a status flag (underflow)
        chunks, stopped = _read_blocks(cb, [4], frame_bytes, status_seq=[1])
        assert not stopped
        collected.extend(chunks)

        # Two Ctrl+C presses: first disables looping, second requests immediate stop
        handler._loop_interrupt_handler()
        handler._loop_interrupt_handler()
        chunks2, stopped2 = _read_blocks(cb, [4], frame_bytes, status_seq=[0])
        assert stopped2
        collected.extend(chunks2)
        finished_cb()

    monkeypatch.setattr(
        "pymusiclooper.playback.sd", lambda: _make_fake_sd(captured, driver)
    )

    handler = PlaybackHandler()
    handler.play_looping(audio, samplerate=44100, n_channels=2, loop_start=0, loop_end=16, blocksize=4)

    assert handler.underflow_count == 1
    assert np.all(collected[0] == 1.0)
    assert np.all(collected[1] == 0.0)


def test_invalid_loop_bounds_raise_value_error():
    audio = np.zeros((10, 2), dtype=np.float32)
    handler = PlaybackHandler()

    with pytest.raises(ValueError, match="wrong order"):
        handler.play_looping(audio, samplerate=44100, n_channels=2, loop_start=8, loop_end=4)

    with pytest.raises(ValueError, match="out of bounds"):
        handler.play_looping(audio, samplerate=44100, n_channels=2, loop_start=0, loop_end=11)

    with pytest.raises(ValueError, match="out of bounds"):
        handler.play_looping(audio, samplerate=44100, n_channels=2, loop_start=5, loop_end=5)
