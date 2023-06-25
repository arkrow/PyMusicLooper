import functools
import logging
import os
import warnings

import rich_click as click

from . import __version__
from .handler import LoopHandler, LoopExportHandler, BatchHandler

# CLI --help styling
_basic_options = ["--path"]
_loop_options = ["--min-duration-multiplier", "--min-loop-duration", "--max-loop-duration"]
_export_options = ["--output-dir"]
_batch_options = ["--recursive", "--flatten", "--n-jobs"]

def _option_groups(additional_basic_options: list[str]=None):
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
    "pymusiclooper tag": _option_groups(['--tag-names']),
    "pymusiclooper export-loop-points": _option_groups(['--export-to']),
}

# End CLI styling

@click.group("pymusiclooper")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enables verbose logging output.")
@click.option("--interactive", "-i", is_flag=True, default=False, help="Enables interactive mode to manually preview/choose the desired loop point.")
@click.option("--in-samples", "-s", is_flag=True, default=False, help="Display all loop points in interactive mode in sample points instead of the default mm:ss.sss format.") 
@click.version_option(__version__, prog_name="pymusiclooper")
def cli_main(verbose, interactive, in_samples):
    """A program for repeating music seamlessly and endlessly, by automatically finding the best loop points."""
    # Store flags in environ instead of passing them as parameters
    os.environ['PML_VERBOSE'] = str(int(verbose))
    os.environ['PML_INTERACTIVE_MODE'] = str(int(interactive))
    os.environ['PML_DISPLAY_SAMPLES'] = str(int(in_samples))


    warnings.filterwarnings("ignore")
    os.environ["PYTHONWARNINGS"] = "ignore" # to suppress warnings in batch mode's subprocesses

    if verbose:
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    else:
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.ERROR)


def common_loop_options(f):
    @click.option('--path', type=click.Path(exists=True), required=True, help='path to audio file (or directory if batch processing)')
    @click.option('--min-duration-multiplier', type=click.FloatRange(min=0.0, max=1.0), default=0.35, show_default=True, help="specify minimum loop duration as a multiplier of the audio track's duration")
    @click.option('--min-loop-duration', type=int, default=None, help='specify the minimum loop duration in seconds (Note: overrides the --min-duration-multiplier option if specified)')
    @click.option('--max-loop-duration', type=int, default=None, help='specify the maximum loop duration in seconds')   
    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper_common_options


def common_export_options(f):
    @click.option('--output-dir', '-o', type=click.Path(exists=False, writable=True, file_okay=False), help="specify the output directory for exports (defaults to a new 'Loops' folder in the audio file's directory).")
    @click.option("--recursive", "-r", is_flag=True, default=False, help="process directories and their contents recursively (has an effect only if the given path is a directory).")
    @click.option("--flatten", "-f", is_flag=True, default=False, help="flatten the output directory structure instead of preserving it when using the --recursive flag (note: files with identical filenames are silently overwritten).")
    @functools.wraps(f)
    def wrapper_common_options(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper_common_options


@cli_main.command()
@common_loop_options
def play(path, min_duration_multiplier, min_loop_duration, max_loop_duration):
    """Play an audio file on repeat from the terminal with the best discovered loop points (default), or a chosen point if interactive mode is active."""
    try:
        in_samples = bool(os.environ.get('PML_DISPLAY_SAMPLES', False))
        handler = LoopHandler(file_path=path,
                              min_duration_multiplier=min_duration_multiplier,
                              min_loop_duration=min_loop_duration,
                              max_loop_duration=max_loop_duration)
        interactive_mode = bool(os.environ.get('PML_INTERACTIVE_MODE', False))
        chosen_loop_pair = handler.choose_loop_pair(interactive_mode=interactive_mode)

        looper = handler.get_musiclooper_obj()

        start_time = looper.frames_to_samples(chosen_loop_pair.loop_start) if in_samples else looper.frames_to_ftime(chosen_loop_pair.loop_start) 
        end_time = looper.frames_to_samples(chosen_loop_pair.loop_end) if in_samples else looper.frames_to_ftime(chosen_loop_pair.loop_end) 

        click.echo(
            "Playing with looping active from {} back to {}; similarity: {:.1%}".format(
                end_time,
                start_time,
                chosen_loop_pair.score if chosen_loop_pair.score is not None else 'unavailable',
            )
        )
        click.echo("(press Ctrl+C to stop looping.)")

        handler.play_looping(chosen_loop_pair.loop_start, chosen_loop_pair.loop_end)

    except Exception as e:
        logging.error(e)
        return


@cli_main.command()
@common_loop_options
@common_export_options
@click.option('--n-jobs', '-n', type=click.IntRange(min=1), default=1, show_default=True, help="number of files to batch process at a time. WARNING: greater values result in higher memory consumption.")
def split_audio(path, min_duration_multiplier, min_loop_duration, max_loop_duration, output_dir, recursive, flatten, n_jobs):
    """Split the input audio into intro, loop and outro sections (WAV format)"""
    default_out = os.path.join(os.path.dirname(path), "Loops")
    output_dir = output_dir if output_dir is not None else default_out

    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    if os.path.isfile(path):
        export_handler = LoopExportHandler(file_path=path,
                                           min_duration_multiplier=min_duration_multiplier,
                                           min_loop_duration=min_loop_duration,
                                           max_loop_duration=max_loop_duration,
                                           output_dir=output_dir,
                                           split_audio=True,
                                           to_txt=False,
                                           to_stdout=False,
                                           tag_names=None)
        export_handler.run()
    else:
        batch_handler = BatchHandler(directory_path=path,
                                     min_duration_multiplier=min_duration_multiplier,
                                     min_loop_duration=min_loop_duration,
                                     max_loop_duration=max_loop_duration,
                                     output_dir=output_dir,
                                     split_audio=True,
                                     to_txt=False,
                                     to_stdout=False,
                                     recursive=recursive,
                                     flatten=flatten,
                                     n_jobs=n_jobs,
                                     tag_names=None)
        batch_handler.run()


@cli_main.command()
@common_loop_options
@common_export_options
@click.option("--export-to", type=click.Choice(('STDOUT', 'TXT'), case_sensitive=False), default="STDOUT", required=True, show_default=True, help="STDOUT: prints the loop points of a track in samples to the terminal's stdout (OR) TXT: export the loop points of a track in samples and append to a loop.txt file (compatible with LoopingAudioConverter).")
def export_loop_points(path, min_duration_multiplier, min_loop_duration, max_loop_duration, output_dir, recursive, flatten, export_to):
    """Export the best discovered or chosen loop points to a text file or to the terminal (stdout)"""

    to_stdout = export_to.upper() == 'STDOUT'
    to_txt = export_to.upper() == 'TXT'

    default_out = os.path.join(os.path.dirname(path), "Loops")
    output_dir = output_dir if output_dir is not None else default_out

    if not os.path.exists(output_dir) and to_txt:
        os.mkdir(output_dir)

    if os.path.isfile(path):
        export_handler = LoopExportHandler(file_path=path,
                                           min_duration_multiplier=min_duration_multiplier,
                                           min_loop_duration=min_loop_duration,
                                           max_loop_duration=max_loop_duration,
                                           output_dir=output_dir,
                                           split_audio=False,
                                           to_txt=to_txt,
                                           to_stdout=to_stdout,
                                           tag_names=None)
        export_handler.run()
    else:
        # Disable multiprocessing until a thread-safe multiprocessing queue is implemented 
        n_jobs = 1

        batch_handler = BatchHandler(directory_path=path,
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
                                     tag_names=None)
        batch_handler.run()


@cli_main.command()
@common_loop_options
@common_export_options
@click.option('--n-jobs', '-n', type=click.IntRange(min=1), default=1, show_default=True, help="number of files to batch process at a time. WARNING: greater values result in higher memory consumption.")
@click.option('--tag-names', type=str, required=True, nargs=2, help='the name to use for the metadata tags, e.g. --tag-names LOOP_START LOOP_END')
def tag(path, min_duration_multiplier, min_loop_duration, max_loop_duration, output_dir, recursive, flatten, n_jobs, tag_names):
    """Adds metadata tags of loop points to a copy of the input audio file(s)"""
    default_out = os.path.join(os.path.dirname(path), "Loops")
    output_dir = output_dir if output_dir is not None else default_out

    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    if os.path.isfile(path):
        export_handler = LoopExportHandler(file_path=path,
                                       min_duration_multiplier=min_duration_multiplier,
                                       min_loop_duration=min_loop_duration,
                                       max_loop_duration=max_loop_duration,
                                       output_dir=output_dir,
                                       split_audio=False,
                                       to_txt=False,
                                       to_stdout=False,
                                       tag_names=tag_names)
        export_handler.run()
    else:
        batch_handler = BatchHandler(directory_path=path,
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
                                     tag_names=tag_names)
        batch_handler.run()


if __name__ == "__main__":
    cli_main()
