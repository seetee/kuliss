# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`kuliss` (AGPL-3.0-or-later) is a set of Kdenlive tools for the **Samkväm** let's play, run as one `kuliss` command (`__main__.py` dispatches; `notes` is imported lazily so it never loads skia/PyAV/Silero). It merges two former projects, `indicate-speaker` and `kdenlive-commentor`, and both histories are kept.

Klatch (`../klatch`, an automatic podcast pipeline) will reuse `vad.py`, `sync.py`, `render.py` and the YouTube chapter/limit logic in `notes.py`. Klatch's input is per-person audio files, **not** a Kdenlive project, so keep those parts free of Kdenlive dependencies. Split the YouTube helpers out of `notes.py` only once Klatch actually imports them.

## Commands

```bash
uv run kuliss speaker P.kdenlive --dry-run      # analyse only; prints switches + screen/talk %
uv run kuliss speaker P.kdenlive --preview 90   # first 90 s -> indicate-speaker/overlay-preview.mkv
uv run kuliss speaker P.kdenlive                # render + patch the project
uv run kuliss notes [dir]                       # session dir, parent dir, or bare from anywhere inside a session tree
uv run kuliss notes --dry-run                   # diff preview, no writes
uv run kuliss notes --show avsnittXXX           # print one episode's section
uv run kuliss new                               # scaffold next session dir + its .kdenlive
uv run kuliss sync [session dir]                # sources/*.mkv onto the project's tracks, in sync
uv run pytest                                   # single test: -k <name>; no media needed
```

Test end to end only on a **copy** of a real project or session directory. The user's projects and Kdenlive backups live under `~/documents/samkvam.online/…` and `~/.local/share/kdenlive/.backup/`. CI (`.github/workflows/test.yml`) runs pytest on 3.11/3.14 and `ruff check --select E,F` (line-length 100; E741 enforced, so no single-letter `l`).

## `kuliss speaker`

`kuliss speaker` (`speaker.py`, formerly the separate `indicate-speaker`) reads a Kdenlive project of a multi-player let's play and patches it **in place**, after a timestamped `.bak`. It adds one video track and one audio track, both named `indicate-speaker`:
- The video track holds a transparent overlay: a backdrop with 1–8 player avatars, the viewed player enlarged with a name label, and a talking marker on whoever speaks.
- The audio track holds a transition sound at every switch between players' views.

The look comes from a per-game `theme.toml` (see `theme.example.toml`), found next to or above the project.

The project file is the single input. Cuts, clip-to-player mapping (by source file name; by default the files on the player's voice track, see `with_sources`) and each voice's audio stream (`audio_index` on the voice track's clips) all come from it. Don't reintroduce file-name/date/stream-title matching.

The `indicate-speaker` names of the tracks, bin clips (`TRACK_NAME`/`CLIP_PREFIX` in `timeline.py`) and output folder are what existing projects already contain. Don't rename them to `kuliss`, or re-runs on old projects would add a second set.

- `config.py`: `Theme`/`Player` dataclasses and `load_theme`. Every value is type- and range-checked, and unknown keys warn (`THEME_KEYS`/`PLAYER_KEYS`: add new keys there). Every expected failure goes through `die()` → `VoiceError`, printed once by `main()` as `ERROR: …`. `timeline.load` also converts structural surprises (`KeyError` and similar) into `die()`.
- `timeline.py`: stdlib ElementTree only, with targeted edits. Everything the tool doesn't own must round-trip untouched.
  - `load` finds the active sequence tractor (via `docproperties.activetimeline`) and turns playlists into `Entry`s (timeline start, length, resource, src_in, audio_index, fullscreen).
  - `view_map`: the topmost visible video track showing a player's clip wins. A full-screen non-player clip (avformat/qimage without a `qtblend`/`affine` filter) means "no view".
  - `view_spans` absorbs runs shorter than `MIN_SPAN`.
  - `cuts` only counts player→player switches.
  - `patch` reuses or creates our tracks and bin clips (bin clips are identified by `kdenlive:clipname` prefix `indicate-speaker`), so re-runs are byte-identical.
  - Inserting a track must renumber `a_track`/`b_track` on the sequence's transitions, the track indices in the `sequenceproperties.groups` JSON, and `activeTrack`/`audioTarget`/`videoTarget`. Those Kdenlive indices exclude the black track, so they are `seq index - 1`. Also bump `tracksCount`.
- `vad.py`: must not import Kdenlive code at runtime (`timeline.Entry` is a `TYPE_CHECKING` import only), so Klatch can call `decode`/`speech_windows` on raw audio files. PyAV decodes each voice entry (seek, then resample to 16 kHz mono). `silero-vad-lite` scores 512-sample windows; `smooth()` applies hysteresis, hangover and minimum burst. There is no loudness gate or normalisation: quiet mics are fine for Silero.
- `render.py`:
  - skia draws each frame; PyAV encodes per `CODECS`: theme `codec` is `ffv1` (default, `.mkv`, `bgra`) or `qtrle` (`.mov`, `argb`). Alpha is load-bearing: never add a codec without checking that alpha survives in Kdenlive (VP8/VP9 WebM alpha doesn't). `test_render_is_lossless_with_alpha` round-trips both.
  - `Painter` is built before speech analysis so bad avatars, backdrops or fonts fail fast. `load_image`/`load_font` turn skia failures into `die()`.
  - The canvas always has the **profile's aspect ratio**, so MLT maps it 1:1 onto a qtblend `rect` of the same size (verified with melt). Don't make it a different aspect.
  - Label text colour is `on_colour()` (black or white): the better of the two is always ≥ 4.5:1, so no colour ever needs adjusting.
  - Identical frame states are cached.

## `kuliss notes` and `kuliss new`

`notes.py` (formerly `kdenlive_commentor.py`, stdlib only) extracts timestamped notes from Kdenlive project files (the `kdenlive:documentnotes` XML property) and merges them into a session Markdown file, repairing that file to a canonical skeleton on every run. It assumes the directory layout and session-file skeleton documented in README.md.

The checklist flags YouTube pitfalls: Titel > 100 chars, chapter lists with < 3 entries. `scaffold_session` derives the next session number from existing `session_*` dirs, prompts interactively for the recording date and software versions (`_prompt` falls back to defaults on EOF, which is what the tests use), and creates `sources/`, `kortisar/` (shorts/TikToks), a placeholder episode dir `avsnittXX<nr>` (literal `XX` — episode numbers aren't known at scaffold time), the skeleton `.md` via the `_ensure_*` machinery, and (via `session.create_project`, imported lazily) `session_<nr>_<date>.kdenlive` from `<root>/_assets/samkvam-session_template.kdenlive`, with the template's relative asset paths made absolute and a fresh `documentid`.

Exit code is 1 if any warning was printed (unreadable `.kdenlive`, stale `###` section with no matching directory). Real writes are atomic (`_write_atomic`) and preceded by a `<name>.md.bak` backup of the previous version.

Tests build synthetic `.kdenlive` fixtures in temp dirs (`SessionTree` helper in `tests/test_notes.py`) — no committed fixture data.

Pipeline:

1. **Discovery** — `_discover` walks up from the start directory to find a session dir (name starts with `session_`, or contains `session_*.md`/`.txt`), falling back to scanning for `session_*` children. Episodes are subdirectories containing a same-named `.kdenlive` file, natural-sorted.

2. **Extraction** — `_extract_project` parses the `.kdenlive` XML, feeding the `kdenlive:documentnotes` Qt-richtext HTML into `_NotesParser` (an `html.parser.HTMLParser`). Headings at any level typed in Kdenlive's notes panel become section names; notes before any heading are collected under the internal `ORPHAN_SECTION` name and end up appended to the end of `#### Noteworthy` after a blank line (no separate section is written; `_prune_orphan_section` removes legacy empty/superseded ones). `<a>` tags carry `HH:MM:SS:FF` timestamps, converted to `MM:SS` (or `HH:MM:SS`) and sorted chronologically. It also reads `kdenlive:docproperties.kdenliveversion`. Per-episode parse errors warn and continue.

3. **Document model** — the session `.md` is parsed by `_parse` into a `_Block` tree (heading level/title + verbatim body lines + children) and rendered back with `_render`. A block ends at the next heading of same-or-higher level, so content after an episode under a `##`/`#` heading is never mistaken for episode content. Untouched blocks round-trip byte-for-byte.

4. **Skeleton repair** — `_ensure_skeleton` / `_ensure_episode` / `_ensure_metadata` / `_ensure_section` create anything missing: the `# Session …` title, `## Mjukvaruversioner` (seeded from `SOFTWARE_DEFAULTS` when empty), `## Avsnittsinfo`, and a `### <episode>` block with the `METADATA_FIELDS` lines per on-disk episode. `_ensure_metadata` also normalizes unbolded metadata lines (`Titel: x` → `**Titel:** x`) in place — never duplicating them. Only `#### Noteworthy` is created unconditionally; `Bryggpromenader` (and any custom section) only when notes exist for it.

5. **Managed updates** — `_set_bullets` rewrites a section's `* ` bullets (and the Bryggpromenader tally lines, auto-counted by `_tally` from `H+1`-style tokens); `_update_software` maintains the `* Kdenlive <version>` line. A per-episode release checklist is printed by `_print_report`.

6. **Chapters** — a `*` typed directly after a note's timestamp in Kdenlive flags it as a YouTube chapter (`_NotesParser.chapters`; the `*` is stripped from the note, `_strip_attribution` drops trailing `-h`-style tokens from the title). `_chapters` assembles `#### Kapitel`: always opens `00:00 Äventyret börjar!`, one chapter per Bryggpromenader entry (`<names joined by 'och'> tar en lång promenad på en kort brygga` via `_chapter_names`), plus starred notes, time-sorted. Body lines are plain `MM:SS Title` (matched by `_CHAPTER_LINE_RE`, fully script-managed via `_set_chapter_lines`); the section exists only when there is ≥1 real chapter (`_prune_chapter_section` removes managed-only leftovers).

**Idempotency and non-destructiveness are the core contract**, and both are covered by tests — run the suite after any change to the merge logic. Rules:

- Script-managed lines only: `* ` bullets in a `####` section are replaced **only when that section has incoming notes this run**; the tally lines (`Joel:`/`Robin:`/`Henrik:`/`Kenneth:`) and the `* Kdenlive …` line are always script-managed. Everything else the user wrote must round-trip unchanged.
- Running twice must produce byte-identical output (`test_idempotent`).
- Heading levels are load-bearing: `## ` top-level sections, `### <episode-dir-name>`, `#### <section>` — section names must exactly match the headings typed in Kdenlive's notes panel.

## `kuliss sync`

`session.py` places `sources/*.mkv` on the session project. Unlike `speaker`, it matches by file name and **stream title**, because that is the crew's recording standard (decided 2026-10-30): `<date>_<initial>.mkv`, initials from `notes.TALLY_NAMES`, audio titled `Full mix` (unused backup), `Game audio`, `Voice audio`, `Comms`. `TRACKS` maps them to the template's track names: `<I> Comms`, `<Name> Voice`, `<I> Game`, video `<Name> Game`.
- `sync.py` (Kdenlive-free): a 100 Hz log-loudness envelope of the first 30 min (via `vad.decode`), FFT cross-correlation. `offset` measures both directions (my voice in your Comms, yours in mine) and averages, cancelling the call delay; confidence (peak/std) below `MIN_CONFIDENCE` is dropped, and both weak is an error. Session 28's real matches scored 23–35.
- It refuses if any target track already has clips: never touch an edit in progress. The earliest recording starts at the end of the first clip on the `Assets` audio track (the intro music).
- `timeline.add_source` writes a bin chain plus one timeline chain for the video and one per audio stream, the layout Kdenlive itself uses; Kdenlive re-probes the rest. Verified by rendering a synced project through `AppRun --render`.
- `timeline.write` is the shared backup + changed-on-disk check + atomic replace (also used by `speaker`).

## Verifying against real Kdenlive

`melt` is not on PATH. Extract it from the AppImage (`~/bin/gearlever_kdenlive_*.appimage --appimage-extract`), source `apprun-hooks/craft-runenv-hook.sh`, and set `LD_LIBRARY_PATH=squashfs-root/usr/lib`. To render the timeline rather than `main_bin`, point the root `producer` attribute at the `kdenlive:projectTractor` tractor. `AppRun --render P.kdenlive out.mp4` (with `QT_QPA_PLATFORM=offscreen`) loads the project through Kdenlive's own document model.
