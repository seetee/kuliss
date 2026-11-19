# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`kuliss` (AGPL-3.0-or-later) is a set of Kdenlive tools for the **Samkväm** let's play, run as one `kuliss` command.

**API first:** `cli.py` and `gui.py` are the only front ends: the only modules that parse arguments, print, prompt or set exit codes (argparse subcommands; each imports its module lazily, so `notes`/`new` never load skia/PyAV/Silero). The report text both show after a command lives in `steps.py` (`*_report`), with `steps.state`, which reads where a session stands from disk. Everything else is a library: functions return data (`finish.analyse` → `Analysis`, `notes.process_session` → `SessionResult`, `session.sync_session` → `SyncResult`, `scaffold.scaffold_session` → `Scaffolded`), warn through `logging`, and fail with `errors.die()` → `VoiceError`. Don't add `print`, `input` or `sys.exit` outside them.

It merges two former projects, `indicate-speaker` and `kdenlive-commentor`, and both histories are kept.

Klatch (`../klatch`, an automatic podcast pipeline) will reuse `vad.py`, `sync.py`, `render.py` and the YouTube chapter/limit logic in `notes.py`. Klatch's input is per-person audio files, **not** a Kdenlive project, so keep those parts free of Kdenlive dependencies. Split the YouTube helpers out of `notes.py` only once Klatch actually imports them.

## Commands

```bash
uv run kuliss finish P.kdenlive --dry-run      # analyse only; prints switches + screen/talk %
uv run kuliss finish P.kdenlive --preview 90   # first 90 s -> P-overlay-preview.mkv
uv run kuliss finish P.kdenlive                # render + patch the project
uv run kuliss notes [dir]                       # session dir, parent dir, or bare from anywhere inside a session tree
uv run kuliss notes --dry-run                   # diff preview, no writes
uv run kuliss notes --show avsnittXXX           # print one episode's section
uv run kuliss new                               # scaffold next session dir + its .kdenlive
uv run kuliss sync [session dir]                # sources/*.mkv onto the project's tracks, in sync
uv run --extra gui kuliss gui                   # the session window (PySide6 is the optional gui extra)
uv run pytest                                   # single test: -k <name>; no media needed
```

Test end to end only on a **copy** of a real project or session directory. The user's projects and Kdenlive backups live under `~/documents/samkvam.online/…` and `~/.local/share/kdenlive/.backup/`. CI (`.github/workflows/test.yml`) runs pytest on 3.12/3.14 (Linux and Windows) from `uv.lock`, once more with `--resolution lowest-direct`, then `uv run ruff check` and `uv run ruff format --check` (rules in `pyproject.toml`: E, F, UP, B, SIM, I; line-length 100; E741 enforced, so no single-letter `l`). Run `uv run ruff format` before committing. The actions are pinned to commit SHAs (tag in a comment); bump both together. No 3.15 job yet: `silero-vad-lite` 0.4.0 has no cp315 wheel (checked 2026-11-18).

## `kuliss finish`

`kuliss finish` (`finish.py`: `analyse` → `render_overlay` → `apply`; called `kuliss speaker` until 2026-11-17, and before that the separate `indicate-speaker`) reads a Kdenlive project of a multi-player let's play and patches it **in place**, after a timestamped `.bak`. It adds one video track named `kuliss` (on top) and puts its other clips on the project's `Assets` tracks, beside the editor's own clips there, as the crew did by hand (avsnitt227):
- The `kuliss` video track holds a transparent overlay: a backdrop with 1–8 player avatars, the viewed player enlarged with a name label (with a camera badge on its corner), and a talking marker on whoever speaks.
- The `Assets` audio track gets a transition sound at every switch between players' views, plus the intro and outro music; the `Assets` video track the intro video and outro card. A missing `Assets` track is created (audio at the bottom, mixer `SOUND_LEVEL` = −24 dB).

The look comes from a per-game `theme.toml` (see `theme.example.toml`), found next to or above the project (`config.nearest_theme`; the crew keeps its main game's theme in the folder holding the `session_*` dirs, and `kuliss new` warns when there is none).

The project file is the single input. Cuts, clip-to-player mapping (by source file name; by default the files on the player's voice track, see `with_sources`) and each voice's audio stream (`audio_index` on the voice track's clips) all come from it. Don't reintroduce file-name/date/stream-title matching.

The overlay track is named `kuliss` (`TRACK_NAME`) and the bin clips `kuliss speaker …` (`CLIP_PREFIX`; kept when the command became `finish`), and those names are how a re-run finds them. Tracks still named `kuliss finish` (`OLD_TRACK_NAME`, used for a few hours on 2026-11-11) are found and renamed. Until 2026-11-18 the sounds went on a `kuliss` audio track and the intro/outro on `Assets Kuliss` when `Assets` held the editor's clips (`OLD_TRACKS`); a re-run empties those of our clips and warns that they can be deleted (kuliss never deletes a track). The overlay is written next to the project as `<project>-overlay.mkv`. (The `indicate-speaker` names and `indicate-speaker/` folder from before 2026-11-11 were only ever used in tests; no project depends on them.)

- `config.py`: `Theme`/`Player` dataclasses and `load_theme`. Every value is type- and range-checked, and unknown keys warn (`THEME_KEYS`/`PLAYER_KEYS`: add new keys there). Every expected failure goes through `die()` → `VoiceError` (both in `errors.py`), printed once by `cli.main()` as `ERROR: …`. `timeline.load` also converts structural surprises (`KeyError` and similar) into `die()`.
- `timeline.py`: stdlib ElementTree only, with targeted edits. Everything the tool doesn't own must round-trip untouched.
  - `load` finds the active sequence tractor (via `docproperties.activetimeline`) and turns playlists into `Entry`s (timeline start, length, resource, src_in, audio_index, fullscreen).
  - `view_map`: the topmost visible video track showing a player's clip wins. Clips that are no player's are ignored, wherever they are (until 2026-11-18 a full-screen one meant "no view"; an editor's transparent green-screen clip on `Assets` then hid the overlay). `finish.analyse` blanks the intro video and outro card spans itself.
  - `view_spans` absorbs runs shorter than `MIN_SPAN`.
  - `cuts` only counts player→player switches.
  - `patch` reuses or creates our tracks and bin clips (bin clips are identified by `kdenlive:clipname` prefix `kuliss speaker`), so re-runs are byte-identical. `_ensure_clip` rewrites our clips' properties but keeps `EDITOR_PROPS` (bin folder, markers, rating, tags). The overlay's Transform effect carries `kuliss:rect` (`PLACED`), the rect we last wrote; if the live `rect` differs from it (`_moved_placement`), the editor moved it and the filter is kept as it is. Kdenlive keeps that property when it saves the project (checked in the GUI on 2026-11-18).
  - Intro and outro (`_bookend_entries`, theme keys `config.BOOKENDS`): `bookends(length, fps)` gives the fixed positions, copied to the frame from the crew's hand-edited episodes (avsnitt215, 227), with the volume curves in `LEVELS` and the card's fades. Only the intro's duck moves: it starts where the first voice clip does (`duck_at`, within `DUCK_RANGE`, else `DUCK_AT`). `_refill` merges our clips into a track: it drops our old entries (by bin `kdenlive:id`, `_our_ids`), keeps every editor entry at its frame, and adds ours in priority order (intro and outro before switch sounds), leaving out with one warning any that would overlap something already there (also the second playlist, which holds same-track mixes). The editor's clips are never moved or changed. The outro is anchored to the project's end and never extends it. `finish.analyse` blanks the view over the intro video and outro card itself, so the first run (clips not yet placed) and every re-run give the same overlay. An image clip is a single `producer` shared by bin and timeline (`_ensure_clip(image=True)`), as Kdenlive writes them.
  - Inserting a track must renumber `a_track`/`b_track` on the sequence's transitions, the track indices in the `sequenceproperties.groups` JSON, and `activeTrack`/`audioTarget`/`videoTarget`. Those Kdenlive indices exclude the black track, so they are `seq index - 1`. Also bump `tracksCount`.
- `show_view = false` (theme): only who talks. `layout` drops the enlarged size and label room, `Painter.draw` the label, `analyse` returns no cuts (so no switch sounds), and `sound` becomes optional (`patch` takes `sound=None`).
- `vad.py`: must not import Kdenlive code at runtime (`timeline.Entry` is a `TYPE_CHECKING` import only), so Klatch can call `decode`/`speech_windows` on raw audio files. PyAV decodes each voice entry (seek, then resample to 16 kHz mono). `silero-vad-lite` scores 512-sample windows; `smooth()` applies hysteresis, hangover, minimum burst and a 2-window onset lead. The constants were tuned on avsnitt215 (2026-11-11): `MIN_BURST = 0.12` dropped about one burst in ten (short words), so keep it at 0.06 unless measured otherwise; the theme's `speech_threshold` overrides `ON`. `talking()` decodes `WARMUP` seconds before each clip so Silero isn't cold at a cut, and returns a per-frame voice level (`window_levels`, dB relative to the clip's loud speech; 0 = silent), which drives the glow and sound bars. There is no loudness gate or normalisation: quiet mics are fine for Silero. Keep `silero-vad-lite>=0.4`: 0.2.1 (which an old local lock pinned) has no Python 3.14 wheels and a weaker model; on avsnitt215, 0.4.0 finds 2–4 points more talk time, all of it sound about 10 dB below normal speech and 30 dB above silence, and is so decisive that `speech_threshold` between 0.35 and 0.7 changes under 1 point.
- `render.py`:
  - skia draws each frame; PyAV encodes per `CODECS`: theme `codec` is `ffv1` (default, `.mkv`, `bgra`) or `qtrle` (`.mov`, `argb`). Alpha is load-bearing: never add a codec without checking that alpha survives in Kdenlive (VP8/VP9 WebM alpha doesn't). `test_render_is_lossless_with_alpha` round-trips both.
  - `Painter` is built before speech analysis so bad avatars, backdrops or fonts fail fast. `load_image`/`load_font` turn skia failures into `die()`.
  - The canvas always has the **profile's aspect ratio**, so MLT maps it 1:1 onto a qtblend `rect` of the same size (verified with melt). Don't make it a different aspect.
  - Label text colour is `on_colour()` (black or white): the better of the two is always ≥ 4.5:1, so no colour ever needs adjusting.
  - Identical frame states are cached; voice levels are quantised to `LEVEL_STEPS` so the cache keeps hitting.
  - FFV1 encoding is ~90% of a run (drawing is negligible), so optimise encoder options, not Python. 16 slices measured 40% faster than 4.
  - The panel is inset by `Layout.inset` inside the canvas (room for its shadow); `placement()` subtracts it so the panel's edge, not the canvas's, sits at the theme margin. Avatar shadows follow the picture's alpha (`DropShadowOnly`), since avatars often have a transparent border.

## `kuliss notes` and `kuliss new`

`notes.py` (formerly `kdenlive_commentor.py`, stdlib only) merges timestamped notes from Kdenlive project files into a session Markdown file, repairing that file to a canonical skeleton on every run. Extraction (the `kdenlive:documentnotes` XML property) lives in `kdnotes.py`, the Markdown block model in `mdoc.py`, and `kuliss new` in `scaffold.py`; `notes.py` re-imports their names. It assumes the directory layout and session-file skeleton documented in README.md.

The checklist flags YouTube pitfalls: Titel > 100 chars, chapter lists with < 3 entries. `scaffold.next_session` derives the next session number from existing `session_*` dirs; `cli._new` prompts for the recording date and software versions (`_prompt` falls back to defaults on EOF, which is what the tests use); `scaffold.scaffold_session` creates `sources/`, `kortisar/` (shorts/TikToks), a placeholder episode dir `avsnittXX<nr>` (literal `XX` — episode numbers aren't known at scaffold time), the skeleton `.md` via the `ensure_*` machinery, and (via `timeline.create_project`; `new` loads numpy but never PyAV, skia or Silero) `session_<nr>_<date>.kdenlive`, built from code since 2026-11-17 (there is no template any more): `timeline.new_project` (the `SKELETON` string, 1080p60, cut down from a Kdenlive 26.08 save) plus the two empty `Assets` tracks and the master volume. The software lines are `notes.SOFTWARE_DEFAULTS` (OBS, Kdenlive, kuliss: every session) after the chosen game's lines from the crew file's `[software]` table (`scaffold.software_presets`; first game is the default, `none` allowed). Mixer settings come from the crew file `<root>/_assets/kuliss.toml` (`config.CREW_FILE`, `load_crew` → `Crew`; see `crew.example.toml`); a missing file warns and gives 0 dB, centred. `timeline._mix` writes a track's mixer (acontrast, volume, panner) as Kdenlive does, only when the track is created.

Exit code is 1 if any warning was printed (unreadable `.kdenlive`, stale `###` section with no matching directory). Real writes are atomic and preceded by a timestamped `<name>.md.<stamp>.bak` of the previous version (`files.write_atomic`/`files.backup`, shared by every command).

Tests build synthetic `.kdenlive` fixtures in temp dirs (`SessionTree` helper in `tests/test_notes.py`) — no committed fixture data.

Pipeline:

1. **Discovery** — `discover` walks up from the start directory to find a session dir (name starts with `session_`, or contains `session_*.md`/`.txt`), falling back to scanning for `session_*` children. Episodes (`notes.episodes`) are subdirectories named `avsnitt…` (`EPISODE_PREFIX`) holding a same-named `.kdenlive` or, failing that, exactly one `.kdenlive`; natural-sorted. `kortisar/`, `smaklipp/` and the like are never episodes, even with a same-named project inside.

2. **Extraction** — `extract_project` parses the `.kdenlive` XML, feeding the `kdenlive:documentnotes` Qt-richtext HTML into `_NotesParser` (an `html.parser.HTMLParser`). Headings at any level typed in Kdenlive's notes panel become section names; notes before any heading are collected under the internal `ORPHAN_SECTION` name and end up appended to the end of `#### Noteworthy` after a blank line (no separate section is written; `_prune_orphan_section` removes legacy empty/superseded ones). `<a>` tags carry `HH:MM:SS:FF` timestamps, converted to `MM:SS` (or `HH:MM:SS`) and sorted chronologically. It also reads `kdenlive:docproperties.kdenliveversion`. Per-episode parse errors warn and continue.

3. **Document model** — the session `.md` is parsed by `parse_doc` into a `Block` tree (heading level/title + verbatim body lines + children) and rendered back with `render_doc`. A block ends at the next heading of same-or-higher level, so content after an episode under a `##`/`#` heading is never mistaken for episode content. Untouched blocks round-trip byte-for-byte.

4. **Skeleton repair** — `ensure_skeleton` / `ensure_episode` / `_ensure_metadata` / `ensure_section` create anything missing: the `# Session …` title, `## Mjukvaruversioner` (seeded from `SOFTWARE_DEFAULTS` when empty), `## Avsnittsinfo`, and a `### <episode>` block with the `METADATA_FIELDS` lines per on-disk episode. `_ensure_metadata` also normalizes unbolded metadata lines (`Titel: x` → `**Titel:** x`) in place — never duplicating them. Only `#### Noteworthy` is created unconditionally; `Bryggpromenader` (and any custom section) only when notes exist for it.

5. **Managed updates** — `_set_bullets` rewrites a section's `* ` bullets (and the Bryggpromenader tally lines, auto-counted by `_tally` from `H+1`-style tokens); `_update_software` maintains the `* Kdenlive <version>` line. A per-episode release checklist comes from `checklist()` (`Check` objects, also in `SessionResult.checklist`).

6. **Chapters** — a `*` typed directly after a note's timestamp in Kdenlive flags it as a YouTube chapter (`_NotesParser.chapters`; the `*` is stripped from the note, `_strip_attribution` drops trailing `-h`-style tokens from the title). `_chapters` assembles `#### Kapitel`: always opens `00:00 Äventyret börjar!`, one chapter per Bryggpromenader entry (`<names joined by 'och'> tar en lång promenad på en kort brygga` via `_chapter_names`), plus starred notes, time-sorted. Body lines are plain `MM:SS Title` (matched by `_CHAPTER_LINE_RE`, fully script-managed via `_set_chapter_lines`); the section exists only when there is ≥1 real chapter (`_prune_chapter_section` removes managed-only leftovers).

**Idempotency and non-destructiveness are the core contract**, and both are covered by tests — run the suite after any change to the merge logic. Rules:

- Script-managed lines only: `* ` bullets in a `####` section are replaced **only when that section has incoming notes this run**; the tally lines (`Joel:`/`Robin:`/`Henrik:`/`Kenneth:`) and the `* Kdenlive …` line are always script-managed. Everything else the user wrote must round-trip unchanged.
- Running twice must produce byte-identical output (`test_idempotent`).
- Heading levels are load-bearing: `## ` top-level sections, `### <episode-dir-name>`, `#### <section>` — section names must exactly match the headings typed in Kdenlive's notes panel.

## `kuliss sync`

`session.py` places `sources/*.mkv` on the session project. Unlike `finish`, it matches by file name and **stream title**, because that is the crew's recording standard (decided 2026-10-30): `<date>_<initial>.mkv`, initials from `notes.TALLY_NAMES`, audio titled `Full mix` (unused backup), `Game audio`, `Voice audio`, `Comms`. `TRACKS` maps them to track names: `<I> Comms`, `<Name> Voice`, `<I> Game`, video `<Name> Game`.
- `sync.py` (Kdenlive-free): a 100 Hz log-loudness envelope of the first 30 min (via `vad.decode`), FFT cross-correlation. `offset` measures both directions (my voice in your Comms, yours in mine) and averages, cancelling the call delay; confidence (peak/std) below `MIN_CONFIDENCE` is dropped, and both weak is an error. Session 28's real matches scored 23–35.
- Guests: a file suffix of more than one letter that isn't a crew name (`_jesper.mkv`) is a guest; `TRACKS` then uses their name for `{i}` too, and their tracks are created like the crew's. A crew member's full name (`_kenneth.mkv`) maps to the crew. Guests are not added to `TALLY_NAMES`, which also drives the tally lines.
- `finish` drops players with no voice clips (`timeline.present`), so whoever missed a session gets no avatar.
- Forgiving per recording (2026-11-19): a missing stream or video only warns and gets no track; without `Comms` (or the reference's) `sync.offset` uses the one direction left and warns; an unreadable or unmatched file, or one with neither Voice nor Comms, is skipped with a warning (`SyncResult.left_out`). The reference is the first recording with both. Only the safety checks below and "no recordings at all" still stop the run.
- After placing, `timeline.group` writes Kdenlive "Normal" groups (as Ctrl+G does) into `sequenceproperties.groups`: all Voice clips, and per player the game video with its Game audio. Leaves are `<track index without black>:<start frame>:-1`.
- Then `timeline.collapse_tracks` sets `kdenlive:collapsed` = 28 (`COLLAPSED`, the header height; 0 = full view) on every track, as in 304 of the crew's 307 track tractors.
- It refuses if any target track already has clips: never touch an edit in progress. The earliest recording starts at 0 (`kuliss finish` places the intro over it).
- It creates every missing player track, grouped by kind (all Comms, all Voice, all Game, then the video tracks under `Assets`), crew in `TALLY_NAMES` order, guests last, with the crew file's mixer on Voice and Game tracks.
- `timeline.add_source` writes a bin chain plus one timeline chain for the video and one per audio stream, the layout Kdenlive itself uses; Kdenlive re-probes the rest. Verified by rendering a synced project through `AppRun --render`.
- `timeline.write` is the shared backup + changed-on-disk check + atomic replace (also used by `finish`).

## `kuliss gui`

`gui.py` (PySide6-Essentials, the optional `gui` extra; `cli._gui` says how to install it when it's missing) is one window listing a session's steps in the order of the README's session workflow. Its text follows the crew's workflow (create, recordings, sync, mark the episodes, then per episode: make its project, choose the views, finish, notes, render). Episodes come from the session project's guides named `avsnitt…` (`steps.markers`, start frames), merged with the episode folders on disk. Done or not comes from `steps.state`, re-read whenever the window gets focus; nothing is stored except the last session opened (`QSettings`). Files open through `QDesktopServices` (links in `QLabel`s with `setOpenExternalLinks`), never a named program. Commands run in a `Job` (`QThread`); widgets are touched only through signals, the window is disabled while one runs and refuses to close. Library warnings reach the log pane through `LogHandler`. `steps.py` must not import Qt, so `tests/test_gui.py` tests the state without the extra; its window test skips without PySide6. CI installs the extra (plus Qt's libGL/xkbcommon/fontconfig on Linux).

## Verifying against real Kdenlive

`melt` is not on PATH. Extract it from the AppImage (`~/bin/gearlever_kdenlive_*.appimage --appimage-extract`), source `apprun-hooks/craft-runenv-hook.sh`, and set `LD_LIBRARY_PATH=squashfs-root/usr/lib`. To render the timeline rather than `main_bin`, point the root `producer` attribute at the `kdenlive:projectTractor` tractor. `AppRun --render P.kdenlive out.mp4` (with `QT_QPA_PLATFORM=offscreen`) loads the project through Kdenlive's own document model.
