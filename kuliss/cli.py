"""kuliss: Kdenlive tools for Samkväm.

    kuliss finish PROJECT.kdenlive [...]    overlay, switch sounds, intro and outro
    kuliss notes [DIR] [...]                sync Document Notes into the session .md
    kuliss new [DIR]                        scaffold the next session directory
    kuliss sync [SESSION_DIR]               put sources/*.mkv in sync on the project's tracks
    kuliss gui [DIR]                        a window that walks through a whole session

Run `kuliss COMMAND --help` for each command's options.

This module and gui.py are the only places that parse arguments, print and set exit codes; each
command imports its own module so `notes` and `new` never load skia, PyAV or Silero.
"""

import argparse
import logging
import sys
from datetime import date
from importlib.metadata import version
from pathlib import Path

from .errors import VoiceError, die
from .steps import analysis_report, new_report, preview_report, sync_report, updated_report


def positive(text: str) -> float:
    try:
        seconds = float(text)
    except ValueError:
        seconds = 0
    if not seconds > 0:
        raise argparse.ArgumentTypeError(f"must be a number of seconds above 0, got {text!r}")
    return seconds


def _progress(done: int, total: int) -> None:
    end = "\n" if done >= total or not sys.stdout.isatty() else ""
    print(f"\r  rendering {100 * done // max(total, 1):3d}%", end=end, flush=True)


def _finish(args: argparse.Namespace) -> int:
    from . import finish

    analysis = finish.analyse(args.project, args.theme)
    print("\n".join(analysis_report(analysis)))
    if args.dry_run:
        return 0
    overlay = finish.render_overlay(analysis, args.preview, _progress)
    if args.preview is not None:
        print(preview_report(overlay))
        return 0
    backup = finish.apply(analysis, overlay)
    print(updated_report(analysis.path, backup))
    return 0


def _sessions(directory: str) -> list[Path]:
    from .notes import discover

    start = Path(directory).resolve()
    if not start.is_dir():
        die(f"{start} is not a directory")
    return discover(start)


def _notes(args: argparse.Namespace) -> int:
    from . import notes

    sessions = _sessions(args.directory)
    if not sessions:
        die(
            f"{Path(args.directory).resolve()} is not inside a session directory and contains "
            "no session_* directories"
        )
    if args.show:
        shown = [
            text
            for session in sessions
            if (text := notes.show_episode(session, args.show)) is not None
        ]
        if not shown:
            die(f"episode {args.show!r} not found in any session file")
        print(shown[0])
        return 0
    warnings = 0
    for session in sessions:
        res = notes.process_session(session, dry_run=args.dry_run)
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


def _new(args: argparse.Namespace) -> int:
    from . import scaffold
    from .notes import SOFTWARE_DEFAULTS

    start = Path(args.directory).resolve()
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
    while not (raw := _prompt(f"Session number [{number}]: ", str(number))).isdigit() or not int(
        raw
    ):
        print(f"  invalid number {raw!r}")
    number = int(raw)

    presets = scaffold.software_presets(root)
    lines = SOFTWARE_DEFAULTS
    if presets:
        games = [*presets, "none"]
        while (
            game := _prompt(f"Game ({' / '.join(games)}) [{games[0]}]: ", games[0])
        ) not in games:
            print(f"  unknown game {game!r}")
        lines = presets.get(game, []) + SOFTWARE_DEFAULTS

    print("Software versions (Enter keeps the value, type to replace):")
    software = []
    for line in lines:
        indent = line[: len(line) - len(line.lstrip())]
        text = line.lstrip()[2:]  # drop the '* ' bullet
        software.append(f"{indent}* {_prompt(f'  {text}: ', text)}")
    while extra := _prompt("  add more (empty to finish): ", ""):
        software.append(f"* {extra}")

    made = scaffold.scaffold_session(root, number, session_date, software)
    print("\n".join(new_report(made)))
    print('Put the recordings in sources/, then run "kuliss sync" there.')
    return 0


def _sync(args: argparse.Namespace) -> int:
    from . import session

    sessions = _sessions(args.directory)
    if len(sessions) != 1:
        die("run it inside one session directory, or name one")
    res = session.sync_session(sessions[0])
    print("\n".join(sync_report(res)))
    return 0


def _gui(args: argparse.Namespace) -> int:
    try:
        from . import gui
    except ModuleNotFoundError as e:
        if not (e.name or "").startswith(("PySide6", "shiboken6")):
            raise
        die(
            "the window needs PySide6, the gui extra. Reinstall with it: "
            'uv tool install --force --editable "<your clone>[gui]", or '
            '"kuliss[gui] @ git+https://github.com/seetee/kuliss.git"; '
            "in a clone you can also run: uv run --extra gui kuliss gui"
        )
    start = Path(args.directory).expanduser().resolve() if args.directory else None
    if start and not start.is_dir():
        die(f"{start} is not a directory")
    return gui.run(start)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kuliss",
        description=__doc__.split("\n\nThis module")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {version('kuliss')}")
    sub = ap.add_subparsers(dest="command", metavar="COMMAND", required=True)

    p = sub.add_parser(
        "finish",
        help="overlay, switch sounds, intro and outro",
        description="Finish analysis episode: add the who-we-watch / who-talks overlay, "
        "a sound at every switch, and the intro and outro.",
    )
    p.add_argument("project", help="the .kdenlive project to update in place")
    p.add_argument("--theme", help="theme TOML (default: theme.toml next to or above the project)")
    p.add_argument("--dry-run", action="store_true", help="analyse and report; write nothing")
    p.add_argument(
        "--preview",
        type=positive,
        metavar="SECS",
        help="render only the first SECS to PROJECT-overlay-preview.mkv; project untouched",
    )
    p.set_defaults(run=_finish)

    p = sub.add_parser(
        "notes",
        help="sync Document Notes into the session .md",
        description="Sync Kdenlive episode notes into the session Markdown file.",
    )
    p.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="any directory inside a session tree, a session directory, or a "
        "parent of session_* directories (default: current directory)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would change as a diff, without writing anything",
    )
    p.add_argument(
        "--show",
        metavar="EPISODE",
        help="print analysis episode's metadata and notes from the session file, then exit",
    )
    p.set_defaults(run=_notes)

    p = sub.add_parser(
        "new",
        help="scaffold the next session directory",
        description="Scaffold the next session directory and its Kdenlive project.",
    )
    p.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="the folder holding the session_* directories, or anywhere inside one",
    )
    p.set_defaults(run=_new)

    p = sub.add_parser(
        "sync",
        help="put sources/*.mkv in sync on the project's tracks",
        description="Put a session's recordings, in sync, on the session project's tracks.",
    )
    p.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="the session directory, or any directory inside it (default: .)",
    )
    p.set_defaults(run=_sync)

    p = sub.add_parser(
        "gui",
        help="a window that walks through a whole session",
        description="Open a window with a session's steps, from new session to finished "
        "episodes, and links to the files involved.",
    )
    p.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="a session directory, anywhere inside one, or the folder holding them "
        "(default: the last session opened, else .)",
    )
    p.set_defaults(run=_gui)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    # the library reports through logging; warnings go to stderr as "WARNING: ..."
    logging.basicConfig(level=logging.WARNING, format="WARNING: %(message)s", force=True)
    try:
        return args.run(args)
    except VoiceError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
