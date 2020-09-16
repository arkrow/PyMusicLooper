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

    try:
        track = MusicLooper(file_path, min_duration_multiplier)
    except TypeError as e:
        logging.warning(f"Skipping '{file_path}'. {e}")
        return

    vprint("Loaded '{}'. Analyzing...".format(file_path))

    loop_pair_list = track.find_loop_pairs()
    if not loop_pair_list:
        logging.error(f"No suitable loop point found for '{file_path}'.")

    return loop_pair_list


if __name__ == "__main__":
    parser = ArgParser(
        prog="python -m pymusiclooper",
        description="A script for repeating music seamlessly and endlessly, by automatically finding the best loop points.",
    )

    args = parser.parse_args()

    default_out = os.path.join(os.path.dirname(args.path), "Loops")
    output_dir = args.output_dir if args.output_dir else default_out

    if args.verbose:
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    else:
        warnings.filterwarnings("ignore")
        logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.ERROR)

    if not os.path.isdir(args.path) or args.verbose:
        def vprint(*args):
            print(*args)
    else:
        vprint = lambda *args: None

    def interactive_handler(loop_pair_list, file_path):
        preview_looper = MusicLooper(file_path, args.min_duration_multiplier)
        print("Discovered loop points:")
        for idx, pair in enumerate(loop_pair_list):
            # import pdb; pdb.set_trace()
            start_time = preview_looper.frames_to_ftime(pair['loop_start'])
            end_time = preview_looper.frames_to_ftime(pair['loop_end'])
            score = pair['score']
            dB_diff = pair['dB_diff']
            print(f"  {idx}) from {end_time} back to {start_time}; dB_diff: {dB_diff:.1f}; score: {score:.2%}")

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
                    offset = preview_looper.seconds_to_frames(5)
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

    def export_handler(file_path, output_directory=output_dir):
        loop_pair_list = loop_pairs(file_path, args.min_duration_multiplier)

        if not loop_pair_list:
            return

        loop_start, loop_end, score = choose_loop_pair(loop_pair_list, file_path)

        track = MusicLooper(file_path, min_duration_multiplier=args.min_duration_multiplier)

        if args.json:
            track.export_json(loop_start, loop_end, score, output_dir=output_directory)
            vprint(
                f"Successfully exported '{track.filename}' loop points to a json in '{output_directory}'"
            )
        if args.txt:
            track.export_txt(loop_start, loop_end, output_dir=output_directory)
            out_path =  os.path.join(output_directory, 'loop.txt')
            vprint(
                f"Successfully added '{track.filename}' loop points to '{out_path}'"
            )
        if args.export:
            track.export(
                loop_start,
                loop_end,
                output_dir=output_directory,
                preserve_tags=args.preserve_tags,
            )
            vprint(f"Successfully exported '{track.filename}' intro/loop/outro sections to '{output_directory}'")

    def batch_handler(dir_path):
        dir_path = os.path.abspath(dir_path)

        if args.n_jobs <= 0:
            logging.error(
                f"n_jobs must be a non-zero positive integer; n_jobs provided: {args.n_jobs}"
            )
            return

        if args.recursive:
            files = [
                os.path.join(directory, filename)
                for directory, sub_dir_list, file_list in os.walk(dir_path)
                for filename in file_list
            ]

        else:
            files = [
                os.path.join(dir_path, f)
                for f in os.listdir(dir_path)
                if os.path.isfile(os.path.join(dir_path, f))
            ]
        
        if not args.flatten:
            common_path = os.path.commonpath(files)
            output_dirs = [
                os.path.join(
                    os.path.abspath(output_dir),
                    os.path.dirname(os.path.relpath(file, start=common_path))
                    ) for file in files]
            for out_dir in output_dirs:
                if not os.path.isdir(out_dir):
                    os.makedirs(out_dir, exist_ok=True)

        if len(files) == 0:
            logging.error(f"No files found in '{dir_path}'")

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
                            kwargs={
                                "file_path": files[file_idx],
                                "output_directory":
                                    output_dir
                                    if args.flatten
                                    else output_dirs[file_idx]
                                },
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

    if args.export or args.json or args.txt:
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        if os.path.isfile(args.path):
            export_handler(args.path)
        else:
            batch_handler(args.path)

    if args.play and not (args.export or args.json or args.txt):
        try:
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
