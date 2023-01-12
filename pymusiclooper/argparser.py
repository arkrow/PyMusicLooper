from argparse import ArgumentParser, ArgumentTypeError


class ArgParser(ArgumentParser):
    def __init__(self, *args, **kwargs):
        super(ArgParser, self).__init__(*args, **kwargs)
        self.add_argument("path", type=str, help="path to file or directory")

        play_options = self.add_argument_group("Play")
        export_options = self.add_argument_group("Export")
        batch_options = self.add_argument_group("Batch Options")
        general_options = self.add_argument_group("General Options")

        self.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            default=False,
            help="enable verbose logging output",
        )
        self.add_argument(
            "-i",
            "--interactive",
            action="store_true",
            default=False,
            help="manually preview/choose which loop to use out of the discovered loop points",
        )

        play_options.add_argument(
            "-p",
            "--play",
            action="store_true",
            default=True,
            help="play the song on repeat with the best discovered loop point (default).",
        )
        export_options.add_argument(
            "-e",
            "--export",
            action="store_true",
            default=False,
            help="export the song into intro, loop and outro files (WAV format).",
        )
        export_options.add_argument(
            "-t",
            "--txt",
            action="store_true",
            default=False,
            help="export the loop points of a track in samples and append to a loop.txt file (compatible with LoopingAudioConverter).",
        )
        export_options.add_argument(
            "--stdout",
            action="store_true",
            default=False,
            help="print the loop points of a track in samples to stdout (Standard Output)",
        )
        batch_options.add_argument(
            "-r",
            "--recursive",
            action="store_true",
            default=False,
            help="process directories and their contents recursively (has an effect only if the given path is a directory).",
        )
        batch_options.add_argument(
            "-f",
            "--flatten",
            action="store_true",
            default=False,
            help="flatten the output directory structure instead of preserving it when using the --recursive flag.",
        )
        batch_options.add_argument(
            "-n",
            "--n-jobs",
            type=int,
            default=1,
            help="number of files to batch process at a time (default: 1). WARNING: greater values result in higher memory consumption.",
        )
        general_options.add_argument(
            "-o",
            "--output-dir",
            type=str,
            default="",
            help="specify a different output directory.",
        )

        def bounded_float(x):
            try:
                x = float(x)
            except ValueError:
                raise ArgumentTypeError(
                    "%r not a floating-point literal" % (x,)
                )

            if x <= 0.0 or x >= 1.0:
                raise ArgumentTypeError(
                    "%r is not between 0.0 and 1.0" % (x,)
                )
            return x

        general_options.add_argument(
            "-m",
            "--min-duration-multiplier",
            type=bounded_float,
            default=0.35,
            help="specify minimum loop duration as a multiplier of song duration (default: 0.35)",
        )
