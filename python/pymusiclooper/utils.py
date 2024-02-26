"""General utility functions."""
import os
from typing import Optional

from pymusiclooper.youtube import YoutubeDownloader


def get_outputdir(path: str, output_dir: Optional[str] = None) -> str:
    """Returns the absolute output directory path to use for all export outputs.

    Args:
        path (str): The path of the file or directory being processed.
        output_dir (str, optional): The output directory to use. If None, will append the directory 'LooperOutput' in the path provided.

    Returns:
        str: The path to the output directory.
    """
    if os.path.isdir(path):
        default_out = os.path.join(path, "LooperOutput")
    else:
        default_out = os.path.join(os.path.dirname(path), "LooperOutput")
    return os.path.abspath(default_out) if output_dir is None else os.path.abspath(output_dir)

def mk_outputdir(path: str, output_dir: Optional[str] = None) -> str:
    """Creates the output directory in the `path` provided (if it does not exists) and returns the output directory path.

    Args:
        path (str): The path of the file or directory being processed.
        output_dir (str, optional): The output directory to use. If None, will create the directory 'LooperOutput' in the path provided.

    Returns:
        str: The path to the output directory.
    """
    output_dir_to_use = get_outputdir(path, output_dir)
    if not os.path.exists(output_dir_to_use):
        os.mkdir(output_dir_to_use)
    return output_dir_to_use


def download_audio(url: str, output_dir: str) -> str:
    """Downloads an audio file using yt-dlp from the URL provided and returns its filepath

    Args:
        url (str): The URL of the stream to pass to yt-dlp to extract audio from
        output_dir (str): The directory path to store the downloaded audio to

    Returns:
        str: The filepath of the extracted audio
    """
    yt = YoutubeDownloader(url, output_dir)
    return yt.filepath
