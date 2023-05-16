import threading
import signal
import sounddevice as sd
import logging
import signal

class PlaybackHandler:
    def __init__(self) -> None:
        self.event = threading.Event()

    def play_looping(self, playback_audio, samplerate, loop_start, loop_end, start_from=0):
        self.current_frame = 0
        self.loop_counter = 0
        self.looping = True

        try:
            data, fs = playback_audio.T, samplerate
            self.current_frame = start_from

            def callback(outdata, frames, time, status):
                chunksize = min(len(data) - self.current_frame, frames)

                # Audio looping logic
                if self.looping and self.current_frame + chunksize > loop_end:
                    self.current_frame = loop_start
                    self.loop_counter+=1
                    print(f'Currently on loop #{self.loop_counter}.',end='\r')

                outdata[:chunksize] = data[self.current_frame:self.current_frame + chunksize]

                if chunksize < frames:
                    outdata[chunksize:] = 0
                    raise sd.CallbackStop()
                self.current_frame += chunksize

            stream = sd.OutputStream(
                samplerate=fs, channels=data.shape[1],
                callback=callback, finished_callback=self.event.set)

            with stream:
                # Workaround for python issue on Windows
                # (threading.Event().wait() not interruptable with Ctrl-C on Windows): https://bugs.python.org/issue35935
                signal.signal(signal.SIGINT, self._loop_interrupt_handler) # Override SIGINT/KeyboardInterrupt with own logic for loop handling
                while not self.event.wait(.5): # 0.5 second timeout to handle interrupts in-between
                    pass
        except Exception as e:
            # parser.exit(type(e).__name__ + ': ' + str(e))
            logging.error(e)
    
    def _loop_interrupt_handler(self, *args):
        if self.looping:
            self.looping = False
            print('(Looping disabled. Ctrl+C again to stop playback.)')
        else:
            signal.signal(signal.SIGINT, signal.default_int_handler) # restore default SIGINT handler
            self.event.set()
            print('Playback interrupted by user.')
