"""kuliss new: scaffold the next session directory. Stdlib only at import time."""

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import VoiceError, die
from .mdoc import _parse, _render
from .notes import (
    EPISODE_PREFIX,
    _ensure_episode,
    _ensure_section,
    _ensure_skeleton,
    _is_session_dir,
    _session_title,
    _write_atomic,
)

TEMPLATE = Path('_assets') / 'samkvam-session_template.kdenlive'


@dataclass
class Scaffolded:
    dir: Path
    episode: str             # the placeholder episode folder
    project: Path | None     # the session .kdenlive, None if it could not be made
    warning: str | None      # why not


def next_session(start: Path) -> tuple[Path, int]:
    """(the folder holding the session_* dirs, the next session number), from
    anywhere in or above a session tree."""
    root = next((c.parent for c in (start, *start.parents) if _is_session_dir(c)), start)
    numbers = [int(m[1]) for d in root.iterdir()
               if d.is_dir() and (m := re.match(r'^session_(\d+)_', d.name))]
    if not numbers:
        die(f'no session_* directories in {root} to base the new session on')
    return root, max(numbers) + 1


def scaffold_session(root: Path, number: int, session_date: str,
                     software_lines: list[str]) -> Scaffolded:
    """Create session_<number>_<date>/ with sources/, kortisar/ (shorts/TikToks), an
    avsnittXX<number> placeholder episode (episode numbers aren't known yet), the
    skeleton .md and, from <root>/_assets' template, the session's Kdenlive project."""
    name = f'session_{number}_{session_date}'
    session_dir = root / name
    if session_dir.exists():
        die(f'{session_dir} already exists')

    episode = f'{EPISODE_PREFIX}XX{number}'
    (session_dir / 'sources').mkdir(parents=True)
    (session_dir / 'kortisar').mkdir()
    (session_dir / episode).mkdir()

    doc = _parse('')
    software, info = _ensure_skeleton(doc, _session_title(name))
    software.lines = ['\n'] + [f'{line}\n' for line in software_lines] + ['\n']
    block = _ensure_episode(doc, info, episode)
    _ensure_section(block, 'Noteworthy')
    _write_atomic(session_dir / f'{name}.md', _render(doc))

    template, project, warning = root / TEMPLATE, session_dir / f'{name}.kdenlive', None
    if template.is_file():
        from .session import create_project  # imported here: `kuliss new` stays light
        try:
            create_project(template, project)
        except VoiceError as e:
            project, warning = None, f'no Kdenlive project created: {e}'
    else:
        project, warning = None, f'no {template}, so no Kdenlive project created'
    return Scaffolded(session_dir, episode, project, warning)
