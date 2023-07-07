import functools
import logging
import os
import tempfile
import warnings
from typing import List, Optional

import rich_click as click
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich_click.cli import patch as rich_click_patch
from yt_dlp.utils import YoutubeDLError

rich_click_patch()
from click_option_group import RequiredMutuallyExclusiveOptionGroup, optgroup
from click_params import PUBLIC_URL as UrlParamType

from . import __version__
from .console import COMMAND_GROUPS, OPTION_GROUPS, rich_console
from .core import MusicLooper
from .exceptions import AudioLoadError, LoopNotFoundError
from .handler import BatchHandler, LoopExportHandler, LoopHandler
from .youtube import YoutubeDownloader

# CLI --help styling
click.rich_click.OPTION_GROUPS = OPTION_GROUPS
click.rich_click.COMMAND_GROUPS = COMMAND_GROUPS
click.rich_click.USE_RICH_MARKUP = True
# End CLI styling


@click.group("pymusiclooper", epilog="Full documentation and examples can be found at https://github.com/arkrow/PyMusicLooper")
@click.option("--debug", "-d", is_flag=True, default=False, help="Enables debugging mode.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enables verbose logging output.")
@click.option("--interactive", "-i", is_flag=True, default=False, help="Enables interactive mode to manually preview/choose the desired loop point.")
@click.option("--samples", "-s", is_flag=True, default=False, help="Display all the loop points shown in interactive mode in sample points instead of the default mm:ss.sss format.")
@click.version_option(__version__, prog_name="pymusiclooper", message="%(prog)s %(version)s")
def cli_main(debug, verbose, interactive, samples):
    """A program for repeating music seamlessly and endlessly, by automatically finding the best loop points."""
    # Store flags in environ instead of passing them as parameters
    if verbose:
        os.environ["PML_VERBOSE"] = "1"
    if interactive:
        os.environ["PML_INTERACTIVE_MODE"] = "1"
    if samples:
        os.environ["PML_DISPLAY_SAMPLES"] = "1"

    if debug:
        os.environ["PML_DEBUG"] = "1"
        warnings.simplefilter("default")
    else:
        warnings.filterwarnings("ignore")

    if verbose:
        logging.basicConfig(format="%(message)s", level=logging.INFO, handlers=[RichHandler(level=logging.INFO, console=rich_console, rich_tracebacks=True, show_path=debug, show_time=False, tracebacks_suppress=[click])])
    else:
        logging.basicConfig(format="%(message)s", level=logging.ERROR, handlers=[RichHandler(level=logging.ERROR, console=rich_console, show_time=False, show_path=False)])


def common_path_options(f):
    @optgroup.group("audio path", cls=RequiredMutuallyExclusiveOptionGroup, help="the path to the audio track(s) to load")
    @optgroup.option("--path", type=click.Path(exists=True), default=None, help=r"Path to the audio file(s). [dim cyan]\[mutually exclusive with --url][/] [dim red]\[at least one required][/]")
    @optgroup.option("--url",type=UrlParamType, default=None, help=r"Link to the youtube video (or any stream supported by yt-dlp) to extract audio from and use. [dim cyan]\[mutually exclusive with --path][/] [dim red]\[at least one required][/]")

    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper_common_options


def common_loop_options(f):
    @click.option('--min-duration-multiplier', type=click.FloatRange(min=0.0, max=1.0, min_open=True, max_open=True), default=0.35, show_default=True, help="The minimum loop duration as a multiplier of the audio track's total duration.")
    @click.option('--min-loop-duration', type=click.FloatRange(min=0, min_open=True), default=None, help='The minimum loop duration in seconds. [dim](overrides --min-duration-multiplier if set)[/]')
    @click.option('--max-loop-duration', type=click.FloatRange(min=0, min_open=True), default=None, help='The maximum loop duration in seconds.')
    @click.option('--approx-loop-position', type=click.FloatRange(min=0), nargs=2, default=None, help='The approximate desired loop start and loop end in seconds. [dim](+/-2 second search window for each point)[/]')
    @click.option("--brute-force", is_flag=True, default=False, help=r"Check the entire audio track instead of just the detected beats. [dim yellow](Warning: may take several minutes to complete.)[/]")
    @click.option("--disable-pruning", is_flag=True, default=False, help="Disables filtering of the detected loop points from the initial pass.")

    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper_common_options


def common_export_options(f):
    @click.option('--output-dir', '-o', type=click.Path(exists=False, writable=True, file_okay=False), help="The output directory to use for the exported files.")
    @click.option("--recursive", "-r", is_flag=True, default=False, help="Process directories recursively.")
    @click.option("--flatten", "-f", is_flag=True, default=False, help="Flatten the output directory structure instead of preserving it when using the --recursive flag. [dim yellow](Note: files with identical filenames are silently overwritten.)[/]")
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
    brute_force,
    disable_pruning
):
    """Play an audio file on repeat from the terminal with the best discovered loop points, or a chosen point if interactive mode is active."""
    try:
        if url is not None:
            path = download_audio(url, tempfile.gettempdir())

        with Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            TimeElapsedColumn(),
            console=rich_console,
            transient=True
        ) as progress:
            progress.add_task("Processing", total=None)
            handler = LoopHandler(
                file_path=path,
                min_duration_multiplier=min_duration_multiplier,
                min_loop_duration=min_loop_duration,
                max_loop_duration=max_loop_duration,
                approx_loop_position=approx_loop_position,
                brute_force=brute_force,
                disable_pruning=disable_pruning,
            )

        in_samples = "PML_DISPLAY_SAMPLES" in os.environ
        interactive_mode = "PML_INTERACTIVE_MODE" in os.environ

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

        rich_console.print(
            "\nPlaying with looping active from [green]{}[/] back to [green]{}[/]; similarity: {:.2%}".format(
                end_time,
                start_time,
                chosen_loop_pair.score,
            )
        )
        rich_console.print("(Press [red]Ctrl+C[/] to stop looping.)")

        handler.play_looping(chosen_loop_pair.loop_start, chosen_loop_pair.loop_end)

    except YoutubeDLError:
        # Already logged from youtube.py
        pass
    except (AudioLoadError, LoopNotFoundError) as e:
        logging.error(e)
    except Exception as e:
        logging.error(e)


@cli_main.command()
@click.option('--path', type=click.Path(exists=True), required=True, help='Path to the audio file.')
@click.option("--tag-names", type=str, required=True, nargs=2, help="Name of the loop metadata tags to read from, e.g. --tags-names LOOP_START LOOP_END  (note: values must be integers and in sample units).")
def play_tagged(path, tag_names):
    """Skips loop analysis and reads the loop points directly from the tags present in the file."""
    try:
        looper = MusicLooper(path)
        loop_start, loop_end = looper.read_tags(tag_names[0], tag_names[1])

        in_samples = "PML_DISPLAY_SAMPLES" in os.environ

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

        rich_console.print(f"\nPlaying with looping active from [green]{end_time}[/] back to [green]{start_time}[/]")
        rich_console.print("(Press [red]Ctrl+C[/] to stop looping.)")

        looper.play_looping(loop_start, loop_end)

    except Exception as e:
        logging.error(e)


@cli_main.command()
@common_path_options
@common_loop_options
@common_export_options
@click.option('--format', type=click.Choice(("WAV", "FLAC", "OGG", "MP3"), case_sensitive=False), default="WAV", show_default=True, help="Audio format to use for the exported split audio files.")
def split_audio(
    path,
    url,
    min_duration_multiplier,
    min_loop_duration,
    max_loop_duration,
    approx_loop_position,
    brute_force,
    disable_pruning,
    output_dir,
    recursive,
    flatten,
    format,
):
    """Split the input audio into intro, loop and outro sections."""
    try:
        if url is not None:
            output_dir = mk_outputdir(os.getcwd(), output_dir)
            path = download_audio(url, output_dir)
        else:
            output_dir = mk_outputdir(path, output_dir)

        if os.path.isfile(path):
            with Progress(
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                console=rich_console,
                transient=True
            ) as progress:
                progress.add_task("Processing", total=None)
                export_handler = LoopExportHandler(
                    file_path=path,
                    min_duration_multiplier=min_duration_multiplier,
                    min_loop_duration=min_loop_duration,
                    max_loop_duration=max_loop_duration,
                    approx_loop_position=approx_loop_position,
                    brute_force=brute_force,
                    disable_pruning=disable_pruning,
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
                brute_force=brute_force,
                disable_pruning=disable_pruning,
                output_dir=output_dir,
                split_audio=True,
                split_audio_format=format,
                to_txt=False,
                to_stdout=False,
                recursive=recursive,
                flatten=flatten,
                tag_names=None,
            )
            batch_handler.run()
    except YoutubeDLError:
        # Already logged from youtube.py
        pass
    except (AudioLoadError, LoopNotFoundError) as e:
        logging.error(e)
    except Exception as e:
        logging.error(e)


@cli_main.command()
@common_path_options
@common_loop_options
@common_export_options
@click.option("--export-to", type=click.Choice(('STDOUT', 'TXT'), case_sensitive=False), default="STDOUT", show_default=True, help="STDOUT: print the loop points of a track in samples to the terminal; TXT: export the loop points of a track in samples and append to a loop.txt file.")
def export_points(
    path,
    url,
    min_duration_multiplier,
    min_loop_duration,
    max_loop_duration,
    approx_loop_position,
    brute_force,
    disable_pruning,
    output_dir,
    recursive,
    flatten,
    export_to,
):
    """Export the best discovered or chosen loop points to a text file or to the terminal."""
    try:
        to_stdout = export_to.upper() == "STDOUT"
        to_txt = export_to.upper() == "TXT"

        if url is not None:
            output_dir = mk_outputdir(os.getcwd(), output_dir)
            path = download_audio(url, output_dir)
        else:
            output_dir = mk_outputdir(path, output_dir)

        if os.path.isfile(path):
            with Progress(
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                console=rich_console,
                transient=True
            ) as progress:
                progress.add_task("Processing", total=None)
                export_handler = LoopExportHandler(
                    file_path=path,
                    min_duration_multiplier=min_duration_multiplier,
                    min_loop_duration=min_loop_duration,
                    max_loop_duration=max_loop_duration,
                    approx_loop_position=approx_loop_position,
                    brute_force=brute_force,
                    disable_pruning=disable_pruning,
                    output_dir=output_dir,
                    split_audio=False,
                    to_txt=to_txt,
                    to_stdout=to_stdout,
                    tag_names=None,
                )
            export_handler.run()
        else:
            batch_handler = BatchHandler(
                directory_path=path,
                min_duration_multiplier=min_duration_multiplier,
                min_loop_duration=min_loop_duration,
                max_loop_duration=max_loop_duration,
                brute_force=brute_force,
                disable_pruning=disable_pruning,
                output_dir=output_dir,
                split_audio=False,
                to_txt=to_txt,
                to_stdout=to_stdout,
                recursive=recursive,
                flatten=flatten,
                tag_names=None,
            )
            batch_handler.run()
    except YoutubeDLError:
        # Already logged from youtube.py
        pass
    except (AudioLoadError, LoopNotFoundError) as e:
        logging.error(e)
    except Exception as e:
        logging.error(e)


@cli_main.command()
@common_path_options
@common_loop_options
@common_export_options
@click.option('--tag-names', type=str, required=True, nargs=2, help='Name of the loop metadata tags to use, e.g. --tag-names LOOP_START LOOP_END')
def tag(
    path,
    url,
    min_duration_multiplier,
    min_loop_duration,
    max_loop_duration,
    approx_loop_position,
    brute_force,
    disable_pruning,
    output_dir,
    recursive,
    flatten,
    tag_names,
):
    """Adds metadata tags of loop points to a copy of the input audio file(s)."""
    try:
        if url is not None:
            output_dir = mk_outputdir(os.getcwd(), output_dir)
            path = download_audio(url, output_dir)
        else:
            output_dir = mk_outputdir(path, output_dir)

        if os.path.isfile(path):
            with Progress(
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                console=rich_console,
                transient=True
            ) as progress:
                progress.add_task("Processing", total=None)
                export_handler = LoopExportHandler(
                    file_path=path,
                    min_duration_multiplier=min_duration_multiplier,
                    min_loop_duration=min_loop_duration,
                    max_loop_duration=max_loop_duration,
                    approx_loop_position=approx_loop_position,
                    brute_force=brute_force,
                    disable_pruning=disable_pruning,
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
                brute_force=brute_force,
                disable_pruning=disable_pruning,
                output_dir=output_dir,
                split_audio=False,
                to_txt=False,
                to_stdout=False,
                recursive=recursive,
                flatten=flatten,
                tag_names=tag_names,
            )
            batch_handler.run()
    except YoutubeDLError:
        # Already logged from youtube.py
        pass
    except (AudioLoadError, LoopNotFoundError) as e:
        logging.error(e)
    except Exception as e:
        logging.error(e)


def mk_outputdir(path: str, output_dir: Optional[str] = None) -> str:
    """Creates the output directory in the `path` provided (if it does not exists) and returns the output directory path.

    Args:
        path (str): The path of the file or directory being processed.
        output_dir (str, optional): The output directory to use. If None, will create the directory 'LooperOutput' in the path provided.

    Returns:
        str: The path to the output directory.
    """
    if os.path.isdir(path):
        default_out = os.path.join(path, "LooperOutput")
    else:
        default_out = os.path.join(os.path.dirname(path), "LooperOutput")
    output_dir_to_use = default_out if output_dir is None else output_dir

    if not os.path.exists(output_dir_to_use):
        os.mkdir(output_dir_to_use)
    return output_dir_to_use


def download_audio(url: str, output_dir: str) -> str:
    """Downloads an audio file using yt-dlp from the URL provided and returns its filepath

    Args:
        url (str): The URL of the stream to pass to yt-dlp to extract audio from
        output_dir (str): The directory path to store the downloaded audio to

    Returns:
        str: The filepath of the extracted audio
    """
    yt = YoutubeDownloader(url, output_dir)
    return yt.filepath

if __name__ == "__main__":
    cli_main()
