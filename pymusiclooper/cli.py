import click
import logging
import os
import warnings

from pymusiclooper import __version__

from .handler import CliLoopHandler, ExportHandler, BatchHandler


@click.group("pymusiclooper")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enables verbose logging output.")
@click.option("--interactive", "-i", is_flag=True, default=False, help="Enables interactive mode to manually preview/choose the desired loop point.")
@click.version_option(__version__, prog_name="pymusiclooper")
@click.pass_context
def cli_main(ctx, verbose, interactive):
    """A program for repeating music seamlessly and endlessly, by automatically finding the best loop points."""
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose
    ctx.obj['INTERACTIVE'] = interactive
    if verbose:
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    else:
        warnings.filterwarnings("ignore")
        os.environ["PYTHONWARNINGS"] = "ignore" # to suppress warnings in batch mode's subprocesses
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.ERROR)

@cli_main.command()
@click.option('--path', type=click.Path(exists=True), required=True, help='path to audio file')
@click.option('--min-duration-multiplier', type=float, default=0.35)
@click.pass_context
def play(ctx, path, min_duration_multiplier):
    """Play an audio file on repeat from the terminal with the best discovered loop point (default), or a chosen point if interactive mode is active."""
    try:
        handler = CliLoopHandler(path, min_duration_multiplier)
        loop_start, loop_end, score = handler.choose_loop_pair(interactive_mode=ctx.obj['INTERACTIVE'])

        looper = handler.get_musiclooper_obj()

        click.echo(
            "Playing with loop from {} back to {}; similarity: {:.1%}".format(
                looper.frames_to_ftime(loop_end),
                looper.frames_to_ftime(loop_start),
                score if score is not None else 'unavailable',
            )
        )
        print("(press Ctrl+C to stop looping.)")

        handler.play_looping(loop_start, loop_end)

    except Exception as e:
        logging.error(e)
        return

@cli_main.command()
@click.option('--path', type=click.Path(exists=True), required=True, help='path to audio file or directory')
@click.option('--min-duration-multiplier', type=click.FloatRange(min=0.0, max=1.0), default=0.35, help="specify minimum loop duration as a multiplier of song duration (default: 0.35)")
@click.option('--output-dir', '-o', type=click.Path(exists=False, writable=True, file_okay=False), help="specify the output directory for exports (defaults to a new 'Loops' folder in the audio file's directory).")
@click.option("--to-txt", "-t", is_flag=True, default=False, help="export the loop points of a track in samples and append to a loop.txt file (compatible with LoopingAudioConverter).")
@click.option("--to-stdout", is_flag=True, default=False, help="print the loop points of a track in samples to stdout (Standard Output).")
@click.option("--samples", is_flag=True, default=False, help="Display all loop points in sample units instead of the default mm:ss.SSS format.")
@click.option("--recursive", "-r", is_flag=True, default=False, help="process directories and their contents recursively (has an effect only if the given path is a directory).")
@click.option("--flatten", "-f", is_flag=True, default=False, help="flatten the output directory structure instead of preserving it when using the --recursive flag.")
@click.option('--n-jobs', '-n', type=click.IntRange(min=1), default=1, help="number of files to batch process at a time (default: 1). WARNING: greater values result in higher memory consumption.")
@click.pass_context
def export(ctx, path, min_duration_multiplier, output_dir, to_txt, to_stdout, samples, recursive, flatten, n_jobs):
    """Export the audio into intro, loop and outro files (WAV format, default)"""
    default_out = os.path.join(os.path.dirname(path), "Loops")
    output_dir = output_dir if output_dir is not None else default_out

    interactive_mode = ctx.obj['INTERACTIVE']

    if not os.path.exists(output_dir) and not to_stdout:
        os.mkdir(output_dir)

    if os.path.isfile(path):
        export_handler = ExportHandler(path, min_duration_multiplier, output_dir, to_txt, to_stdout, samples, interactive_mode)
        export_handler.run()
    else:
        batch_handler = BatchHandler(path, min_duration_multiplier, output_dir, to_txt, to_stdout, samples, recursive, flatten, n_jobs, interactive_mode)
        batch_handler.run()

if __name__ == "__main__":
    cli_main()
