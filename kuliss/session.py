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
from .errors import VoiceError, die
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
    streams: dict[str, int]  # title -> stream index, only the TITLES it has
    length: int  # frames
    video: bool = True


@dataclass
class SyncResult:
    path: Path  # the patched project
    backup: Path
    reference: str  # whose recording is the clock
    offsets: dict[str, tuple[float, float]]  # name -> (s after the reference, confidence)
    added_tracks: list[tuple[str, bool]] = field(default_factory=list)  # (name, audio?)
    seconds: float = 0.0  # analysis time
    left_out: list[str] = field(default_factory=list)  # files not placed (see the warnings)


def probe(path: Path, fps: float) -> Recording | None:
    """Who a recording belongs to (from its file name) and where its streams are; None
    (with a warning) for a file that can't be used. A missing stream only warns."""
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
            titles = {s.metadata.get("title"): s.index for s in container.streams.audio}
            video = bool(container.streams.video)
            length = math.ceil(container.duration / av.time_base * fps)
    except (av.FFmpegError, TypeError) as e:
        log.warning("%s: cannot read it (%s); skipped", path.name, e)
        return None
    streams = {title: titles[title] for title in TITLES if title in titles}
    has = ", ".join(map(str, titles)) or "no audio"
    if "Voice audio" not in streams and "Comms" not in streams:
        log.warning(
            "%s: no audio stream titled Voice audio or Comms to sync on (it has %s); skipped",
            path.name,
            has,
        )
        return None
    missing = [title for title in TITLES if title not in streams] + ([] if video else ["video"])
    if missing:
        log.warning(
            "%s: no %s (it has %s), so no track for that", path.name, ", ".join(missing), has
        )
    return Recording(path, initial, name, streams, length, video)


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

    recordings, left_out = [], []
    for file in sorted((session_dir / "sources").glob("*.mkv")):
        rec = probe(file, project.fps)
        if rec is None:
            left_out.append(file.name)
        else:
            recordings.append(rec)
    if not recordings:
        die(f"no usable recordings in {session_dir / 'sources'} (see the warnings)")
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
    jobs = [
        (rec, title)
        for rec in recordings
        for title in ("Voice audio", "Comms")
        if title in rec.streams
    ]
    with ThreadPoolExecutor(len(jobs)) as pool:
        results = pool.map(
            lambda job: sync.envelope(str(job[0].path), job[0].streams[job[1]]), jobs
        )
        envelopes = {
            (rec.name, title): env for (rec, title), env in zip(jobs, results, strict=True)
        }
    # the clock everyone else is measured against: best one with both streams to sync on
    reference = next(
        (r for r in recordings if {"Voice audio", "Comms"} <= r.streams.keys()), recordings[0]
    )
    offsets = {reference.name: 0.0}
    found: dict[str, tuple[float, float]] = {}
    for rec in recordings:
        if rec is reference:
            continue
        try:
            found[rec.name] = sync.offset(
                envelopes.get((reference.name, "Voice audio")),
                envelopes.get((reference.name, "Comms")),
                envelopes.get((rec.name, "Voice audio")),
                envelopes.get((rec.name, "Comms")),
                rec.name,
            )
        except VoiceError as e:  # one bad file shouldn't stop the others
            log.warning("%s; %s left out, place it by hand", e, rec.path.name)
            left_out.append(rec.path.name)
            continue
        offsets[rec.name] = found[rec.name][0]
    recordings = [r for r in recordings if r.name in offsets]
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
            if (name, is_audio) in tracks or not has(rec, title):
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

    starts: dict[str, int] = {}
    earliest = min(offsets.values())  # whoever started recording first starts at 0
    for rec in recordings:
        bin_id, video, audio = timeline.add_source(
            project, rec.path, rec.length, list(rec.streams.values())
        )
        start = round((offsets[rec.name] - earliest) * project.fps)
        for fmt, is_audio, title in TRACKS:
            if not has(rec, title):
                continue
            producer = audio[rec.streams[title]] if is_audio else video
            timeline.place(
                project, track_name(fmt, rec), is_audio, producer, bin_id, start, rec.length
            )
        starts[rec.name] = start
    # as the crew groups them: every Voice clip together, and each player's game
    # video with its game audio, so they move as one
    timeline.group(
        project,
        [
            (track_name("{name} Voice", r), True, starts[r.name])
            for r in recordings
            if has(r, "Voice audio")
        ],
    )
    for r in recordings:
        if r.video and has(r, "Game audio"):
            timeline.group(
                project,
                [
                    (track_name("{name} Game", r), False, starts[r.name]),
                    (track_name("{i} Game", r), True, starts[r.name]),
                ],
            )
    timeline.collapse_tracks(project)
    backup = timeline.write(project, path, mtime)
    return SyncResult(path, backup, reference.name, found, added, seconds, left_out)


def has(rec: Recording, title: str | None) -> bool:
    """Whether the recording has the stream a TRACKS entry needs (None: the video)."""
    return rec.video if title is None else title in rec.streams
