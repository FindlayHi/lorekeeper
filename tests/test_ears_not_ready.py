"""A Whisper model that never loaded says so plainly, at once, instead of waiting a minute and then crashing."""
import os, sys, threading, types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import ears  # noqa: E402


def whisper(monkeypatch, model):
    fake = types.ModuleType('faster_whisper')
    fake.WhisperModel = model
    monkeypatch.setitem(sys.modules, 'faster_whisper', fake)


def test_a_model_that_fails_both_ways_still_sets_ready_and_says_why(monkeypatch):
    def model(*a, **k):
        raise OSError('could not download base.en: no internet')
    whisper(monkeypatch, model)
    e = ears.Ears('base.en', 'cuda')
    assert e.ready.wait(5) and e.model is None and 'no internet' in e.why
    with pytest.raises(RuntimeError, match="speech model isn't ready: it downloads the first time, check your connection"):
        e.text(np.zeros(16000, dtype='float32'))


def test_a_model_still_loading_says_so(monkeypatch):
    gate = threading.Event()
    whisper(monkeypatch, lambda *a, **k: gate.wait(5))
    e = ears.Ears('base.en', 'cpu')
    monkeypatch.setattr(e.ready, 'wait', lambda secs: False)   # the minute ran out
    with pytest.raises(RuntimeError, match='still loading'):
        e.text(np.zeros(16000, dtype='float32'))
    gate.set()


def test_cuda_failing_falls_back_to_cpu(monkeypatch):
    def model(size, device, compute_type):
        if device == 'cuda':
            raise RuntimeError('no CUDA')
        return 'cpu model'
    whisper(monkeypatch, model)
    e = ears.Ears('base.en', 'cuda')
    assert e.ready.wait(5) and e.model == 'cpu model' and e.why == ''
