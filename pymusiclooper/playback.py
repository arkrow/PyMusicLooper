import threading
import signal
import logging
import signal

import sounddevice as sd

class PlaybackHandler:
    def __init__(self) -> None:
        self.event = threading.Event()

    def play_looping(self, playback_audio, samplerate, loop_start, loop_end, start_from=0):
        self.loop_counter = 0
        self.looping = True
        playback_data = playback_audio.T
        self.current_frame = start_from
        try:
            def callback(outdata, frames, time, status):
                chunksize = min(len(playback_data) - self.current_frame, frames)

                # Audio looping logic
                if self.looping and self.current_frame + frames > loop_end:
                    pre_loop_index = (loop_end - self.current_frame)
                    remaining_frames = frames - (loop_end - self.current_frame)
                    adjusted_next_frame_idx = loop_start + remaining_frames
                    outdata[:pre_loop_index]  = playback_data[self.current_frame:loop_end]
                    outdata[pre_loop_index:frames] = playback_data[loop_start:adjusted_next_frame_idx]
                    self.current_frame = adjusted_next_frame_idx
                    self.loop_counter+=1
                    print(f'Currently on loop #{self.loop_counter}.',end='\r')
                else:
                    outdata[:chunksize] = playback_data[self.current_frame:self.current_frame + chunksize]
                    self.current_frame += chunksize
                    if chunksize < frames:
                        outdata[chunksize:] = 0
                        raise sd.CallbackStop()                

            self.stream = sd.OutputStream(
                samplerate=samplerate, channels=playback_data.shape[1],
                callback=callback, finished_callback=self.event.set)

            with self.stream:
                # Override SIGINT/KeyboardInterrupt handler with custom logic for loop handling
                signal.signal(signal.SIGINT, self._loop_interrupt_handler)
                # Workaround for python issue on Windows
                # (threading.Event().wait() not interruptable with Ctrl-C on Windows): https://bugs.python.org/issue35935
                while not self.event.wait(0.5): # 0.5 second timeout to handle interrupts in-between
                    pass
        except Exception as e:
            logging.error(e)
    
    def _loop_interrupt_handler(self, *args):
        if self.looping:
            self.looping = False
            print('(Looping disabled. Ctrl+C again to stop playback.)')
        else:
            self.event.set()
            self.stream.stop()
            self.stream.close()
            print('Playback interrupted by user.')
            signal.signal(signal.SIGINT, signal.default_int_handler) # restore default SIGINT handler
