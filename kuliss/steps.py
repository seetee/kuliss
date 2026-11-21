"""Where a session stands in the session workflow, read from the files on disk, and the
report text every front end shows after a command. No Qt, nothing stored: the GUI asks
again whenever its window gets focus."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING

from . import config
from .config import BOOKENDS, CREW_FILE, Crew, Theme, crew_file, nearest_theme
from .errors import VoiceError, die
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


@dataclass
class Recording:
    file: str
    player: str  # "" when sync can't tell whose it is
    streams: set[str]  # the stream titles sync uses that it has, plus "video"
    seconds: float
    note: str  # why sync skips it or leaves a track out ("" when complete)


def recordings(session: Path) -> list[Recording]:
    """sources/*.mkv as sync will see them: whose, which streams, how long. Reads only
    the files' headers; probe's warnings become each row's note instead of the log."""
    files = sorted((session / "sources").glob("*.mkv"))
    if not files:
        return []
    from . import session as sync_mod  # PyAV; only once there are files

    notes: list[str] = []
    catch = logging.Handler()
    catch.emit = lambda record: notes.append(record.getMessage())
    sync_mod.log.addHandler(catch)
    sync_mod.log.propagate = False  # shortcut: not thread-safe; the GUI never reads during a job
    rows = []
    try:
        for path in files:
            notes.clear()
            rec = sync_mod.probe(path, 100.0)
            note = notes[0].removeprefix(f"{path.name}: ") if notes else ""
            if rec is None:
                rows.append(Recording(path.name, "", set(), 0.0, note))
                continue
            streams = set(rec.streams) | ({"video"} if rec.video else set())
            rows.append(Recording(path.name, rec.name, streams, rec.length / 100, note))
    finally:
        sync_mod.log.removeHandler(catch)
        sync_mod.log.propagate = True
    return rows


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


# ── the Settings pages: what the theme and the crew file hold, in order of use ──

# every theme key but the players (their own table) and `assets` (already applied to the paths)
THEME_ORDER = (
    "avatars",
    "show_view",
    "position",
    "orientation",
    "avatar_size",
    "margin",
    "offset",
    "backdrop",
    "font",
    "sound",
    "sound_offset",
    *BOOKENDS,
    "speech_threshold",
    "codec",
)
CREW_ORDER = ("archive", "master_gain", "assets_gain", "game_gain")  # + software, voice tables
EXAMPLES = {"theme": "theme.example.toml", "crew": "crew.example.toml"}


def _shown(value) -> str:
    if value is None:
        return "–"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, Path):
        return value.name
    if isinstance(value, tuple):
        return ", ".join(map(str, value))
    return str(value)


def _quietly(read, path: Path):
    """read(path), with the config warnings (unknown keys and the like) returned as
    problems for the page instead of going to the log: the page is re-read on every focus."""
    problems: list[str] = []

    class Catch(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            problems.append(record.getMessage())

    logger, catch = logging.getLogger(config.__name__), Catch()
    logger.addHandler(catch)
    logger.propagate = False
    try:
        return read(path), problems
    except VoiceError as e:
        return None, [*problems, str(e)]
    finally:
        logger.removeHandler(catch)
        logger.propagate = True


def read_theme(path: Path) -> tuple[Theme | None, list[str]]:
    """The theme, or None if it doesn't load; and what is wrong with it."""
    return _quietly(config.load_theme, path)


def read_crew(path: Path) -> tuple[Crew | None, list[str]]:
    return _quietly(config.load_crew, path)


def theme_rows(theme: Theme) -> list[tuple[str, str, str]]:
    """(key, value, default) for every theme key but the players, in order of use."""
    defaults = {f.name: f.default for f in fields(Theme)}
    return [(k, _shown(getattr(theme, k)), _shown(defaults.get(k))) for k in THEME_ORDER]


def crew_rows(crew: Crew) -> list[tuple[str, str, str]]:
    defaults = {f.name: f.default for f in fields(Crew)}
    return [(k, _shown(getattr(crew, k)), _shown(defaults.get(k))) for k in CREW_ORDER]


def theme_target(session: Path | None, root: Path) -> Path:
    """Where a new theme goes: the game folder (a session's parent, else the folder opened)."""
    return (session.parent if session else root) / "theme.toml"


def crew_target(session: Path | None, root: Path) -> Path:
    """The crew file in use, or where a new one goes: _assets/ in the show folder, the one
    above the game folder."""
    game = theme_target(session, root).parent
    found = crew_file(game)
    return found if found.is_file() else game.parent / CREW_FILE


def create_from_example(kind: str, target: Path) -> Path:
    """Copy the commented example (kind "theme" or "crew") to target; never overwrites."""
    text = (Path(__file__).parent / EXAMPLES[kind]).read_text(encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(target, "x", encoding="utf-8") as f:
            f.write(text)
    except FileExistsError:
        die(f"{target} already exists")
    return target
