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
import logging
import os
import sys
import warnings
from multiprocessing import Process

from tqdm import tqdm

from .core import MusicLooper
from .argparser import ArgParser


def loop_track(filename, min_duration_multiplier):
    try:
        # Load the file
        print("Loading {}...".format(filename))

        track = MusicLooper(filename, min_duration_multiplier)

        loop_pair_list = track.find_loop_pairs()

        if len(loop_pair_list) == 0:
            logging.error(f"No suitable loop point found for '{filename}'.")
            sys.exit(1)

        loop_start = loop_pair_list[0]["loop_start"]
        loop_end = loop_pair_list[0]["loop_end"]
        score = loop_pair_list[0]["score"]

        print(
            "Playing with loop from {} back to {}; similarity: {:.1%}".format(
                track.frames_to_ftime(loop_end),
                track.frames_to_ftime(loop_start),
                score if score is not None else 0,
            )
        )
        print("(press Ctrl+C to exit)")

        track.play_looping(loop_start, loop_end)

    except (TypeError, FileNotFoundError) as e:
        logging.error("Error: {}".format(e))


if __name__ == "__main__":
    parser = ArgParser(
        prog="python -m pymusiclooper",
        description="A script for repeating music seamlessly and endlessly, by automatically finding the best loop points."
        )

    args = parser.parse_args()

    default_out = os.path.join(os.path.dirname(args.path), "looper_output")
    output_dir = args.output_dir if args.output_dir != "" else default_out
    
    if args.verbose:
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    else:
        warnings.filterwarnings("ignore")
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.ERROR)

    if not os.path.isdir(args.path) or args.verbose:
        def vprint(*args):
            for arg in args:
                print(arg,)
    else:
        vprint = lambda *args: None

    def export_handler(file_path):
        if not os.path.exists(file_path):
            raise parser.warning(f"File or directory '{os.path.abspath(args.path)}' not found")
            return

        output_path = os.path.join(output_dir, os.path.split(file_path)[1])

        try:
            track = MusicLooper(file_path, args.min_duration_multiplier)
        except TypeError as e:
            logging.warning(f"Skipping '{file_path}'. {e}")
            return

        vprint("Loaded '{}'. Analyzing...".format(file_path))

        loop_pair_list = track.find_loop_pairs()
        if not loop_pair_list:
            logging.error(f"No suitable loop point found for '{file_path}'.")
            return
        loop_start = loop_pair_list[0]["loop_start"]
        loop_end = loop_pair_list[0]["loop_end"]
        score = loop_pair_list[0]["score"]

        if args.json:
            track.export_json(loop_start, loop_end, score, output_dir=output_dir)
            vprint(
                f"Successfully exported loop points to '{output_path}.loop_points.json'"
            )
        if args.export:
            track.export(
                loop_start,
                loop_end,
                output_dir=output_dir,
                preserve_tags=args.preserve_tags,
            )
            vprint(f"Successfully exported intro/loop/outro sections to '{output_dir}'")
        vprint("")

    def batch_handler(dir_path):
        if args.n_jobs <= 0:
            raise parser.error(
                f"n_jobs must be a non-zero positive integer; n_jobs provided: {args.n_jobs}"
            )

        if args.recursive:
            files = []
            for directory, sub_dir_list, file_list in os.walk(args.path):
                for filename in file_list:
                    files.append(os.path.join(directory, filename))
        else:
            files = [
                f
                for f in os.listdir(args.path)
                if os.path.isfile(os.path.join(args.path, f))
            ]

        if len(files) == 0:
            logging.error(f"No files found in '{args.path}'")

        num_files = len(files)

        if args.n_jobs == 1:
            tqdm_files = tqdm(files)
            for file in tqdm_files:
                tqdm_files.set_description(f"Processing '{file}'")
                export_handler(file)
        else:
            processes = []
            file_idx = 0

            with tqdm(total=num_files) as pbar:
                while file_idx < num_files:
                    for pid in range(args.n_jobs):
                        p = Process(
                            target=export_handler,
                            kwargs={"file_path": files[file_idx]},
                            daemon=True,
                        )
                        processes.append(p)
                        p.start()
                        file_idx += 1
                        if file_idx >= num_files:
                            break

                    # Wait till current batch finishes
                    for process in processes:
                        process.join()
                        process.terminate()
                        pbar.update()

                    processes = []

    if args.export or args.json:
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        if os.path.isfile(args.path):
            export_handler(args.path)
        else:
            batch_handler(args.path)

    if args.play and not (args.export or args.json):
        loop_track(args.path, args.min_duration_multiplier) 
