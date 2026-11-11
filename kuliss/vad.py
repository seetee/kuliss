"""Who is talking: Silero VAD over each player's voice clips, as edited."""

from typing import TYPE_CHECKING

import av
import numpy as np
from silero_vad_lite import SileroVAD

from .errors import die

if TYPE_CHECKING:  # decode/speech_windows stay Kdenlive-free for Klatch
    from .timeline import Entry

RATE = 16000
WINDOW = 512        # samples per Silero call at 16 kHz (32 ms)
ON = 0.35           # speech probability that starts "talking"; it ends below OFF_RATIO * ON
OFF_RATIO = 0.6
HANGOVER = 0.20     # s kept "talking" after the probability drops (bridges short pauses)
MIN_BURST = 0.06    # s; shorter bursts (clicks, key presses) are dropped. Short words
#                     ("ja", "nä") must survive: 0.12 lost one burst in ten on real voices
LEAD = 2            # windows the marker starts before the detected onset (first syllables)
WARMUP = 0.5        # s decoded before a clip's first frame, so Silero isn't cold at a cut
LEVEL_RANGE = 30    # dB below a clip's loud speech that still moves the level


def decode(path: str, stream: int, start: float, dur: float) -> np.ndarray:
    """Mono float32 at RATE for [start, start+dur) seconds of one audio stream."""
    try:
        with av.open(path) as c:
            st = c.streams[stream]
            if st.type != "audio":
                die(f"{path}: stream {stream} is {st.type}, not audio")
            c.seek(int(start / st.time_base), stream=st)   # lands at or before start
            rs = av.AudioResampler(format="flt", layout="mono", rate=RATE)
            chunks, first, got = [], None, 0
            for frame in c.decode(st):
                if frame.pts is None:
                    continue
                if first is None:
                    first = float(frame.pts * frame.time_base)
                for r in rs.resample(frame):
                    chunks.append(r.to_ndarray()[0])
                    got += chunks[-1].size
                if first + got / RATE >= start + dur:
                    break
    except av.FFmpegError as e:
        die(f"cannot decode {path}: {e}")
    pcm = np.concatenate(chunks) if chunks else np.zeros(0, np.float32)
    # the seek can land anywhere at or before start, including pts 0 (one big
    # cluster), so trim from where decoding actually began
    skip = max(0, round((start - (start if first is None else first)) * RATE))
    return pcm[skip:skip + round(dur * RATE)]


def smooth(probs: np.ndarray, on_at: float = ON) -> np.ndarray:
    """Speech probability per window -> talking yes/no per window."""
    hang = round(HANGOVER * RATE / WINDOW)
    off_at = on_at * OFF_RATIO
    on = np.zeros(len(probs), bool)
    state, left = False, 0
    for i, p in enumerate(probs):
        if p >= on_at:
            state, left = True, hang
        elif state and p < off_at:
            left -= 1
            state = left > 0
        on[i] = state
    edges = np.flatnonzero(np.diff(np.r_[0, on.astype(np.int8), 0]))
    for s, e in zip(edges[::2], edges[1::2], strict=True):
        if (e - s - hang) * WINDOW / RATE < MIN_BURST:
            on[s:e] = False
        else:
            on[max(s - LEAD, 0):s] = True
    return on


def speech_windows(pcm: np.ndarray, on_at: float = ON) -> np.ndarray:
    """Per WINDOW samples of mono float32 at RATE: is it speech?"""
    vad = SileroVAD(RATE)
    n = len(pcm) // WINDOW
    probs = np.fromiter((vad.process(memoryview(pcm[i * WINDOW:(i + 1) * WINDOW]))
                         for i in range(n)), np.float32, n)
    return smooth(probs, on_at)


def window_levels(pcm: np.ndarray, speech: np.ndarray) -> np.ndarray:
    """Voice level per window: 0 where there is no speech, else 0..1 on a dB scale
    relative to this clip's loud speech (so a quiet mic moves as much as a loud one)."""
    n = len(speech)
    out = np.zeros(n, np.float32)
    if not speech.any():
        return out
    db = 10 * np.log10((pcm[:n * WINDOW].reshape(n, WINDOW) ** 2).mean(1) + 1e-12)
    top = np.percentile(db[speech], 95)
    out[speech] = np.clip(1 + (db[speech] - top) / LEVEL_RANGE, 0.05, 1)
    return out


# shortcut: no cross-track bleed check; each player has their own mic track and wears
# headphones (measured on avsnitt215: -60 dBFS while only the others talk). Add one
# (compare simultaneous windows' level across players) if someone starts using speakers.
def talking(entries: list["Entry"], fps: float, length: int, on_at: float = ON) -> np.ndarray:
    """Per timeline frame: this player's voice level, 0 when not talking."""
    out = np.zeros(length, np.float32)
    for e in entries:
        n = min(e.length, length - e.start)
        if n <= 0:
            continue
        lead = min(WARMUP, e.src_in / fps)
        pcm = decode(e.resource, e.audio_index, e.src_in / fps - lead, n / fps + lead)
        speech = speech_windows(pcm, on_at)
        if not len(speech):
            continue
        idx = np.minimum(((np.arange(n) / fps + lead) * RATE / WINDOW).astype(int),
                         len(speech) - 1)
        seg = out[e.start:e.start + n]
        np.maximum(seg, window_levels(pcm, speech)[idx], out=seg)
    return out
