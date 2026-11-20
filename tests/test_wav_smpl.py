import struct
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import taglib

from pymusiclooper.core import MusicLooper
from pymusiclooper.wav_smpl import is_wav_file, read_wav_smpl, write_wav_smpl
from tests.conftest import make_loopable_wav


@pytest.fixture
def wav_44k(tmp_path: Path) -> Path:
    return make_loopable_wav(tmp_path / "sample.wav", sr=44100, duration_s=2.0)


def test_is_wav_file(wav_44k: Path, tmp_path: Path):
    assert is_wav_file(str(wav_44k))

    non_wav = tmp_path / "not_a_wav.wav"
    non_wav.write_bytes(b"OggS1234567890")
    assert not is_wav_file(str(non_wav))
    assert not is_wav_file(str(tmp_path / "missing.wav"))


def test_smpl_write_read_and_replace(wav_44k: Path):
    assert read_wav_smpl(str(wav_44k)) is None

    write_wav_smpl(str(wav_44k), 16388, 30219, 44100)
    assert read_wav_smpl(str(wav_44k)) == (16388, 30219)

    raw = wav_44k.read_bytes()
    assert raw[:4] == b"RIFF"
    assert struct.unpack("<I", raw[4:8])[0] == len(raw) - 8
    idx = raw.find(b"smpl")
    assert idx > 12
    assert struct.unpack("<I", raw[idx + 4 : idx + 8])[0] == 60
    fields = struct.unpack("<9I6I", raw[idx + 8 : idx + 68])
    assert fields[7] == 1  # cSampleLoops
    assert fields[11] == 16388  # dwStart
    assert fields[12] == 30218  # dwEnd (inclusive)

    # Replacing an existing smpl chunk must leave only one smpl chunk
    write_wav_smpl(str(wav_44k), 1000, 50000, 44100)
    assert read_wav_smpl(str(wav_44k)) == (1000, 50000)
    assert wav_44k.read_bytes().count(b"smpl") == 1

    data, sr = sf.read(str(wav_44k))
    assert sr == 44100
    assert data.shape == (88200, 2)


def test_smpl_with_rf64_wav(tmp_path: Path):
    rf64_path = tmp_path / "big.wav"
    data = np.zeros((44100, 2), dtype=np.float32)
    with sf.SoundFile(
        str(rf64_path), mode="w", samplerate=44100, channels=2, format="RF64"
    ) as f:
        f.write(data)
    assert is_wav_file(str(rf64_path))

    write_wav_smpl(str(rf64_path), 5000, 40000, 44100)
    assert read_wav_smpl(str(rf64_path)) == (5000, 40000)

    read_back, sr = sf.read(str(rf64_path))
    assert sr == 44100
    assert read_back.shape == (44100, 2)


def test_export_tags_writes_both_taglib_and_smpl_for_wav(wav_44k: Path, tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    ml = MusicLooper(str(wav_44k))

    # Offset tag LOOPLENGTH stores relative length in ID3 while smpl stores absolute bounds
    result = ml.export_tags(
        10000,
        50000,
        "LOOPSTART",
        "LOOPLENGTH",
        output_dir=str(out_dir),
    )
    assert result == ("10000", "40000")

    tagged_path = out_dir / "sample-tagged.wav"
    assert tagged_path.exists()
    assert read_wav_smpl(str(tagged_path)) == (10000, 50000)
    with taglib.File(str(tagged_path), save_on_exit=False) as tf:
        assert tf.tags["LOOPSTART"] == ["10000"]
        assert tf.tags["LOOPLENGTH"] == ["40000"]


def test_export_tags_smpl_only_and_read_tags_fallback(wav_44k: Path, tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    ml = MusicLooper(str(wav_44k))

    result = ml.export_tags(
        12000,
        60000,
        output_dir=str(out_dir),
        write_smpl=True,
    )
    assert result == ("12000", "60000")

    tagged_path = out_dir / "sample-tagged.wav"
    assert read_wav_smpl(str(tagged_path)) == (12000, 60000)
    assert MusicLooper(str(tagged_path)).read_tags() == (12000, 60000)


def test_export_tags_no_smpl_opt_out(wav_44k: Path, tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    ml = MusicLooper(str(wav_44k))
    ml.export_tags(
        10000,
        50000,
        "LOOP_START",
        "LOOP_END",
        output_dir=str(out_dir),
        write_smpl=False,
    )
    assert read_wav_smpl(str(out_dir / "sample-tagged.wav")) is None


def test_export_tags_smpl_on_non_wav_raises(wav_44k: Path, tmp_path: Path):
    ogg_path = tmp_path / "sample.ogg"
    data, sr = sf.read(str(wav_44k))
    sf.write(str(ogg_path), data, sr, format="OGG")
    ml = MusicLooper(str(ogg_path))

    with pytest.raises(ValueError):
        ml.export_tags(10000, 50000, output_dir=str(tmp_path), write_smpl=True)
    with pytest.raises(ValueError):
        ml.export_tags(10000, 50000, output_dir=str(tmp_path))
