"""
Sync Kdenlive episode notes into the Samkväm session Markdown file.

Usage:
    kuliss notes [DIRECTORY]

Run it from anywhere inside a session tree (the session directory itself, an
episode subdirectory, or deeper) and it finds the session automatically.
Given a directory containing session_* children, all of them are processed.

On every run the session file is created if missing and repaired to the
canonical skeleton:

    # Session XX - YYYY-MM-DD

    ## Mjukvaruversioner

    ## Avsnittsinfo

    ### avsnittXXX

    **Titel:**
    **Blurb (large):**
    **Blurb (short):**
    **Trailer:**

    #### Noteworthy
    #### Bryggpromenader        (only when the episode has such notes)
    #### Kapitel                (only when the episode has chapters)

Notes typed without a section heading in Kdenlive's Document Notes panel are
appended to the end of "Noteworthy" after a blank line.  A Bryggpromenader
section gets an auto-counted tally (Joel/Robin/Henrik/Kenneth, from tokens
like "H+1").  Metadata lines written without bold markers ("Titel: …") are
normalized in place to the bold form.

Kapitel is a paste-ready YouTube chapter list: it always opens with
"00:00 Äventyret börjar!", every Bryggpromenader entry becomes a chapter named
"<Namn> tar en lång promenad på en kort brygga", and any note flagged with a
'*' right after its timestamp in Kdenlive becomes a chapter (with the trailing
speaker token like "-h" stripped from the title).

Only script-managed lines are ever rewritten: the '* ' bullets of sections
that have incoming notes, the Bryggpromenader tally, and the '* Kdenlive …'
version line.  Everything written by hand is preserved.  A per-episode
completeness checklist is printed after each run.
"""

import difflib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from .kdnotes import ORPHAN_SECTION, _extract_project, _ts_seconds
from .mdoc import _Block, _find_block, _insert_child, _locate, _new_block, _parse, _render

EPISODE_PREFIX = 'avsnitt'
BRYGG_SECTION = 'Bryggpromenader'
CHAPTER_SECTION = 'Kapitel'
STANDARD_SECTIONS = ['Noteworthy', ORPHAN_SECTION, BRYGG_SECTION, CHAPTER_SECTION]
METADATA_FIELDS = ['Titel', 'Blurb (large)', 'Blurb (short)', 'Trailer']
TALLY_NAMES = [('J', 'Joel'), ('R', 'Robin'), ('H', 'Henrik'), ('K', 'Kenneth')]
CHAPTER_OPENING = 'Äventyret börjar!'
BRYGG_PHRASE = 'tar en lång promenad på en kort brygga'

SOFTWARE_DEFAULTS = [
    '* Prism Launcher 9.2',
    '* Project Ozone 3 3.4.10',
    '* Minecraft 1.12.2',
    '* Resource packs',
    '  * Faithful 32x',
    '  * Faithful Mods - Project Ozone 3',
    '  * Ozone Resources 3',
    '* OBS 23.0.3',
]

_META_RE = re.compile(r'^\*\*(.+?):\*\*')
_META_FILLED_RE = re.compile(r'^\*\*(.+?):\*\*\s*\S')
_TALLY_LINE_RE = re.compile(r'^(Joel|Robin|Henrik|Kenneth)\s*:')
_TALLY_TOKEN_RE = re.compile(r'\b([JRHK])\s*\+\s*(\d+)', re.IGNORECASE)
_KDENLIVE_LINE_RE = re.compile(r'^\*\s+Kdenlive\b')
_CHAPTER_LINE_RE = re.compile(r'^\d{2}:\d{2}(:\d{2})?\s')


def _natural_key(name: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]


# ── Skeleton repair ───────────────────────────────────────────────────────────

def _session_title(dirname: str) -> str:
    m = re.match(r'^session_(\d+)_(.+)$', dirname)
    return f'Session {m.group(1)} - {m.group(2)}' if m else dirname


def _ensure_skeleton(root: _Block, title: str) -> tuple[_Block, _Block]:
    """Ensure # title, ## Mjukvaruversioner and ## Avsnittsinfo exist."""
    h1 = next((c for c in root.children if c.level == 1), None)
    if h1 is None:
        h1 = _new_block(1, title)
        _insert_child(root, 0, h1)

    software = _find_block(root, 2, 'Mjukvaruversioner')
    if software is None:
        software = _new_block(2, 'Mjukvaruversioner')
        software.lines = []
        _insert_child(h1, 0, software)

    info = _find_block(root, 2, 'Avsnittsinfo')
    if info is None:
        info = _new_block(2, 'Avsnittsinfo')
        parent, idx = _locate(root, software)
        _insert_child(parent, idx + 1, info)

    return software, info


def _ensure_episode(root: _Block, info: _Block, name: str) -> _Block:
    episode = _find_block(root, 3, name)
    if episode is not None:
        return episode
    episode = _Block(3, name, f'### {name}\n')
    episode.lines = ['\n'] + [f'**{f}:**\n' for f in METADATA_FIELDS] + ['\n']
    pos = len(info.children)
    for i, child in enumerate(info.children):
        if child.level == 3 and _natural_key(child.title) > _natural_key(name):
            pos = i
            break
    _insert_child(info, pos, episode)
    return episode


def _ensure_metadata(episode: _Block) -> None:
    # Normalize unbolded metadata lines ("Titel: x") to the bold form in place.
    for i, line in enumerate(episode.lines):
        for name in METADATA_FIELDS:
            m = re.match(rf'^{re.escape(name)}\s*:\s*(.*?)\s*$', line)
            if m:
                value = m.group(1)
                episode.lines[i] = f'**{name}:** {value}\n' if value else f'**{name}:**\n'
                break

    present = set()
    last_meta = None
    for i, line in enumerate(episode.lines):
        m = _META_RE.match(line)
        if m:
            present.add(m.group(1))
            last_meta = i
    missing = [f for f in METADATA_FIELDS if f not in present]
    if not missing:
        return
    insert = [f'**{f}:**\n' for f in missing]
    if last_meta is not None:
        pos = last_meta + 1
    else:
        pos = 0
        while pos < len(episode.lines) and not episode.lines[pos].strip():
            pos += 1
        if pos == 0:
            insert = ['\n'] + insert
    episode.lines[pos:pos] = insert
    end = pos + len(insert)
    if end >= len(episode.lines) or episode.lines[end].strip():
        episode.lines.insert(end, '\n')


def _ensure_section(episode: _Block, name: str) -> _Block:
    for child in episode.children:
        if child.title == name:
            return child
    block = _new_block(4, name)
    if name in STANDARD_SECTIONS:
        rank = STANDARD_SECTIONS.index(name)
        pos = 0
        for i, child in enumerate(episode.children):
            if child.title in STANDARD_SECTIONS and STANDARD_SECTIONS.index(child.title) < rank:
                pos = i + 1
    else:
        pos = len(episode.children)
    _insert_child(episode, pos, block)
    return block


# ── Managed content updates ───────────────────────────────────────────────────

def _tally(entries: list[tuple[str, str]]) -> list[tuple[str, int]]:
    by_initial = dict(TALLY_NAMES)
    counts = dict.fromkeys(by_initial.values(), 0)
    for _, text in entries:
        for initial, num in _TALLY_TOKEN_RE.findall(text):
            counts[by_initial[initial.upper()]] += int(num)
    return list(counts.items())


def _bullet(entry: tuple[str, str]) -> str:
    ts, text = entry
    return f'* {ts} {text}' if ts else f'* {text}'


def _set_bullets(section: _Block, bullets: list[str],
                 tally: list[tuple[str, int]] | None = None,
                 appendix: list[str] | None = None) -> None:
    """Replace the managed lines of a section, keeping hand-written extras."""
    extra = [
        line for line in section.lines
        if line.strip() and not line.startswith('* ') and not _TALLY_LINE_RE.match(line)
    ]
    lines = [f'{b}\n' for b in bullets]
    if appendix:
        lines += ['\n'] + [f'{b}\n' for b in appendix]
    if tally is not None:
        lines += ['\n'] + [f'{name}: {count}\n' for name, count in tally]
    if extra:
        lines += ['\n'] + extra
    lines.append('\n')
    section.lines = lines


def _chapter_names(text: str) -> list[str]:
    """Full names, in mention order, from the tally tokens in a note text."""
    by_initial = dict(TALLY_NAMES)
    return list(dict.fromkeys(by_initial[i.upper()] for i, _ in _TALLY_TOKEN_RE.findall(text)))


def _chapters(
    notes: dict[str, list[tuple[str, str]]], starred: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Assemble the YouTube chapter list; empty when there are no real chapters."""
    items = []
    for ts, text in notes.get(BRYGG_SECTION, []):
        names = _chapter_names(text)
        if names and ts:
            items.append((ts, f'{" och ".join(names)} {BRYGG_PHRASE}'))
    items += [(ts, title) for ts, title in starred if ts]
    if not items:
        return []
    items.append(('00:00', CHAPTER_OPENING))
    return sorted(items, key=lambda c: _ts_seconds(c[0]))


def _set_chapter_lines(section: _Block, items: list[tuple[str, str]]) -> None:
    """Replace the managed chapter lines, keeping hand-written extras."""
    extra = [
        line for line in section.lines
        if line.strip() and not _CHAPTER_LINE_RE.match(line)
    ]
    lines = [f'{ts} {title}\n' for ts, title in items]
    if extra:
        lines += ['\n'] + extra
    lines.append('\n')
    section.lines = lines


def _prune_section(episode: _Block, title: str, keep) -> None:
    """Drop the childless `title` section unless `keep(line)` holds for a non-blank line."""
    for i, child in enumerate(episode.children):
        if child.title == title and not child.children:
            if not any(line.strip() and keep(line) for line in child.lines):
                del episode.children[i]
            return


def _prune_chapter_section(episode: _Block) -> None:
    """Drop a Kapitel section that holds nothing but managed chapter lines."""
    _prune_section(episode, CHAPTER_SECTION, lambda line: not _CHAPTER_LINE_RE.match(line))


def _prune_orphan_section(episode: _Block, incoming_bullets: set[str]) -> None:
    """Drop a legacy 'Other comments without a home' section when it is empty or
    contains nothing but bullets now emitted at the end of Noteworthy."""
    _prune_section(episode, ORPHAN_SECTION, lambda line: line.strip() not in incoming_bullets)


def _update_software(software: _Block, version: str | None) -> None:
    if not any(line.strip() for line in software.lines):
        software.lines = ['\n'] + [f'{line}\n' for line in SOFTWARE_DEFAULTS]
        if version:
            software.lines.append(f'* Kdenlive {version}\n')
        software.lines.append('\n')
        return
    if not version:
        return
    for i, line in enumerate(software.lines):
        if _KDENLIVE_LINE_RE.match(line):
            software.lines[i] = f'* Kdenlive {version}\n'
            return
    end = len(software.lines)
    while end and not software.lines[end - 1].strip():
        end -= 1
    software.lines.insert(end, f'* Kdenlive {version}\n')


# ── Session processing ────────────────────────────────────────────────────────

def _locate_session_file(session_dir: Path) -> tuple[Path, str]:
    """Return (md_path, current_text); a session_*.txt is promoted on write."""
    md = next(iter(sorted(session_dir.glob('session_*.md'))), None)
    if md:
        return md, md.read_text(encoding='utf-8')
    txt = next(iter(sorted(session_dir.glob('session_*.txt'))), None)
    if txt:
        return txt.with_suffix('.md'), txt.read_text(encoding='utf-8')
    return session_dir / f'{session_dir.name}.md', ''


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


def show_episode(session_dir: Path, episode: str) -> str | None:
    """An episode's block from the session file, or None if it has none."""
    _, original = _locate_session_file(session_dir)
    block = _find_block(_parse(original), 3, episode) if original else None
    return None if block is None else _render(block).rstrip('\n')


@dataclass
class Check:
    """One episode's line in the release checklist."""

    name: str
    issues: list[str]
    notes: str          # e.g. "Noteworthy 12, Kapitel 5"

    def __str__(self) -> str:
        if self.issues:
            return f'✗ {self.name}: {"; ".join(self.issues)}  [{self.notes}]'
        return f'✓ {self.name}: ready  [{self.notes}]'


def checklist(root: _Block, episode_names: list[str]) -> list[Check]:
    """Per episode: missing metadata and YouTube pitfalls (Titel > 100, < 3 chapters)."""
    checks = []
    for name in episode_names:
        episode = _find_block(root, 3, name)
        if episode is None:
            checks.append(Check(name, ['not in session file'], 'no notes yet'))
            continue
        filled = {m.group(1) for line in episode.lines if (m := _META_FILLED_RE.match(line))}
        missing = [f for f in METADATA_FIELDS if f not in filled]
        issues = []
        if missing:
            issues.append(f'fill in {", ".join(missing)}')
        titel = next((m.group(1) for line in episode.lines
                      if (m := re.match(r'^\*\*Titel:\*\*\s*(\S.*?)\s*$', line))), '')
        if len(titel) > 100:
            issues.append(f'Titel too long ({len(titel)}/100 chars)')
        counts = [
            f'{c.title} {sum(1 for line in c.lines if line.startswith("* "))}'
            for c in episode.children
            if any(line.startswith('* ') for line in c.lines)
        ]
        chapter_count = sum(bool(_CHAPTER_LINE_RE.match(line)) for c in episode.children
                            if c.title == CHAPTER_SECTION for line in c.lines)
        if chapter_count:
            counts.append(f'{CHAPTER_SECTION} {chapter_count}')
        if 0 < chapter_count < 3:
            issues.append(f'only {chapter_count} chapters (YouTube needs 3+)')
        checks.append(Check(name, issues, ', '.join(counts) if counts else 'no notes yet'))
    return checks


def episodes(session_dir: Path) -> tuple[list[tuple[str, Path]], list[str]]:
    """([(episode name, project file)], warnings). An episode is a folder named
    avsnitt… holding its same-named .kdenlive or, failing that, exactly one .kdenlive
    (a project not yet renamed from the avsnittXX<nr> placeholder)."""
    found, warnings = [], []
    for d in sorted(session_dir.iterdir(), key=lambda d: _natural_key(d.name)):
        if not (d.is_dir() and d.name.startswith(EPISODE_PREFIX)):
            continue
        projects = [d / f'{d.name}.kdenlive']
        if not projects[0].exists():
            projects = sorted(d.glob('*.kdenlive'))
        if len(projects) == 1:
            found.append((d.name, projects[0]))
        elif projects:
            warnings.append(f'{d.name}: {len(projects)} .kdenlive files and none named '
                            f'{d.name}.kdenlive; skipped')
    return found, warnings


@dataclass
class SessionResult:
    """What process_session found and did. `lines` is the human-readable report."""

    session_dir: Path
    md: Path | None = None
    original: str = ''
    updated: str = ''
    written: bool = False
    warnings: int = 0
    lines: list[str] = field(default_factory=list)
    checklist: list[Check] = field(default_factory=list)

    def _warn(self, text: str) -> None:
        self.warnings += 1
        self.lines.append(f'  {text}')


def process_session(session_dir: Path, dry_run: bool = False) -> SessionResult:
    """Merge one session's episode notes into its Markdown file (not written on dry_run)."""
    res = SessionResult(session_dir)
    say = res.lines.append
    say(f'session: {session_dir.name}')

    found, skipped = episodes(session_dir)
    for text in skipped:
        res._warn(f'WARNING - {text}')
    if not found:
        say('  no episode subdirectories found')
        return res

    md, original = _locate_session_file(session_dir)
    if original and not original.endswith('\n'):
        original += '\n'

    root = _parse(original)
    software, info = _ensure_skeleton(root, _session_title(session_dir.name))

    kdenlive_version = None
    episode_names = [name for name, _ in found]

    for name, project in found:
        episode = _ensure_episode(root, info, name)
        _ensure_metadata(episode)
        _ensure_section(episode, 'Noteworthy')
        _prune_orphan_section(episode, set())

        try:
            notes, starred, version = _extract_project(project)
        except (ET.ParseError, OSError) as exc:
            res._warn(f'{name}: WARNING - could not read project file ({exc})')
            continue
        kdenlive_version = version or kdenlive_version

        orphans = notes.pop(ORPHAN_SECTION, [])
        orphan_bullets = [_bullet(e) for e in orphans]
        _prune_orphan_section(episode, set(orphan_bullets))

        chapter_items = _chapters(notes, starred)
        if not chapter_items:
            _prune_chapter_section(episode)

        if notes or orphans:
            # Naked bullets directly under the episode heading are leftovers
            # from the pre-section format; the structured sections replace them.
            episode.lines = [line for line in episode.lines if not line.startswith('* ')]
            if orphans:
                notes.setdefault('Noteworthy', [])
            for section_name, entries in notes.items():
                section = _ensure_section(episode, section_name)
                bullets = [_bullet(e) for e in entries]
                appendix = None
                if section_name == 'Noteworthy' and orphan_bullets:
                    if bullets:
                        appendix = orphan_bullets
                    else:
                        bullets = orphan_bullets
                tally = _tally(entries) if section_name == BRYGG_SECTION else None
                _set_bullets(section, bullets, tally, appendix)
            if chapter_items:
                _set_chapter_lines(_ensure_section(episode, CHAPTER_SECTION), chapter_items)
            counts = {s: len(e) for s, e in notes.items()}
            if orphans:
                counts['Noteworthy'] += len(orphans)
            if chapter_items:
                counts[CHAPTER_SECTION] = len(chapter_items)
            summary = ', '.join(f'{s} ({n})' for s, n in counts.items())
            say(f'  {name}: {summary}')
        else:
            say(f'  {name}: no notes')

    _update_software(software, kdenlive_version)

    on_disk = set(episode_names)
    for child in info.children:
        if child.level == 3 and child.title not in on_disk:
            res._warn(f"WARNING - section '### {child.title}' has no matching episode directory")

    updated = _render(root)
    res.md, res.original, res.updated = md, original, updated
    if updated == original:
        say(f'  {md.name} already up to date')
    elif dry_run:
        say(f'  dry run - {md.name} would be {"updated" if md.exists() else "created"}:')
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f'{md.name} (current)',
            tofile=f'{md.name} (updated)',
        )
        res.lines += ['    ' + line.rstrip('\n') for line in diff]
    else:
        created = not md.exists()
        if not created:
            _write_atomic(md.with_name(md.name + '.bak'), original)
        _write_atomic(md, updated)
        res.written = True
        note = '' if created else ' (previous version in .bak)'
        say(f'  {"created" if created else "updated"} {md.name}{note}')

    res.checklist = checklist(root, episode_names)
    say('  checklist:')
    res.lines += [f'    {check}' for check in res.checklist]
    return res


# ── Discovery ─────────────────────────────────────────────────────────────────

def _is_session_dir(path: Path) -> bool:
    return (
        path.name.startswith('session_')
        or any(path.glob('session_*.md'))
        or any(path.glob('session_*.txt'))
    )


def _discover(start: Path) -> list[Path]:
    """Sessions to process: walk up to a session dir, else scan for children."""
    for candidate in (start, *start.parents):
        if _is_session_dir(candidate):
            return [candidate]
    return sorted(
        (d for d in start.iterdir() if d.is_dir() and d.name.startswith('session_')),
        key=lambda d: _natural_key(d.name),
    )

