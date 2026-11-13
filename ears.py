"""The mic while the hotkey is held, and Whisper (faster-whisper) on this PC. Audio never leaves it."""
import os, re, threading, time
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


def repo(size):
    """The Hugging Face repo faster-whisper fetches a model from: "base.en" -> "Systran/faster-whisper-base.en"."""
    from faster_whisper import utils
    return size if '/' in size else utils._MODELS.get(size, size)


def have(size):
    """Is the model on this PC already, so loading it downloads nothing? True when that can't be told."""
    try:
        from faster_whisper.utils import download_model
    except ImportError:
        return True
    try:
        download_model(size, local_files_only=True)
        return True
    except Exception:
        return False


def folder(size):
    """Where the download lands: Hugging Face's cache folder for the model."""
    from huggingface_hub import constants
    return os.path.join(constants.HF_HUB_CACHE, 'models--' + repo(size).replace('/', '--'))


def got(path):
    """Bytes downloaded so far: the files in the cache folder, part-written ones (blobs/*.incomplete) included.
    Links are skipped: where Windows allows them, the finished files are links to the blobs, and would count twice."""
    n = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                if not os.path.islink(os.path.join(root, f)):
                    n += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return n


def total(size):
    """The model's size in bytes as Hugging Face lists it, 0 if it won't say."""
    try:
        from huggingface_hub import HfApi
        files = HfApi().model_info(repo(size), files_metadata=True, timeout=10).siblings
        return sum(f.size or 0 for f in files if re.fullmatch(r'config\.json|preprocessor_config\.json|model\.bin|tokenizer\.json|vocabulary\..*', f.rfilename))
    except Exception:
        return 0


WAIT = 'The speech model is still downloading. Ask again when it is done.'


class Ears:
    def __init__(self, size='base.en', device='cpu', progress=None):
        """progress(done, total, finished): called while the model downloads (the first run, or a new model picked):
        bytes so far and in all (0 if unknown) with finished None, then once with finished True or False."""
        self.model, self.chunks, self.stream, self.why = None, [], None, ''   # why: the model failed to load, and how
        self.mic = ''   # a mic's name from inputs(); '' = Windows' default (unplugged: falls back to the default too)
        self.getting = None   # is the model being downloaded? None until that is known
        self.ready = threading.Event()
        threading.Thread(target=self._load, args=(size, device, progress), daemon=True).start()   # a few seconds; the first ask waits for it

    def _load(self, size, device, progress=None):
        """Ready is set however it ends, so a question never waits on a model that will never come; why says what broke."""
        try:
            self.getting = not have(size)
            if self.getting and progress:
                threading.Thread(target=self._watch, args=(size, progress), daemon=True).start()
            from faster_whisper import WhisperModel
            try:
                self.model = WhisperModel(size, device=device, compute_type='int8' if device == 'cpu' else 'float16')
            except Exception:
                self.model = WhisperModel(size, device='cpu', compute_type='int8')   # no CUDA after all
        except Exception as e:
            self.why = f'{type(e).__name__}: {e}'
            print('speech model:', self.why, flush=True)
        finally:
            was, self.getting = self.getting, False
            self.ready.set()
            if was and progress:
                progress(0, 0, bool(self.model))

    def _watch(self, size, progress, every=0.5):
        """Report the download as it grows: at the start, then each time another 5% (or 10 MB, the size unknown) is in."""
        try:
            path, all_, last = folder(size), total(size), -1
            while self.getting:
                done = got(path)
                step = done * 20 // all_ if all_ else done // 10_000_000
                if step > last:
                    last = step
                    progress(min(done, all_) if all_ else done, all_, None)
                time.sleep(every)
        except Exception as e:
            print('speech model progress:', e, flush=True)

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
        if self.getting:
            raise RuntimeError(WAIT)
        if not self.ready.wait(60):
            raise RuntimeError("The speech model is still loading. Try again in a moment.")
        if not self.model:
            raise RuntimeError("The speech model isn't ready: it downloads the first time, check your connection")
        segs, _ = self.model.transcribe(audio, language='en', beam_size=1, vad_filter=True, initial_prompt=hint or None,
                                        condition_on_previous_text=False)
        return ' '.join(s.text.strip() for s in segs).strip()
