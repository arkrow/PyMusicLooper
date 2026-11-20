import shutil
import subprocess
from pathlib import Path

import pytest
import soundfile as sf

from pymusiclooper.analysis import LoopPair
from pymusiclooper.cli import cli_main
from pymusiclooper.core import MusicLooper
from pymusiclooper.handler import LoopHandler
from tests.conftest import make_loopable_wav


def test_play_start_before_end_cli(loopable_wav: Path, cli_runner, monkeypatch):
    recorded = {}

    def fake_play_looping(self_ml, loop_start, loop_end, start_from=0):
        recorded["loop_start"] = loop_start
        recorded["loop_end"] = loop_end
        recorded["start_from"] = start_from

    monkeypatch.setattr(MusicLooper, "play_looping", fake_play_looping)
    res = cli_runner.invoke(
        cli_main,
        [
            "play",
            "--path",
            str(loopable_wav),
            "--min-duration-multiplier",
            "0.25",
            "--start-before-end",
            "1.5",
        ],
    )
    assert res.exit_code == 0, res.output
    expected_offset = int(round(1.5 * 22050))
    assert abs(recorded["start_from"] - max(0, recorded["loop_end"] - expected_offset)) <= 2


def test_play_tagged_start_before_end_cli(loopable_wav: Path, cli_runner, monkeypatch):
    ml = MusicLooper(str(loopable_wav))
    ml.export_tags(22050, 150000, in_place=True, write_smpl=True)

    recorded = {}

    def fake_play_looping(self_ml, loop_start, loop_end, start_from=0):
        recorded["loop_start"] = loop_start
        recorded["loop_end"] = loop_end
        recorded["start_from"] = start_from

    monkeypatch.setattr(MusicLooper, "play_looping", fake_play_looping)
    res = cli_runner.invoke(
        cli_main,
        ["play-tagged", "--path", str(loopable_wav), "--start-before-end", "2.0"],
    )
    assert res.exit_code == 0, res.output
    assert recorded["loop_start"] == 22050
    assert recorded["loop_end"] == 150000
    assert abs(recorded["start_from"] - (150000 - 44100)) <= 2


def test_interactive_handler_more_and_custom_preview_offset(loopable_wav: Path, monkeypatch):
    handler = LoopHandler.__new__(LoopHandler)
    handler.filepath = str(loopable_wav)
    handler._musiclooper = MusicLooper(str(loopable_wav))
    handler.in_samples = True
    handler.start_before_end = 2.0
    handler.loop_pair_list = [
        LoopPair(0, 100, 0.01, 0.01, 0.99, 10000, 120000),
        LoopPair(0, 100, 0.02, 0.02, 0.98, 20000, 130000),
    ]

    preview_calls = []

    def fake_play_looping(loop_start, loop_end, start_from=0):
        preview_calls.append((loop_start, loop_end, start_from))

    inputs = iter(["more", "0p", "1"])
    monkeypatch.setattr(handler._musiclooper, "play_looping", fake_play_looping)
    monkeypatch.setattr("pymusiclooper.handler.rich_console.input", lambda _: next(inputs))

    selected = handler.interactive_handler(show_top=1)
    assert selected == 1
    assert len(preview_calls) == 1
    assert abs(preview_calls[0][2] - (120000 - 44100)) <= 2


def test_play_auto_reads_tags_and_no_read_tags_forces_analysis(
    loopable_wav: Path, cli_runner, monkeypatch
):
    ml = MusicLooper(str(loopable_wav))
    ml.export_tags(11111, 144444, "LOOP_START", "LOOP_END", in_place=True)

    recorded = {}

    def fake_play(self_ml, loop_start, loop_end, start_from=0):
        recorded["points"] = (loop_start, loop_end)

    def fail_analyze(*args, **kwargs):
        raise AssertionError("should not analyze")

    monkeypatch.setattr(MusicLooper, "play_looping", fake_play)
    with monkeypatch.context() as m:
        m.setattr(MusicLooper, "find_loop_pairs", fail_analyze)
        res = cli_runner.invoke(cli_main, ["play", "--path", str(loopable_wav)])
    assert res.exit_code == 0, res.output
    assert recorded["points"] == (11111, 144444)

    res = cli_runner.invoke(
        cli_main,
        [
            "play",
            "--path",
            str(loopable_wav),
            "--min-duration-multiplier",
            "0.25",
            "--no-read-tags",
        ],
    )
    assert res.exit_code == 0, res.output
    assert recorded["points"] != (11111, 144444)


def test_read_tags_flag_errors_when_untagged(loopable_wav: Path, cli_runner, monkeypatch):
    def fail_analyze(*args, **kwargs):
        raise AssertionError("should not analyze")

    monkeypatch.setattr(MusicLooper, "find_loop_pairs", fail_analyze)
    res = cli_runner.invoke(cli_main, ["play", "--path", str(loopable_wav), "--read-tags"])
    assert res.exit_code == 0, res.output

    res_pt = cli_runner.invoke(cli_main, ["play-tagged", "--path", str(loopable_wav)])
    assert res_pt.exit_code == 0, res_pt.output


def test_split_audio_extend_and_export_points_use_tags(
    loopable_wav: Path, tmp_path: Path, cli_runner, monkeypatch
):
    ml = MusicLooper(str(loopable_wav))
    ml.export_tags(
        20000, 120000, "CUSTOM_START", "CUSTOM_END", in_place=True, write_smpl=False
    )

    def fail_analyze(*args, **kwargs):
        raise AssertionError("should not analyze")

    monkeypatch.setattr(MusicLooper, "find_loop_pairs", fail_analyze)

    split_dir = tmp_path / "split"
    res_split = cli_runner.invoke(
        cli_main,
        [
            "split-audio",
            "--path",
            str(loopable_wav),
            "--tag-names",
            "CUSTOM_START",
            "CUSTOM_END",
            "--loop-only",
            "--output-dir",
            str(split_dir),
        ],
    )
    assert res_split.exit_code == 0, res_split.output
    assert [p.name for p in split_dir.iterdir()] == ["track.wav-loop.wav"]
    data, _ = sf.read(str(split_dir / "track.wav-loop.wav"))
    assert data.shape[0] == 100000

    extend_dir = tmp_path / "extend"
    res_ext = cli_runner.invoke(
        cli_main,
        [
            "extend",
            "--path",
            str(loopable_wav),
            "--tag-names",
            "CUSTOM_START",
            "CUSTOM_END",
            "--extended-count",
            "2",
            "--format",
            "WAV",
            "--output-dir",
            str(extend_dir),
        ],
    )
    assert res_ext.exit_code == 0, res_ext.output
    assert [p.name for p in extend_dir.iterdir()] == ["track.wav-extended-2lp.wav"]

    res_pts = cli_runner.invoke(
        cli_main,
        [
            "export-points",
            "--path",
            str(loopable_wav),
            "--tag-names",
            "CUSTOM_START",
            "CUSTOM_END",
        ],
    )
    assert res_pts.exit_code == 0, res_pts.output
    assert "20000" in res_pts.output
    assert "120000" in res_pts.output


def test_tag_command_still_analyzes_when_file_has_old_tags(loopable_wav: Path, cli_runner):
    ml = MusicLooper(str(loopable_wav))
    ml.export_tags(11111, 144444, "LOOP_START", "LOOP_END", in_place=True)

    res = cli_runner.invoke(
        cli_main,
        [
            "tag",
            "--path",
            str(loopable_wav),
            "--min-duration-multiplier",
            "0.25",
            "--tag-names",
            "LOOP_START",
            "LOOP_END",
            "--in-place",
        ],
    )
    assert res.exit_code == 0, res.output
    assert MusicLooper(str(loopable_wav)).read_tags() != (11111, 144444)


def test_split_audio_url_opus_unicode_filename(tmp_path: Path, cli_runner, monkeypatch):
    if shutil.which("ffmpeg") is None:
        pytest.skip("Requires ffmpeg")

    src_wav = make_loopable_wav(tmp_path / "source.wav", sr=48000, duration_s=8.0)
    out_dir = tmp_path / "LooperOutput"
    out_dir.mkdir()
    opus_name = "Come On! (Faithful Cover) \uff5c\uff5c Mario & Luigi\uff1a Superstar Saga [Zo2Wp0D4VU0].opus"
    opus_path = out_dir / opus_name
    res = subprocess.run(
        ["ffmpeg", "-y", "-i", str(src_wav), "-c:a", "libopus", str(opus_path)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr

    monkeypatch.setattr("pymusiclooper.cli.download_audio", lambda _url, _out: str(opus_path))
    cli_res = cli_runner.invoke(
        cli_main,
        [
            "split-audio",
            "--url",
            "https://www.youtube.com/watch?v=Zo2Wp0D4VU0",
            "--min-duration-multiplier",
            "0.25",
            "--output-dir",
            str(out_dir),
            "--format",
            "OGG",
        ],
    )
    assert cli_res.exit_code == 0, cli_res.output
    for suffix in ("intro", "loop", "outro"):
        section_path = out_dir / f"{opus_name}-{suffix}.ogg"
        assert section_path.exists(), f"Missing {suffix}"
        assert section_path.stat().st_size > 0, f"Empty {suffix}"


@pytest.mark.parametrize(
    "args",
    [
        ["--help"],
        ["play", "--help"],
        ["play-tagged", "--help"],
        ["split-audio", "--help"],
        ["extend", "--help"],
        ["export-points", "--help"],
        ["tag", "--help"],
    ],
)
def test_cli_help_all_commands(cli_runner, args):
    res = cli_runner.invoke(cli_main, args)
    assert res.exit_code == 0, f"{args} failed: {res.output}"
