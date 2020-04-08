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
import json
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

            track.cache_loop_points(loop_start, loop_end, score)

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
    parser.add_argument("path",
                        type=str,
                        nargs="?",
                        help="path to music file.")

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
        "specify minimum loop duration as a multiplier of song duration (default: 0.35); use with --skip-cache.",
    )
    parser.add_argument(
        "--skip-cache",
        action="store_true",
        default=False,
        help="skip loading cached loop points.",
    )
    parser.add_argument(
        "--purge-cache",
        action="store_true",
        default=False,
        help="purges all cached loop points and exits.",
    )

    args = parser.parse_args()

    cached_loop_start = None
    cached_loop_end = None
    cached_score = None

    dirpath = os.path.dirname(os.path.realpath(__file__))
    cache_path = os.path.join(dirpath, "cache.json")

    if args.purge_cache and os.path.exists(cache_path):
        os.remove(cache_path)
        print("Cache purged.")
        sys.exit(0)

    # Remaining options need a path
    if args.path is None:
        parser.error("missing argument: path.")

    if not args.skip_cache and os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as file:
                cache = json.load(file)
                full_path = os.path.abspath(args.path)
                if full_path in cache:
                    cached_loop_start = cache[full_path]["loop_start"]
                    cached_loop_end = cache[full_path]["loop_end"]
                    cached_score = cache[full_path]["score"]
        except Exception:
            pass

    if args.export or args.json:
        track = MusicLooper(args.path, args.min_duration_multiplier)

        if cached_loop_start is not None and cached_loop_end is not None:
            if args.json:
                track.export_json(cached_loop_start, cached_loop_end,
                                  cached_score)
            if args.export:
                track.export(cached_loop_start, cached_loop_end)
            sys.exit(0)

        loop_pair_list = track.find_loop_pairs()

        if len(loop_pair_list) == 0:
            print("No suitable loop point found.")
            sys.exit(1)

        loop_start = loop_pair_list[0]["loop_start"]
        loop_end = loop_pair_list[0]["loop_end"]
        score = loop_pair_list[0]["score"]

        track.cache_loop_points(loop_start, loop_end, score)

        if args.json:
            track.export_json(loop_start, loop_end, score)
            print("Successfully exported loop points to {}".format(
                os.path.dirname(args.path)))

        if args.export:
            track.export(loop_start, loop_end, score)
            print("Successfully exported intro/loop/outro parts to {}".format(
                os.path.dirname(args.path)))

    elif args.play:
        loop_track(
            args.path,
            args.min_duration_multiplier,
            loop_start=cached_loop_start,
            loop_end=cached_loop_end,
            score=cached_score,
        )
