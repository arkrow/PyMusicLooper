import os
import sys
import numpy as np
from mpg123 import Mpg123, Out123
import mpg123
import librosa

class MusicLooper:
    def __init__(self, filename):
        # Load the file if it exists
        if os.path.exists(filename) and os.path.isfile(filename):
            try:
                audio, sr = librosa.load(filename, sr=None, mono=False)
            except:
                raise TypeError("Unsupported file type.")
        else:
            raise FileNotFoundError("Specified file not found.")

        # Get the waveform data from the mp3 file
        self.audio = librosa.core.to_mono(audio)
        self.rate = sr
        self.playback_audio = audio

        # Initialize parameters for playback
        self.channels = self.playback_audio.shape[0]
        self.encoding = mpg123.ENC_FLOAT_32

    def find_loop_pairs(self, method='corr_mod', min_duration_multiplier=0.5, use_plp=False, keep_at_most=4):
        
        if use_plp:
            # onset_env = librosa.onset.onset_strength(y=self.audio, sr=self.rate)
            n = (self.rate / 22050) * 384
            pulse = librosa.beat.plp(y=self.audio, sr=self.rate, win_length=n)
            beats = np.flatnonzero(librosa.util.localmax(pulse))
        else:
            _, beats = librosa.beat.beat_track(y=self.audio, sr=self.rate)

        S = librosa.core.stft(y=self.audio)
        S_power = np.abs(S)**2
        S_weighed = librosa.core.perceptual_weighting(S_power, librosa.fft_frequencies(sr=self.rate))
        mel_spectrogram = librosa.feature.melspectrogram(S=S_weighed)

        chroma = librosa.feature.chroma_stft(S=S_power, sr=self.rate)

        power_db = librosa.power_to_db(mel_spectrogram, ref=np.max)
        min_duration = int(chroma.shape[-1] * min_duration_multiplier)
        candidate_pairs = []

        for i in range(beats.size):
            for j in range(i):
                if beats[i] - beats[j] < min_duration:
                    continue
                
                if method == 'euclid_dist':
                    dist = np.linalg.norm(chroma[..., beats[i]] - chroma[..., beats[j]])
                    if dist <= 0.15:
                        candidate_pairs.append((beats[j], beats[i], dist))
        
                elif method == 'angle':
                    angle = np.abs(self.angle_between(chroma[..., beats[i]], chroma[..., beats[j]]))
                    if angle <= 10:
                        candidate_pairs.append((beats[j], beats[i], angle))
                
                elif method == 'corr':
                    corr = np.corrcoef(chroma[..., beats[i]], chroma[..., beats[j]])
                    corr = np.min(corr.flatten())
                    if corr >= 0.99:
                        candidate_pairs.append((beats[j], beats[i], corr))

                elif method == 'corr_mod':
                    corr = np.corrcoef(chroma[..., beats[i]], chroma[..., beats[j]])
                    corr = np.min(corr.flatten())
                    if corr >= 0.99 and np.linalg.norm(chroma[..., beats[i]] - chroma[..., beats[j]]) <= np.min([np.linalg.norm(chroma[..., beats[j]] - (chroma[..., beats[j]] * 1.1)), np.linalg.norm(chroma[..., beats[i]] - (chroma[..., beats[i]] * 1.1))]):# and np.abs(self.angle_between(chroma[..., beats[i]], chroma[..., beats[j]])) <= 10:
                        candidate_pairs.append((beats[j], beats[i], corr))

        print(len(candidate_pairs))
        most_similar_pairs = []

        for start, end, dist in candidate_pairs:
            if self._is_db_similar(power_db[..., end], power_db[..., start], threshold=2):
                most_similar_pairs.append((start, end, dist))
        
        use_decending = True if method == 'corr' or method == 'corr_mod' else False
        
        pruned_list = sorted(most_similar_pairs, reverse=use_decending, key=lambda x: x[2])[:keep_at_most]

        print(pruned_list)

        return pruned_list

    def _is_db_similar(self, power_db_f1, power_db_f2, threshold):
        return np.abs(np.average(power_db_f1) - np.average(power_db_f2)) <= threshold
    
    def unit_vector(self, vector):
        """ Returns the unit vector of the vector """
        return vector / np.linalg.norm(vector)

    def angle_between(self, v1, v2):
        """ Returns the angle in degrees between vectors 'v1' and 'v2' """
        v1_u = self.unit_vector(v1)
        v2_u = self.unit_vector(v2)
        return np.arccos(np.clip(np.dot(v1_u, v2_u), -1.0, 1.0)) * 360 / np.pi
    
    def frames_to_samples(self, frame):
        return librosa.core.frames_to_samples(frame)

    def frames_to_ftime(self, frame):
        time_sec = librosa.core.frames_to_time(frame, sr=self.rate, n_fft=2048)
        return "{:02.0f}:{:06.3f}".format(
                    time_sec // 60,
                    time_sec % 60
                    )

    def play_looping(self, start_offset, loop_offset):
        out = Out123()
        out.start(self.rate, self.channels, self.encoding)
        
        playback_frames  = librosa.util.frame(self.playback_audio.flatten(order='F'))
        adjusted_start_offset = start_offset * self.channels
        adjusted_loop_offset = loop_offset * self.channels

        i = adjusted_loop_offset - 1500
        try:
            while True:
                out.play(playback_frames[..., i])
                i += 1
                
                if i == adjusted_loop_offset:
                    i = adjusted_start_offset

        except KeyboardInterrupt:
            print() # so that the program ends on a newline

def lag_finder(y1, y2):
    diff = np.empty(y2.size)
    for i in range(y2.size):
        diff[i] = np.abs(y1[..., 0]-y2[..., i])
    arg_min = np.argmin(diff) 
    print(arg_min)
    print(diff[arg_min])
    return np.argmin(diff)
    # from scipy import signal, fftpack
    # import matplotlib.pyplot as plt
    # n = len(y1)
    # corr = np.correlate(y2, y1, mode='same') #/ np.sqrt(np.correlate(y1, y1, mode='same')[int(n/2)] * np.correlate(y2, y2, mode='same')[int(n/2)])
    # print('y2 is ' + str(np.argmax(corr)) + 'samples behind y1')
    # plt.figure()
    # plt.plot(delay_arr, corr)
    # plt.title('Lag: ' + str(np.round(delay, 3)) + ' s')
    # plt.xlabel('Lag')
    # plt.ylabel('Correlation coeff')
    # plt.show()

    # A = fftpack.fft(y1)
    # B = fftpack.fft(y2)
    # Ar = -A.conjugate()
    # Br = -B.conjugate()
    # # print(np.argmax(signal.correlate(a,b)))
    # # import pdb; pdb.set_trace()
    # # print(np.argmin(np.abs(np.subtract(a, b))))
    # print(np.argmax(np.abs(fftpack.ifft(A*Br))))

def loop_track(filename, prioritize_duration=False, start_offset=None, loop_offset=None):
    try:
        # Load the file
        print("Loading {}...".format(filename))
        track = MusicLooper(filename)
        if start_offset is None and loop_offset is None:
            a = track.find_loop_pairs()
            # Use the loop point with the best similarity
            if len(a) == 0:
                print('No suitable loop point found.')
                exit()

            if prioritize_duration:
                a = sorted(a, key=lambda x: np.abs(x[0] - x[1]), reverse=True)

            start_offset, loop_offset, score = a[0]
        else:
            score = None
        start_s = track.frames_to_samples(start_offset)
        end_s = track.frames_to_samples(loop_offset)
        # lag_finder(track.playback_audio[0, start_s:start_s+512], track.playback_audio[0, end_s:end_s+512])
        
        print("Playing with loop from {} back to {}, prioritizing {}, (score={})".format(
            track.frames_to_ftime(loop_offset),
            track.frames_to_ftime(start_offset),
            'duration' if prioritize_duration else 'beat similarity',
            score if score is not None else 'unknown'))
        print("(press Ctrl+C to exit)")
        # print(track.frames_to_samples(loop_offset), '\n', track.frames_to_samples(start_offset))
        track.play_looping(start_offset, loop_offset)

    except (TypeError, FileNotFoundError) as e:
        print("Error: {}".format(e))

if __name__ == '__main__':
    # Load the file
    if len(sys.argv) == 2:
        loop_track(sys.argv[1])
    else:
        print("Error: No file specified.",
                "\nUsage: python3 loop.py file.mp3")
