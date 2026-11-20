from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from pymusiclooper import core as core_module
from pymusiclooper.cli import cli_main
from pymusiclooper.core import MusicLooper, _resolve_soundfile_format
from tests.conftest import make_loopable_wav


def test_loop_only_export(short_wav: Path, tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    ml = MusicLooper(str(short_wav))
    ml.export(10000, 60000, format="WAV", output_dir=str(out_dir), loop_only=True)

    files = [p.name for p in out_dir.iterdir()]
    assert files == ["track.wav-loop.wav"]
    data, sr = sf.read(str(out_dir / "track.wav-loop.wav"))
    assert sr == 22050
    assert data.shape == (50000, 2)


def test_split_audio_all_sections(short_wav: Path, tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    ml = MusicLooper(str(short_wav))
    ml.export(10000, 60000, format="WAV", output_dir=str(out_dir), loop_only=False)

    assert sorted(p.name for p in out_dir.iterdir()) == [
        "track.wav-intro.wav",
        "track.wav-loop.wav",
        "track.wav-outro.wav",
    ]


@pytest.mark.parametrize("fmt", ["WAV", "FLAC", "OGG", "MP3"])
def test_large_buffer_chunked_export_no_crash(tmp_path: Path, fmt: str):
    """Large OGG/FLAC/MP3/WAV exports must write cleanly in chunks without crashing."""
    sr = 44100
    one_sec = 0.3 * np.sin(2 * np.pi * 440.0 * np.arange(sr, dtype=np.float32) / sr)
    stereo_1s = np.column_stack([one_sec, one_sec * 0.9])
    large_audio = np.tile(stereo_1s, (139, 1))
    large_wav = tmp_path / "large.wav"
    sf.write(str(large_wav), large_audio, sr, format="WAV")

    ml = MusicLooper(str(large_wav))
    out_dir = tmp_path / fmt
    out_dir.mkdir()
    ml.export(100_000, 6_000_000, format=fmt, output_dir=str(out_dir), loop_only=True)
    out_file = out_dir / f"large.wav-loop.{fmt.lower()}"
    assert out_file.exists()
    assert out_file.stat().st_size > 10_000


@pytest.mark.parametrize("fmt", ["WAV", "FLAC", "OGG", "MP3"])
def test_empty_intro_outro_all_formats(short_wav: Path, tmp_path: Path, fmt: str):
    ml = MusicLooper(str(short_wav))
    out_dir = tmp_path / f"empty_{fmt}"
    out_dir.mkdir()
    ml.export(0, ml.mlaudio.length, format=fmt, output_dir=str(out_dir))
    assert len(list(out_dir.iterdir())) == 3


@pytest.mark.parametrize(
    ("fmt", "n_frames", "n_channels", "expected"),
    [
        ("WAV", 3600 * 48000, 2, "WAV"),
        ("WAV", 36000 * 48000, 2, "RF64"),
        ("WAV", 11185 * 48000, 2, "RF64"),
        ("FLAC", 36000 * 48000, 2, "FLAC"),
        ("OGG", 36000 * 48000, 2, "OGG"),
        ("MP3", 36000 * 48000, 2, "MP3"),
    ],
)
def test_resolve_soundfile_format_threshold(fmt, n_frames, n_channels, expected):
    assert _resolve_soundfile_format(fmt, n_frames, n_channels) == expected


def test_extend_switches_to_rf64_when_exceeding_threshold(tmp_path: Path, monkeypatch):
    wav_path = make_loopable_wav(tmp_path / "short.wav", sr=22050, duration_s=2.0)
    ml = MusicLooper(str(wav_path))
    monkeypatch.setattr(core_module, "_WAV_STANDARD_MAX_BYTES", 100_000)

    out_path = ml.extend(
        10000,
        30000,
        extended_length=6.0,
        fade_length=1.0,
        format="WAV",
        output_dir=str(tmp_path),
    )
    assert out_path.endswith(".wav")
    assert Path(out_path).read_bytes()[:4] == b"RF64"
    data, sr = sf.read(out_path)
    assert sr == 22050
    assert data.shape[0] / sr >= 5.5


def test_extend_count_integer_with_fade_out(short_wav: Path, tmp_path: Path):
    ml = MusicLooper(str(short_wav))
    out_path = ml.extend(
        10000,
        50000,
        extended_count=3,
        fade_length=0.5,
        format="WAV",
        output_dir=str(tmp_path),
    )
    assert out_path.endswith("-extended-3lp.wav")
    data, sr = sf.read(out_path)
    assert sr == 22050
    assert data.shape[0] == 130000
    assert float(np.max(np.abs(data[-10:]))) < 0.01


def test_extend_count_fractional_with_fade_out(short_wav: Path, tmp_path: Path):
    ml = MusicLooper(str(short_wav))
    out_path = ml.extend(
        10000,
        50000,
        extended_count=2.5,
        fade_length=0.5,
        format="WAV",
        output_dir=str(tmp_path),
    )
    assert out_path.endswith("-extended-2.5lp.wav")
    data, _ = sf.read(out_path)
    assert data.shape[0] == 110000


def test_extend_count_disable_fade_out_includes_outro(short_wav: Path, tmp_path: Path):
    ml = MusicLooper(str(short_wav))
    outro_len = ml.mlaudio.length - 50000
    out_path = ml.extend(
        10000,
        50000,
        extended_count=3,
        disable_fade_out=True,
        format="WAV",
        output_dir=str(tmp_path),
    )
    assert out_path.endswith("-extended-3lp.wav")
    data, _ = sf.read(out_path)
    assert data.shape[0] == 10000 + 3 * 40000 + outro_len


def test_extend_count_and_length_mutually_exclusive(short_wav: Path, cli_runner):
    ml = MusicLooper(str(short_wav))
    with pytest.raises(ValueError):
        ml.extend(10000, 50000, extended_length=10.0, extended_count=2)
    with pytest.raises(ValueError):
        ml.extend(10000, 50000)

    res_both = cli_runner.invoke(
        cli_main,
        [
            "extend",
            "--path",
            str(short_wav),
            "--extended-length",
            "10",
            "--extended-count",
            "2",
        ],
    )
    assert res_both.exit_code != 0

    res_neither = cli_runner.invoke(cli_main, ["extend", "--path", str(short_wav)])
    assert res_neither.exit_code != 0


def test_extend_count_cli(loopable_wav: Path, tmp_path: Path, cli_runner):
    out_dir = tmp_path / "out"
    res = cli_runner.invoke(
        cli_main,
        [
            "extend",
            "--path",
            str(loopable_wav),
            "--min-duration-multiplier",
            "0.25",
            "--extended-count",
            "2",
            "--format",
            "WAV",
            "--output-dir",
            str(out_dir),
        ],
    )
    assert res.exit_code == 0, res.output
    files = [p.name for p in out_dir.iterdir()]
    assert len(files) == 1
    assert files[0].endswith("-extended-2lp.wav")
