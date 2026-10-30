"""kuliss: Kdenlive tools for Samkväm.

    kuliss speaker PROJECT.kdenlive [...]   who-we-watch / who-talks overlay
    kuliss notes [DIR] [...]                sync Document Notes into the session .md
    kuliss new [DIR]                        scaffold the next session directory
    kuliss sync [SESSION_DIR]               put sources/*.mkv in sync on the project's tracks

Run `kuliss COMMAND --help` for each command's options.
"""

import sys


def main() -> int:
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else (None, [])
    if cmd == "speaker":
        from . import speaker
        return speaker.main(args)
    if cmd == "sync":
        from . import session
        return session.main(args)
    if cmd in ("notes", "new"):
        from . import notes  # imported lazily: speaker pulls in skia, PyAV and Silero
        sys.argv[0] = "kuliss notes"
        return notes.main(["--new", *args] if cmd == "new" else args)
    print(__doc__, file=sys.stderr if cmd not in ("-h", "--help") else sys.stdout)
    return 0 if cmd in ("-h", "--help") else 2


if __name__ == "__main__":
    sys.exit(main())
