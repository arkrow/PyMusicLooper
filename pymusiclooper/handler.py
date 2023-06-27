import os
import logging
import click
import sys
from multiprocessing import Process

from tqdm import tqdm
from rich.console import Console
from rich.table import Table

from .core import MusicLooper
from .analysis import LoopPair
from .exceptions import LoopNotFoundError, AudioLoadError


class LoopHandler:
    def __init__(self, file_path, min_duration_multiplier, min_loop_duration, max_loop_duration, approx_loop_position:tuple=None) -> None:
        self.approx_loop_start = approx_loop_position[0] if approx_loop_position is not None else None
        self.approx_loop_end = approx_loop_position[1] if approx_loop_position is not None else None
        self.musiclooper = MusicLooper(filepath=file_path,
                                       min_duration_multiplier=min_duration_multiplier,
                                       min_loop_duration=min_loop_duration,
                                       max_loop_duration=max_loop_duration,
                                       approx_loop_start=self.approx_loop_start,
                                       approx_loop_end=self.approx_loop_end)
        logging.info(f"Loaded '{file_path}'. Analyzing...")
        self.loop_pair_list = self.musiclooper.find_loop_pairs()
        self.interactive_mode = (os.environ.get('PML_INTERACTIVE_MODE', 'False') == 'True')
        self.in_samples = (os.environ.get('PML_DISPLAY_SAMPLES', 'False') == 'True')


    def get_all_loop_pairs(self) -> list[LoopPair]:
        """
        Returns the discovered loop points of an audio file as a list of LoopPair objects
        """
        return self.loop_pair_list

    def get_best_loop_pair(self) -> LoopPair:
        """
        Returns the *best* discovered loop point of an audio file as a LoopPair object
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

        return self.loop_pair_list[index]

    def interactive_handler(self, show_top=25):
        preview_looper = self.musiclooper
        total_candidates = len(self.loop_pair_list)
        more_prompt_message = "\nEnter 'more' to display additional loop points, 'all' to display all of them, or 'reset' to display the default amount." if show_top < total_candidates else ""
        click.echo()
        table = Table(title=f"Discovered loop points ({min(show_top, total_candidates)}/{total_candidates} displayed)", caption=more_prompt_message)
        table.add_column("Index", justify="right", style="cyan", no_wrap=True)
        table.add_column("Loop Start", style="magenta")
        table.add_column("Loop End", style="green")
        table.add_column("Note Distance", style="yellow")
        table.add_column("Loudness Difference (dB)", style="blue")
        
        table.add_column("Score", justify="right", style="red")

        for idx, pair in enumerate(self.loop_pair_list[:show_top]):
            start_time = preview_looper.frames_to_samples(pair.loop_start) if self.in_samples else preview_looper.frames_to_ftime(pair.loop_start) 
            end_time = preview_looper.frames_to_samples(pair.loop_end) if self.in_samples else preview_looper.frames_to_ftime(pair.loop_end) 
            score = pair.score
            loudness_difference = pair.loudness_difference
            note_distance = pair.note_distance
            table.add_row(str(idx), str(start_time), str(end_time), f"{note_distance:.4f}", f"{loudness_difference:.4f}", f"{score:.2%}")
        
        console = Console()
        console.print(table)
        click.echo()

        def get_user_input():
            try:
                num_input = input("Enter the index number for the loop you'd like to use (append p to preview; e.g. 0p):")
                idx = 0
                preview = False

                if num_input == 'more':
                    self.interactive_handler(show_top=show_top*2)
                if num_input == 'all':
                    self.interactive_handler(show_top=total_candidates)
                if num_input == 'reset':
                    self.interactive_handler()

                if num_input[-1] == "p":
                    idx = int(num_input[:-1])
                    preview = True
                else:
                    idx = int(num_input)

                if not 0 <= idx < len(self.loop_pair_list):
                    raise IndexError

                if preview:
                    click.echo(f"Previewing loop #{idx} (Press Ctrl+C to stop looping):")
                    loop_start = self.loop_pair_list[idx].loop_start
                    loop_end = self.loop_pair_list[idx].loop_end
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

        try:
            selected_index = get_user_input()
            
            if selected_index is None:
                click.echo('Please select a valid number.')
                return get_user_input()

            return selected_index
        except KeyboardInterrupt:
            click.echo("\nOperation terminated by user. Exiting.")
            sys.exit()


class LoopExportHandler(LoopHandler):
    def __init__(self,
                 file_path,
                 min_duration_multiplier,
                 min_loop_duration,
                 max_loop_duration,
                 output_dir,
                 approx_loop_position:tuple=None,
                 split_audio=True,
                 split_audio_format="WAV",
                 to_txt=False,
                 to_stdout=False,
                 tag_names:tuple[str, str]=None,
                 batch_mode=False,
                 multiprocess=False) -> None:
        super().__init__(file_path, min_duration_multiplier, min_loop_duration, max_loop_duration, approx_loop_position)
        self.output_directory = output_dir
        self.split_audio = split_audio
        self.split_audio_format = split_audio_format
        self.to_txt = to_txt
        self.to_stdout = to_stdout
        self.tag_names = tag_names
        self.batch_mode = batch_mode

        # Disable thread-unsafe options if files are being processed concurrently
        if multiprocess:
            self.interactive_mode = False
            self.in_samples = False
            self.to_txt = False
            self.to_stdout = False 

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

        chosen_loop_pair = self.choose_loop_pair(self.interactive_mode)
        loop_start = chosen_loop_pair.loop_start
        loop_end = chosen_loop_pair.loop_end
        score = chosen_loop_pair.score

        music_looper = self.get_musiclooper_obj()

        if self.tag_names is not None:
            loop_start_tag, loop_end_tag = self.tag_names
            music_looper.export_tags(loop_start, loop_end, loop_start_tag, loop_end_tag, output_dir=self.output_directory)

            loop_start_samples, loop_end_samples = music_looper.frames_to_samples(loop_start), music_looper.frames_to_samples(loop_end)
            
            message = f"Exported {loop_start_tag}:{loop_start_samples} and {loop_end_tag}:{loop_end_samples} to a copy in {self.output_directory}"
            if self.batch_mode:
                logging.info(message)
            else:
                click.echo(message)

        if self.to_stdout:
            loop_start_samples = music_looper.frames_to_samples(loop_start)
            loop_end_samples = music_looper.frames_to_samples(loop_end)
            click.echo(f"\nLoop points for [{music_looper.filename}]:\nLOOP_START: {loop_start_samples}\nLOOP_END: {loop_end_samples}\n")
        if self.to_txt:
            music_looper.export_txt(loop_start, loop_end, output_dir=self.output_directory)
            out_path = os.path.join(self.output_directory, 'loop.txt')
            message = f"Successfully added '{music_looper.filename}' loop points to '{out_path}'"
            if self.batch_mode:
                logging.info(message)
            else:
                click.echo(message)
        if self.split_audio:
            try:
                music_looper.export(
                    loop_start,
                    loop_end,
                    format=self.split_audio_format,
                    output_dir=self.output_directory
                )
                message = f"Successfully exported '{music_looper.filename}' intro/loop/outro sections to '{self.output_directory}'"
                if self.batch_mode:
                    logging.info(message)
                else:
                    click.echo(message)
            # Usually: unknown file format specified; raised by soundfile
            except ValueError as e:
                logging.error(e)

class BatchHandler:
    def __init__(self,
                 directory_path,
                 min_duration_multiplier,
                 min_loop_duration,
                 max_loop_duration,
                 output_dir,
                 split_audio,
                 split_audio_format="WAV",
                 to_txt=False,
                 to_stdout=False,
                 recursive=False,
                 flatten=False,
                 n_jobs=1,
                 tag_names:tuple[str, str]=None) -> None:
        self.directory_path = os.path.abspath(directory_path)
        self.min_duration_multiplier = min_duration_multiplier
        self.min_loop_duration = min_loop_duration
        self.max_loop_duration = max_loop_duration
        self.output_directory = output_dir
        self.split_audio = split_audio
        self.split_audio_format = split_audio_format
        self.to_txt = to_txt
        self.to_stdout = to_stdout
        self.recursive = recursive
        self.flatten = flatten
        self.n_jobs = max(n_jobs, 1)
        self.tag_names = tag_names

    def run(self):
        files = self.get_files_in_directory(self.directory_path, recursive=self.recursive)
        
        output_dirs = None if self.flatten else self.clone_file_tree_structure(files, self.output_directory)

        if not files:
            logging.error(f"No files found in '{self.directory_path}'")
            return

        if self.n_jobs == 1:
            tqdm_files = tqdm(files)
            for file_idx, file in enumerate(tqdm_files):
                tqdm_files.set_description(f"Processing '{file}'")
                self._batch_export_helper(
                    file_path=file,
                    min_duration_multiplier=self.min_duration_multiplier,
                    min_loop_duration=self.min_loop_duration,
                    max_loop_duration=self.max_loop_duration,
                    split_audio_format=self.split_audio_format,
                    output_dir=self.output_directory if self.flatten else output_dirs[file_idx],
                    split_audio=self.split_audio,
                    to_txt=self.to_txt,
                    to_stdout=self.to_stdout,
                    tag_names=self.tag_names)
        else:
            # Note: some arguments are disabled due to inherent incompatibility with the current multiprocessing implementation
            self._batch_multiprocess(files, output_dirs)

    def _batch_multiprocess(self, files, output_dirs):
        processes = []
        num_files = len(files)
        file_idx = 0

        with tqdm(total=num_files) as pbar:
            while file_idx < num_files:
                for _ in range(self.n_jobs):
                    p = Process(
                            target=self._batch_export_helper,
                            kwargs={
                                "file_path": files[file_idx],
                                "output_dir":
                                    self.output_directory
                                    if self.flatten
                                    else output_dirs[file_idx],
                                "min_duration_multiplier": self.min_duration_multiplier,
                                "min_loop_duration": self.min_loop_duration,
                                "max_loop_duration": self.max_loop_duration,
                                "split_audio": self.split_audio,
                                "split_audio_format": self.split_audio_format,
                                "to_txt": False,
                                "to_stdout": False,
                                "tag_names":self.tag_names,
                                "multiprocess": True,
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
    def _batch_export_helper(file_path, min_duration_multiplier, min_loop_duration, max_loop_duration, output_dir, split_audio, split_audio_format, to_txt, to_stdout, tag_names, multiprocess=False):
            export_handler = LoopExportHandler(file_path=file_path,
                                           min_duration_multiplier=min_duration_multiplier,
                                           min_loop_duration=min_loop_duration,
                                           max_loop_duration=max_loop_duration,
                                           output_dir=output_dir,
                                           split_audio=split_audio,
                                           split_audio_format=split_audio_format,
                                           to_txt=to_txt,
                                           to_stdout=to_stdout,
                                           tag_names=tag_names,
                                           batch_mode=True,
                                           multiprocess=multiprocess)
            export_handler.run()
