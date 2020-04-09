#!/usr/bin/python3
# coding=utf-8
""" PyMusicLooper
    Copyright (C) 2020  Hazem Nabil

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>."""

import argparse
import os
import sys
import time
import warnings

from .core import MusicLooper

warnings.filterwarnings("ignore")


def loop_track(filename,
               min_duration_multiplier,
               loop_start=None,
               loop_end=None,
               score=None):
    try:
        runtime_start = time.time()
        # Load the file
        print("Loading {}...".format(filename))

        track = MusicLooper(filename, min_duration_multiplier)

        if loop_start is None and loop_end is None:
            loop_pair_list = track.find_loop_pairs()

            if len(loop_pair_list) == 0:
                print("No suitable loop point found.")
                sys.exit(1)

            loop_start = loop_pair_list[0]["loop_start"]
            loop_end = loop_pair_list[0]["loop_end"]
            score = loop_pair_list[0]["score"]

        runtime_end = time.time()
        total_runtime = runtime_end - runtime_start
        print("Total elapsed time (s): {:.3}".format(total_runtime))

        print(
            "Playing with loop from {} back to {}; similarity: {:.1%}".format(
                track.frames_to_ftime(loop_end),
                track.frames_to_ftime(loop_start),
                score if score is not None else 0,
            ))
        print("(press Ctrl+C to exit)")

        track.play_looping(loop_start, loop_end)

    except (TypeError, FileNotFoundError) as e:
        print("Error: {}".format(e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="python -m pymusiclooper",
        description=
        "Automatically find loop points in music files and play/export them.",
    )
    parser.add_argument("path", type=str, help="path to music file.")

    parser.add_argument(
        "-p",
        "--play",
        action="store_true",
        default=True,
        help=
        "play the song on repeat with the best discovered loop point (default).",
    )
    parser.add_argument(
        "-e",
        "--export",
        action="store_true",
        default=False,
        help="export the song into intro, loop and outro files (WAV format).",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        default=False,
        help=
        "export the loop points (in samples) to a JSON file in the song's directory.",
    )
    parser.add_argument(
        "-b",
        "--batch",
        action="store_true",
        default=False,
        help=
        "batch process all the files within the given path (usage with export args [-e] or [-j] only).",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        default=False,
        help=
        "process directories and their contents recursively (usage with [-b/--batch] only).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default=os.path.join(os.getcwd(), "looper_output"),
        help="specify a different output directory.",
    )

    def bounded_float(x):
        try:
            x = float(x)
        except ValueError:
            raise argparse.ArgumentTypeError(
                "%r not a floating-point literal" % (x, ))

        if x <= 0.0 or x >= 1.0:
            raise argparse.ArgumentTypeError(
                "%r not in range (0.0, 1.0) exclusive" % (x, ))
        return x

    parser.add_argument(
        "-m",
        "--min-duration-multiplier",
        type=bounded_float,
        default=0.35,
        help=
        "specify minimum loop duration as a multiplier of song duration (default: 0.35)",
    )

    args = parser.parse_args()

    def export_handler(file_path, output_dir):
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        output_path = os.path.join(output_dir, os.path.split(file_path)[1])

        track = MusicLooper(file_path, args.min_duration_multiplier)

        print("Loaded '{}'".format(file_path))

        loop_pair_list = track.find_loop_pairs()
        if len(loop_pair_list) == 0:
            print("No suitable loop point found.")
            return
        loop_start = loop_pair_list[0]["loop_start"]
        loop_end = loop_pair_list[0]["loop_end"]
        score = loop_pair_list[0]["score"]

        if args.json:
            track.export_json(loop_start,
                              loop_end,
                              score,
                              output_dir=output_dir)
            print(
                f"Successfully exported loop points to '{output_path}-loop_points.json'"
            )
        if args.export:
            track.export(loop_start, loop_end, output_dir=output_dir)
            print(
                f"Successfully exported intro/loop/outro sections to '{output_dir}'"
            )
        print()

    if args.batch:
        if args.recursive:
            files = []
            for directory, sub_dir_list, file_list in os.walk(args.path):
                for filename in file_list:
                    files.append(os.path.join(directory, filename))
        else:
            files = [
                f for f in os.listdir(args.path)
                if os.path.isfile(os.path.join(args.path, f))
            ]

        if len(files) == 0:
            print(f"No files found in '{args.path}'")

        for file in files:
            try:
                export_handler(file, output_dir=args.output_dir)
            except (TypeError, FileNotFoundError):
                print("Skipping: {}".format(file))

        sys.exit(0)

    if args.export or args.json:
        export_handler(args.path, output_dir=args.output_dir)

    if args.play and not (args.export or args.json or args.batch):
        loop_track(args.path, args.min_duration_multiplier)
