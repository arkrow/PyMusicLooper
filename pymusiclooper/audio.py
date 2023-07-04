import os

import librosa
import numpy as np

from .exceptions import AudioLoadError


class MLAudio:
    """Wrapper class for loading audio files and containing the necessary audio data for PyMusicLooper."""

    total_duration: int
    filepath: str
    filename: str
    audio: np.ndarray
    trim_offset: int
    rate: int
    playback_audio: np.ndarray
    n_channels: int
    length: int

    def __init__(self, filepath: str) -> None:
        """Initializes the MLAudio object and its data by loading the audio using the filepath provided.

        Args:
            filepath (str): path to the audio file

        Raises:
            AudioLoadError: If the file could not be loaded.
        """
        # Load the file if it exists
        raw_audio, sampling_rate = librosa.load(filepath, sr=None, mono=False)
        self.total_duration = librosa.get_duration(y=raw_audio, sr=sampling_rate)

        if raw_audio.size == 0:
            raise AudioLoadError(
                "The audio file could not be loaded for analysis. The file may be"
                " corrupted, or the current environment may be lacking the necessary"
                " tools to open this file format."
            )

        self.filepath = filepath
        self.filename = os.path.basename(filepath)

        mono_signal = librosa.core.to_mono(raw_audio)
        # Normalize audio channels to between -1.0 and +1.0 before analysis
        mono_signal /= np.max(np.abs(mono_signal))

        self.audio, self.trim_offset = librosa.effects.trim(mono_signal, top_db=40)
        self.trim_offset = self.trim_offset[0]

        self.rate = sampling_rate

        # Initialize parameters for playback
        self.playback_audio = raw_audio
        # Mono if the loaded audio is 1-D, else get the number of channels from the shape (n_channels, samples)
        self.n_channels = (
            1 if len(self.playback_audio.shape) == 1 else self.playback_audio.shape[0]
        )
        # Convert the audio array into one suitable for playback
        # New shape: (samples, n_channels)
        self.playback_audio = self.playback_audio.T if self.n_channels > 1 else self.playback_audio[:, np.newaxis]
        self.length = self.playback_audio.shape[0]

    def apply_trim_offset(self, frame):
        return (
            librosa.samples_to_frames(
                librosa.frames_to_samples(frame) + self.trim_offset
            )
            if self.trim_offset
            else frame
        )

    def samples_to_frames(self, samples):
        return librosa.core.samples_to_frames(samples)

    def samples_to_seconds(self, samples):
        return librosa.core.samples_to_time(samples, sr=self.rate)

    def frames_to_samples(self, frame):
        return librosa.core.frames_to_samples(frame)

    def seconds_to_frames(self, seconds, apply_trim_offset=False):
        if apply_trim_offset:
            seconds = seconds - librosa.core.samples_to_time(
                self.trim_offset, sr=self.rate
            )
        return librosa.core.time_to_frames(seconds, sr=self.rate)

    def seconds_to_samples(self, seconds):
        return librosa.core.time_to_samples(seconds, sr=self.rate)

    def frames_to_ftime(self, frame: int):
        time_sec = librosa.core.frames_to_time(frame, sr=self.rate)
        return "{:02.0f}:{:06.3f}".format(time_sec // 60, time_sec % 60)
    
    def samples_to_ftime(self, samples: int):
        time_sec = librosa.core.samples_to_time(samples, sr=self.rate)
        return "{:02.0f}:{:06.3f}".format(time_sec // 60, time_sec % 60)
