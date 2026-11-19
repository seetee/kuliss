"""Where a session stands in the session workflow, read from the files on disk, and the
report text every front end shows after a command. No Qt, nothing stored: the GUI asks
again whenever its window gets focus."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .config import CREW_FILE, nearest_theme
from .errors import VoiceError
from .notes import _natural_key, episodes, is_session_dir

if TYPE_CHECKING:  # heavy modules; only their results are formatted here
    from .finish import Analysis
    from .scaffold import Scaffolded
    from .session import SyncResult

REOPEN = "If it is open in Kdenlive, reopen it without saving first."
PLACEHOLDER = re.compile(r"^avsnittXX\d+$")  # the episode folder kuliss new makes


@dataclass
class Episode:
    name: str
    project: Path
    finished: bool  # has the kuliss overlay track


@dataclass
class State:
    session: Path
    root: Path  # the folder holding the session_* dirs
    project: Path  # the session's own .kdenlive
    md: Path
    recordings: list[str]  # sources/*.mkv names
    synced: bool
    episodes: list[Episode] = field(default_factory=list)
    notes_current: bool = False  # the .md is newer than every episode project
    problems: list[str] = field(default_factory=list)  # unreadable projects and the like

    @property
    def theme(self) -> Path | None:
        return nearest_theme(self.session)

    @property
    def crew_file(self) -> Path:
        return self.root / CREW_FILE

    @property
    def cut(self) -> bool:
        """At least one episode renamed from the avsnittXX<nr> placeholder."""
        return any(not PLACEHOLDER.match(e.name) for e in self.episodes)


def pick_session(start: Path) -> Path | None:
    """The session `start` is in, else the newest session_* under it."""
    for candidate in (start, *start.parents):
        if is_session_dir(candidate):
            return candidate
    children = [d for d in start.iterdir() if d.is_dir() and d.name.startswith("session_")]
    return max(children, key=lambda d: _natural_key(d.name), default=None)


def _tracks(project: Path, problems: list[str]):
    from . import timeline  # numpy; only once there is a project to read

    try:
        return timeline.load(project).tracks
    except VoiceError as e:
        problems.append(str(e))
        return []


def state(session: Path) -> State:
    from .timeline import OLD_TRACK_NAME, TRACK_NAME

    md = next(iter(sorted(session.glob("session_*.md"))), session / f"{session.name}.md")
    project = session / f"{session.name}.kdenlive"
    sources = session / "sources"
    s = State(
        session=session,
        root=session.parent,
        project=project,
        md=md,
        recordings=sorted(p.name for p in sources.glob("*.mkv")) if sources.is_dir() else [],
        synced=False,
    )
    if project.is_file():
        s.synced = any(t.entries for t in _tracks(project, s.problems))
    found, skipped = episodes(session)
    s.problems += skipped
    for name, path in found:
        names = {t.name for t in _tracks(path, s.problems) if not t.audio}
        s.episodes.append(Episode(name, path, bool(names & {TRACK_NAME, OLD_TRACK_NAME})))
    if md.is_file() and found:
        newest = max(path.stat().st_mtime_ns for _, path in found)
        s.notes_current = md.stat().st_mtime_ns >= newest
    return s


def new_report(made: Scaffolded) -> list[str]:
    files = f"{made.dir.name}.md" + (f", {made.project.name}" if made.project else "")
    lines = [f"created {made.dir}", f"  {made.episode}/, kortisar/, sources/, {files}"]
    if made.warning:
        lines.insert(0, f"warning: {made.warning}")
    return lines


def sync_report(res: SyncResult) -> list[str]:
    lines = [
        f"{res.path.name}: synced {len(res.offsets) + 1} recordings on their call audio "
        f"in {res.seconds:.0f} s",
        f"  {res.reference:<10} reference",
    ]
    lines += [
        f"  {name:<10} {seconds:+9.2f} s   (confidence {confidence:.0f})"
        for name, (seconds, confidence) in res.offsets.items()
    ]
    lines += [
        f"  added the {'audio' if audio else 'video'} track {name!r}"
        for name, audio in res.added_tracks
    ]
    if res.left_out:
        lines.append(f"  left out (see the warnings): {', '.join(res.left_out)}")
    lines.append(f"Updated {res.path.name} (backup: {res.backup.name}). {REOPEN}")
    return lines


def analysis_report(analysis: Analysis) -> list[str]:
    fps = analysis.proj.fps
    lines = []
    if analysis.absent:
        lines.append("Not in this project (no voice clips): " + ", ".join(analysis.absent))
    lines.append(
        f"{analysis.path.name}: {analysis.proj.length / fps / 60:.1f} min, "
        f"{len(analysis.cuts)} view switches"
    )
    lines.append(f"  speech detected in {analysis.seconds:.0f} s")
    lines += [
        f"  {name:<12} on screen {on_screen:4.1f}%   talking {talking:4.1f}%"
        for name, on_screen, talking in analysis.stats()
    ]
    return lines
