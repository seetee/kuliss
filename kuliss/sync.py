"""Line up recordings of one session by their audio. Kdenlive-free, so Klatch can use it."""

import numpy as np

from .errors import die
from .vad import RATE, decode

ENV_RATE = 100      # Hz; the envelope's 10 ms steps are the sync resolution
SPAN = 30 * 60      # s of each recording compared; the crew overlaps well within this
MIN_CONFIDENCE = 10  # correlation peak / std: session 28's matches scored 24-35, a non-match 3.6


def envelope(path: str, stream: int, seconds: float = SPAN) -> np.ndarray:
    """Normalised log loudness of one audio stream at ENV_RATE."""
    pcm = decode(path, stream, 0.0, seconds)
    hop = RATE // ENV_RATE   # samples per envelope step
    loud = np.log1p(np.abs(pcm[:len(pcm) // hop * hop]).reshape(-1, hop).mean(1) * 1000)
    return (loud - loud.mean()) / (loud.std() + 1e-9)


def lag(ref: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    """(s, confidence): x[t] lines up with ref[t + s]. Cross-correlation via FFT."""
    size = 1 << int(np.ceil(np.log2(len(ref) + len(x))))   # a power of two, no wrap-around
    corr = np.fft.irfft(np.fft.rfft(ref, size) * np.conj(np.fft.rfft(x, size)), size)
    peak = int(np.argmax(corr))
    steps = peak - size if peak > size // 2 else peak   # the second half holds negative lags
    return steps / ENV_RATE, float(corr[peak] / corr.std())


def offset(ref_voice: np.ndarray, ref_comms: np.ndarray, voice: np.ndarray, comms: np.ndarray,
           who: str) -> tuple[float, float]:
    """(s, confidence): where `who`'s recording starts on the reference recording's clock.
    Each side's voice is heard in the other's call audio, late by the call's delay;
    averaging both directions cancels that delay."""
    theirs_in_ref, conf_a = lag(ref_comms, voice)    # offset + delay
    ref_in_theirs, conf_b = lag(comms, ref_voice)    # delay - offset
    good = [seconds for seconds, conf in ((theirs_in_ref, conf_a), (-ref_in_theirs, conf_b))
            if conf >= MIN_CONFIDENCE]
    if not good:
        die(f"{who}: cannot find their voice in the call audio (confidence {conf_a:.0f} and "
            f"{conf_b:.0f}, need {MIN_CONFIDENCE}); is the recording from this session?")
    if max(good) - min(good) > 1:
        die(f"{who}: the two sync directions disagree "
            f"({theirs_in_ref:+.2f} s vs {-ref_in_theirs:+.2f} s)")
    return sum(good) / len(good), max(conf_a, conf_b)
