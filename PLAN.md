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

## Keep the editor's own changes on re-run

- [ ] Check in the Kdenlive GUI that a save keeps the `kuliss:rect` property on the overlay's
      Transform effect. If it is dropped, a moved overlay is reset on re-run, as before
      2026-11-11; then compare against the theme's rect stored elsewhere (the bin clip).

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
- [ ] `ruff format`: `notes.py`, `mdoc.py`, `kdnotes.py` use single quotes, the rest double.
      One formatting-only commit, when nothing else is in flight.

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
