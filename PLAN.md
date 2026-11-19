# Plan

What is left after the full code edit of 2026-11-11, the template removal of 2026-11-17 and the audit of 2026-11-18 (API-first module split, notes episode
rule, detector tuning, overlay polish, lockfile and CI hardening).

## Next up (state at close, 2026-11-18 evening)

Done on 2026-11-18 (`5e80d84`..`04f0392`):
- **Code audit and fixes.** The audit found the code healthy and secure. Fixes:
  - `sync` refuses two recordings of one player.
  - `new` no longer loads PyAV or Silero.
  - Atomic writes and timestamped `.bak` files are shared by every command.
  - Readable names, `ruff format`, CI actions pinned to SHAs.
- **Assets tracks.** The intro, outro and switch sounds now go on the project's own
  `Assets` tracks, beside the editor's clips. kuliss's clips never move the editor's;
  one that would overlap them is left out with a warning.
- **Overlay.** It follows only players' clips, so a green screen on `Assets` no longer
  hides it.
- **Theme.** New `show_view = false`: only who talks, with no switch sounds.
- **README:**
  - a Windows install section;
  - "Making a theme", with every asset's format and size;
  - the show folder standard, "Where files live" (`samkvam.online/` plus `_assets/`).
- **Real files.** `samkvam.online/theme.toml` has the new comments; its settings are
  unchanged.

Checked in the Kdenlive GUI on 2026-11-18:
- Green screen and `Assets` placement on the avsnitt228 copy.
- Deleting the emptied old tracks.
- The moved overlay is kept.
- A full render.

For Kenneth, in this order:

- [ ] **avsnitt227 (real).** Delete the 24 hand-placed swooshes on `Assets`, then run
      `kuliss finish`. Listen for missing or doubled swooshes.
- [ ] **`show_view = false`.** On a copy, run `--preview 30`. Check that all avatars are
      the same size, there is no label, the talking marker works and there are no
      swooshes. Then do a full run on a copy that already has swooshes and check that they
      are gone.
- [ ] **`kuliss new` + `kuliss sync`.** Use a scratch session with copied recordings and
      open it in Kdenlive. Check that the clips are there, the sync by ear, the track order
      and the mixer values (voice gain, pan, Audio contrast), and that Kdenlive saves it
      without complaint.
- [ ] **Overlap warning.** Put one of your own clips on `Assets` audio where a swoosh would
      go and run again. Expect a warning ("switch sound at MM:SS"), the swoosh left out,
      and your clip untouched.
- [ ] **Windows.** Follow the README's "Install and run your first project on Windows"
      exactly; note any step that fails or is unclear.
- [ ] **Linux ↔ Windows** (only if projects travel). Open a project saved on the other
      system and check that Kdenlive's missing-clips dialog finds everything when pointed at
      the show folder.
- [ ] **Theme from scratch.** Build one using only the README's "Making a theme"; anything
      you had to guess is a gap in the docs.
- [ ] `_assets/samkvam-session_template.kdenlive` can be deleted (no longer used).

The evening routine:
1. `kuliss new`, move the .mkv files to `sources/`, `kuliss sync`.
2. Rename `avsnittXX<nr>` to `avsnitt<nr>`, copy the project there as
   `avsnitt<nr>.kdenlive`, cut it to the episode starting at 0, and edit.
3. `kuliss notes`.
4. `kuliss finish`. Re-run it after any change to the edit.

Decided:
- 2026-11-17: no session template; namecards are replaced by the overlay; the duck stays on
  the first voice clip.
- 2026-11-18:
  - kuliss uses the `Assets` tracks and never adds its own, except the `kuliss` overlay
    track.
  - One show folder with `_assets/`; no `.kuliss` folder.
  - No `relink` command.

## For Kenneth to judge

- [ ] Watch a `kuliss finish --preview 90` in Kdenlive: are words still missed, and does the
      new look (shadows, voice-level glow and bars) work? If words are still missed, lower
      `speech_threshold` in the theme; the default was tuned on avsnitt215 only.
- [ ] `session_28_2025-10-24/avsnitt224/avsnittXX28.kdenlive` is now found without a rename
      (an `avsnitt*` folder with exactly one `.kdenlive`). Renaming it is still tidier.

## Speed and memory

- [ ] Rendering is ~90% FFV1 encoding (about 1.2 ms per 800x450 frame at 16 slices). The only
      big win left is fewer pixels, which the profile-aspect canvas rule forbids; `qtrle` is
      no way out: measured 2026-11-11 it is no faster and only 20% smaller, now that the
      overlay has soft shadows and glow. A cache for the speech analysis was measured and
      dropped: analysis is 14 s of a 2-minute run.
- [ ] Stream decoded audio into Silero window by window instead of buffering the whole voice
      track (about 77 MB per player). `window_levels` and the warm-up would need to stream too.

## Before publishing

- [ ] Privacy: use generic player names and paths in `CLAUDE.md`, `theme.example.toml` and the
      tests, instead of the crew's names and `~/documents/samkvam.online`/`~/bin/gearlever_*`.

## `kuliss gui`: a session checklist window (proposed 2026-11-19)

One window that walks through editing a whole session in the evening routine's order.
Each step shows whether it's done (read from the files on disk), a button that runs it, and
links that open the files involved in their default program. It's a second front end beside
`cli.py`, calling the same library functions; no new logic about sessions or projects.

**The window.** At the top: the session folder (a folder picker; defaults to the newest
`session_*` under the last folder used). Below it, the steps as a numbered list. At the bottom:
a log pane (warnings and results) and a progress bar. Errors (`VoiceError`) open a dialog.

**The steps** (✓ / ○ worked out from disk each time the window gets focus; nothing is stored):

1. **New session.** A form: recording date (date field) and the software versions
   (`notes.SOFTWARE_DEFAULTS`, editable), then `scaffold.next_session` + `scaffold_session`.
   Done when the session folder exists. Links: session folder.
2. **Recordings.** Move the `.mkv` files into `sources/` by hand. Shows the files found
   (`session.probe`), with the player each maps to. Done when there is at least one.
   Links: `sources/` (file manager).
3. **Sync.** `session.sync_session`. Done when the player tracks have clips. Links:
   `session_<nr>_<date>.kdenlive` (opens Kdenlive).
4. **Episodes.** Rename `avsnittXX<nr>`, copy the project in, cut it in Kdenlive (by hand).
   Lists the episodes (`notes.episodes`), each with a link to its `.kdenlive`. Done when
   there is an episode not named `avsnittXX…`. Links: the session folder.
5. **Notes.** `notes.process_session`, with a dry-run checkbox. Shows the release checklist
   (`SessionResult.checklist`) as ✓ / ○ per episode. Links: the session `.md` (text editor).
6. **Finish**, per episode: Analyse (shows switches and screen/talk %), Preview 90 s (then opens
   `<project>-overlay-preview.mkv` in the default video player), Finish. Done when
   `<project>-overlay.mkv` is newer than the project. After Finish: "reopen the project in
   Kdenlive" with a link.

**Links to where things live**, always visible in a side panel:
- the theme (`config.nearest_theme`; missing → a note pointing at `theme.example.toml`),
- the crew file (`<root>/_assets/kuliss.toml`, `config.CREW_FILE`),
- the show's `_assets/` folder, the session `.md`, the README on GitHub.

**Opening files.** `QDesktopServices.openUrl(QUrl.fromLocalFile(path))` everywhere: on Linux it
goes through `xdg-open` (so `.toml`/`.md` open in Kate if that is the default text editor,
`.kdenlive` in Kdenlive, folders in Dolphin), on Windows through the file associations. No
editor names in the code. If the system has no program for `.toml`, open it as plain text
(`text/plain`); check on both systems what happens by default.

**How it's built.**
- `kuliss/gui.py`, PySide6 (LGPL, fine beside AGPL), an optional extra: `pyproject.toml`
  `[project.optional-dependencies] gui = ["PySide6>=…"]`, started with
  `uv run --extra gui kuliss gui`. `cli.py` gets a `gui` subcommand that imports it lazily and
  says how to install the extra if PySide6 is missing.
- Long steps (sync, analyse, render) run in a `QThread`; the window stays usable but the
  step buttons are disabled while one runs. `render_overlay`'s `progress` callback drives
  the bar (through a signal, never touching widgets from the thread).
- A `logging.Handler` that forwards records to the log pane (through a signal).
- The text `cli.py` prints after a run (stats, `REOPEN`, sync summary) moves into small
  functions both front ends call, so the wording stays the same in one place.
- CLAUDE.md's API-first rule changes to "`cli.py` and `gui.py` are the only front ends".

**Tests and CI.** Step state from disk is plain functions (`gui_state.py` or inside `gui.py`
without Qt imports) and gets unit tests on the existing temp-dir fixtures. One CI smoke test
starts the window offscreen (`QT_QPA_PLATFORM=offscreen`) and closes it, on Linux and
Windows, with the `gui` extra; skip it on a Python version PySide6 has no wheels for (check
3.14 before starting).

**Left out:** an embedded video player, a theme editor, editing the Kdenlive project in the
window, automatic episode rename/copy (step 4 stays by hand until it's clear what's
repetitive), a packaged Windows `.exe` (later, if `uv run` is too much for the crew).

**Estimate:** one to two days, most of it in step state and threading, not in widgets.

## `kuliss sync` and `kuliss new` (added 2026-10-30)

- [ ] First real run: when session 29's recordings are in `sources/`, run `kuliss sync`, open
      the project in the Kdenlive GUI and check each clip plays the right audio stream. So far
      only verified on synthetic recordings and through `AppRun --render`.
- [ ] First real guest `.mkv`: check that the created guest tracks look right in the GUI.
- [ ] Known limits, fix only if they bite: re-syncing after clearing the tracks adds the files
      to the bin again (`timeline.add_source`); guest names with a hyphen or space
      (`_anna-karin.mkv`) are skipped.

## Future options (only if needed)

- [ ] More detector knobs in the theme (hangover, minimum burst); `speech_threshold` exists.
- [ ] A cross-mic bleed check, if someone starts using speakers (measured 2026-11-11: none).
- [ ] README note: clips with Kdenlive speed effects (time remapping) get slightly shifted
      speech timing.
- [ ] `--show` reprints a section of a Markdown file the user already has open. Cut it if it
      goes unused.
