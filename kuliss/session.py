"""kuliss sync: put a session's recordings, in sync, on the session project's tracks.

    kuliss sync [SESSION_DIR]

Each recording in sources/ is <date>_<initial>.mkv with audio streams titled
"Comms", "Voice audio" and "Game audio". Each player's voice is heard in the others'
Comms streams, which is what lines the files up.
"""

import argparse
import math
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import av

from . import sync, timeline
from .config import VoiceError, die
from .notes import TALLY_NAMES, _discover

NAMES = dict(TALLY_NAMES)   # initial -> player
TRACKS = (   # track name, audio track?, stream title (None: the video)
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
    streams: dict[str, int]   # title -> stream index
    length: int               # frames


def create_project(template: Path, dest: Path) -> None:
    """A new session project from the template, with the template's relative asset
    paths made absolute so the project can live in the session folder."""
    try:
        tree = ET.parse(template)
    except (OSError, ET.ParseError) as e:
        die(f"cannot read the template {template}: {e}")
    root = tree.getroot()
    base = Path(root.get("root") or template.parent)
    for e in root:
        if e.tag in ("chain", "producer"):
            res = timeline.props(e).get("resource", "")
            if res and not Path(res).is_absolute() and (base / res).exists():
                timeline.set_prop(e, "resource", base / res)
    root.set("root", str(dest.parent))
    for e in root.iter("property"):   # Kdenlive keys its cache and proxies on this
        if e.get("name") == "kdenlive:docproperties.documentid":
            e.text = str(int(time.time() * 1000))
    tree.write(dest, encoding="utf-8", xml_declaration=True)


def probe(path: Path, fps: float) -> Recording | None:
    m = re.search(r"_([A-Za-z])$", path.stem)
    if not m or m[1].upper() not in NAMES:
        print(f"WARNING: {path.name}: the name doesn't end in _<initial> of a known player "
              f"({', '.join(NAMES)}); skipped")
        return None
    try:
        with av.open(str(path)) as c:
            streams = {s.metadata.get("title"): s.index for s in c.streams.audio}
            missing = [t for t in TITLES if t not in streams]
            if missing or not c.streams.video:
                die(f"{path.name}: needs a video stream and audio streams titled "
                    f"{', '.join(TITLES)}; it has {', '.join(map(str, streams)) or 'no audio'}")
            length = math.ceil(c.duration / av.time_base * fps)
    except (av.FFmpegError, TypeError) as e:
        die(f"cannot read {path}: {e}")
    i = m[1].upper()
    return Recording(path, i, NAMES[i], streams, length)


def sync_session(session_dir: Path) -> None:
    path = session_dir / f"{session_dir.name}.kdenlive"
    if not path.is_file():
        die(f"no {path.name} in {session_dir} (kuliss new creates it)")
    mtime = path.stat().st_mtime_ns
    proj = timeline.load(path)
    recs = [r for f in sorted((session_dir / "sources").glob("*.mkv"))
            if (r := probe(f, proj.fps))]
    if not recs:
        die(f"no recordings in {session_dir / 'sources'}")
    tracks = {(t.name, t.audio): t for t in proj.tracks}
    for r in recs:
        for fmt, audio, _ in TRACKS:
            name = fmt.format(i=r.initial, name=r.name)
            t = tracks.get((name, audio))
            if t is None:
                die(f"{path.name} has no {'audio' if audio else 'video'} track named {name!r}")
            if t.entries:   # never touch an edit in progress
                die(f"the {name!r} track already has clips; clear the recordings' tracks "
                    "to sync again")

    print(f"{path.name}: syncing {len(recs)} recordings on their call audio")
    t0 = time.monotonic()
    keys = [(r, t) for r in recs for t in ("Voice audio", "Comms")]
    with ThreadPoolExecutor(len(keys)) as pool:
        env = dict(zip(((r.name, t) for r, t in keys),
                       pool.map(lambda k: sync.envelope(str(k[0].path), k[0].streams[k[1]]),
                                keys)))
    ref = recs[0]
    offsets = {ref.name: 0.0}
    print(f"  {ref.name:<10} reference")
    for r in recs[1:]:
        offsets[r.name], conf = sync.offset(env[ref.name, "Voice audio"], env[ref.name, "Comms"],
                                            env[r.name, "Voice audio"], env[r.name, "Comms"],
                                            r.name)
        print(f"  {r.name:<10} {offsets[r.name]:+9.2f} s   (confidence {conf:.0f})")
    print(f"  analysed in {time.monotonic() - t0:.0f} s")

    # recordings start where the intro music ends (the template's Assets audio track)
    intro = tracks.get(("Assets", True))
    at = intro.entries[0].start + intro.entries[0].length if intro and intro.entries else 0
    first = min(offsets.values())
    for r in recs:
        kid, video, audio = timeline.add_source(proj, r.path, r.length,
                                                [r.streams[t] for t in TITLES])
        start = at + round((offsets[r.name] - first) * proj.fps)
        for fmt, is_audio, title in TRACKS:
            timeline.place(proj, fmt.format(i=r.initial, name=r.name), is_audio,
                           audio[r.streams[title]] if is_audio else video, kid, start, r.length)
    backup = timeline.write(proj, path, mtime)
    print(f"Updated {path.name} (backup: {backup.name}). "
          "If it is open in Kdenlive, reopen it without saving first.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kuliss sync", description=__doc__.split("\n")[0])
    ap.add_argument("directory", nargs="?", default=".",
                    help="the session directory, or any directory inside it (default: .)")
    a = ap.parse_args(argv)
    try:
        sessions = _discover(Path(a.directory).resolve())
        if len(sessions) != 1:
            die("run it inside one session directory, or name one")
        sync_session(sessions[0])
    except VoiceError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0
