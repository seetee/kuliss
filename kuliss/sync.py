"""Line up recordings of one session by their audio. Kdenlive-free."""

import logging

import numpy as np

from .errors import die
from .vad import RATE, decode

log = logging.getLogger(__name__)

ENV_RATE = 100  # Hz; the envelope's 10 ms steps are the sync resolution
SPAN = 30 * 60  # s of each recording compared; the crew overlaps well within this
MIN_CONFIDENCE = 10  # correlation peak / std: session 28's matches scored 24-35, a non-match 3.6


def envelope(path: str, stream: int, seconds: float = SPAN) -> np.ndarray:
    """Normalised log loudness of one audio stream at ENV_RATE."""
    pcm = decode(path, stream, 0.0, seconds)
    hop = RATE // ENV_RATE  # samples per envelope step
    loud = np.log1p(np.abs(pcm[: len(pcm) // hop * hop]).reshape(-1, hop).mean(1) * 1000)
    return (loud - loud.mean()) / (loud.std() + 1e-9)


def lag(ref: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    """(s, confidence): x[t] lines up with ref[t + s]. Cross-correlation via FFT."""
    size = 1 << int(np.ceil(np.log2(len(ref) + len(x))))  # a power of two, no wrap-around
    corr = np.fft.irfft(np.fft.rfft(ref, size) * np.conj(np.fft.rfft(x, size)), size)
    peak = int(np.argmax(corr))
    steps = peak - size if peak > size // 2 else peak  # the second half holds negative lags
    return steps / ENV_RATE, float(corr[peak] / corr.std())


def offset(
    ref_voice: np.ndarray | None,
    ref_comms: np.ndarray | None,
    voice: np.ndarray | None,
    comms: np.ndarray | None,
    who: str,
) -> tuple[float, float]:
    """(s, confidence): where `who`'s recording starts on the reference recording's clock.
    Each side's voice is heard in the other's call audio, late by the call's delay;
    averaging both directions cancels that delay. A missing stream (None) leaves one
    direction, which is late by the call delay (a fraction of a second)."""
    tries = []  # (s, confidence)
    if ref_comms is not None and voice is not None:
        seconds, conf = lag(ref_comms, voice)  # offset + delay
        tries.append((seconds, conf))
    if comms is not None and ref_voice is not None:
        seconds, conf = lag(comms, ref_voice)  # delay - offset
        tries.append((-seconds, conf))
    if not tries:
        die(f"{who}: no stream pair to sync on (their Voice audio and the other's Comms)")
    good = [(seconds, conf) for seconds, conf in tries if conf >= MIN_CONFIDENCE]
    if not good:
        found = " and ".join(f"{conf:.0f}" for _, conf in tries)
        die(
            f"{who}: cannot find their voice in the call audio (confidence {found}, need "
            f"{MIN_CONFIDENCE}); is the recording from this session?"
        )
    if len(good) == 2 and abs(good[0][0] - good[1][0]) > 1:
        log.warning(
            "%s: the two sync directions disagree (%+.2f s vs %+.2f s); used the surer one, "
            "check it by ear",
            who,
            good[0][0],
            good[1][0],
        )
        good = [max(good, key=lambda g: g[1])]
    elif len(tries) == 1:
        log.warning("%s: synced one way only, so it may be a fraction of a second late", who)
    return sum(g[0] for g in good) / len(good), max(conf for _, conf in tries)
