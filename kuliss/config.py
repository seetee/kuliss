"""The theme: one TOML per game, holding the look, the sound and the players.
The crew file: one TOML for all sessions, holding the mixer settings of the tracks."""

import logging
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .errors import die

log = logging.getLogger(__name__)

POSITIONS = (
    "top-left",
    "top",
    "top-right",
    "left",
    "right",
    "bottom-left",
    "bottom",
    "bottom-right",
)  # corners and edge centres
ORIENTATIONS = ("horizontal", "vertical")
BOOKENDS = ("intro_audio", "intro_video", "outro_audio", "outro_image")


@dataclass(frozen=True)
class Player:
    name: str
    colour: tuple[int, int, int]
    avatar: Path
    source: tuple[str, ...]  # globs matched against clip file names, e.g. "*_h.mkv";
    # empty = the files used on the voice track
    voice_track: str  # Kdenlive audio track holding this player's voice


@dataclass(frozen=True)
class Theme:
    players: tuple[Player, ...]
    sound: Path | None  # None only when show_view is off
    backdrop: Path | None = None
    font: Path | None = None
    position: str = "top-left"
    offset: tuple[int, int] = (0, 0)  # px nudge after placing: +x right, +y down
    orientation: str = "horizontal"  # a row of avatars, or a column along the edge
    margin: int = 24  # px from the frame edges
    avatar_size: int = 48  # px; the viewed player's avatar is drawn larger
    sound_offset: float = 0.0  # s; shifts every transition sound relative to its cut
    codec: str = "ffv1"  # overlay video codec, see CODECS
    speech_threshold: float = 0.35  # Silero speech probability that counts as talking
    show_view: bool = True  # False: only who talks; no viewed avatar, label or switch sounds
    intro_audio: Path | None = None  # the four below: placed on the Assets tracks,
    intro_video: Path | None = None  # see timeline.bookends
    outro_audio: Path | None = None
    outro_image: Path | None = None


@dataclass(frozen=True)
class Mixer:
    """A Kdenlive track's mixer: what a new track gets; later changes in Kdenlive stay."""

    gain: float = 0.0  # dB
    pan: float = 0.5  # 0 left, 1 right
    contrast: int = 0  # the acontrast effect (0-100); 0 = none


@dataclass(frozen=True)
class Crew:
    master_gain: float = 0.0  # dB on the sequence's master
    assets_gain: float = 0.0  # the Assets audio track (intro, outro, sounds)
    game_gain: float = 0.0  # every player's game audio track
    voice: dict[str, Mixer] = field(default_factory=dict)  # player -> their voice track
    software: dict[str, list[str]] = field(default_factory=dict)  # game -> its .md lines
    archive: Path | None = None  # where older sessions are kept: <archive>/<game>/session_*

    def voice_of(self, name: str) -> Mixer:
        return self.voice.get(name, Mixer())


def parse_colour(text: str, where: str) -> tuple[int, int, int]:
    digits = str(text).lstrip("#")
    if len(digits) != 6:
        die(f'{where}: colour must look like "#e0a030", got {text!r}')
    try:
        return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        die(f'{where}: colour must look like "#e0a030", got {text!r}')


THEME_KEYS = {
    "assets",
    "sound",
    "backdrop",
    "font",
    "position",
    "offset",
    "orientation",
    "margin",
    "avatar_size",
    "sound_offset",
    "codec",
    "speech_threshold",
    "show_view",
    "player",
    *BOOKENDS,
}
PLAYER_KEYS = {"name", "colour", "avatar", "source", "voice_track"}
CREW_FILE = Path("_assets") / "kuliss.toml"  # in the show folder, above every game folder
CREW_KEYS = {"master_gain", "assets_gain", "game_gain", "voice", "software", "archive"}
VOICE_KEYS = {"gain", "pan", "contrast"}
CODECS = ("ffv1", "qtrle")  # ffv1: free/open, lossless; qtrle: about 20% smaller files, no faster


def _warn_unknown(table: dict, known: set[str], where: str) -> None:
    for key in sorted(table.keys() - known):
        log.warning("%s: unknown key %r (ignored; typo?)", where, key)


def _get(
    table: dict,
    key: str,
    kind: type,
    default,
    where: str,
    check: Callable[[object], bool] = lambda value: True,
    rule: str = "",
):
    """table[key] if present, else default; dies unless it is a `kind` passing `check`."""
    value = table.get(key, default)
    if kind is float and type(value) is int:
        value = float(value)
    if type(value) is not kind or not check(value):
        want = rule or {str: "text", int: "a whole number", float: "a number"}[kind]
        die(f"{where}: {key} must be {want}, got {value!r}")
    return value


def _nearest(start: Path, name: Path | str) -> Path | None:
    return next((d / name for d in (start, *start.parents) if (d / name).is_file()), None)


def nearest_theme(start: Path) -> Path | None:
    """theme.toml in `start` or the nearest folder above it: the game folder's serves
    every session of that game; a session's own one wins."""
    return _nearest(start, "theme.toml")


def crew_file(start: Path) -> Path:
    """The crew file in `start` or the nearest folder above it (the show folder);
    where it would be, next to `start`, if there is none."""
    return _nearest(start, CREW_FILE) or start / CREW_FILE


def load_theme(path: Path) -> Theme:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"theme not found: {path}")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        die(f"{path}: {e}")
    base = path.parent
    if "assets" in raw:  # the folder every other path is relative to, set once
        assets = raw["assets"]
        if not isinstance(assets, str) or not (base / Path(assets).expanduser()).is_dir():
            die(f"{path.name}: assets = {assets!r}: no such folder")
        base = (base / Path(assets).expanduser()).resolve()

    def file(value: object, key: str) -> Path:
        if not isinstance(value, str) or not value:
            die(f"{path.name}: {key} must be a file path, got {value!r}")
        p = (base / Path(value).expanduser()).resolve()  # ~ first: after joining it's literal
        if not p.is_file():
            die(f"{path.name}: {key} = {value!r}: no such file ({p})")
        return p

    _warn_unknown(raw, THEME_KEYS, path.name)
    table = raw.get("player", [])
    if not isinstance(table, list):
        die(f"{path.name}: players are written as [[player]] sections")
    players = []
    for number, entry in enumerate(table, 1):
        where = f"{path.name}: player #{number}"
        missing = {"name", "colour", "avatar"} - entry.keys()
        if missing:
            die(f"{where} is missing {', '.join(sorted(missing))}")
        _warn_unknown(entry, PLAYER_KEYS, where)
        name = _get(entry, "name", str, "", where, lambda v: v.strip() != "", "non-empty text")
        source = entry.get("source", [])
        source = [source] if isinstance(source, str) else source
        if not isinstance(source, list) or not all(isinstance(s, str) and s for s in source):
            die(f"{where}: source must be a file-name pattern or a list of them")
        players.append(
            Player(
                name=name,
                colour=parse_colour(entry["colour"], where),
                avatar=file(entry["avatar"], f"{name}.avatar"),
                source=tuple(source),
                voice_track=_get(entry, "voice_track", str, name, where),
            )
        )
    if not 1 <= len(players) <= 8:
        die(f"{path.name}: needs 1-8 [[player]] sections, found {len(players)}")
    if len({p.name for p in players}) != len(players):
        die(f"{path.name}: player names must be unique")

    w = path.name  # where: for the error messages
    show_view = _get(raw, "show_view", bool, True, w, rule="true or false")
    if show_view and "sound" not in raw:
        die(f'{path.name}: missing sound = "..." (the transition sound)')
    return Theme(
        players=tuple(players),
        sound=file(raw["sound"], "sound") if show_view else None,
        backdrop=file(raw["backdrop"], "backdrop") if "backdrop" in raw else None,
        font=file(raw["font"], "font") if "font" in raw else None,
        position=_get(
            raw,
            "position",
            str,
            "top-left",
            w,
            lambda v: v in POSITIONS,
            "one of " + ", ".join(POSITIONS),
        ),
        offset=tuple(
            _get(
                raw,
                "offset",
                list,
                [0, 0],
                w,
                lambda v: len(v) == 2 and all(type(n) is int and abs(n) <= 4000 for n in v),
                "[x, y] in whole pixels, e.g. [0, -40]",
            )
        ),
        orientation=_get(
            raw,
            "orientation",
            str,
            "horizontal",
            w,
            lambda v: v in ORIENTATIONS,
            "one of " + ", ".join(ORIENTATIONS),
        ),
        margin=_get(raw, "margin", int, 24, w, lambda v: 0 <= v <= 500, "0-500 (px)"),
        avatar_size=_get(raw, "avatar_size", int, 48, w, lambda v: 16 <= v <= 256, "16-256 (px)"),
        sound_offset=_get(
            raw, "sound_offset", float, 0.0, w, lambda v: abs(v) <= 10, "between -10 and 10 (s)"
        ),
        codec=_get(
            raw, "codec", str, "ffv1", w, lambda v: v in CODECS, "one of " + ", ".join(CODECS)
        ),
        speech_threshold=_get(
            raw,
            "speech_threshold",
            float,
            0.35,
            w,
            lambda v: 0.1 <= v <= 0.9,
            "between 0.1 and 0.9",
        ),
        show_view=show_view,
        **{k: file(raw[k], k) for k in BOOKENDS if k in raw},
    )


def load_crew(path: Path) -> Crew:
    """The crew file; without one every track starts at 0 dB, centred."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.warning("no crew file %s: new tracks start at 0 dB, centred", path)
        return Crew()
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        die(f"{path}: {e}")
    w = path.name
    _warn_unknown(raw, CREW_KEYS, w)

    def gain(table: dict, key: str, where: str) -> float:
        return _get(
            table, key, float, 0.0, where, lambda v: -60 <= v <= 20, "between -60 and 20 (dB)"
        )

    voices = raw.get("voice", {})
    if not isinstance(voices, dict) or not all(isinstance(v, dict) for v in voices.values()):
        die(f"{w}: voices are written as [voice.<player>] sections")
    voice = {}
    for name, v in voices.items():
        where = f"{w}: voice.{name}"
        _warn_unknown(v, VOICE_KEYS, where)
        voice[name] = Mixer(
            gain=gain(v, "gain", where),
            pan=_get(
                v, "pan", float, 0.5, where, lambda p: 0 <= p <= 1, "between 0 (left) and 1 (right)"
            ),
            contrast=_get(v, "contrast", int, 0, where, lambda c: 0 <= c <= 100, "0-100"),
        )
    software = raw.get("software", {})
    if not isinstance(software, dict) or not all(
        isinstance(lines, list) and all(isinstance(line, str) for line in lines)
        for lines in software.values()
    ):
        die(f'{w}: software is written as [software] with "<game>" = ["* line", ...]')
    archive = raw.get("archive")
    if archive is not None and (not isinstance(archive, str) or not archive):
        die(f"{w}: archive must be a folder path, got {archive!r}")
    return Crew(
        gain(raw, "master_gain", w),
        gain(raw, "assets_gain", w),
        gain(raw, "game_gain", w),
        voice,
        software,
        # relative to the show folder, which holds _assets/
        path.parent.parent / Path(archive).expanduser() if archive else None,
    )
