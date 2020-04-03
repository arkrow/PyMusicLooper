import os
import multiprocessing
import sys
import numpy as np
from mpg123 import Mpg123, Out123
import mpg123
import librosa
from multiprocessing import Queue
import time

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
        self.filename = filename
        self.audio, self.trim_offset = librosa.effects.trim(librosa.core.to_mono(audio))
        self.rate = sr
        self.playback_audio = audio

        # Initialize parameters for playback
        self.channels = self.playback_audio.shape[0]
        self.encoding = mpg123.ENC_FLOAT_32

    def _loop_finding_routine(self, beats, i_start, i_stop, chroma, min_duration, method):
        for i in range(i_start, i_stop):
            for j in range(i):
                    if beats[i] - beats[j] < min_duration:
                        continue
                    
                    if method == 'dist':
                        dist = np.linalg.norm(chroma[..., beats[i]] - chroma[..., beats[j]])
                        if dist <= 0.15:
                            self._candidate_pairs_q.put((beats[j], beats[i], dist))
            
                    elif method == 'angle':
                        angle = np.abs(self.angle_between(chroma[..., beats[i]], chroma[..., beats[j]]))
                        if angle <= 10:
                            self._candidate_pairs_q.put((beats[j], beats[i], angle))
                    
                    elif method == 'corr':
                        corr = np.corrcoef(chroma[..., beats[i]], chroma[..., beats[j]])
                        corr = np.min(corr.flatten())
                        if corr >= 0.99:
                            self._candidate_pairs_q.put((beats[j], beats[i], corr))

                    elif method == 'corr_mod':
                        corr = np.corrcoef(chroma[..., beats[i]], chroma[..., beats[j]])
                        corr = np.abs(np.min(corr.flatten()))
                        if corr >= 0.995:
                            dist = np.linalg.norm(chroma[..., beats[i]] - chroma[..., beats[j]])
                            deviation = np.max([np.linalg.norm(chroma[..., beats[j]] * 0.1), np.linalg.norm(chroma[..., beats[i]] * 0.1)])
                            if dist <= deviation:
                                self._candidate_pairs_q.put((beats[j], beats[i], dist/deviation))

    def find_loop_pairs(self, method='corr_mod', min_duration_multiplier=0.3, combine_beat_plp=True, keep_at_most=4, multithread=True):
        runtime_start = time.time()
        fmin = 27.5
        fmax = 16000
        
        if combine_beat_plp:
            onset_env = librosa.onset.onset_strength(y=self.audio, sr=self.rate, fmin=fmin, fmax=fmax)
            pulse = librosa.beat.plp(sr=self.rate, onset_envelope=onset_env)
            beats_plp = np.flatnonzero(librosa.util.localmax(pulse))
            _, beats_bt = librosa.beat.beat_track(sr=self.rate, onset_envelope=onset_env)
            beats = np.union1d(beats_bt, beats_plp)
        else:
            onset_env = librosa.onset.onset_strength(y=self.audio, sr=self.rate, fmin=fmin, fmax=fmax)
            _, beats = librosa.beat.beat_track(sr=self.rate, onset_envelope=onset_env)

        S = librosa.core.stft(y=self.audio)
        S_power = np.abs(S)**2
        S_weighed = librosa.core.perceptual_weighting(S_power, librosa.fft_frequencies(sr=self.rate))
        mel_spectrogram = librosa.feature.melspectrogram(S=S_weighed)

        chroma = librosa.feature.chroma_stft(S=S_power, sr=self.rate)

        power_db = librosa.power_to_db(mel_spectrogram, ref=np.max)
        min_duration = int(chroma.shape[-1] * min_duration_multiplier)
        candidate_pairs = []

        self._candidate_pairs_q = Queue()

        runtime_end = time.time()
        print('Finished prep in {}s'.format(runtime_end - runtime_start))


        if multithread:
            processes = []
            affinity = 8
            i_step = np.concatenate([[1, int(beats.size/2)], np.arange(int(beats.size/2)+int(beats.size/affinity), beats.size, step=int(beats.size/affinity), dtype=np.intp)])
            i_step[-1] = int(beats.size)
            for i in range(i_step.size - 1):
                p = multiprocessing.Process(target=self._loop_finding_routine, args=(beats, i_step[i], i_step[i+1], chroma, min_duration, method))
                processes.append(p)
                p.daemon=True
                p.start()
        else:
            self._loop_finding_routine(beats, 1, beats.size, chroma, min_duration, method)

        if multithread:
            for process in processes:
                process.join()
        
        candidate_pairs = []
        while not self._candidate_pairs_q.empty():
            candidate_pairs.append(self._candidate_pairs_q.get())
        
        print(len(candidate_pairs))
        most_similar_pairs = []

        for start, end, score in candidate_pairs:
            if self._is_db_similar(power_db[..., end], power_db[..., start], threshold=2):
                most_similar_pairs.append((start, end, score))
        
        use_decending = True if method == 'corr' else False

        pruned_list = sorted(most_similar_pairs, reverse=use_decending, key=lambda x: x[2])[:keep_at_most]

        if self.trim_offset[0] > 0:
            offset_f = lambda x: librosa.samples_to_frames(librosa.frames_to_samples(x) + self.trim_offset[0])
            offset_f(pruned_list)

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
        time_sec = librosa.core.frames_to_time(frame, sr=self.rate)
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

        i = adjusted_loop_offset - 1000
        try:
            while True:
                out.play(playback_frames[..., i])
                i += 1
                
                if i == adjusted_loop_offset:
                    i = adjusted_start_offset

        except KeyboardInterrupt:
            print() # so that the program ends on a newline
    
    def export_loop_file(self, start_offset, loop_offset, filename=None, format='WAV'):
        import soundfile as sf
        if filename is None:
            filename = os.path.splitext(self.filename)[0] + '-loop' + '.wav'
        filename = os.path.abspath(filename)
        start_offset = self.frames_to_samples(start_offset)
        loop_offset = self.frames_to_samples(loop_offset)
        loop_section = self.playback_audio[..., start_offset:loop_offset]
        sf.write(filename, loop_section.T, self.rate)


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
        runtime_start = time.time()
        print("Loading {}...".format(filename))
        track = MusicLooper(filename)
        runtime_end = time.time()
        print('Loaded file in {}s'.format(runtime_end - runtime_start))
        if start_offset is None and loop_offset is None:
            a = track.find_loop_pairs()
            # Use the loop point with the best similarity
            if len(a) == 0:
                print('No suitable loop point found.')
                sys.exit()

            if prioritize_duration:
                a = sorted(a, key=lambda x: np.abs(x[0] - x[1]), reverse=True)

            start_offset, loop_offset, score = a[0]
        else:
            score = None
        runtime_end = time.time()
        print('Total elapsed time (s): {}'.format(runtime_end - runtime_start))
        start_s = track.frames_to_samples(start_offset)
        end_s = track.frames_to_samples(loop_offset)
        # lag_finder(track.playback_audio[0, start_s:start_s+512], track.playback_audio[0, end_s:end_s+512])
        # track.export_loop_file(start_offset, loop_offset)
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
