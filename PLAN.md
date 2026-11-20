# Plan

What is left after the full code edit of 2026-11-11, the template removal of 2026-11-17 and the audit of 2026-11-18 (API-first module split, notes episode
rule, detector tuning, overlay polish, lockfile and CI hardening).

## Next up (state at close, 2026-11-18)

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

## `kuliss gui`: a session checklist window (built 2026-11-19)

Built as proposed (`gui.py`, `steps.py`, `tests/test_gui.py`). Still to do:
- [ ] **Kenneth:** run `uv run --extra gui kuliss gui` and work one real session through it.
      Check that each link opens the right program (Kate for `.toml`/`.md`, Kdenlive,
      Dolphin, the video player for the preview), and that a running Finish shows progress.
- [ ] **Robin's Windows beta (PlateUp! one-shot, Robin, Jesper, Henrik, Kenneth):** install
      as in the README's Windows section, edit the session through the window, report what
      breaks or confuses. `plateup/theme.toml` drafted 2026-11-20 (`show_view = false`;
      session 02, first episode avsnitt09); still needs `_assets/avatars/jesper.png` and his
      colour, then the theme's files from `_assets/` go to Robin.
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
