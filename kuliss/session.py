"""kuliss sync: put a session's recordings, in sync, on the session project's tracks.

Each recording in sources/ is <date>_<initial>.mkv (a guest: <date>_<name>.mkv) with
audio streams titled "Comms", "Voice audio" and "Game audio". Each player's voice is
heard in the others' Comms streams, which is what lines the files up.
"""

import logging
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import av

from . import sync, timeline
from .config import CREW_FILE, Crew, Mixer, load_crew
from .errors import die
from .notes import TALLY_NAMES

log = logging.getLogger(__name__)

NAMES = dict(TALLY_NAMES)   # initial -> player
CREW = {n.lower(): (i, n) for i, n in TALLY_NAMES}
TRACKS = (   # track name, audio track?, stream title (None: the video)
    ("{i} Comms", True, "Comms"),
    ("{name} Voice", True, "Voice audio"),
    ("{i} Game", True, "Game audio"),
    ("{name} Game", False, None),
)
TITLES = [t for _, _, t in TRACKS if t]


@dataclass
class Recording:
    path: Path
    initial: str
    name: str
    streams: dict[str, int]   # title -> stream index
    length: int               # frames


@dataclass
class SyncResult:
    path: Path                                  # the patched project
    backup: Path
    reference: str                              # whose recording is the clock
    offsets: dict[str, tuple[float, float]]     # name -> (s after the reference, confidence)
    added_tracks: list[tuple[str, bool]] = field(default_factory=list)   # (name, audio?)
    seconds: float = 0.0                        # analysis time


def create_project(dest: Path, crew: Crew) -> None:
    """A new, empty session project: the Assets tracks, which the intro and outro go
    on (`kuliss speaker`), and the crew's master volume. `kuliss sync` adds the rest."""
    proj = timeline.new_project(dest)
    timeline._ensure_track(proj, True, timeline.ASSETS, "assets_audio", mixer=Mixer(crew.assets_gain))
    timeline._ensure_track(proj, False, timeline.ASSETS, "assets_video")
    timeline.master(proj, Mixer(crew.master_gain))
    tmp = dest.with_name(dest.name + ".partial")
    try:
        timeline.save(proj, tmp)
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def probe(path: Path, fps: float) -> Recording | None:
    m = re.search(r"_([^\W\d_]+)$", path.stem)
    tag = m[1] if m else ""
    if tag.upper() in NAMES:
        i, name = tag.upper(), NAMES[tag.upper()]
    elif tag.lower() in CREW:
        i, name = CREW[tag.lower()]
    elif len(tag) > 1:   # a guest: all their tracks carry their name
        i = name = tag.capitalize()
    else:
        log.warning("%s: the name doesn't end in _<initial> of a known player (%s) or "
                    "_<guest name>; skipped", path.name, ", ".join(NAMES))
        return None
    try:
        with av.open(str(path)) as c:
            streams = {s.metadata.get("title"): s.index for s in c.streams.audio}
            missing = [t for t in TITLES if t not in streams]
            if missing or not c.streams.video:
                die(f"{path.name}: needs a video stream and audio streams titled "
                    f"{', '.join(TITLES)}; it has {', '.join(map(str, streams)) or 'no audio'}")
            length = math.ceil(c.duration / av.time_base * fps)
    except (av.FFmpegError, TypeError) as e:
        die(f"cannot read {path}: {e}")
    return Recording(path, i, name, streams, length)


def sync_session(session_dir: Path) -> SyncResult:
    """Place sources/*.mkv on the session project's tracks, lined up on the call audio."""
    path = session_dir / f"{session_dir.name}.kdenlive"
    if not path.is_file():
        die(f"no {path.name} in {session_dir} (kuliss new creates it)")
    mtime = path.stat().st_mtime_ns
    proj = timeline.load(path)
    recs = [r for f in sorted((session_dir / "sources").glob("*.mkv"))
            if (r := probe(f, proj.fps))]
    if not recs:
        die(f"no recordings in {session_dir / 'sources'}")
    tracks = {(t.name, t.audio): t for t in proj.tracks}
    for r in recs:
        for fmt, audio, _ in TRACKS:
            name = fmt.format(i=r.initial, name=r.name)
            t = tracks.get((name, audio))
            if t is not None and t.entries:   # never touch an edit in progress
                die(f"the {name!r} track already has clips; clear the recordings' tracks "
                    "to sync again")

    t0 = time.monotonic()
    keys = [(r, t) for r in recs for t in ("Voice audio", "Comms")]
    with ThreadPoolExecutor(len(keys)) as pool:
        env = dict(zip(((r.name, t) for r, t in keys),
                       pool.map(lambda k: sync.envelope(str(k[0].path), k[0].streams[k[1]]),
                                keys), strict=True))
    ref = recs[0]
    offsets, found, added = {ref.name: 0.0}, {}, []
    for r in recs[1:]:
        found[r.name] = sync.offset(env[ref.name, "Voice audio"], env[ref.name, "Comms"],
                                    env[r.name, "Voice audio"], env[r.name, "Comms"], r.name)
        offsets[r.name] = found[r.name][0]
    seconds = time.monotonic() - t0

    # tracks first, grouped like the former template: all Comms, all Voice, all Game
    crew = load_crew(session_dir.parent / CREW_FILE)
    order = [i for i, _ in TALLY_NAMES]
    for fmt, is_audio, title in TRACKS:
        for r in sorted(recs, key=lambda r: order.index(r.initial) if r.initial in order else 99):
            name = fmt.format(i=r.initial, name=r.name)
            if (name, is_audio) in tracks:
                continue
            mixer = {"Voice audio": crew.voice_of(r.name),
                     "Game audio": Mixer(crew.game_gain)}.get(title)
            slug = re.sub(r"\W+", "_", name.lower()) + ("_a" if is_audio else "_v")
            timeline._ensure_track(proj, is_audio, name, f"kuliss_{slug}", under="Assets",
                                   mixer=mixer)
            tracks[name, is_audio] = None
            added.append((name, is_audio))

    first = min(offsets.values())
    for r in recs:
        kid, video, audio = timeline.add_source(proj, r.path, r.length,
                                                [r.streams[t] for t in TITLES])
        start = round((offsets[r.name] - first) * proj.fps)
        for fmt, is_audio, title in TRACKS:
            timeline.place(proj, fmt.format(i=r.initial, name=r.name), is_audio,
                           audio[r.streams[title]] if is_audio else video, kid, start, r.length)
    return SyncResult(path, timeline.write(proj, path, mtime), ref.name, found, added, seconds)
