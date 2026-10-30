# kuliss

[![Tests](https://github.com/seetee/kuliss/actions/workflows/test.yml/badge.svg)](https://github.com/seetee/kuliss/actions/workflows/test.yml)
[![vibe coded](https://img.shields.io/badge/vibe_coded-%E2%9C%A8-ff69b4?style=flat-square)](https://en.wikipedia.org/wiki/Vibe_coding)
[![coded with Claude](https://img.shields.io/badge/coded_with-Claude_Code-CC785C?style=flat-square&logo=anthropic)](https://claude.ai/code)
[![license: AGPL v3](https://img.shields.io/badge/license-AGPL_v3-blue?style=flat-square)](LICENSE)

Tools for the boring parts of producing a multi-player let's play from Kdenlive, built for **Samkväm**. *Kuliss* is Swedish for the scenery behind the stage.

| Command | What it does |
|---|---|
| `kuliss speaker` | Adds a who-we-watch / who-talks overlay to a Kdenlive project. |
| `kuliss notes` | Syncs Kdenlive's Document Notes into the session Markdown file, with YouTube chapters. |
| `kuliss new` | Scaffolds the next session directory, with its Kdenlive project. |
| `kuliss sync` | Puts the session's recordings on the project's tracks, in sync. |

## Install

Needs [uv](https://docs.astral.sh/uv/). All dependencies (numpy, PyAV, skia-python, silero-vad-lite) are wheels, so nothing needs compiling and no system ffmpeg is required.

```bash
uv tool install git+https://github.com/seetee/kuliss.git
# or, from a clone:
uv run kuliss speaker ~/episodes/avsnitt217/avsnitt217.kdenlive --dry-run
```

## Session workflow

1. **Before recording:** in the folder that holds the `session_*` folders, run
   `kuliss new`. Give the recording date and software versions; it creates
   `session_<nr>_<date>/` with its `.md`, its Kdenlive project and `sources/`.
2. **After recording:** everyone's OBS `.mkv` goes into `sources/`, named
   `<date>_<initial>.mkv` (guests `<date>_<name>.mkv`).
3. **Sync:** inside the session folder, close the project in Kdenlive and run
   `kuliss sync`. Check that every offset has a confidence well above 10, open
   the project, and delete the `Comms` clips once the sync sounds right.
4. **Edit, one episode at a time:** open the synced session project and
   *Save Copy* it into the episode's folder, as `avsnitt<nr>/avsnitt<nr>.kdenlive`
   (rename the `avsnittXX<nr>` placeholder first). Folder and file must share
   the name, or `kuliss notes` won't see the episode. Close the session
   project, open the episode copy, trim away the start and end that belong to
   other episodes, and edit. Jot down moments in Kdenlive's Document Notes as
   you go, with a `*` after the timestamp for a YouTube chapter.
5. **Notes:** run `kuliss notes` anywhere in the session. It fills the session
   `.md` and prints what is still missing per episode.
6. **Overlay:** with the game's `theme.toml` next to or above the episode, run
   `kuliss speaker avsnitt<nr>/avsnitt<nr>.kdenlive --preview 90`, check
   `indicate-speaker/overlay-preview.mkv`, then run it without `--preview`.
   Re-run it after any re-edit.
7. **Publish:** render in Kdenlive and take the title, blurbs and `Kapitel`
   list for YouTube from the session `.md`.

## `kuliss speaker`: speaker overlay

Run it on a finished (or half-finished) Kdenlive project of a multi-player let's play. It adds a small overlay that shows:

- **whose view we are watching**: that player's avatar is enlarged and gets a name label in their colour;
- **who is talking**: a ring in the player's colour plus a small sound-bars badge, so the cue never relies on colour alone;
- **every switch between views**: the label slides to the new player and a transition sound plays.

Everything is read from the project itself: your cuts, which clip is whose, and which audio stream is each person's voice. There are no file-name dates or stream titles to configure. The overlay fades out during the intro, the outro and other full-screen clips that aren't a player's view. It works for any game: the look comes from a small theme file with a backdrop, 1–8 avatars, colours, a font and the transition sound.

### Run

| Command | What it does |
|---|---|
| `kuliss speaker P.kdenlive --dry-run` | Reports view switches, and screen and talk time per player. Writes nothing. |
| `kuliss speaker P.kdenlive --preview 90` | Renders the first 90 s to `indicate-speaker/overlay-preview.mkv`. The project is untouched. |
| `kuliss speaker P.kdenlive` | Renders the overlay and **updates the project in place**. |
| `--theme path/to/theme.toml` | Uses this theme instead of the `theme.toml` found next to or above the project. |

**Close the project in Kdenlive before running**, or at least don't save it afterwards: reopen it instead. The tool refuses to write if the project changed on disk while it worked.

### What it changes in your project

- It first saves a backup, `P.kdenlive.YYYYmmdd-HHMMSS.bak`, next to the project.
- It adds one video track (on top) and one audio track (above your other audio tracks), both named `indicate-speaker`.
- The video track holds `indicate-speaker/overlay.mkv`, spanning the whole timeline and positioned with a Transform effect. By default the file is FFV1 with alpha, which is lossless, free and open. With `codec = "qtrle"` in the theme it is `overlay.mov` instead: also lossless with alpha, about 6× smaller, but QuickTime's codec.
- The audio track holds one transition sound per view switch.
- It adds two bin clips, `indicate-speaker overlay` and `indicate-speaker sound`.

Running it again after you re-edit reuses the same tracks and clips and regenerates their contents. Nothing else in the project is touched. To take it out again, delete the two tracks and the two bin clips.

### The theme

Copy [`theme.example.toml`](theme.example.toml) to `theme.toml` next to the project, or into a folder above it such as the season folder; the nearest one wins. Keep one theme per game.

- `position` picks a corner (`top-left`, `top-right`, `bottom-left`, `bottom-right`) or an edge centre (`top`, `bottom`, `left`, `right`). `margin` is the distance from the edges the bar sits against, and `offset = [x, y]` nudges it from there in pixels (positive = right/down). For example, `position = "left"` with `offset = [0, -100]` centres the bar on the left edge, 100 px above the middle.
- `orientation = "horizontal"` (the default) draws a row, `"vertical"` a column along the frame edge. The name label sits under the viewed avatar either way; the column spaces the avatars out to leave room for it.

- `voice_track` is the name of the Kdenlive **audio track** holding that player's voice; it defaults to the player's name, and a track named `<name> Voice` (as in the session template) is found too. The tool uses the audio stream and the cuts you chose on that track.
- Video clips from the same file as that voice track count as the player's view, whichever video track they sit on. Set `source` only when someone's view is recorded in a different file. It takes a file-name pattern such as `"*_h.mkv"`, or a list of them.
- Unknown keys get a warning (usually a typo), and wrong values stop the run with a message saying what is expected.

### How it decides

- **Whose view**: for each frame, the topmost visible video track showing a player's clip wins.
  - A full-screen clip that belongs to no player hides the overlay. That means a video or image without a Transform effect, such as the intro.
  - Placed clips (namecards, picture-in-picture) and titles don't count.
  - Views shorter than 1 s are treated as flashes: they get no switch and no sound.
- **Who talks**: [Silero VAD](https://github.com/snakers4/silero-vad) runs on each voice track, following your cuts. Two thresholds (hysteresis), a 200 ms hangover and a 120 ms minimum burst stop it from flickering on breaths and clicks.
- **Contrast**: label text is black or white, whichever contrasts more with the player's colour. That is always at least 4.5:1 (WCAG AA), so any colour is safe. The talking ring gets a black or white edge so it stays visible on any backdrop.

## `kuliss notes`: session notes

Pulls the timestamped notes you write during Kdenlive
episode editing and drops them straight into your session's Markdown file — in
the right place, every time, no matter how many times you run it. It also keeps
the session file itself in shape: missing files, headings, and metadata fields
are created and repaired automatically on every run.

### What it does

When editing a multi-episode project in Kdenlive, you can use the built-in
**Document Notes** panel to jot down memorable moments, funny quotes, and
anything else worth keeping track of — complete with clickable timestamps.
This script reads those notes and writes them into your session's `.md` file
under the correct episode heading, ready for use in video descriptions, social
media posts, or wherever you need them.

On every run it:

* converts Kdenlive's internal timestamp format (`00:06:29:32`) to a clean
  `MM:SS` format (or `HH:MM:SS` past the hour) and sorts notes chronologically;
* strips all the HTML that Kdenlive wraps around the notes;
* appends notes typed **without** a section heading to the end of
  `#### Noteworthy` (after a blank line), so nothing is ever lost;
* repairs the session file to the canonical skeleton (see below) — creating it
  from scratch if it doesn't exist yet, and normalizing metadata lines written
  without bold markers (`Titel: …` becomes `**Titel:** …` in place);
* keeps the `* Kdenlive …` line under `## Mjukvaruversioner` up to date with
  the version read from the project files;
* auto-counts the **Bryggpromenader** tally from `H+1`-style notes;
* builds a paste-ready **YouTube chapter list** (`#### Kapitel`) per episode
  from the Bryggpromenader entries and any note you star (see below);
* prints a per-episode release checklist so you instantly see what still needs
  filling in.

Run it again after adding more notes? Go ahead. Only script-managed lines (note
bullets, the tally, the Kdenlive version line) are ever replaced. Everything
you wrote by hand — titles, blurbs, trailers, stray sections — stays exactly
where you put it.

### Built specifically for Samkväm

This tool is purpose-built around the **Samkväm** production workflow. It won't
work out of the box with a differently structured project — it expects the
directory layout and file naming convention below. If you're not producing
Samkväm, you're welcome to adapt the script to fit your own setup — it's short
and straightforward.

### Directory structure

```
recordings/
└── session_26_2025-06-30/
    ├── session_26_2025-06-30.md         ← session notes file (created if missing)
    ├── session_26_2025-06-30.kdenlive   ← main rough-cut project (not processed)
    ├── sources/                          ← raw recordings (not processed)
    ├── kortisar/                         ← YouTube shorts & TikToks (not processed)
    ├── avsnitt207/
    │   ├── avsnitt207.kdenlive          ← episode project with notes ✓
    │   └── ...
    └── avsnitt208/
        ├── avsnitt208.kdenlive          ← episode project with notes ✓
        └── ...
```

The rule is simple: any subdirectory whose name matches the `.kdenlive` file
inside it is treated as an episode and processed. Everything else is left
alone. Episodes are sorted naturally (`avsnitt9` before `avsnitt10`).

### Session file format

The script creates and maintains this skeleton:

```markdown
# Session 26 - 2025-06-30

## Mjukvaruversioner

* Prism Launcher 9.2
* Project Ozone 3 3.4.10
* Minecraft 1.12.2
* Resource packs
  * Faithful 32x
  * Faithful Mods - Project Ozone 3
  * Ozone Resources 3
* OBS 23.0.3
* Kdenlive 25.04.2

## Avsnittsinfo

### avsnitt207

**Titel:**
**Blurb (large):**
**Blurb (short):**
**Trailer:**

#### Noteworthy
* 06:29 A memorable quote -h
* 14:46 Something worth clipping -k

* a note typed without a section heading

#### Bryggpromenader
* 05:28 H+1
* 12:03 J+1

Joel: 1
Robin: 0
Henrik: 1
Kenneth: 0

#### Kapitel
00:00 Äventyret börjar!
05:28 Henrik tar en lång promenad på en kort brygga
06:29 A memorable quote
12:03 Joel tar en lång promenad på en kort brygga
```

(The `06:29` chapter comes from starring the corresponding Noteworthy note —
its `*` and the `-h` speaker token never reach the chapter title.)

`Noteworthy` always exists for every episode; notes typed without a section
heading are appended to its end after a blank line. `Bryggpromenader` only
appears when the episode actually has such notes, and its tally (counted from
`J+1` / `R+1` / `H+1` / `K+1` tokens) is recomputed on every run. Any other
section you create with a heading in Kdenlive's Document Notes panel becomes
an additional `####` section.

Missing metadata fields and headings are added automatically; values you've
already filled in are never touched. Metadata lines written without bold
markers (`Titel: …`) are normalized in place.

#### YouTube chapters

The `#### Kapitel` section is a chapter list ready to paste into a YouTube
description. It always opens with `00:00 Äventyret börjar!`, every
Bryggpromenader entry becomes a chapter named after who walked the plank, and
you can flag any other note as a chapter by typing a `*` directly after the
timestamp in Kdenlive's Document Notes panel:

```
00:06:29:32* Grottan öppnas -h
```

The `*` is stripped from the note bullet, and the trailing speaker token
(`-h`) is dropped from the chapter title. The section only appears when there
is at least one real chapter. Note YouTube's rules: chapters are recognized
only with at least 3 entries, the first at `00:00`, each ≥10 seconds long.

### Usage

```bash
# From anywhere inside a session tree — the session dir, an episode dir, deeper…
kuliss notes

# …or point it at a session directory
kuliss notes /path/to/session_26_2025-06-30/

# …or at a parent directory to process all sessions
kuliss notes /path/to/recordings/

# Preview what would change as a diff, without writing anything
kuliss notes --dry-run

# Print an episode's metadata and notes for copy-pasting, then exit
kuliss notes --show avsnitt207

# Scaffold the next session (asks for date and software versions)
kuliss new
```

Each run ends with a release checklist that also flags YouTube pitfalls — a
`Titel` over 100 characters (YouTube truncates), or a chapter list with fewer
than 3 entries (YouTube ignores it):

```
  checklist:
    ✗ avsnitt207: fill in Blurb (short); Titel too long (112/100 chars)  [Noteworthy 12, Kapitel 5]
    ✓ avsnitt208: ready  [Noteworthy 8, Kapitel 4]
```

`kuliss new` looks at your existing sessions and scaffolds the
next one interactively: it asks for the recording date (Enter = today) and
walks through the software versions (Enter keeps each value, type to replace,
plus free extra lines). It then creates `session_<nr>_<date>/` containing
`sources/`, `kortisar/` (for YouTube shorts and TikToks), a placeholder
episode directory `avsnittXX<nr>` (the `XX` is a literal placeholder — rename
it once the real episode number is known), a pre-filled skeleton `.md`, and
the session's Kdenlive project `session_<nr>_<date>.kdenlive`, made from
`_assets/samkvam-session_template.kdenlive` (intro, namecards, outro and the
named tracks).

## `kuliss sync`: recordings in sync

Copy everyone's recordings into the session's `sources/`, close the project in
Kdenlive, and run `kuliss sync` inside the session. It puts each recording on
the project's tracks, lined up so everyone's audio and video is in sync, with
the earliest recording starting where the intro music ends.

The recordings must follow the crew's OBS standard:

| File | Stream | Title | Goes on track |
|---|---|---|---|
| `<date>_<initial>.mkv` (`j`, `r`, `h`, `k`; guests `<date>_<name>.mkv`) | video | | `<Name> Game` (video) |
| | audio 1 | `Full mix` | not used (backup) |
| | audio 2 | `Game audio` | `<I> Game` |
| | audio 3 | `Voice audio` | `<Name> Voice` |
| | audio 4 | `Comms` | `<I> Comms` |

The streams are found by title, not by position. Syncing listens for each
person's voice in the others' `Comms` (the call as they heard it), in both
directions, which cancels the call's delay. On session 28 it landed within
0.15 s of the hand sync even in one direction. It prints each offset with a
confidence and stops if a recording can't be matched. Once you're happy with
the sync, delete the `Comms` tracks' clips unless you need them as a backup.

**Someone missing?** Sync whoever recorded; the absent player's tracks stay
empty. `kuliss speaker` leaves anyone without clips on their voice track out
of the overlay, so they get no avatar. Remove their namecard by hand.

**Guests** record to the same OBS standard and name the file after themselves:
`<date>_jesper.mkv`. Their tracks don't exist in the template, so `kuliss sync`
adds `Jesper Comms`, `Jesper Voice`, `Jesper Game` (audio) and a `Jesper Game`
video track, which goes under the intro and namecards. For the overlay, add the
guest as a `[[player]]` in that game's `theme.toml`. A crew member may also use
their full name (`_kenneth.mkv`).

`kuliss sync` refuses to touch a track that already has clips, so it can never
disturb an edit in progress; clear the recordings' tracks to sync again. Like
`kuliss speaker`, it saves a timestamped `.bak` first.

Safety details:

* Before the session file is modified, the previous version is saved next to it
  as `<name>.md.bak`, and the write itself is atomic (a crash can never leave a
  half-written file).
* The exit code is non-zero when any warning was printed (unreadable project
  file, or a `### avsnittXXX` section with no matching directory — e.g. after
  renaming an episode folder).

## Development

```bash
uv run pytest            # no media files needed
```

The code is in `kuliss/`. `vad.py`, `sync.py` and `render.py` don't depend on Kdenlive, so [Klatch](https://github.com/seetee/klatch) can reuse them.

| File | Contents |
|---|---|
| `config.py` | Theme loading and validation |
| `timeline.py` | Reading and patching the Kdenlive XML |
| `vad.py` | Speech detection |
| `render.py` | Drawing and encoding the overlay |
| `speaker.py` | `kuliss speaker` |
| `notes.py` | `kuliss notes` and `kuliss new` |
| `sync.py` | Lining recordings up by their audio |
| `session.py` | `kuliss sync`, and the project `kuliss new` creates |
| `__main__.py` | The `kuliss` command |

## License

GNU Affero General Public License v3.0 or later. See [LICENSE](LICENSE).
