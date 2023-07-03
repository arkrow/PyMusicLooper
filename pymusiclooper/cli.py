import functools
import logging
import os
import tempfile
import warnings

import rich_click as click
from rich_click.cli import patch as rich_click_patch
from yt_dlp.utils import YoutubeDLError

rich_click_patch()
from click_option_group import RequiredMutuallyExclusiveOptionGroup, optgroup
from click_params import PUBLIC_URL as UrlParamType

from . import __version__
from .core import MusicLooper
from .handler import BatchHandler, LoopExportHandler, LoopHandler
from .youtube import YoutubeDownloader

# CLI --help styling
_basic_options = ["--path", "--url"]
_loop_options = [
    "--min-duration-multiplier",
    "--min-loop-duration",
    "--max-loop-duration",
    "--approx-loop-position",
]
_export_options = ["--output-dir", "--format"]
_batch_options = ["--recursive", "--flatten", "--n-jobs"]


def _option_groups(additional_basic_options: list[str] = None):
    if additional_basic_options is not None:
        combined_basic_options = _basic_options + additional_basic_options
    else:
        combined_basic_options = _basic_options
    return [
        {
            "name": "Basic options",
            "options": combined_basic_options,
        },
        {
            "name": "Advanced loop options",
            "options": _loop_options,
        },
        {
            "name": "Export options",
            "options": _export_options,
        },
        {
            "name": "Batch options",
            "options": _batch_options,
        },
    ]


_common_option_groups = _option_groups()
click.rich_click.OPTION_GROUPS = {
    "pymusiclooper play": _common_option_groups,
    "pymusiclooper split-audio": _common_option_groups,
    "pymusiclooper tag": _option_groups(["--tag-names"]),
    "pymusiclooper export-loop-points": _option_groups(["--export-to"]),
}
click.rich_click.USE_RICH_MARKUP = True
# End CLI styling


@click.group("pymusiclooper", epilog="Full documentation and examples can be found at https://github.com/arkrow/PyMusicLooper")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enables verbose logging output.")
@click.option("--interactive", "-i", is_flag=True, default=False, help="Enables interactive mode to manually preview/choose the desired loop point.")
@click.option("--samples", "-s", is_flag=True, default=False, help="Display all loop points in interactive mode in sample points instead of the default mm:ss.sss format.")
@click.version_option(__version__, prog_name="pymusiclooper")
def cli_main(verbose, interactive, samples):
    """A program for repeating music seamlessly and endlessly, by automatically finding the best loop points."""
    # Store flags in environ instead of passing them as parameters
    os.environ["PML_VERBOSE"] = str(verbose)
    os.environ["PML_INTERACTIVE_MODE"] = str(interactive)
    os.environ["PML_DISPLAY_SAMPLES"] = str(samples)

    warnings.filterwarnings("ignore")
    # To suppress warnings in batch mode's subprocesses
    os.environ["PYTHONWARNINGS"] = "ignore"

    if verbose:
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    else:
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.ERROR)


def common_path_options(f):
    @optgroup.group('audio path', cls=RequiredMutuallyExclusiveOptionGroup, help='the path to the audio track(s) to load')
    @optgroup.option('--path', type=click.Path(exists=True), default=None, help='path to the audio file(s). [dim]\[[/][dim cyan]mutually exclusive with --url;[/] [dim red]at least one required[/][dim]][/]')
    @optgroup.option('--url',type=UrlParamType, default=None, help='url of the youtube video (or any stream supported by yt-dlp) to extract audio from and use. [dim]\[[/][dim cyan]mutually exclusive with --path;[/] [dim red]at least one required[/][dim]][/]')

    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper_common_options


def common_loop_options(f):
    @click.option('--min-duration-multiplier', type=click.FloatRange(min=0.0, max=1.0), default=0.35, show_default=True, help="the minimum loop duration as a multiplier of the audio track's total duration.")
    @click.option('--min-loop-duration', type=click.FloatRange(min=0), default=None, help='the minimum loop duration in seconds (note: overrides --min-duration-multiplier if specified).')
    @click.option('--max-loop-duration', type=click.FloatRange(min=0), default=None, help='the maximum loop duration in seconds.')
    @click.option('--approx-loop-position', type=click.FloatRange(min=0), nargs=2, default=None, help='the approximate desired loop start and loop end in seconds for a specific audio track (note: only those points will be checked, with a search window of +/- 2 seconds).')

    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper_common_options


def common_export_options(f):
    @click.option('--output-dir', '-o', type=click.Path(exists=False, writable=True, file_okay=False), help="the output directory to use for the exported files.")
    @click.option("--recursive", "-r", is_flag=True, default=False, help="process directories recursively.")
    @click.option("--flatten", "-f", is_flag=True, default=False, help="flatten the output directory structure instead of preserving it when using the --recursive flag (note: files with identical filenames are silently overwritten).")
    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper_common_options


@cli_main.command()
@common_path_options
@common_loop_options
def play(
    path,
    url,
    min_duration_multiplier,
    min_loop_duration,
    max_loop_duration,
    approx_loop_position,
):
    """Play an audio file on repeat from the terminal with the best discovered loop points (default), or a chosen point if interactive mode is active."""
    try:
        if url is not None:
            path = download_audio(url, tempfile.gettempdir())

        handler = LoopHandler(
            file_path=path,
            min_duration_multiplier=min_duration_multiplier,
            min_loop_duration=min_loop_duration,
            max_loop_duration=max_loop_duration,
            approx_loop_position=approx_loop_position,
        )

        in_samples = os.environ.get("PML_DISPLAY_SAMPLES", "False") == "True"
        interactive_mode = os.environ.get("PML_INTERACTIVE_MODE", "False") == "True"

        chosen_loop_pair = handler.choose_loop_pair(interactive_mode=interactive_mode)

        looper = handler.get_musiclooper_obj()

        start_time = (
            chosen_loop_pair.loop_start
            if in_samples
            else looper.samples_to_ftime(chosen_loop_pair.loop_start)
        )
        end_time = (
            chosen_loop_pair.loop_start
            if in_samples
            else looper.samples_to_ftime(chosen_loop_pair.loop_end)
        )

        click.echo(
            "Playing with looping active from {} back to {}; similarity: {:.2%}".format(
                end_time,
                start_time,
                chosen_loop_pair.score,
            )
        )
        click.echo("(press Ctrl+C to stop looping.)")

        handler.play_looping(chosen_loop_pair.loop_start, chosen_loop_pair.loop_end)

    except YoutubeDLError:
        # Already logged from youtube.py
        pass
    except Exception as e:
        logging.error(e)


@cli_main.command()
@click.option('--path', type=click.Path(exists=True), required=True, help='path to audio file')
@click.option("--tag-names", type=str, required=True, nargs=2, help="The name of the metadata tags to read from, e.g. --tags-names LOOP_START LOOP_END  (note: values must be in samples and integer values)")
def play_tagged(path, tag_names):
    """Skips loop analysis and reads the loop points directly from the tags present in the file."""
    try:
        looper = MusicLooper(path)
        loop_start, loop_end = looper.read_tags(tag_names[0], tag_names[1])

        in_samples = os.environ.get("PML_DISPLAY_SAMPLES", "False") == "True"

        start_time = (
            loop_start
            if in_samples
            else looper.samples_to_ftime(loop_start)
        )
        end_time = (
            loop_end
            if in_samples
            else looper.samples_to_ftime(loop_end)
        )

        click.echo(f"Playing with looping active from {end_time} back to {start_time}")
        click.echo("(press Ctrl+C to stop looping.)")

        looper.play_looping(loop_start, loop_end)

    except Exception as e:
        logging.error(e)


@cli_main.command()
@common_path_options
@common_loop_options
@common_export_options
@click.option('--format', type=click.Choice(("WAV", "FLAC", "OGG", "MP3"), case_sensitive=False), default="WAV", show_default=True, help="audio format of the exported split audio files")
@click.option('--n-jobs', '-n', type=click.IntRange(min=1), default=1, show_default=True, help="number of files to batch process at a time [yellow](warning: memory intensive)[/].")
def split_audio(
    path,
    url,
    min_duration_multiplier,
    min_loop_duration,
    max_loop_duration,
    approx_loop_position,
    output_dir,
    recursive,
    flatten,
    format,
    n_jobs,
):
    """Split the input audio into intro, loop and outro sections"""
    try:
        if url is not None:
            output_dir = mk_outputdir(os.getcwd(), output_dir)
            path = download_audio(url, output_dir)
        else:
            output_dir = mk_outputdir(path, output_dir)

        if os.path.isfile(path):
            export_handler = LoopExportHandler(
                file_path=path,
                min_duration_multiplier=min_duration_multiplier,
                min_loop_duration=min_loop_duration,
                max_loop_duration=max_loop_duration,
                approx_loop_position=approx_loop_position,
                output_dir=output_dir,
                split_audio=True,
                split_audio_format=format,
                to_txt=False,
                to_stdout=False,
                tag_names=None,
            )
            export_handler.run()
        else:
            batch_handler = BatchHandler(
                directory_path=path,
                min_duration_multiplier=min_duration_multiplier,
                min_loop_duration=min_loop_duration,
                max_loop_duration=max_loop_duration,
                output_dir=output_dir,
                split_audio=True,
                split_audio_format=format,
                to_txt=False,
                to_stdout=False,
                recursive=recursive,
                flatten=flatten,
                n_jobs=n_jobs,
                tag_names=None,
            )
            batch_handler.run()
    except YoutubeDLError:
        # Already logged from youtube.py
        pass
    except Exception as e:
        logging.error(e)


@cli_main.command()
@common_path_options
@common_loop_options
@common_export_options
@click.option("--export-to", type=click.Choice(('STDOUT', 'TXT'), case_sensitive=False), default="STDOUT", required=True, show_default=True, help="STDOUT: prints the loop points of a track in samples to the terminal's stdout (OR) TXT: export the loop points of a track in samples and append to a loop.txt file (compatible with LoopingAudioConverter).")
def export_loop_points(
    path,
    url,
    min_duration_multiplier,
    min_loop_duration,
    max_loop_duration,
    approx_loop_position,
    output_dir,
    recursive,
    flatten,
    export_to,
):
    """Export the best discovered or chosen loop points to a text file or to the terminal (stdout)"""
    try:
        to_stdout = export_to.upper() == "STDOUT"
        to_txt = export_to.upper() == "TXT"

        if url is not None:
            output_dir = mk_outputdir(os.getcwd(), output_dir)
            path = download_audio(url, output_dir)
        else:
            output_dir = mk_outputdir(path, output_dir)

        if os.path.isfile(path):
            export_handler = LoopExportHandler(
                file_path=path,
                min_duration_multiplier=min_duration_multiplier,
                min_loop_duration=min_loop_duration,
                max_loop_duration=max_loop_duration,
                approx_loop_position=approx_loop_position,
                output_dir=output_dir,
                split_audio=False,
                to_txt=to_txt,
                to_stdout=to_stdout,
                tag_names=None,
            )
            export_handler.run()
        else:
            # Disable multiprocessing until a thread-safe multiprocessing queue is implemented
            n_jobs = 1

            batch_handler = BatchHandler(
                directory_path=path,
                min_duration_multiplier=min_duration_multiplier,
                min_loop_duration=min_loop_duration,
                max_loop_duration=max_loop_duration,
                output_dir=output_dir,
                split_audio=False,
                to_txt=to_txt,
                to_stdout=to_stdout,
                recursive=recursive,
                flatten=flatten,
                n_jobs=n_jobs,
                tag_names=None,
            )
            batch_handler.run()
    except YoutubeDLError:
        # Already logged from youtube.py
        pass
    except Exception as e:
        logging.error


@cli_main.command()
@common_path_options
@common_loop_options
@common_export_options
@click.option('--n-jobs', '-n', type=click.IntRange(min=1), default=1, show_default=True, help="number of files to batch process at a time [yellow](warning: memory intensive)[/].")
@click.option('--tag-names', type=str, required=True, nargs=2, help='the name to use for the metadata tags, e.g. --tag-names LOOP_START LOOP_END')
def tag(
    path,
    url,
    min_duration_multiplier,
    min_loop_duration,
    max_loop_duration,
    approx_loop_position,
    output_dir,
    recursive,
    flatten,
    n_jobs,
    tag_names,
):
    """Adds metadata tags of loop points to a copy of the input audio file(s)"""
    try:
        if url is not None:
            output_dir = mk_outputdir(os.getcwd(), output_dir)
            path = download_audio(url, output_dir)
        else:
            output_dir = mk_outputdir(path, output_dir)

        if os.path.isfile(path):
            export_handler = LoopExportHandler(
                file_path=path,
                min_duration_multiplier=min_duration_multiplier,
                min_loop_duration=min_loop_duration,
                max_loop_duration=max_loop_duration,
                approx_loop_position=approx_loop_position,
                output_dir=output_dir,
                split_audio=False,
                to_txt=False,
                to_stdout=False,
                tag_names=tag_names,
            )
            export_handler.run()
        else:
            batch_handler = BatchHandler(
                directory_path=path,
                min_duration_multiplier=min_duration_multiplier,
                min_loop_duration=min_loop_duration,
                max_loop_duration=max_loop_duration,
                output_dir=output_dir,
                split_audio=False,
                to_txt=False,
                to_stdout=False,
                recursive=recursive,
                flatten=flatten,
                n_jobs=n_jobs,
                tag_names=tag_names,
            )
            batch_handler.run()
    except YoutubeDLError:
        # Already logged from youtube.py
        pass
    except Exception as e:
        logging.error(e)


def mk_outputdir(path, output_dir):
    if os.path.isdir(path):
        default_out = os.path.join(path, "LooperOutput")
    else:
        default_out = os.path.join(os.path.dirname(path), "LooperOutput")
    output_dir_to_use = default_out if output_dir is None else output_dir

    if not os.path.exists(output_dir_to_use):
        os.mkdir(output_dir_to_use)
    return output_dir_to_use


def download_audio(url, output_dir):
    yt = YoutubeDownloader(url, output_dir)
    return yt.filepath

if __name__ == "__main__":
    cli_main()
