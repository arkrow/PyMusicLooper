import functools
import logging
import os
import tempfile
import warnings

import rich_click as click
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
from rich.traceback import install as rich_traceback_handler
from rich_click.patch import patch as rich_click_patch
from yt_dlp.utils import YoutubeDLError

rich_click_patch()
from click_option_group import RequiredMutuallyExclusiveOptionGroup, optgroup
from click_params import URL as UrlParamType

from pymusiclooper import __version__
from pymusiclooper.console import _COMMAND_GROUPS, _OPTION_GROUPS, rich_console
from pymusiclooper.core import MusicLooper
from pymusiclooper.exceptions import AudioLoadError, LoopNotFoundError
from pymusiclooper.handler import BatchHandler, LoopExportHandler, LoopHandler
from pymusiclooper.utils import download_audio, get_outputdir, mk_outputdir
# CLI --help styling
click.rich_click.OPTION_GROUPS = _OPTION_GROUPS
click.rich_click.COMMAND_GROUPS = _COMMAND_GROUPS
click.rich_click.USE_RICH_MARKUP = True
# End CLI styling


def cli_main(kwargs):
    debug = verbose = interactive = samples = False
    
    """A program for repeating music seamlessly and endlessly, by automatically finding the best loop points."""
    print('inside cli_main')
    # Store flags in environ instead of passing them as parameters
    if debug:
        os.environ["PML_DEBUG"] = "1"
        warnings.simplefilter("default")
        rich_traceback_handler(console=rich_console, suppress=[click])
    else:
        warnings.filterwarnings("ignore")

    if verbose:
        os.environ["PML_VERBOSE"] = "1"
    if interactive:
        os.environ["PML_INTERACTIVE_MODE"] = "1"
    if samples:
        os.environ["PML_DISPLAY_SAMPLES"] = "1"

    if verbose:
        logging.basicConfig(format="%(message)s", level=logging.INFO, handlers=[RichHandler(level=logging.INFO, console=rich_console, rich_tracebacks=True, show_path=debug, show_time=False, tracebacks_suppress=[click])])
    else:
        logging.basicConfig(format="%(message)s", level=logging.ERROR, handlers=[RichHandler(level=logging.ERROR, console=rich_console, show_time=False, show_path=False)])

    return split_audio(**kwargs)
    




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
    @click.option('--approx-loop-position', type=click.FloatRange(min=0), nargs=2, default=None, help='The approximate desired loop start and loop end in seconds. [dim]([cyan]+/-2[/] second search window for each point)[/]')
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


# @cli_main.command()
@common_path_options
@common_loop_options
def play(**kwargs):
    """Play an audio file on repeat from the terminal with the best discovered loop points, or a chosen point if interactive mode is active."""
    try:
        if kwargs.get("url", None) is not None:
            kwargs["path"] = download_audio(kwargs["url"], tempfile.gettempdir())

        with Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            TimeElapsedColumn(),
            console=rich_console,
            transient=True
        ) as progress:
            progress.add_task("Processing", total=None)
            handler = LoopHandler(**kwargs)

        in_samples = "PML_DISPLAY_SAMPLES" in os.environ
        interactive_mode = "PML_INTERACTIVE_MODE" in os.environ

        chosen_loop_pair = handler.choose_loop_pair(interactive_mode=interactive_mode)

        start_time = handler.format_time(chosen_loop_pair.loop_start, in_samples=in_samples)
        end_time = handler.format_time(chosen_loop_pair.loop_end, in_samples=in_samples)

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
    except (AudioLoadError, LoopNotFoundError, Exception) as e:
        print_exception(e)


# @cli_main.command()
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
        print_exception(e)


# @cli_main.command()
@common_path_options
@common_loop_options
@common_export_options
@click.option('--format', type=click.Choice(("WAV", "FLAC", "OGG", "MP3"), case_sensitive=False), default="WAV", show_default=True, help="Audio format to use for the exported split audio files.")
def split_audio(**kwargs):
    """Split the input audio into intro, loop and outro sections."""
    print('inside split_audio')
    kwargs["split_audio"] = True
    return run_handler(**kwargs)

# @cli_main.command()
@common_path_options
@common_loop_options
@common_export_options
@click.option('--format', type=click.Choice(("WAV", "FLAC", "OGG", "MP3"), case_sensitive=False), default="MP3", show_default=True, help="Audio format to use for the output audio file.")
@click.option('--extended-length', type=float, required=True, help="Desired length of the extended looped track in seconds. [Must be longer than the audio's original length.]")
@click.option('--fade-length', type=float, default=5, show_default=True, help="Desired length of the loop fade out in seconds.")
@click.option('--disable-fade-out', is_flag=True, default=False, help="Extend the track with all its sections (intro/loop/outro) without fading out. --extended-length will be treated as an 'at least' constraint.")
def extend(**kwargs):
    """Create an extended version of the input audio by looping it to a specific length."""
    run_handler(**kwargs)


# @cli_main.command()
@common_path_options
@common_loop_options
@common_export_options
@click.option("--export-to", type=click.Choice(("STDOUT", "TXT"), case_sensitive=False), default="STDOUT", show_default=True, help="STDOUT: print the loop points of a track in samples to the terminal; TXT: export the loop points of a track in samples and append to a loop.txt file.")
@click.option("--fmt", type=click.Choice(("SAMPLES", "SECONDS", "TIME"), case_sensitive=False), default="SAMPLES", show_default=True, help="Export loop points formatted as samples (default), seconds, or time (mm:ss.sss).")
@click.option("--alt-export-top", type=int, default=0, help="Alternative export format of the top N loop points instead of the best detected/chosen point. --alt-export-top -1 to export all points.")
def export_points(**kwargs):
    """Export the best discovered or chosen loop points to a text file or to the terminal."""
    kwargs["to_stdout"] = kwargs["export_to"].upper() == "STDOUT"
    kwargs["to_txt"] = kwargs["export_to"].upper() == "TXT"
    kwargs.pop("export_to", "")

    run_handler(**kwargs)


# @cli_main.command()
@common_path_options
@common_loop_options
@common_export_options
@click.option('--tag-names', type=str, required=True, nargs=2, help='Name of the loop metadata tags to use, e.g. --tag-names LOOP_START LOOP_END')
def tag(**kwargs):
    """Adds metadata tags of loop points to a copy of the input audio file(s)."""
    run_handler(**kwargs)


def run_handler(**kwargs):
    try:
        print(kwargs)
        if kwargs.get("url", None) is not None:
            kwargs["output_dir"] = mk_outputdir(os.getcwd(), kwargs["output_dir"])
            kwargs["path"] = download_audio(kwargs["url"], kwargs["output_dir"])
        else:  
            kwargs["output_dir"] = get_outputdir(kwargs["path"], kwargs["output_dir"])

        if os.path.isfile(kwargs["path"]):
            with Progress(
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                console=rich_console,
                transient=True
            ) as progress:
                progress.add_task("Processing", total=None)
                export_handler = LoopExportHandler(**kwargs)
            # export_handler.run()
            pairs = export_handler.run_and_return_all_loop_pairs(pairs_count=kwargs['pairs_count'])
            print('First loop pairs:', pairs[0])
            return pairs
        else:
            batch_handler = BatchHandler(**kwargs)
            batch_handler.run()
    except YoutubeDLError:
        # Already logged from youtube.py
        pass
    except (AudioLoadError, LoopNotFoundError, Exception) as e:
        print_exception(e)

def print_exception(e: Exception):
    if "PML_DEBUG" in os.environ:
        rich_console.print_exception(suppress=[click])
    else:
        logging.error(e)

if __name__ == "__main__":
    cli_main()

