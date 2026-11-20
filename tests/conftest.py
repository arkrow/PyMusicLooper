from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from click.testing import CliRunner


def make_loopable_wav(
    filepath: str | Path,
    sr: int = 22050,
    duration_s: float = 8.0,
) -> Path:
    """Generates a deterministic stereo WAV with a repeating musical pattern."""
    path = Path(filepath)
    n = int(sr * duration_s)
    t = np.arange(n, dtype=np.float32) / sr
    phase = t % 2.0
    freq = np.where(
        phase < 0.5,
        220.0,
        np.where(phase < 1.0, 277.18, np.where(phase < 1.5, 329.63, 440.0)),
    )
    env = 0.5 + 0.3 * np.sin(2 * np.pi * 2.0 * t)
    sig = (0.4 * env * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    stereo = np.column_stack([sig, sig * 0.9])
    sf.write(str(path), stereo, sr, format="WAV")
    return path


@pytest.fixture
def loopable_wav(tmp_path: Path) -> Path:
    """An 8-second stereo loopable WAV file at 22.05 kHz."""
    return make_loopable_wav(tmp_path / "track.wav", sr=22050, duration_s=8.0)


@pytest.fixture
def short_wav(tmp_path: Path) -> Path:
    """A 4-second stereo WAV file at 22.05 kHz."""
    return make_loopable_wav(tmp_path / "track.wav", sr=22050, duration_s=4.0)


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()
