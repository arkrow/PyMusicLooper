import logging
import os
import sys
from typing import List, Tuple

from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn
from rich.table import Table

from .analysis import LoopPair
from .console import rich_console
from .core import MusicLooper
from .exceptions import AudioLoadError, LoopNotFoundError


class LoopHandler:
    def __init__(
        self,
        file_path,
        min_duration_multiplier,
        min_loop_duration,
        max_loop_duration,
        approx_loop_position: tuple = None,
        brute_force: bool = False,
        disable_pruning: bool = False,
    ):
        if approx_loop_position is not None:
            self.approx_loop_start = approx_loop_position[0]
            self.approx_loop_end = approx_loop_position[1]
        else:
            self.approx_loop_start = None
            self.approx_loop_end = None

        self.musiclooper = MusicLooper(
            filepath=file_path,
            min_duration_multiplier=min_duration_multiplier,
            min_loop_duration=min_loop_duration,
            max_loop_duration=max_loop_duration,
            approx_loop_start=self.approx_loop_start,
            approx_loop_end=self.approx_loop_end,
            brute_force=brute_force,
            disable_pruning=disable_pruning,
        )

        logging.info(f"Loaded \"{file_path}\". Analyzing...")

        self.loop_pair_list = self.musiclooper.find_loop_pairs()
        self.interactive_mode = "PML_INTERACTIVE_MODE" in os.environ
        self.in_samples = "PML_DISPLAY_SAMPLES" in os.environ

    def get_all_loop_pairs(self) -> List[LoopPair]:
        """
        Returns the discovered loop points of an audio file as a list of LoopPair objects
        """
        return self.loop_pair_list

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
        rich_console.print()
        table = Table(title=f"Discovered loop points ({min(show_top, total_candidates)}/{total_candidates} displayed)", caption=more_prompt_message)
        table.add_column("Index", justify="right", style="cyan", no_wrap=True)
        table.add_column("Loop Start", style="magenta")
        table.add_column("Loop End", style="green")
        table.add_column("Length", style="white")
        table.add_column("Note Distance", style="yellow")
        table.add_column("Loudness Difference", style="blue")
        table.add_column("Score", justify="right", style="red")

        for idx, pair in enumerate(self.loop_pair_list[:show_top]):
            start_time = (
                pair.loop_start
                if self.in_samples
                else preview_looper.samples_to_ftime(pair.loop_start)
            )
            end_time = (
                pair.loop_end
                if self.in_samples
                else preview_looper.samples_to_ftime(pair.loop_end)
            )
            length = (
                pair.loop_end - pair.loop_start
                if self.in_samples
                else preview_looper.samples_to_ftime(pair.loop_end - pair.loop_start)
            )
            score = pair.score
            loudness_difference = pair.loudness_difference
            note_distance = pair.note_distance
            table.add_row(
                str(idx),
                str(start_time),
                str(end_time),
                str(length),
                f"{note_distance:.4f}",
                f"{loudness_difference:.4f}",
                f"{score:.2%}",
            )

        rich_console.print(table)
        rich_console.print()

        def get_user_input():
            try:
                num_input = rich_console.input("Enter the index number for the loop you'd like to use (append [cyan]p[/] to preview; e.g. [cyan]0p[/]):")
                idx = 0
                preview = False

                if num_input == "more":
                    self.interactive_handler(show_top=show_top * 2)
                if num_input == "all":
                    self.interactive_handler(show_top=total_candidates)
                if num_input == "reset":
                    self.interactive_handler()

                if num_input[-1] == "p":
                    idx = int(num_input[:-1])
                    preview = True
                else:
                    idx = int(num_input)

                if not 0 <= idx < len(self.loop_pair_list):
                    raise IndexError

                if preview:
                    rich_console.print(f"Previewing loop [cyan]#{idx}[/] | (Press [red]Ctrl+C[/] to stop looping):")
                    loop_start = self.loop_pair_list[idx].loop_start
                    loop_end = self.loop_pair_list[idx].loop_end
                    # start preview 5 seconds before the looping point
                    offset = preview_looper.seconds_to_samples(5)
                    preview_offset = loop_end - offset if loop_end - offset > 0 else 0
                    preview_looper.play_looping(loop_start, loop_end, start_from=preview_offset)
                    return get_user_input()
                else:
                    return idx

            except (ValueError, IndexError):
                rich_console.print(f"Please enter a number within the range [0,{len(self.loop_pair_list)-1}].")
                return get_user_input()

        try:
            selected_index = get_user_input()

            if selected_index is None:
                rich_console.print("[red]Please select a valid number.[/]")
                return get_user_input()

            return selected_index
        except KeyboardInterrupt:
            rich_console.print("\n[red]Operation terminated by user. Exiting.[/]")
            sys.exit()


class LoopExportHandler(LoopHandler):
    def __init__(
        self,
        file_path,
        min_duration_multiplier,
        min_loop_duration,
        max_loop_duration,
        output_dir,
        approx_loop_position: tuple = None,
        brute_force: bool = False,
        disable_pruning: bool = False,
        split_audio=True,
        split_audio_format="WAV",
        to_txt=False,
        to_stdout=False,
        tag_names: Tuple[str, str] = None,
        batch_mode=False,
    ):
        super().__init__(
            file_path,
            min_duration_multiplier,
            min_loop_duration,
            max_loop_duration,
            approx_loop_position,
            brute_force,
            disable_pruning,
        )
        self.output_directory = output_dir
        self.split_audio = split_audio
        self.split_audio_format = split_audio_format
        self.to_txt = to_txt
        self.to_stdout = to_stdout
        self.tag_names = tag_names
        self.batch_mode = batch_mode

    def run(self):
        self.loop_pair_list = self.get_all_loop_pairs()
        chosen_loop_pair = self.choose_loop_pair(self.interactive_mode)
        loop_start = chosen_loop_pair.loop_start
        loop_end = chosen_loop_pair.loop_end

        music_looper = self.get_musiclooper_obj()

        if self.tag_names is not None:
            loop_start_tag, loop_end_tag = self.tag_names
            music_looper.export_tags(
                loop_start,
                loop_end,
                loop_start_tag,
                loop_end_tag,
                output_dir=self.output_directory,
            )
            message = f"Exported {loop_start_tag}: {loop_start} and {loop_end_tag}: {loop_end} of \"{music_looper.filename}\" to a copy in \"{self.output_directory}\""
            if self.batch_mode:
                logging.info(message)
            else:
                rich_console.print(message)

        if self.to_stdout:
            rich_console.print(f"\nLoop points for \"{music_looper.filename}\":\nLOOP_START: {loop_start}\nLOOP_END: {loop_end}\n")
        if self.to_txt:
            music_looper.export_txt(loop_start, loop_end, output_dir=self.output_directory)
            out_path = os.path.join(self.output_directory, "loop.txt")
            message = f"Successfully added \"{music_looper.filename}\" loop points to \"{out_path}\""
            if self.batch_mode:
                logging.info(message)
            else:
                rich_console.print(message)
        if self.split_audio:
            try:
                music_looper.export(
                    loop_start,
                    loop_end,
                    format=self.split_audio_format,
                    output_dir=self.output_directory
                )
                message = f"Successfully exported \"{music_looper.filename}\" intro/loop/outro sections to \"{self.output_directory}\""
                if self.batch_mode:
                    logging.info(message)
                else:
                    rich_console.print(message)
            # Usually: unknown file format specified; raised by soundfile
            except ValueError as e:
                logging.error(e)


class BatchHandler:
    def __init__(
        self,
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
        tag_names: Tuple[str, str] = None,
        brute_force: bool = False,
        disable_pruning: bool = False,
    ):
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
        self.tag_names = tag_names
        self.brute_force = brute_force
        self.disable_pruning = disable_pruning

    def run(self):
        files = self.get_files_in_directory(
            self.directory_path, recursive=self.recursive
        )

        if len(files) == 0:
            raise FileNotFoundError(f"No files found in \"{self.directory_path}\"")

        output_dirs = (
            None
            if self.flatten
            else self.clone_file_tree_structure(files, self.output_directory)
        )

        with Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            MofNCompleteColumn(),
            console=rich_console,
        ) as progress:
            pbar = progress.add_task("Processing...", total=len(files))
            for file_idx, file in enumerate(files):
                progress.update(
                    pbar,
                    advance=1,
                    description=(
                        f"Processing \"{os.path.relpath(file, self.directory_path)}\""
                    ),
                )
                self._batch_export_helper(
                    file_path=file,
                    min_duration_multiplier=self.min_duration_multiplier,
                    min_loop_duration=self.min_loop_duration,
                    max_loop_duration=self.max_loop_duration,
                    brute_force=self.brute_force,
                    disable_pruning=self.disable_pruning,
                    split_audio_format=self.split_audio_format,
                    output_dir=(
                        self.output_directory if self.flatten else output_dirs[file_idx]
                    ),
                    split_audio=self.split_audio,
                    to_txt=self.to_txt,
                    to_stdout=self.to_stdout,
                    tag_names=self.tag_names,
                )

    @staticmethod
    def clone_file_tree_structure(in_files, output_directory):
        common_path = os.path.commonpath(in_files)
        output_dirs = [
            os.path.join(
                os.path.abspath(output_directory),
                os.path.dirname(os.path.relpath(file, start=common_path)),
            )
            for file in in_files
        ]
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
    def _batch_export_helper(*args, **kwargs):
        try:
            export_handler = LoopExportHandler(*args, **kwargs, batch_mode=True)
            export_handler.run()
        except (AudioLoadError, LoopNotFoundError) as e:
            logging.error(e)
        except Exception as e:
            logging.error(e)
