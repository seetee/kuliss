# Plan

What is left after the full code edit of 2026-11-11 (API-first module split, notes episode
rule, detector tuning, overlay polish, lockfile and CI hardening).

## Next up (state at close, 2026-11-11 evening)

Added late on 2026-11-11 (commit `d9a8019`, CI green): tracks named `kuliss`, audio track
at the bottom at -24 dB, camera badge on the name pill, intro and outro placed from the theme
(`intro_audio`, `intro_video`, `outro_audio`, `outro_image`), intro music ducked where the
first voice clip starts. None of it has been opened in the Kdenlive GUI or listened to.

For Kenneth, in this order:

- [x] The four intro/outro lines are in the shared PO3 `theme.toml` in the samkvam folder
      (2026-11-17). Sessions 27 and 28 still have their own copy without them, which wins there.
- [ ] Run `kuliss finish` on a copy of an episode with no hand-placed intro, outro or
      swooshes; open it in Kdenlive. Check the first 10 s (intro video, music, the duck when
      the voices start), the last 40 s (outro music rising, card fading in and out), the
      swoosh volume against the voices, and the camera badge in motion.
- [ ] Working order agreed: game video from 0, first words at about 5-6 s, edit ends where
      the outro card should end with about 20 s of footage under it. Kuliss moves no clips.
- [ ] avsnitt227 (real): delete the old `kuliss speaker` audio track, or restore
      `avsnitt227.kdenlive.20261111-172920.bak`, and run again; a re-run renames the old
      track but does not move it or set its volume. Its `Assets` track also still holds 24
      hand-placed swooshes, so the swoosh plays twice until those are deleted.

Decided 2026-11-17:

- No session template: `kuliss new` builds the project itself (1080p60, only the `Assets`
  tracks); `kuliss sync` creates the players' tracks with the mixer from the crew file
  `_assets/kuliss.toml` and starts the recordings at 0. Still to do by Kenneth:
  - [ ] Put a `kuliss.toml` in `_assets` with the old template's mixer values (see
        `crew.example.toml`). The old template can then be deleted.
  - [ ] Open a fresh `kuliss new` + `kuliss sync` project in the Kdenlive GUI: track order,
        mixer values (voice gain, pan, Audio contrast), and that Kdenlive saves it without
        complaint. Verified so far only through `AppRun --render`.
- Namecards: the overlay replaces them; no `Nametags` track.
- The duck stays on the first voice clip.

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
