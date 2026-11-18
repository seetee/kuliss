"""kuliss sync: put a session's recordings, in sync, on the session project's tracks.

Each recording in sources/ is <date>_<initial>.mkv (a guest: <date>_<name>.mkv) with
audio streams titled "Comms", "Voice audio" and "Game audio". Each player's voice is
heard in the others' Comms streams, which is what lines the files up.
"""

import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import av

from . import sync, timeline
from .config import CREW_FILE, Mixer, load_crew
from .errors import die
from .notes import TALLY_NAMES

log = logging.getLogger(__name__)

NAMES = dict(TALLY_NAMES)  # initial -> player
CREW = {n.lower(): (i, n) for i, n in TALLY_NAMES}
TRACKS = (  # track name, audio track?, stream title (None: the video)
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
    streams: dict[str, int]  # title -> stream index
    length: int  # frames


@dataclass
class SyncResult:
    path: Path  # the patched project
    backup: Path
    reference: str  # whose recording is the clock
    offsets: dict[str, tuple[float, float]]  # name -> (s after the reference, confidence)
    added_tracks: list[tuple[str, bool]] = field(default_factory=list)  # (name, audio?)
    seconds: float = 0.0  # analysis time


def probe(path: Path, fps: float) -> Recording | None:
    """Who a recording belongs to (from its file name) and where its streams are."""
    match = re.search(r"_([^\W\d_]+)$", path.stem)
    tag = match[1] if match else ""
    if tag.upper() in NAMES:
        initial, name = tag.upper(), NAMES[tag.upper()]
    elif tag.lower() in CREW:
        initial, name = CREW[tag.lower()]
    elif len(tag) > 1:  # a guest: all their tracks carry their name
        initial = name = tag.capitalize()
    else:
        log.warning(
            "%s: the name doesn't end in _<initial> of a known player (%s) or "
            "_<guest name>; skipped",
            path.name,
            ", ".join(NAMES),
        )
        return None
    try:
        with av.open(str(path)) as container:
            streams = {s.metadata.get("title"): s.index for s in container.streams.audio}
            missing = [title for title in TITLES if title not in streams]
            if missing or not container.streams.video:
                die(
                    f"{path.name}: needs a video stream and audio streams titled "
                    f"{', '.join(TITLES)}; it has {', '.join(map(str, streams)) or 'no audio'}"
                )
            length = math.ceil(container.duration / av.time_base * fps)
    except (av.FFmpegError, TypeError) as e:
        die(f"cannot read {path}: {e}")
    return Recording(path, initial, name, streams, length)


def track_name(fmt: str, rec: Recording) -> str:
    """A TRACKS name pattern filled in for one recording, e.g. "{i} Comms" -> "K Comms"."""
    return fmt.format(i=rec.initial, name=rec.name)


def sync_session(session_dir: Path) -> SyncResult:
    """Place sources/*.mkv on the session project's tracks, lined up on the call audio."""
    path = session_dir / f"{session_dir.name}.kdenlive"
    if not path.is_file():
        die(f"no {path.name} in {session_dir} (kuliss new creates it)")
    mtime = path.stat().st_mtime_ns
    project = timeline.load(path)

    recordings = []
    for file in sorted((session_dir / "sources").glob("*.mkv")):
        rec = probe(file, project.fps)
        if rec is not None:
            recordings.append(rec)
    if not recordings:
        die(f"no recordings in {session_dir / 'sources'}")
    files_of: dict[str, list[str]] = {}
    for rec in recordings:
        files_of.setdefault(rec.name, []).append(rec.path.name)
    for name, files in files_of.items():
        if len(files) > 1:  # one track per player: two files would overwrite each other
            die(
                f"{name} has {len(files)} recordings ({', '.join(files)}); join them into "
                "one file or move the extra ones out of sources/"
            )
    tracks = {(t.name, t.audio): t for t in project.tracks}
    for rec in recordings:
        for fmt, is_audio, _ in TRACKS:
            name = track_name(fmt, rec)
            track = tracks.get((name, is_audio))
            if track is not None and track.entries:  # never touch an edit in progress
                die(
                    f"the {name!r} track already has clips; clear the recordings' tracks "
                    "to sync again"
                )

    # loudness envelopes of everyone's own voice and call audio, decoded in parallel
    started = time.monotonic()
    jobs = [(rec, title) for rec in recordings for title in ("Voice audio", "Comms")]
    with ThreadPoolExecutor(len(jobs)) as pool:
        results = pool.map(
            lambda job: sync.envelope(str(job[0].path), job[0].streams[job[1]]), jobs
        )
        envelopes = {
            (rec.name, title): env for (rec, title), env in zip(jobs, results, strict=True)
        }
    reference = recordings[0]  # the clock everyone else is measured against
    offsets = {reference.name: 0.0}
    found: dict[str, tuple[float, float]] = {}
    for rec in recordings[1:]:
        found[rec.name] = sync.offset(
            envelopes[reference.name, "Voice audio"],
            envelopes[reference.name, "Comms"],
            envelopes[rec.name, "Voice audio"],
            envelopes[rec.name, "Comms"],
            rec.name,
        )
        offsets[rec.name] = found[rec.name][0]
    seconds = time.monotonic() - started

    # tracks first, grouped like the former template: all Comms, all Voice, all Game;
    # crew in TALLY_NAMES order, guests last
    crew = load_crew(session_dir.parent / CREW_FILE)
    crew_order = [initial for initial, _ in TALLY_NAMES]

    def rank(rec: Recording) -> int:
        return crew_order.index(rec.initial) if rec.initial in crew_order else len(crew_order)

    added = []
    for fmt, is_audio, title in TRACKS:
        for rec in sorted(recordings, key=rank):
            name = track_name(fmt, rec)
            if (name, is_audio) in tracks:
                continue
            mixer = {
                "Voice audio": crew.voice_of(rec.name),
                "Game audio": Mixer(crew.game_gain),
            }.get(title)
            slug = re.sub(r"\W+", "_", name.lower()) + ("_a" if is_audio else "_v")
            timeline.ensure_track(
                project, is_audio, name, f"kuliss_{slug}", under="Assets", mixer=mixer
            )
            tracks[name, is_audio] = None
            added.append((name, is_audio))

    earliest = min(offsets.values())  # whoever started recording first starts at 0
    for rec in recordings:
        bin_id, video, audio = timeline.add_source(
            project, rec.path, rec.length, [rec.streams[title] for title in TITLES]
        )
        start = round((offsets[rec.name] - earliest) * project.fps)
        for fmt, is_audio, title in TRACKS:
            producer = audio[rec.streams[title]] if is_audio else video
            timeline.place(
                project, track_name(fmt, rec), is_audio, producer, bin_id, start, rec.length
            )
    backup = timeline.write(project, path, mtime)
    return SyncResult(path, backup, reference.name, found, added, seconds)
