from pathlib import Path

import taglib

from pymusiclooper.core import MusicLooper
from pymusiclooper.handler import BatchHandler, LoopExportHandler
from pymusiclooper.wav_smpl import read_wav_smpl


def test_export_tags_in_place_no_copy(loopable_wav: Path, tmp_path: Path):
    ml = MusicLooper(str(loopable_wav))
    ml.export_tags(
        5000,
        50000,
        "LOOP_START",
        "LOOP_END",
        in_place=True,
    )
    assert [p.name for p in tmp_path.iterdir()] == ["track.wav"]
    assert read_wav_smpl(str(loopable_wav)) == (5000, 50000)
    with taglib.File(str(loopable_wav), save_on_exit=False) as tf:
        assert tf.tags["LOOP_START"] == ["5000"]
        assert tf.tags["LOOP_END"] == ["50000"]


def test_export_tags_default_output_dir_none(loopable_wav: Path, tmp_path: Path):
    ml = MusicLooper(str(loopable_wav))
    ml.export_tags(5000, 50000, "LOOP_START", "LOOP_END", output_dir=None)
    assert (tmp_path / "track-tagged.wav").exists()


def test_handler_and_batch_in_place_skip_output_dir(loopable_wav: Path, tmp_path: Path):
    out_dir = tmp_path / "LooperOutput"
    handler = LoopExportHandler(
        path=str(loopable_wav),
        min_duration_multiplier=0.25,
        output_dir=str(out_dir),
        tag_names=("LOOP_START", "LOOP_END"),
        in_place=True,
        tag_mode=True,
    )
    handler.run()
    assert not out_dir.exists()
    assert read_wav_smpl(str(loopable_wav)) is not None

    batch = BatchHandler(
        path=str(tmp_path),
        output_dir=str(out_dir),
        min_duration_multiplier=0.25,
        tag_names=("LOOP_START", "LOOP_END"),
        in_place=True,
        tag_mode=True,
    )
    batch.run()
    assert not out_dir.exists()
