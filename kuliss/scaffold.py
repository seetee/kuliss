"""kuliss new: scaffold the next session directory. Stdlib only at import time."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .config import crew_file, load_crew, nearest_theme
from .errors import VoiceError, die
from .files import write_atomic
from .mdoc import parse_doc, render_doc
from .notes import (
    EPISODE_PREFIX,
    ensure_episode,
    ensure_section,
    ensure_skeleton,
    is_session_dir,
    session_title,
)
from .timeline import create_project

log = logging.getLogger(__name__)


@dataclass
class Scaffolded:
    dir: Path
    episode: str  # the placeholder episode folder
    project: Path | None  # the session .kdenlive, None if it could not be made
    warning: str | None  # why not


def next_session(start: Path) -> tuple[Path, int]:
    """(the folder holding the session_* dirs, the next session number), from
    anywhere in or above a session tree. A game folder with its theme.toml but no
    sessions yet starts at 1."""
    root = next((c.parent for c in (start, *start.parents) if is_session_dir(c)), start)
    folders = [root]
    crew = crew_file(root)
    archive = load_crew(crew).archive if crew.is_file() else None
    if archive:  # sessions moved off this disk still count
        if (archive / root.name).is_dir():
            folders.append(archive / root.name)
        else:
            log.warning(
                "the archive %s is not reachable, so the number counts only the sessions in %s",
                archive / root.name,
                root,
            )
    numbers = [
        int(m[1])
        for folder in folders
        for d in folder.iterdir()
        if d.is_dir() and (m := re.match(r"^session_(\d+)_", d.name))
    ]
    if not numbers:
        if not (root / "theme.toml").is_file():
            die(
                f"no session_* folders in {root}. Run it in a game's folder (e.g. po3/); "
                "to start a new game, give it a folder with its theme.toml first"
            )
        return root, 1
    return root, max(numbers) + 1


def software_presets(root: Path) -> dict[str, list[str]]:
    """Each game's software lines from the crew file ({} without one, quietly: kuliss new
    warns about a missing crew file once, when it builds the project)."""
    path = crew_file(root)
    return load_crew(path).software if path.is_file() else {}


def scaffold_session(
    root: Path, number: int, session_date: str, software_lines: list[str]
) -> Scaffolded:
    """Create session_<number>_<date>/ with sources/, kortisar/ (shorts/TikToks), an
    avsnittXX<number> placeholder episode (episode numbers aren't known yet), the
    skeleton .md and the session's Kdenlive project (mixer levels: the crew file)."""
    name = f"session_{number:02d}_{session_date}"
    session_dir = root / name
    if session_dir.exists():
        die(f"{session_dir} already exists")

    episode = f"{EPISODE_PREFIX}XX{number:02d}"
    (session_dir / "sources").mkdir(parents=True)
    (session_dir / "kortisar").mkdir()
    (session_dir / episode).mkdir()

    doc = parse_doc("")
    software, info = ensure_skeleton(doc, session_title(name))
    software.lines = ["\n"] + [f"{line}\n" for line in software_lines] + ["\n"]
    block = ensure_episode(doc, info, episode)
    ensure_section(block, "Noteworthy")
    text = render_doc(doc)
    write_atomic(session_dir / f"{name}.md", lambda tmp: tmp.write_text(text, encoding="utf-8"))

    if nearest_theme(session_dir) is None:
        log.warning(
            "no theme.toml in %s or above, so kuliss finish will not run; put the "
            "game's theme in %s (see kuliss/theme.example.toml, or Settings → Theme in the window)",
            session_dir,
            root,
        )

    project, warning = session_dir / f"{name}.kdenlive", None
    try:
        create_project(project, load_crew(crew_file(root)))
    except VoiceError as e:
        project, warning = None, f"no Kdenlive project created: {e}"
    return Scaffolded(session_dir, episode, project, warning)
