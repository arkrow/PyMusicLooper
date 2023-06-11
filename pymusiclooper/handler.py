from multiprocessing import Process
import os
from .core import MusicLooper
from .exceptions import LoopNotFoundError, AudioLoadError
import logging
from tqdm import tqdm
from collections import namedtuple
import click
import sys

class CliLoopHandler:
    def __init__(self, file_path, min_duration_multiplier) -> None:
        self.musiclooper = MusicLooper(file_path, min_duration_multiplier)
        logging.info(f"Loaded '{file_path}'. Analyzing...")
        self.loop_pair_list = self.musiclooper.find_loop_pairs()

    def get_all_loop_pairs(self):
        """
        Returns the discovered loop points of an audio file as a list of dicts with keys "loop_start", "loop_end" and "score"
        """
        return self.loop_pair_list

    def get_best_loop_pair(self):
        """
        Returns the *best* discovered loop point of an audio file as a namedtuple with keys "loop_start", "loop_end" and "score"
        """
        return self._return_loop_pair_score_tuple(0)
    
    def get_musiclooper_obj(self):
        return self.musiclooper
    
    def play_looping(self, loop_start, loop_end):
        self.musiclooper.play_looping(loop_start, loop_end)

    def choose_loop_pair(self, interactive_mode=False):
        index = 0
        if self.loop_pair_list and interactive_mode:
            index = self.interactive_handler()

        return self._return_loop_pair_score_tuple(index)

    def _return_loop_pair_score_tuple(self, index):
        loop_pairs_tuple = namedtuple('LoopPair', ['loop_start', 'loop_end', 'score'])
        loop_start = self.loop_pair_list[index]['loop_start']
        loop_end = self.loop_pair_list[index]['loop_end']
        score = self.loop_pair_list[index]['score']
        return loop_pairs_tuple(loop_start, loop_end, score)

    def interactive_handler(self, verbose=False):
        preview_looper = self.musiclooper
        click.echo("Discovered loop points:")
        for idx, pair in enumerate(self.loop_pair_list):
            start_time = preview_looper.frames_to_ftime(pair['loop_start'])
            end_time = preview_looper.frames_to_ftime(pair['loop_end'])
            score = pair['score']
            dB_diff = pair['dB_diff']
            dist = pair['dist']
            if verbose:
                click.echo(f"  {idx}) from {end_time} back to {start_time}; dist: {dist:.4f} ; dB_diff: {dB_diff:.4f}; score: {score:.4%}")
            else:
                click.echo(f"  {idx}) from {end_time} back to {start_time}; score: {score:.2%}")

        def get_user_input():
            try:
                num_input = input("Enter the number for the loop you'd like to use (append p to preview; e.g. 0p):")
                idx = 0
                preview = False

                if num_input[-1] == "p":
                    idx = int(num_input[:-1])
                    preview = True
                else:
                    idx = int(num_input)

                if not 0 <= idx < len(self.loop_pair_list):
                    raise IndexError

                if preview:
                    click.echo(f"Previewing loop #{idx} (Press Ctrl+C to stop looping):")
                    loop_start = self.loop_pair_list[idx]["loop_start"]
                    loop_end = self.loop_pair_list[idx]["loop_end"]
                    offset = preview_looper.seconds_to_frames(5) # start preview 5 seconds before the looping point 
                    preview_offset = loop_end - offset if loop_end - offset > 0 else 0
                    preview_looper.play_looping(
                        loop_start, loop_end, start_from=preview_offset
                    )
                    return get_user_input()
                else:
                    return idx

            except (ValueError, IndexError):
                click.echo(f"Please enter a number within the range [0,{len(self.loop_pair_list)-1}].")
                return get_user_input()

            except KeyboardInterrupt:
                click.echo("\nOperation terminated by user. Exiting.")
                sys.exit()
            except Exception as e:
                click.echo(f"An unexpected error has occured.\n{e}")

        selected_index = get_user_input()
        
        if selected_index is None:
            click.echo('Please select a valid number.')
            return get_user_input()
        
        return selected_index
    
class ExportHandler(CliLoopHandler):
    def __init__(self, file_path, min_duration_multiplier, output_dir, to_txt, to_stdout, samples, interactive_mode, batch_mode=False) -> None:
        super().__init__(file_path, min_duration_multiplier)
        self.output_directory = output_dir
        self.to_txt = to_txt
        self.to_stdout = to_stdout
        self.samples = samples
        self.interactive_mode = interactive_mode
        self.batch_mode = batch_mode
    
    def run(self):
        try:
            self.loop_pair_list = self.get_all_loop_pairs()
        except (LoopNotFoundError, AudioLoadError, FileNotFoundError) as e:
            logging.error(e)
            return
        except TypeError as e:
            logging.error(f"Skipping '{self.file_path}'. {e}")
            return
        except Exception as e:
            logging.error(e)
            return

        loop_start, loop_end, score = self.choose_loop_pair(self.interactive_mode)

        track = self.get_musiclooper_obj()

        if self.to_stdout:
            loop_start_samples = track.frames_to_samples(loop_start)
            loop_end_samples = track.frames_to_samples(loop_end)
            click.echo(f"{track.filename}::\nLOOP_START: {loop_start_samples}\nLOOP_END:{loop_end_samples}")
        if self.to_txt:
            track.export_txt(loop_start, loop_end, output_dir=self.output_directory)
            out_path = os.path.join(self.output_directory, 'loop.txt')
            message = f"Successfully added '{track.filename}' loop points to '{out_path}'"
            if self.batch_mode:
                logging.info(message)
            else:
                click.echo(message)
        if not (self.to_stdout or self.to_txt):
            track.export(
                loop_start,
                loop_end,
                output_dir=self.output_directory
            )
            message = f"Successfully exported '{track.filename}' intro/loop/outro sections to '{self.output_directory}'"
            if self.batch_mode:
                logging.info(message)
            else:
                click.echo(message)

class BatchHandler:
    def __init__(self, directory_path, min_duration_multiplier, output_dir, to_txt, to_stdout, samples, recursive, flatten, n_jobs, interactive_mode) -> None:
        self.directory_path = os.path.abspath(directory_path)
        self.min_duration_multiplier = min_duration_multiplier
        self.output_directory = output_dir
        self.to_txt = to_txt
        self.to_stdout = to_stdout
        self.samples = samples
        self.recursive = recursive
        self.flatten = flatten
        self.n_jobs = max(n_jobs, 1)
        self.interactive_mode = interactive_mode

    def run(self):
        files = self.get_files_in_directory(self.directory_path, recursive=self.recursive)

        if not self.flatten:
            output_dirs = self.clone_file_tree_structure(files, self.output_directory)

        if not files:
            logging.error(f"No files found in '{self.directory_path}'")
            return

        if self.n_jobs == 1:
            tqdm_files = tqdm(files)
            for file_idx, file in enumerate(tqdm_files):
                tqdm_files.set_description(f"Processing '{file}'")
                self.export(
                    file,
                    self.min_duration_multiplier,
                    self.output_directory if self.flatten else output_dirs[file_idx],
                    self.to_txt,
                    self.to_stdout,
                    self.samples,
                    self.interactive_mode
                )
        else:
            # Note: some arguments are disabled due to inherent incompatibility with the current multiprocessing implementation
            self._batch_multiprocess(files, output_dirs, processes=[], file_idx=0, num_files=len(files))

    def _batch_multiprocess(self, files, output_dirs, processes, file_idx, num_files):
        with tqdm(total=num_files) as pbar:
            while file_idx < num_files:
                for pid in range(self.n_jobs):
                    p = Process(
                            target=self.export,
                            kwargs={
                                "path": files[file_idx],
                                "output_directory":
                                    self.output_directory
                                    if self.flatten
                                    else output_dirs[file_idx],
                                "min_duration_multiplier": self.min_duration_multiplier,
                                "to_txt": False,
                                "to_stdout": False,
                                "samples": False,
                                "interactive_mode": False
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

    @staticmethod
    def clone_file_tree_structure(in_files, output_directory):
        common_path = os.path.commonpath(in_files)
        output_dirs = [
                os.path.join(
                    os.path.abspath(output_directory),
                    os.path.dirname(os.path.relpath(file, start=common_path))
                    ) for file in in_files]
        for out_dir in output_dirs:
            if not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)
        return output_dirs

    @staticmethod
    def get_files_in_directory(dir_path, recursive=False):
        return (
            [
                os.path.join(directory, filename)
                for directory, sub_dir_list, file_list in os.walk(dir_path)
                for filename in file_list
            ]
            if recursive
            else [
                os.path.join(dir_path, f)
                for f in os.listdir(dir_path)
                if os.path.isfile(os.path.join(dir_path, f))
            ]
        )
    
    @staticmethod
    def export(path, min_duration_multiplier, output_directory, to_txt, to_stdout, samples, interactive_mode):
            export_handler = ExportHandler(path, min_duration_multiplier, output_directory, to_txt, to_stdout, samples, interactive_mode, batch_mode=True)
            export_handler.run()