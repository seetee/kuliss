"""Where a session stands in the session workflow, read from the files on disk, and the
report text every front end shows after a command. No Qt, nothing stored: the GUI asks
again whenever its window gets focus."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .config import crew_file, nearest_theme
from .errors import VoiceError
from .notes import EPISODE_PREFIX, _locate_session_file, discover, episodes

if TYPE_CHECKING:  # heavy modules; only their results are formatted here
    from .finish import Analysis
    from .scaffold import Scaffolded
    from .session import SyncResult

REOPEN = "If it is open in Kdenlive, reopen it without saving first."


@dataclass
class Episode:
    name: str
    project: Path | None  # None: marked in the session project, not made yet
    finished: bool = False  # has the kuliss overlay track
    start: int | None = None  # its marker's frame in the session project


@dataclass
class State:
    session: Path
    project: Path  # the session's own .kdenlive
    md: Path
    recordings: list[str]  # sources/*.mkv names
    synced: bool
    fps: float = 60.0  # the session project's
    episodes: list[Episode] = field(default_factory=list)  # in marker order, then the rest
    notes_current: bool = False  # the .md is newer than every episode project
    problems: list[str] = field(default_factory=list)  # unreadable projects and the like

    @property
    def theme(self) -> Path | None:
        return nearest_theme(self.session)

    @property
    def crew_file(self) -> Path:
        return crew_file(self.session)

    @property
    def marked(self) -> bool:
        return any(e.start is not None for e in self.episodes)


def pick_session(start: Path) -> Path | None:
    """The session `start` is in, else the newest session_* under it."""
    found = discover(start)  # in natural order, so the newest is last
    return found[-1] if found else None


def _load(project: Path, problems: list[str]):
    from . import timeline  # numpy; only once there is a project to read

    try:
        return timeline.load(project)
    except VoiceError as e:
        problems.append(str(e))
        return None


def markers(project) -> list[tuple[str, int]]:
    """(name, frame) of the session project's guides named avsnitt…: where each episode
    starts, in time order."""
    from .timeline import props

    try:
        guides = json.loads(props(project.seq).get("kdenlive:sequenceproperties.guides") or "[]")
    except json.JSONDecodeError:
        return []
    found = [
        (str(g.get("comment", "")).strip(), int(g.get("pos", 0)))
        for g in guides
        if isinstance(g, dict) and str(g.get("comment", "")).strip().startswith(EPISODE_PREFIX)
    ]
    return sorted(found, key=lambda m: m[1])


def state(session: Path) -> State:
    from .timeline import OLD_TRACK_NAME, TRACK_NAME

    md = _locate_session_file(session)[0]  # as kuliss notes finds it (an old .txt too)
    project = session / f"{session.name}.kdenlive"
    sources = session / "sources"
    s = State(
        session=session,
        project=project,
        md=md,
        recordings=sorted(p.name for p in sources.glob("*.mkv")) if sources.is_dir() else [],
        synced=False,
    )
    main = _load(project, s.problems) if project.is_file() else None
    if main:
        s.synced, s.fps = any(t.entries for t in main.tracks), main.fps
        s.episodes = [Episode(name, None, start=start) for name, start in markers(main)]
    found, skipped = episodes(session)
    s.problems += skipped
    by_name = {e.name: e for e in s.episodes}
    for name, path in found:
        proj = _load(path, s.problems)
        names = {t.name for t in proj.tracks if not t.audio} if proj else set()
        episode = by_name.get(name) or Episode(name, None)
        episode.project, episode.finished = path, bool(names & {TRACK_NAME, OLD_TRACK_NAME})
        if name not in by_name:
            s.episodes.append(episode)
    if md.is_file() and found:
        newest = max(path.stat().st_mtime_ns for _, path in found)
        s.notes_current = md.stat().st_mtime_ns >= newest
    return s


def clock(frame: int, fps: float) -> str:
    """A timeline position as H:MM:SS."""
    seconds = int(frame / fps)
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


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
    lines.append(updated_report(res.path, res.backup))
    return lines


def preview_report(overlay: Path) -> str:
    return f"Preview written: {overlay}"


def updated_report(project: Path, backup: Path) -> str:
    return f"Updated {project.name} (backup: {backup.name}). {REOPEN}"


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
