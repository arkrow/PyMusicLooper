import os

import yt_dlp


class YtdLogger:
    def __init__(self) -> None:
        self.verbose = os.environ.get("PML_VERBOSE", "False") == "True"

    def debug(self, msg):
        # For compatibility with youtube-dl, both debug and info are passed into debug
        # You can distinguish them by the prefix '[debug] '
        if not msg.startswith("[debug] "):
            self.info(msg)

    def info(self, msg):
        # Supress misleading option (only applicable to yt-dlp)
        if "(pass -k to keep)" in msg:
            pass
        elif msg.startswith("[download]"):
            print(msg, end="\r")
        elif msg.startswith("[ExtractAudio]"):
            print(msg)
        elif self.verbose:
            print(msg)

    def warning(self, msg):
        if self.verbose:
            print(msg)

    def error(self, msg):
        print(msg)


class YoutubeDownloader:
    def __init__(self, url, output_path):
        ydl_opts = {
            "logger": YtdLogger(),
            "format": "ogg/bestaudio/best",
            "postprocessors": [
                {  # Extracts audio using ffmpeg
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "vorbis",
                }
            ],
            "sponsorblock-remove": "all",
            "paths": {"home": output_path, "temp": output_path},
            "progress_hooks": [self.progress_hook],
            "postprocessor_hooks": [self.postprocessor_hook],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            self.error_code = ydl.download([url])

    def progress_hook(self, d):
        if d["status"] == "finished":
            print("\nDone downloading, now post-processing...")

    def postprocessor_hook(self, d):
        if d["status"] == "finished":
            self.filepath = d["info_dict"].get("filepath")
