from argparse import ArgumentParser
class ArgParser(ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_argument("path", type=str, help="path to music file.")

        play_options = self.add_argument_group("Play")
        export_options = self.add_argument_group("Export")
        parameter_options = self.add_argument_group("Parameter adjustment")

        self.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            default=False,
            help="enable verbose logging output",
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
            "--preserve-tags",
            action="store_true",
            default=False,
            help="export with the track's original tags.",
        )
        export_options.add_argument(
            "-j",
            "--json",
            action="store_true",
            default=False,
            help="export the loop points (in samples) to a JSON file in the song's directory.",
        )
        export_options.add_argument(
            "-r",
            "--recursive",
            action="store_true",
            default=False,
            help="process directories and their contents recursively (usage with [-b/--batch] only).",
        )
        export_options.add_argument(
            "-n",
            "--n-jobs",
            type=int,
            default=1,
            help="number of parallel jobs to use for batch processing; specify -1 to use all cores (default: 1). WARNING: changing the value will also result in higher memory consumption.",
        )
        parameter_options.add_argument(
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
                raise argparse.ArgumentTypeError("%r not a floating-point literal" % (x,))

            if x <= 0.0 or x >= 1.0:
                raise argparse.ArgumentTypeError(
                    "%r not in range (0.0, 1.0) exclusive" % (x,)
                )
            return x

        parameter_options.add_argument(
            "-m",
            "--min-duration-multiplier",
            type=bounded_float,
            default=0.35,
            help="specify minimum loop duration as a multiplier of song duration (default: 0.35)",
        )