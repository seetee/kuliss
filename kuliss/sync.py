"""Line up recordings of one session by their audio. Kdenlive-free, so Klatch can use it."""

import numpy as np

from .config import die
from .vad import RATE, decode

ENV_RATE = 100      # Hz; the envelope's 10 ms steps are the sync resolution
SPAN = 30 * 60      # s of each recording compared; the crew overlaps well within this
MIN_CONFIDENCE = 10  # correlation peak / std: session 28's matches scored 24-35, a non-match 3.6


def envelope(path: str, stream: int, seconds: float = SPAN) -> np.ndarray:
    """Normalised log loudness of one audio stream at ENV_RATE."""
    x = decode(path, stream, 0.0, seconds)
    hop = RATE // ENV_RATE
    e = np.log1p(np.abs(x[:len(x) // hop * hop]).reshape(-1, hop).mean(1) * 1000)
    return (e - e.mean()) / (e.std() + 1e-9)


def lag(ref: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    """(s, confidence): x[t] lines up with ref[t + s]."""
    n = 1 << int(np.ceil(np.log2(len(ref) + len(x))))
    c = np.fft.irfft(np.fft.rfft(ref, n) * np.conj(np.fft.rfft(x, n)), n)
    k = int(np.argmax(c))
    return (k - n if k > n // 2 else k) / ENV_RATE, float(c[k] / c.std())


def offset(ref_voice, ref_comms, voice, comms, who: str) -> tuple[float, float]:
    """(s, confidence): where `who`'s recording starts on the reference recording's clock.
    Each side's voice is heard in the other's call audio, late by the call's delay;
    averaging both directions cancels that delay."""
    a, ca = lag(ref_comms, voice)     # offset + delay
    b, cb = lag(comms, ref_voice)     # delay - offset
    good = [s for s, c in ((a, ca), (-b, cb)) if c >= MIN_CONFIDENCE]
    if not good:
        die(f"{who}: cannot find their voice in the call audio (confidence {ca:.0f} and "
            f"{cb:.0f}, need {MIN_CONFIDENCE}); is the recording from this session?")
    if max(good) - min(good) > 1:
        die(f"{who}: the two sync directions disagree ({a:+.2f} s vs {-b:+.2f} s)")
    return sum(good) / len(good), max(ca, cb)
