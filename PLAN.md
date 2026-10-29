# Plan

What's left from the code review of 2026-09-18. Everything else from that review is done (commit `16b119d`).

## Keep the editor's own changes on re-run

- [ ] `_ensure_clip` (`timeline.py`) deletes *all* properties on our two bin clips and forces `kdenlive:folderid = -1`. It should replace only the properties it owns, so a bin folder, a favourite star or markers survive a re-run.
- [ ] Keep a user-adjusted overlay position. If the `qtblend` rect on our overlay entry differs from what the tool last wrote, reuse it instead of resetting it. Swooshes can stay regenerated, but document that in the README.

## Speed and memory

- [ ] Stream decoded audio into Silero window by window instead of buffering the whole voice track (`vad.decode`/`speech_windows`). That takes memory from about 77 MB per player to almost nothing, which matters for long episodes or 8 players.

## Tidy-up

- [ ] Remove the unused fields `Track.index` and `Track.tractor` (`timeline.py`).
- [ ] Annotate `die()` as `-> NoReturn` (`config.py`).
- [ ] `"{%s}" % uuid.uuid4()` → f-string (`timeline.py`).
- [ ] Keep `fps` as a `Fraction` straight from the profile, exact for 59.94/29.97, and drop `limit_denominator(1001)` in `render.py`.

## Before publishing

- [ ] Commit `uv.lock` (remove it from `.gitignore`) so installs get the tested versions.
- [ ] GitHub Actions (`uv run pytest` and a basic `ruff check` are in): add `uv run --resolution lowest-direct pytest` to keep the minimum versions honest (they were verified by hand on 2026-09-18), plus `ruff check`.
- [ ] `pyproject.toml`: `requires-python = ">=3.12"` (numpy 2.5 dropped 3.11, so 3.11 pins us to numpy 2.4.x); then classifiers; add `--version` to `kuliss speaker`.
- [ ] Privacy: use generic player names and paths in `CLAUDE.md`, `theme.example.toml` and the tests, instead of the crew's names and `~/documents/samkvam.online`/`~/bin/gearlever_*`.

## Future options (only if needed)

- [ ] An optional `[speech]` theme section for the detector thresholds (`ON`/`OFF`, hangover, minimum burst), for a mic that behaves differently.
- [ ] Crop non-square avatars to a centred square instead of stretching them (`render.py`, `_image`).
- [ ] README note: clips with Kdenlive speed effects (time remapping) get slightly shifted speech timing.

## `notes.py` (from kdenlive-commentor)

### Simplification pass (ponytail-review of `ad328aa~1..1549135`)

Line numbers are against `kdenlive_commentor.py` at 1549135, now `kuliss/notes.py` (one line less: its shebang is gone). Run `uv run pytest tests/test_notes.py`
after each item — idempotency and non-destructiveness are the contract.

- [ ] **L61-69** — drop `_version()`; `--version` can use `f'%(prog)s {__version__}'`.
      Kills the importlib lookup and the duplicated `1.0.0` (or make pyproject's
      version dynamic from `__version__`). *-8*
- [ ] **L455-481** — `_prune_chapter_section` and `_prune_orphan_section` are the same
      loop with a different "is managed" test. One `_prune_section(episode, title,
      is_managed)`. *-10*
- [ ] **L792-796, L805-807** — `--new` and the `new` positional are two spellings of one
      command; the `Path('new').is_dir()` guard exists only to disambiguate them.
      Keep `new` (`kuliss new`), delete the flag and the guard. *-8*
- [ ] **L415-423** — `_chapter_names`: `list(dict.fromkeys(dict(TALLY_NAMES)[i.upper()]
      for i, _ in _TALLY_TOKEN_RE.findall(text)))`. *-6*
- [ ] **L556-560** — chapter count via `next((genexp), 0)` → one `sum(...)`. *-4*
- [ ] **L106-108** — inline `_strip_attribution` into its single caller at L158. *-4*
- [ ] **L546-550** — Titel-length check re-walks lines L541 already walked; fold into a
      `next(...)`. *-3*
- [ ] **L384, L417** — `{k: v for k, v in TALLY_NAMES}` → `dict(TALLY_NAMES)`.

Net: **-45 lines** (-31 if `--show` stays).

#### Deferred / judgement call

- [ ] **L522-531, L797-800** — `--show` reprints a section of a Markdown file the user
      already has open. Cut only if it goes unused in practice. *-14*
