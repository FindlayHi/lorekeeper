"""The mic while the hotkey is held, and Whisper (faster-whisper) on this PC. Audio never leaves it."""
import threading
import numpy as np

RATE = 16000


def inputs():
    """The microphones, each once: Windows lists every mic under several audio systems, so take the default mic's
    system (MME, which also resamples to the 16 kHz Whisper wants)."""
    import sounddevice as sd
    try:
        api = sd.query_devices(sd.default.device[0])['hostapi']
    except Exception:
        return []
    return [d['name'] for d in sd.query_devices() if d['max_input_channels'] > 0 and d['hostapi'] == api
            and 'sound mapper' not in d['name'].lower()]


def device(name):
    """The device number for a mic picked by name (numbers shift as devices come and go), or None: Windows' default."""
    if not name:
        return None
    import sounddevice as sd
    try:
        api = sd.query_devices(sd.default.device[0])['hostapi']
        return next((i for i, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0 and d['hostapi'] == api
                     and d['name'] == name), None)
    except Exception:
        return None


class Ears:
    def __init__(self, size='base.en', device='cpu'):
        self.model, self.chunks, self.stream, self.why = None, [], None, ''   # why: the model failed to load, and how
        self.mic = ''   # a mic's name from inputs(); '' = Windows' default (unplugged: falls back to the default too)
        self.ready = threading.Event()
        threading.Thread(target=self._load, args=(size, device), daemon=True).start()   # a few seconds; the first ask waits for it

    def _load(self, size, device):
        """Ready is set however it ends, so a question never waits on a model that will never come; why says what broke."""
        try:
            from faster_whisper import WhisperModel
            try:
                self.model = WhisperModel(size, device=device, compute_type='int8' if device == 'cpu' else 'float16')
            except Exception:
                self.model = WhisperModel(size, device='cpu', compute_type='int8')   # no CUDA after all
        except Exception as e:
            self.why = f'{type(e).__name__}: {e}'
            print('speech model:', self.why, flush=True)
        finally:
            self.ready.set()

    def start(self):
        import sounddevice as sd
        self.chunks = []
        self.stream = sd.InputStream(samplerate=RATE, channels=1, dtype='float32', device=device(self.mic),
                                     callback=lambda d, *_: self.chunks.append(d.copy()))
        self.stream.start()

    def stop(self):
        """The recording so far, as one float32 array (empty if nothing)."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        return np.concatenate(self.chunks)[:, 0] if self.chunks else np.zeros(0, dtype='float32')

    def text(self, audio, hint=''):
        """hint: the game's name and names from its notes, so Whisper spells "Malenia" right."""
        if len(audio) < RATE * 0.4:
            return ''
        if not self.ready.wait(60):
            raise RuntimeError("The speech model is still loading. Try again in a moment.")
        if not self.model:
            raise RuntimeError("The speech model isn't ready: it downloads the first time, check your connection")
        segs, _ = self.model.transcribe(audio, language='en', beam_size=1, vad_filter=True, initial_prompt=hint or None,
                                        condition_on_previous_text=False)
        return ' '.join(s.text.strip() for s in segs).strip()
