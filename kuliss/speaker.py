"""kuliss speaker: add a who-we-watch / who-talks overlay to a Kdenlive project.

    a = analyse(project)            # reads the project, finds views and speech
    overlay = render_overlay(a)     # draws <project>-overlay.mkv
    backup = apply(a, overlay)      # patches the project in place

The theme is found next to the project or in any folder above it.
"""

import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

import av
import numpy as np

from . import render, timeline, vad
from .config import BOOKENDS, Player, Theme, load_theme
from .errors import die

MIN_SPAN = 1.0   # s; views shorter than this (flash cuts) don't count as a switch


@dataclass
class Analysis:
    path: Path
    mtime: int                        # the project file's, from before it was read
    proj: timeline.Project
    theme: Theme                      # with only the players present in this project
    players: tuple[Player, ...]       # those, with their sources resolved
    absent: tuple[str, ...]           # theme players with no voice clips here
    painter: render.Painter
    view: np.ndarray                  # per frame: index of the viewed player, -1 for none
    spans: list[tuple[int, int, int]]
    cuts: list[int]                   # frames where the view switches between players
    talking: list[np.ndarray]         # per player, per frame: voice level, 0 when silent
    seconds: float                    # how long the speech analysis took

    def stats(self) -> list[tuple[str, float, float]]:
        """(name, % of the timeline on screen, % talking) per player."""
        return [(p.name, 100 * float((self.view == i).mean()),
                 100 * float((self.talking[i] > 0).mean())) for i, p in enumerate(self.players)]


def find_theme(project: Path) -> Path:
    for d in project.parents:
        if (d / "theme.toml").is_file():
            return d / "theme.toml"
    die(f"no theme.toml next to {project.name} or in any folder above it; "
        "pass one with --theme (see README)")


def sound_frames(path: Path, fps: float) -> int:
    try:
        with av.open(str(path)) as c:
            return max(1, math.ceil(c.duration / av.time_base * fps))
    except (av.FFmpegError, TypeError):
        die(f"cannot read {path}")


def analyse(project: str | Path, theme: str | Path | None = None) -> Analysis:
    """Read the project and work out who is on screen and who talks. Writes nothing."""
    path = Path(project).expanduser().resolve()
    th = load_theme(Path(theme).expanduser().resolve() if theme else find_theme(path))
    proj = timeline.load(path)
    mtime = path.stat().st_mtime_ns
    fps = proj.fps
    here = timeline.present(proj, th.players)
    if not here:
        die("no player has clips on their voice track")
    absent = tuple(p.name for p in th.players if p not in here)
    th = replace(th, players=here)   # whoever missed the session gets no avatar
    players = timeline.with_sources(proj, th.players)
    # load every image and font now: a bad asset should fail in a second, not after the analysis
    painter = render.Painter(th, render.layout(th, proj.width, proj.height))

    view = timeline.view_map(proj, players)
    if (view < 0).all():
        clips = sorted({Path(e.resource).name for t in proj.tracks if not t.audio
                        for e in t.entries if e.resource})
        die("no video clip belongs to any player; the project's "
            f"video clips are: {', '.join(clips)}")
    spots = timeline.bookends(proj.length, fps)
    for key in ("intro_video", "outro_image"):   # full-screen once placed: no view there,
        if getattr(th, key):                     # on the first run as on every later one
            start, _, n = spots[key]
            view[max(start, 0):max(start + n, 0)] = -1
    spans = timeline.view_spans(view, round(MIN_SPAN * fps))
    entries = [timeline.voice_entries(proj, p) for p in players]
    t0 = time.monotonic()
    with ThreadPoolExecutor(len(players)) as pool:
        talking = list(pool.map(lambda e: vad.talking(e, fps, proj.length, th.speech_threshold),
                                entries))
    return Analysis(path, mtime, proj, th, players, absent, painter, view, spans,
                    timeline.cuts(spans), talking, time.monotonic() - t0)


def render_overlay(a: Analysis, preview: float | None = None,
                   progress=lambda done, total: None) -> Path:
    """Draw the overlay next to the project; with `preview`, only its first seconds
    (to <project>-overlay-preview.*). Returns the file."""
    n = a.proj.length if preview is None else min(a.proj.length, round(preview * a.proj.fps))
    ext = render.CODECS[a.theme.codec][0]
    out = a.path.with_name(a.path.stem + ("-overlay" if preview is None else "-overlay-preview")
                           + ext)
    render.render(a.painter, a.theme.codec, a.spans, a.talking, a.proj.rate, n, out, progress)
    return out


def apply(a: Analysis, overlay: Path) -> Path:
    """Patch the project in place with the overlay and the switch sounds. Returns the
    timestamped backup of the project as it was."""
    proj, theme, fps = a.proj, a.theme, a.proj.fps
    shift = round(theme.sound_offset * fps)
    card = timeline.bookends(proj.length, fps)["outro_image"][2]
    media = {k: (p, card if k == "outro_image" else sound_frames(p, fps))
             for k in BOOKENDS if (p := getattr(theme, k))}
    timeline.patch(proj, overlay, render.placement(theme, a.painter.lay, proj.width, proj.height),
                   theme.sound, sound_frames(theme.sound, fps),
                   [c + shift for c in a.cuts if 0 <= c + shift < proj.length], media,
                   min(e.start for p in a.players for e in timeline.voice_entries(proj, p)) / fps)
    return timeline.write(proj, a.path, a.mtime)
