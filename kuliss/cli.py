"""kuliss: Kdenlive tools for Samkväm.

    kuliss speaker PROJECT.kdenlive [...]   who-we-watch / who-talks overlay
    kuliss notes [DIR] [...]                sync Document Notes into the session .md
    kuliss new [DIR]                        scaffold the next session directory
    kuliss sync [SESSION_DIR]               put sources/*.mkv in sync on the project's tracks

Run `kuliss COMMAND --help` for each command's options.

This module is the only place that parses arguments, prints and sets exit codes; each
command imports its own module so `notes` and `new` never load skia, PyAV or Silero.
"""

import argparse
import logging
import sys
from datetime import date
from importlib.metadata import version
from pathlib import Path

from .errors import VoiceError, die

REOPEN = "If it is open in Kdenlive, reopen it without saving first."


def positive(text: str) -> float:
    try:
        v = float(text)
    except ValueError:
        v = 0
    if not v > 0:
        raise argparse.ArgumentTypeError(f"must be a number of seconds above 0, got {text!r}")
    return v


def _progress(done: int, total: int) -> None:
    end = "\n" if done >= total or not sys.stdout.isatty() else ""
    print(f"\r  rendering {100 * done // max(total, 1):3d}%", end=end, flush=True)


def _speaker(a) -> int:
    from . import speaker
    an = speaker.analyse(a.project, a.theme)
    if an.absent:
        print("Not in this project (no voice clips): " + ", ".join(an.absent))
    fps = an.proj.fps
    print(f"{an.path.name}: {an.proj.length / fps / 60:.1f} min, {len(an.cuts)} view switches")
    print(f"  speech detected in {an.seconds:.0f} s")
    for name, on_screen, talking in an.stats():
        print(f"  {name:<12} on screen {on_screen:4.1f}%   talking {talking:4.1f}%")
    if a.dry_run:
        return 0
    overlay = speaker.render_overlay(an, a.preview, _progress)
    if a.preview is not None:
        print(f"Preview written: {overlay}")
        return 0
    backup = speaker.apply(an, overlay)
    print(f"Updated {an.path.name} (backup: {backup.name}). {REOPEN}")
    return 0


def _sessions(directory: str) -> list[Path]:
    from .notes import _discover
    start = Path(directory).resolve()
    if not start.is_dir():
        die(f"{start} is not a directory")
    return _discover(start)


def _notes(a) -> int:
    from . import notes
    sessions = _sessions(a.directory)
    if not sessions:
        die(f"{Path(a.directory).resolve()} is not inside a session directory and contains "
            "no session_* directories")
    if a.show:
        shown = [text for s in sessions if (text := notes.show_episode(s, a.show)) is not None]
        if not shown:
            die(f"episode {a.show!r} not found in any session file")
        print(shown[0])
        return 0
    warnings = 0
    for s in sessions:
        res = notes.process_session(s, dry_run=a.dry_run)
        print("\n".join(res.lines))
        warnings += res.warnings
    return 1 if warnings else 0


def _prompt(question: str, default: str) -> str:
    """Interactive prompt; falls back to the default when stdin is closed."""
    try:
        answer = input(question).strip()
    except EOFError:
        return default
    return answer or default


def _new(a) -> int:
    from . import scaffold
    from .notes import SOFTWARE_DEFAULTS
    start = Path(a.directory).resolve()
    if not start.is_dir():
        die(f"{start} is not a directory")
    root, number = scaffold.next_session(start)

    today = date.today().isoformat()
    while True:
        raw = _prompt(f"Recording date [{today}]: ", today)
        try:
            session_date = date.fromisoformat(raw).isoformat()
            break
        except ValueError:
            print(f"  invalid date {raw!r} (expected YYYY-MM-DD)")

    print("Software versions (Enter keeps the value, type to replace):")
    software = []
    for line in SOFTWARE_DEFAULTS:
        indent = line[:len(line) - len(line.lstrip())]
        text = line.lstrip()[2:]  # drop the '* ' bullet
        software.append(f"{indent}* {_prompt(f'  {text}: ', text)}")
    while extra := _prompt("  add more (empty to finish): ", ""):
        software.append(f"* {extra}")

    made = scaffold.scaffold_session(root, number, session_date, software)
    if made.warning:
        print(f"warning: {made.warning}")
    files = f"{made.dir.name}.md" + (f", {made.project.name}" if made.project else "")
    print(f"created {made.dir}")
    print(f"  {made.episode}/, kortisar/, sources/, {files}")
    print('Put the recordings in sources/, then run "kuliss sync" there.')
    return 0


def _sync(a) -> int:
    from . import session
    sessions = _sessions(a.directory)
    if len(sessions) != 1:
        die("run it inside one session directory, or name one")
    res = session.sync_session(sessions[0])
    print(f"{res.path.name}: synced {len(res.offsets) + 1} recordings on their call audio "
          f"in {res.seconds:.0f} s")
    print(f"  {res.reference:<10} reference")
    for name, (seconds, confidence) in res.offsets.items():
        print(f"  {name:<10} {seconds:+9.2f} s   (confidence {confidence:.0f})")
    for name, audio in res.added_tracks:
        print(f"  added the {'audio' if audio else 'video'} track {name!r}")
    print(f"Updated {res.path.name} (backup: {res.backup.name}). {REOPEN}")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="kuliss", description=__doc__.split("\n\nThis module")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"%(prog)s {version('kuliss')}")
    sub = ap.add_subparsers(dest="command", metavar="COMMAND", required=True)

    p = sub.add_parser("speaker", help="who-we-watch / who-talks overlay",
                       description="Add a who-we-watch / who-talks overlay to a Kdenlive project.")
    p.add_argument("project", help="the .kdenlive project to update in place")
    p.add_argument("--theme", help="theme TOML (default: theme.toml next to or above the project)")
    p.add_argument("--dry-run", action="store_true", help="analyse and report; write nothing")
    p.add_argument("--preview", type=positive, metavar="SECS",
                   help="render only the first SECS to PROJECT-overlay-preview.mkv; project untouched")
    p.set_defaults(run=_speaker)

    p = sub.add_parser("notes", help="sync Document Notes into the session .md",
                       description="Sync Kdenlive episode notes into the session Markdown file.")
    p.add_argument("directory", nargs="?", default=".",
                   help="any directory inside a session tree, a session directory, or a "
                        "parent of session_* directories (default: current directory)")
    p.add_argument("--dry-run", action="store_true",
                   help="show what would change as a diff, without writing anything")
    p.add_argument("--show", metavar="EPISODE",
                   help="print an episode's metadata and notes from the session file, then exit")
    p.set_defaults(run=_notes)

    p = sub.add_parser("new", help="scaffold the next session directory",
                       description="Scaffold the next session directory and its Kdenlive project.")
    p.add_argument("directory", nargs="?", default=".",
                   help="the folder holding the session_* directories, or anywhere inside one")
    p.set_defaults(run=_new)

    p = sub.add_parser("sync", help="put sources/*.mkv in sync on the project's tracks",
                       description="Put a session's recordings, in sync, on the session "
                                   "project's tracks.")
    p.add_argument("directory", nargs="?", default=".",
                   help="the session directory, or any directory inside it (default: .)")
    p.set_defaults(run=_sync)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    # the library reports through logging; warnings go to stderr as "WARNING: ..."
    logging.basicConfig(level=logging.WARNING, format="WARNING: %(message)s", force=True)
    try:
        return a.run(a)
    except VoiceError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
