# Plan

What is left after the full code edit of 2026-11-11 (API-first module split, notes episode
rule, detector tuning, overlay polish, lockfile and CI hardening).

## For Kenneth to judge

- [ ] Watch a `kuliss speaker --preview 90` in Kdenlive: are words still missed, and does the
      new look (shadows, voice-level glow and bars) work? If words are still missed, lower
      `speech_threshold` in the theme; the default was tuned on avsnitt215 only.
- [ ] `session_28_2025-10-24/avsnitt224/avsnittXX28.kdenlive` is now found without a rename
      (an `avsnitt*` folder with exactly one `.kdenlive`). Renaming it is still tidier.

## Keep the editor's own changes on re-run

- [ ] Keep a user-adjusted overlay position. If the `qtblend` rect on our overlay entry differs
      from what the tool last wrote, reuse it instead of resetting it. Swooshes can stay
      regenerated, but document that in the README.

## Speed and memory

- [ ] Rendering is ~90% FFV1 encoding (about 1.2 ms per 800x450 frame at 16 slices). The only
      big win left is fewer pixels, which the profile-aspect canvas rule forbids; `codec =
      "qtrle"` is the existing way out. A cache for the speech analysis was measured and
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
      (`_anna-karin.mkv`) are skipped; absent players' namecards stay in the template's
      `Nametags` track.

## Future options (only if needed)

- [ ] More detector knobs in the theme (hangover, minimum burst); `speech_threshold` exists.
- [ ] A cross-mic bleed check, if someone starts using speakers (measured 2026-11-11: none).
- [ ] README note: clips with Kdenlive speed effects (time remapping) get slightly shifted
      speech timing.
- [ ] `--show` reprints a section of a Markdown file the user already has open. Cut it if it
      goes unused.
