# Plan

What is left after the full code edit of 2026-11-11, the template removal of 2026-11-17 and the audit of 2026-11-18 (API-first module split, notes episode
rule, detector tuning, overlay polish, lockfile and CI hardening).

## Next up (state at close, 2026-11-21)

Done on 2026-11-21 (`v3.0-beta2`, `v3.0-beta3`, then on main):
- **Names in the overlay:** every player's name under their avatar, muted, bright while
  talking; `avatars = false` for names only, with or without `show_view`.
- **From the Overlayed review:** a tile with the initial for a player without an avatar;
  `finish --still` (the overlay over one frame, three states, in a second).
- **GUI Settings pages** for the theme and crew file: what they hold in order of use, their
  problems, a preview, Create from the examples (now in `kuliss/`, so they ship). Editing
  stays in the text editor (full editors judged too big). A Still button per episode.
- **Robin's zip rebuilt** for beta3 (in the session's scratchpad; rebuild as below).
- **Privacy:** generic names and paths in the docs, example theme and tests.
- **Klatch:** the reuse promise dropped; Klatch borrows kuliss's methods, not its code.
- **Moved show folder:** `finish` stops with how to relink instead of a decode error.

Done on 2026-11-19 and 2026-11-20 (up to `v3.0-beta1`):
- **Forgiving sync:** a bad recording warns and is left out instead of stopping the run.
- **Game folders:** `<show>/<game>/session_NN_<date>/`, numbers per game; the crew file's
  `archive` counts moved sessions; the theme's `assets` key.
- **Audit fixes 1–6.**
- **The GUI as a guided workflow:** steps on the left, a page per step on the right, step
  5 written out as 5a–5d, Kdenlive's own words (marker [G], Monitor → Switch Monitor
  Fullscreen [F11], Multitrack view [F12]).
- **README rewritten:** install first, the session as one table, details folded away.
- **Robin's beta:** the PlateUp! theme, a zip with the show folder, tag `v3.0-beta1`.

Next, in this order:
1. **Send Robin the zip** and be on chat for his first session (see the GUI section
   below). The zip was built in the session's scratchpad, which a reboot clears; if it is
   gone, rebuild it from `_assets/kuliss.toml` (without the `archive` line), the theme's
   files, `plateup/theme.toml`, and a `README.txt` with the tag's install line, session
   number 2, Game "PlateUp!", first marker avsnitt09, and "sync skipped files by hand".
   Install line, now `v3.0-beta3` (2026-11-21: beta2's names under every avatar,
   `avatars = false`, avatar tiles and `finish --still`, plus the GUI's Settings pages for
   the theme and crew file, Create from the examples, and a Still button per episode):
   `uv tool install --force "kuliss[gui] @ git+https://github.com/seetee/kuliss.git@v3.0-beta3"`
2. **Collect what broke or confused him**, fix it on main, tag `v3.0-beta4`.
3. Kenneth's checks below.

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

- [ ] **`show_view = false`.** On a copy, run `--preview 30`. Check that all avatars are
      the same size, there is no label, the talking marker works and there are no
      swooshes. Then do a full run on a copy that already has swooshes and check that they
      are gone.
- [ ] **Overlap warning.** Put one of your own clips on `Assets` audio where a swoosh would
      go and run again. Expect a warning ("switch sound at MM:SS"), the swoosh left out,
      and your clip untouched.
- [ ] **Windows.** Follow the README's "Windows 10 and 11"
      exactly; note any step that fails or is unclear.
- [ ] **Linux ↔ Windows** (only if projects travel). Open a project saved on the other
      system and check that Kdenlive's missing-clips dialog finds everything when pointed at
      the show folder.
- [ ] **Theme from scratch.** Build one using only the README's "Themes"; anything
      you had to guess is a gap in the docs.

The session workflow:
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
- 2026-11-19:
  - Game software lines live in the crew file's `[software]`; no stream-name aliases in sync.
  - No waveform pre-render in sync (it would copy Kdenlive's undocumented cache format).
- 2026-11-20:
  - The GUI is a guided workflow (option B of three, with the episode matrix from C). No
    page has buttons to other steps; the tree is the navigation.
  - From now on the crew records with the OBS track names sync expects (`Full mix`, `Game
    audio`, `Voice audio`, `Comms`). Older recordings are synced by hand.
  - No stream picker in the GUI for files without those names: too much work for now.
  - Beta testers install a pinned tag (`v3.0-betaN`), never main.
- 2026-11-21:
  - Settings in the GUI show, check, preview and create; no form editors, no `tomlkit`.
  - Absolute paths stay: Kdenlive writes every file outside the project's folder as an
    absolute path when it saves, so kuliss can't keep them relative. After a move, relink
    with Kdenlive's missing-clips dialog pointed at the show folder. Kdenlive has no
    released option for this (checked 2026-11-21: bug 343386, bug 510305 open for
    cross-platform editing, and a `work/relative-paths` branch in testing in October 2026,
    per bug 476104). When a Kdenlive release ships relative paths, check that kuliss's
    `timeline.load` reads them (it already resolves relative resources against `root` and
    the project's folder) and drop the `finish.MOVED` hint if it no longer applies.

## Speed and memory

- [ ] Rendering is ~90% FFV1 encoding (about 1.2 ms per 800x450 frame at 16 slices). The only
      big win left is fewer pixels, which the profile-aspect canvas rule forbids; `qtrle` is
      no way out: measured 2026-11-11 it is no faster and only 20% smaller, now that the
      overlay has soft shadows and glow. A cache for the speech analysis was measured and
      dropped: analysis is 14 s of a 2-minute run.
- [ ] **Memory in `finish` (only if it bites: an 8 GB machine, or hour-long episodes).**
      `vad.decode` returns each voice clip whole, as 16 kHz float32 (3.8 MB per minute), and
      the players run in parallel: about 300 MB for a 20-minute episode with four players,
      900 MB for an hour. Silero only reads 512-sample windows, and the voice level needs one
      loudness value per window plus their 95th percentile, so both can be computed while
      decoding: `decode` yields chunks, `talking` scores each full window as it arrives and
      keeps its probability and dB, `window_levels` works from the dB array. About 1 MB
      instead of 300, same speed. Estimated 30–40 lines in `vad.py`, no new dependency; add
      a test that old and new give identical output on a synthetic clip.

## Before publishing

- [x] Privacy (2026-11-21): generic names and paths in `CLAUDE.md`, the README, the example
      theme and the finish/GUI tests. Kept on purpose: the crew in `notes.TALLY_NAMES` (it is
      the behaviour, tested in `test_notes`/`test_sync`) and git history (no rewrite of a
      public repo).

## `kuliss gui`: a session checklist window (built 2026-11-19)

Built as proposed (`gui.py`, `steps.py`, `tests/test_gui.py`). Still to do:
- [ ] **Kenneth:** run `uv run --extra gui kuliss gui` and work one real session through it.
      Check that each link opens the right program (Kate for `.toml`/`.md`, Kdenlive,
      Dolphin, the video player for the preview), and that a running Finish shows progress.
- [ ] **Robin's Windows beta (PlateUp! one-shot, Robin, Jesper, Henrik, Kenneth):** install
      from the tag `v3.0-beta3` (pinned, so pushes to main don't change his kuliss), edit
      the session through the window, report what breaks or confuses. Kenneth helps over
      chat. His zip (2026-11-20): `_assets/` (crew file without `archive`, with a
      `"PlateUp!"` software entry; avatars incl. Jesper `#fce241`; intro, outro, card),
      `plateup/theme.toml` (`show_view = false`; session 02, first episode avsnitt09) and a
      `README.txt`. The PlateUp! recordings probably lack the OBS stream titles: he syncs
      those by hand. New fixes for him: tag `v3.0-beta4` and send the install line.
- [ ] **Windows:** the same, and that `.toml` has a program to open it (none is set by
      default; associate it with Notepad or Kate if the link does nothing).
- [ ] **Kenneth:** the new layout (2026-11-20, steps on the left, pages on the right): click
      through every page on a real session; are the drawings in steps 4–6 right, and is
      anything still hard to find?
- [ ] Step 2 shows "?" as the player for a file sync skips (probe gives up before naming
      it); fill it from the file name only if it confuses.
- [ ] Analyse, Preview and Finish each analyse again (14 s); keep the `Analysis` between
      them only if that bites.

## `kuliss sync` and `kuliss new` (added 2026-10-30)

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
