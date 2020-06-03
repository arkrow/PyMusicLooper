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


def loop_pairs(file_path, min_duration_multiplier):
    """
    Discovers the possible loop points of an audio file and returns a list of dicts with keys "loop_start", "loop_end" and "score"
    """
    if not os.path.exists(file_path):
        logging.warning(f"File or directory '{os.path.abspath(args.path)}' not found")
        return

    output_path = os.path.join(output_dir, os.path.split(file_path)[1])

    try:
        track = MusicLooper(file_path, min_duration_multiplier)
    except TypeError as e:
        logging.warning(f"Skipping '{file_path}'. {e}")
        return

    vprint("Loaded '{}'. Analyzing...".format(file_path))

    loop_pair_list = track.find_loop_pairs()
    if not loop_pair_list:
        logging.error(f"No suitable loop point found for '{file_path}'.")
        return

    return loop_pair_list


if __name__ == "__main__":
    parser = ArgParser(
        prog="python -m pymusiclooper",
        description="A script for repeating music seamlessly and endlessly, by automatically finding the best loop points.",
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

    def interactive_handler(loop_pair_list, file_path):
        preview_looper = MusicLooper(file_path, args.min_duration_multiplier)
        print("Discovered loop points:")
        for idx, pair in zip(range(len(loop_pair_list)), loop_pair_list):
            # import pdb; pdb.set_trace()
            start_time = preview_looper.frames_to_ftime(pair['loop_start'])
            end_time = preview_looper.frames_to_ftime(pair['loop_end'])
            score = pair['score']
            print(f"  {idx}) from {end_time} back to {start_time}; score: {score:.2%}")

        def get_user_input():
            num_input = input("Enter the number for the loop you'd like to use (append p to preview; e.g. 0p):")
            try:
                idx = 0
                preview = False
                if num_input[-1] == "p":
                    idx = int(num_input[:-1])
                    preview = True
                else:
                    idx = int(num_input)

                if idx < 0 or idx >= len(loop_pair_list):
                    print(f"Please enter a number within the range [0,{len(loop_pair_list)-1}].")
                    return get_user_input()

                if preview:
                    print(f"Previewing loop #{idx} (Press Ctrl+C to stop):")
                    loop_start = loop_pair_list[idx]["loop_start"]
                    loop_end = loop_pair_list[idx]["loop_end"]
                    offset = preview_looper.seconds_to_frames(10)
                    preview_offset = loop_end - offset if loop_end - offset > 0 else 0
                    preview_looper.play_looping(
                        loop_start, loop_end, start_from=preview_offset, adjust_for_playback=True
                    )
                    return get_user_input()
                else:
                    return idx

            except ValueError:
                print("Please enter a valid number.")
                return get_user_input()
            
            except KeyboardInterrupt:
                print("\nOperation terminated by user. Exiting.")
                sys.exit(0)

        selected_index = get_user_input()
        return selected_index

    def choose_loop_pair(loop_pair_list, file_path):
        index = 0
        if args.interactive:
            index = interactive_handler(loop_pair_list, file_path)
        loop_start = loop_pair_list[index]["loop_start"]
        loop_end = loop_pair_list[index]["loop_end"]
        score = loop_pair_list[index]["score"]
        return loop_start, loop_end, score

    def export_handler(file_path):
        loop_pair_list = loop_pairs(file_path, args.min_duration_multiplier)

        loop_start, loop_end, score = choose_loop_pair(loop_pair_list, file_path)

        track = MusicLooper(file_path, min_duration_multiplier=args.min_duration_multiplier)

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
            logging.error(
                f"n_jobs must be a non-zero positive integer; n_jobs provided: {args.n_jobs}"
            )
            return

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
        try:
            # Load the file
            print("Loading {}...".format(args.path))

            loop_pair_list = loop_pairs(args.path, args.min_duration_multiplier)
            loop_start, loop_end, score = choose_loop_pair(loop_pair_list, args.path)

            track = MusicLooper(args.path, min_duration_multiplier=args.min_duration_multiplier)

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
