"""kuliss finish: the who-we-watch / who-talks overlay, a sound at every switch, and
the intro and outro, added to a Kdenlive episode project.

    analysis = analyse(project)     # reads the project, finds views and speech
    overlay = render_overlay(analysis)   # draws <project>-overlay.mkv
    backup = apply(analysis, overlay)    # patches the project in place
    still(project)                       # or only a picture of the theme, in a second

The theme is found next to the project or in any folder above it.
"""

import logging
import math
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

import av
import numpy as np
import skia

from . import render, timeline, vad
from .config import BOOKENDS, Player, Theme, load_theme, nearest_theme
from .errors import die
from .files import write_atomic

log = logging.getLogger(__name__)

MIN_SPAN = 1.0  # s; views shorter than this (flash cuts) don't count as a switch


@dataclass
class Analysis:
    path: Path
    mtime: int  # the project file's, from before it was read
    proj: timeline.Project
    theme: Theme  # with only the players present in this project
    players: tuple[Player, ...]  # those, with their sources resolved
    absent: tuple[str, ...]  # theme players with no voice clips here
    painter: render.Painter
    view: np.ndarray  # per frame: index of the viewed player, -1 for none
    spans: list[tuple[int, int, int]]
    cuts: list[int]  # frames where the view switches between players
    talking: list[np.ndarray]  # per player, per frame: voice level, 0 when silent
    seconds: float  # how long the speech analysis took

    def stats(self) -> list[tuple[str, float, float]]:
        """(name, % of the timeline on screen, % talking) per player."""
        return [
            (
                p.name,
                100 * float((self.view == i).mean()),
                100 * float((self.talking[i] > 0).mean()),
            )
            for i, p in enumerate(self.players)
        ]


def find_theme(project: Path) -> Path:
    return nearest_theme(project.parent) or die(
        f"no theme.toml next to {project.name} or in any folder above it; "
        "pass one with --theme (see README)"
    )


def sound_frames(path: Path, fps: float) -> int:
    """How many timeline frames a media file lasts."""
    try:
        with av.open(str(path)) as container:
            return max(1, math.ceil(container.duration / av.time_base * fps))
    except (av.FFmpegError, TypeError):
        die(f"cannot read {path}")


def _load(project: str | Path, theme_file: str | Path | None):
    """The project, its theme cut to the players present, and the painter."""
    path = Path(project).expanduser().resolve()
    theme = load_theme(Path(theme_file).expanduser().resolve() if theme_file else find_theme(path))
    proj = timeline.load(path)
    mtime = path.stat().st_mtime_ns
    here = timeline.present(proj, theme.players)
    if not here:
        die("no player has clips on their voice track")
    absent = tuple(p.name for p in theme.players if p not in here)
    theme = replace(theme, players=here)  # whoever missed the session gets no avatar
    players = timeline.with_sources(proj, theme.players)
    # load every image and font now: a bad asset should fail in a second, not after the analysis
    painter = render.Painter(theme, render.layout(theme, proj.width, proj.height))
    return path, mtime, proj, theme, players, absent, painter


def analyse(project: str | Path, theme_file: str | Path | None = None) -> Analysis:
    """Read the project and work out who is on screen and who talks. Writes nothing."""
    path, mtime, proj, theme, players, absent, painter = _load(project, theme_file)
    fps = proj.fps
    view = timeline.view_map(proj, players)
    if (view < 0).all():
        clips = sorted(
            {
                Path(e.resource).name
                for t in proj.tracks
                if not t.audio
                for e in t.entries
                if e.resource
            }
        )
        die(
            "no video clip belongs to any player; the project's "
            f"video clips are: {', '.join(clips)}"
        )
    spots = timeline.bookends(proj.length, fps)
    for key in ("intro_video", "outro_image"):  # full-screen once placed: no view there,
        if getattr(theme, key):  # on the first run as on every later one
            start, _, n = spots[key]
            view[max(start, 0) : max(start + n, 0)] = -1
    spans = timeline.view_spans(view, round(MIN_SPAN * fps))
    entries = [timeline.voice_entries(proj, p) for p in players]
    t0 = time.monotonic()
    with ThreadPoolExecutor(len(players)) as pool:
        talking = list(
            pool.map(lambda e: vad.talking(e, fps, proj.length, theme.speech_threshold), entries)
        )
    return Analysis(
        path,
        mtime,
        proj,
        theme,
        players,
        absent,
        painter,
        view,
        spans,
        timeline.cuts(spans) if theme.show_view else [],
        talking,
        time.monotonic() - t0,
    )


def still(project: str | Path, theme_file: str | Path | None = None) -> Path:
    """A picture of the overlay over a frame of the project's first view, three times:
    nobody talks; someone talks; the viewed player talks. No speech analysis and no
    encoding, so a theme can be tried in a second. Writes <project>-overlay-still.png."""
    path, _, proj, theme, players, _, painter = _load(project, theme_file)
    w, h = proj.width, proj.height
    background = np.full((h, w, 4), (90, 90, 90, 255), np.uint8)  # when no frame can be read
    view = timeline.view_map(proj, players)
    shown = np.flatnonzero(view >= 0)
    who = 0  # whose view the frame shows
    if shown.size:  # the middle of the first view: its start may still be black
        start = int(shown[0])
        who = int(view[start])
        later = view[start:] != who
        f = start + (int(np.argmax(later)) if later.any() else later.size) // 2
        e = next(
            e
            for t in reversed(proj.tracks)  # topmost first: the clip view_map chose
            if not t.audio and not t.hidden
            for e in t.entries
            if e.start <= f < e.start + e.length
            and timeline.player_of(e.resource, players) is not None
        )
        grabbed = _grab(e.resource, (e.src_in + f - e.start) / proj.fps, w, h)
        if grabbed is None:
            log.warning("could not read a frame of %s; the still has a grey background", e.resource)
        else:
            background = grabbed
    other = (who + 1) % len(players)  # who itself when alone

    def talks(i: int) -> np.ndarray:  # only player i talks, at a typical voice level
        level = tuple(0.7 * (j == i) for j in range(len(players)))
        return painter.draw(1.0, -1, who, 1.0, level, level)

    states = [talks(-1), talks(other), talks(who)]
    x, y, _, _ = render.placement(theme, painter.lay, w, h)
    sheet = np.concatenate([render.over(background.copy(), s, x, y) for s in states])
    out = path.with_name(path.stem + "-overlay-still.png")
    png = bytes(skia.Image.fromarray(sheet, colorType=skia.kBGRA_8888_ColorType).encodeToData())
    try:
        write_atomic(out, lambda tmp: tmp.write_bytes(png))
    except OSError as e:
        die(f"cannot write {out}: {e.strerror}")
    return out


def _grab(resource: str, seconds: float, w: int, h: int) -> np.ndarray | None:
    """One BGRA frame of a video file at or just after `seconds`, scaled to w x h."""
    try:
        with av.open(resource) as c:
            st = c.streams.video[0]
            c.seek(int(seconds / st.time_base), stream=st)
            frame = None
            for frame in c.decode(st):
                if frame.pts is not None and frame.pts * frame.time_base >= seconds:
                    break
            return None if frame is None else frame.to_ndarray(format="bgra", width=w, height=h)
    except (av.FFmpegError, IndexError, OSError):
        return None


def render_overlay(
    analysis: Analysis,
    preview: float | None = None,
    progress: Callable[[int, int], None] = lambda done, total: None,
) -> Path:
    """Draw the overlay next to the project; with `preview`, only its first seconds
    (to <project>-overlay-preview.*). Returns the file."""
    proj, theme = analysis.proj, analysis.theme
    frames = proj.length if preview is None else min(proj.length, round(preview * proj.fps))
    suffix = "-overlay" if preview is None else "-overlay-preview"
    out = analysis.path.with_name(analysis.path.stem + suffix + render.CODECS[theme.codec][0])
    render.render(
        analysis.painter,
        theme.codec,
        analysis.spans,
        analysis.talking,
        proj.rate,
        frames,
        out,
        progress,
    )
    return out


def apply(analysis: Analysis, overlay: Path) -> Path:
    """Patch the project in place with the overlay and the switch sounds. Returns the
    timestamped backup of the project as it was."""
    proj, theme, fps = analysis.proj, analysis.theme, analysis.proj.fps
    shift = round(theme.sound_offset * fps)
    sounds_at = [cut + shift for cut in analysis.cuts if 0 <= cut + shift < proj.length]
    card_frames = timeline.bookends(proj.length, fps)["outro_image"][2]
    media = {}  # intro/outro key -> (file, frames), for the ones the theme names
    for key in BOOKENDS:
        file = getattr(theme, key)
        if file:
            media[key] = (file, card_frames if key == "outro_image" else sound_frames(file, fps))
    first_voice = min(
        entry.start for player in analysis.players for entry in timeline.voice_entries(proj, player)
    )
    rect = render.placement(theme, analysis.painter.lay, proj.width, proj.height)
    timeline.patch(
        proj,
        overlay,
        rect,
        theme.sound,
        sound_frames(theme.sound, fps) if theme.sound else 0,
        sounds_at,
        media,
        first_voice / fps,
    )
    return timeline.write(proj, analysis.path, analysis.mtime)
