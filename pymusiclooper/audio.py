import os

import librosa
import numpy as np

from .exceptions import AudioLoadError

class MLAudio:
    total_duration: int
    filepath: str
    filename: str
    audio: np.ndarray
    trim_offset: int
    rate: int
    playback_audio: np.ndarray
    channels: int

    def __init__(self, filepath) -> None:
        # Load the file if it exists
        # dtype and subsequent type cast are workarounds for a libsnd bug; see https://github.com/librosa/librosa/issues/1622 and https://github.com/bastibe/python-soundfile/issues/349
        raw_audio, sampling_rate = librosa.load(filepath, sr=None, mono=False, dtype=None)
        raw_audio = raw_audio.astype(np.float32)
        self.total_duration = librosa.get_duration(y=raw_audio,
                                                   sr=sampling_rate)

        if raw_audio.size == 0:
            raise AudioLoadError('The audio file could not be loaded for analysis. The file may be corrupted, or the current environment may be lacking the necessary tools to open this file format.')

        self.filepath = filepath
        self.filename = os.path.basename(filepath)

        mono_signal = librosa.core.to_mono(raw_audio)

        self.audio, self.trim_offset = librosa.effects.trim(mono_signal, top_db=40)
        self.trim_offset = self.trim_offset[0]

        self.rate = sampling_rate

        # Initialize parameters for playback
        self.playback_audio = raw_audio
        self.channels = self.playback_audio.shape[0]
    
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

    def frames_to_samples(self, frame):
        return librosa.core.frames_to_samples(frame)

    def seconds_to_frames(self, seconds):
        return librosa.core.time_to_frames(seconds, sr=self.rate)

    def frames_to_ftime(self, frame):
        time_sec = librosa.core.frames_to_time(frame, sr=self.rate)
        return "{:02.0f}:{:06.3f}".format(time_sec // 60, time_sec % 60)
