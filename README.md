# kuliss

[![Tests](https://github.com/seetee/kuliss/actions/workflows/test.yml/badge.svg)](https://github.com/seetee/kuliss/actions/workflows/test.yml)
[![vibe coded](https://img.shields.io/badge/vibe_coded-%E2%9C%A8-ff69b4?style=flat-square)](https://en.wikipedia.org/wiki/Vibe_coding)
[![coded with Claude](https://img.shields.io/badge/coded_with-Claude_Code-CC785C?style=flat-square&logo=anthropic)](https://claude.ai/code)
[![license: AGPL v3](https://img.shields.io/badge/license-AGPL_v3-blue?style=flat-square)](LICENSE)

Tools for the boring parts of producing a multi-player let's play from Kdenlive, built for **Samkväm**. *Kuliss* is Swedish for the scenery behind the stage.

| Command | What it does |
|---|---|
| `kuliss finish` | Finishes an episode: who-we-watch / who-talks overlay, switch sounds, intro and outro. |
| `kuliss notes` | Syncs Kdenlive's Document Notes into the session Markdown file, with YouTube chapters. |
| `kuliss new` | Scaffolds the next session directory, with its Kdenlive project. |
| `kuliss sync` | Puts the session's recordings on the project's tracks, in sync. |

## Install

Needs [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer (uv fetches it). All dependencies (numpy, PyAV, skia-python, silero-vad-lite) are wheels, so nothing needs compiling and no system ffmpeg is required.

```bash
uv tool install git+https://github.com/seetee/kuliss.git
# or, from a clone:
uv run kuliss finish ~/episodes/avsnitt217/avsnitt217.kdenlive --dry-run
```

Update later with `uv tool upgrade kuliss`.

### Install and run your first project on Windows

kuliss runs on Windows 10 and 11 too; the automated tests run there on every change. A full episode has not yet been finished on Windows, so check the first result carefully.

1. **Install uv.** Open PowerShell (not as administrator) and run the command from the [uv installation page](https://docs.astral.sh/uv/getting-started/installation/):

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Close PowerShell and open a new one, so it finds `uv`.
2. **Install kuliss.** This downloads Python and everything else kuliss needs; git is not required:

   ```powershell
   uv tool install https://github.com/seetee/kuliss/archive/refs/heads/main.zip
   kuliss --help
   ```

   If `kuliss` is not found, run `uv tool update-shell` and open a new PowerShell. To update later, run the install command again with `--force` added.
3. **Get the theme in place.** Put the game's `theme.toml` (see [Making a theme](#making-a-theme)) next to your episode's `.kdenlive` file or in a folder above it, together with the images and sounds it names. The paths inside a theme are relative to the theme file and use `/`, so the same theme works on Linux and Windows.
4. **Check, preview, finish.** Close the project in Kdenlive, then, with the path in quotes if it has spaces:

   ```powershell
   cd "C:\Users\you\Videos\Samkväm\session_28_2026-11-01\avsnitt228"
   kuliss finish avsnitt228.kdenlive --dry-run      # does it find every player?
   kuliss finish avsnitt228.kdenlive --preview 90   # look at avsnitt228-overlay-preview.mkv
   kuliss finish avsnitt228.kdenlive                # render and update the project
   ```

   Open the project in Kdenlive again afterwards. A backup of the old version, `avsnitt228.kdenlive.<date>-<time>.bak`, sits next to it.

Work on a copy the first time. If the crew moves projects between Linux and Windows, check that Kdenlive still finds every clip before running kuliss; that case has not been tested.

## Where files live

One folder holds the whole show, for Samkväm `samkvam.online/`. It is the unit you move, copy or sync to another computer, and nothing outside it is used.

```
samkvam.online/
├── theme.toml              the main game's theme (kuliss finish)
├── _assets/                everything shared between sessions
│   ├── kuliss.toml         the crew file: track mixer levels (kuliss new, sync)
│   ├── avatars/            one picture per player
│   ├── episode-media/      intro and outro music and video
│   ├── design-system/      outro card, logos, fonts
│   └── namecard/, …        switch sound, namecards, title cards, green screens
└── session_28_2025-10-24/
    ├── theme.toml          only when this session plays another game
    ├── session_28_2025-10-24.md
    ├── session_28_2025-10-24.kdenlive
    ├── sources/            the raw recordings
    └── avsnitt228/avsnitt228.kdenlive
```

- **Shared files go in `_assets/`**, never in a session folder or elsewhere on the disk. That is where kuliss looks for the crew file, and themes point into it.
- **A theme uses paths relative to itself**, such as `_assets/avatars/kenneth.png`, so it keeps working wherever the show folder lands, on Linux or Windows.
- **kuliss's own clips repair themselves:** the overlay, switch sounds, intro and outro get their current path on every run of `kuliss finish`.
- **Kdenlive stores full paths** (`/home/kenneth/documents/samkvam.online/_assets/…`) for clips outside the project's own folder, such as namecards placed by hand. On another computer Kdenlive reports them missing when the project opens; let its dialog search the show folder to find them again.

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
   `kuliss finish avsnitt<nr>/avsnitt<nr>.kdenlive --preview 90`, check
   `avsnittNNN-overlay-preview.mkv` next to the project, then run it without `--preview`.
   Re-run it after any re-edit.
7. **Publish:** render in Kdenlive and take the title, blurbs and `Kapitel`
   list for YouTube from the session `.md`.

### The same in a window: `kuliss gui`

```bash
uv run --extra gui kuliss gui            # from a clone
uv tool install --force "kuliss[gui] @ git+https://github.com/seetee/kuliss.git"   # or add the extra to an installed kuliss
```

The window lists the steps above for one session, with ✓ for what is done (worked out from
the files each time the window gets focus), a button for each command, and links that open
the session folder, `sources/`, the projects, the session `.md`, the theme and the crew file
in your default programs (on Linux whatever `xdg-open` picks: Kate for text, Kdenlive for
projects, Dolphin for folders). It opens the session you had last, or pass a folder:
`kuliss gui ~/documents/samkvam.online`. Finish's *Preview 90 s* plays the preview when it is
done. The commands are the same as on the command line; warnings and results show in the
log at the bottom.

## `kuliss finish`: overlay, sounds, intro and outro

Run it on a finished (or half-finished) Kdenlive project of a multi-player let's play. It adds a small overlay that shows:

- **whose view we are watching**: that player's avatar is enlarged and gets a name label in their colour;
- **who is talking**: a ring in the player's colour plus a small sound-bars badge, so the cue never relies on colour alone; the ring's glow and the bars move with the voice level;
- **every switch between views**: the label slides to the new player and a transition sound plays.

With `show_view = false` in the theme it shows only who is talking: all avatars the same size, no name label, and no switch sounds.

Everything is read from the project itself: your cuts, which clip is whose, and which audio stream is each person's voice. There are no file-name dates or stream titles to configure. The overlay fades out during the intro, the outro and other full-screen clips that aren't a player's view. It works for any game: the look comes from a small theme file with a backdrop, 1–8 avatars, colours, a font and the transition sound.

### Run

| Command | What it does |
|---|---|
| `kuliss finish P.kdenlive --dry-run` | Reports view switches, and screen and talk time per player. Writes nothing. |
| `kuliss finish P.kdenlive --preview 90` | Renders the first 90 s to `P-overlay-preview.mkv`, next to the project. The project is untouched. |
| `kuliss finish P.kdenlive` | Renders the overlay and **updates the project in place**. |
| `--theme path/to/theme.toml` | Uses this theme instead of the `theme.toml` found next to or above the project. |

**Close the project in Kdenlive before running**, or at least don't save it afterwards: reopen it instead. The tool refuses to write if the project changed on disk while it worked.

### What it changes in your project

- It first saves a backup, `P.kdenlive.YYYYmmdd-HHMMSS.bak`, next to the project.
- It adds one video track named `kuliss`, on top. Everything else goes on your `Assets` tracks, next to your own clips there; if the project has no `Assets` track, it creates one (the audio one's mixer starts at −24 dB).
- The video track holds `P-overlay.mkv` (written next to the project), spanning the whole timeline and positioned with a Transform effect. By default the file is FFV1 with alpha, which is lossless, free and open. With `codec = "qtrle"` in the theme it is `P-overlay.mov` instead: also lossless with alpha and about 20% smaller (no faster to render), but QuickTime's codec.
- The `Assets` audio track gets one transition sound per view switch. Your own clips on the `Assets` tracks are never moved: a sound, intro or outro that would overlap one of them is left out, and the run warns which.
- It adds two bin clips, `kuliss speaker overlay` and `kuliss speaker sound`.
- With `intro_audio`, `intro_video`, `outro_audio` and `outro_image` in the theme (each optional), it also places the show's intro and outro, with one more bin clip each. They go on the `Assets` tracks (audio and video). The intro music starts at the top and is lowered 15 dB where the first voice clip starts (anywhere from 1 to 15 s in; otherwise at 5.5 s). The intro video starts half a second in. The outro card covers the last 20 s, fading in and out, and the outro music starts 17 s before the card and rises to full volume when it appears. So end your edit where the outro card should end, with about 20 s of footage for it to sit on. The overlay hides during the intro video and the outro card.

Running it again after you re-edit reuses the same tracks and clips and regenerates their contents. If you moved, resized or animated the overlay's Transform effect in Kdenlive, your version is kept; otherwise it follows the theme. Nothing else in the project is touched. To take it out again, delete the `kuliss` track, its clips on `Assets` and its bin clips. Projects finished before 2026-11-18 have a `kuliss` audio track or `Assets Kuliss` tracks; a re-run empties them and tells you to delete them.

### The theme

Copy [`theme.example.toml`](theme.example.toml) to `theme.toml` next to the project, or into a folder above it; the nearest one wins (see [Where files live](#where-files-live)). Keep one theme per game: for the game you play most, put it in the folder holding the `session_*` folders so every session uses it, and give a session with another game its own `theme.toml`. `kuliss new` warns when the new session has no theme above it.

- `position` picks a corner (`top-left`, `top-right`, `bottom-left`, `bottom-right`) or an edge centre (`top`, `bottom`, `left`, `right`). `margin` is the distance from the edges the bar sits against, and `offset = [x, y]` nudges it from there in pixels (positive = right/down). For example, `position = "left"` with `offset = [0, -100]` centres the bar on the left edge, 100 px above the middle.
- `orientation = "horizontal"` (the default) draws a row, `"vertical"` a column along the frame edge. The name label sits under the viewed avatar either way; the column spaces the avatars out to leave room for it.

- `voice_track` is the name of the Kdenlive **audio track** holding that player's voice; it defaults to the player's name, and a track named `<name> Voice` (as `kuliss sync` names them) is found too. The tool uses the audio stream and the cuts you chose on that track.
- Video clips from the same file as that voice track count as the player's view, whichever video track they sit on. Set `source` only when someone's view is recorded in a different file. It takes a file-name pattern such as `"*_h.mkv"`, or a list of them.
- `show_view = false` shows only who is talking: no enlarged avatar, no name label, no switch sounds, and `sound` may be left out. The overlay still fades out over the intro and outro.
- Unknown keys get a warning (usually a typo), and wrong values stop the run with a message saying what is expected.

### Making a theme

A theme is one folder holding `theme.toml` and the files it names. Start from [`theme.example.toml`](theme.example.toml); every line in it is explained there.

1. Make a folder for the game, for example `minecraft-theme/`, next to the `session_*` folders (or put `theme.toml` straight in the folder holding them).
2. Copy `theme.example.toml` into it as `theme.toml`.
3. Add one `[[player]]` section per player (1–8) with `name`, `colour` (`"#rrggbb"`) and `avatar`.
4. Add the files below, and point the theme at them with paths relative to `theme.toml`.
5. Run `kuliss finish P.kdenlive --preview 30` on a copy of an episode and look at the preview. Adjust `position`, `avatar_size` and the rest, and preview again.

| Key | What it is | Format | Size and length |
|---|---|---|---|
| `avatar` (per player) | The player's picture | PNG (transparency kept), JPEG or WebP | Square. Pixel art may be tiny (an 8×8 Minecraft head stays crisp); anything else at least 2.5 × `avatar_size`, so 128×128 px or more for the default 48. Corners are rounded off; a non-square picture is cropped to its centre. |
| `backdrop` | Behind the avatars | PNG, JPEG or WebP | Same shape as the panel (see below), at least twice its size. It is cropped to fill the panel, its corners are rounded and it is darkened 35% so the avatars stand out, so keep it calm and keep anything important in the middle. Leave it out for a plain dark panel. |
| `font` | The name label | TTF or OTF file | Bold works best at small sizes. It needs every letter in the names (å, ä, ö). Leave it out for the system's bold sans-serif. |
| `sound` | Plays on each view switch | FLAC, WAV, OGG or MP3 | Short: under a second. It is cut off at the next switch. Not needed with `show_view = false`. |
| `intro_audio` | The intro music | FLAC, WAV, OGG or MP3 | Played from 1.5 s into the file, for up to 18 s. |
| `intro_video` | The intro animation | Video with transparency: `.mov` (QuickTime Animation or ProRes 4444) or `.mkv` (FFV1) | The project's frame size (1920×1080). Its first 6 s are shown, from 0.6 s into the episode. WebM transparency does not survive in Kdenlive. |
| `outro_audio` | The outro music | FLAC, WAV, OGG or MP3 | Played from 1.7 s into the file, for up to 37 s, ending with the episode. |
| `outro_image` | The end card | PNG, transparent where the footage should show through | The project's frame size (1920×1080). Shown for the last 20 s, fading in and out. |

The intro and outro timings are the ones Samkväm used by hand, so music made for another show may need trimming to fit. A file shorter than its slot simply ends early.

**Backdrop size.** The panel grows with `avatar_size`, the number of players, the longest name and `orientation`. Some examples with four players (Henrik, Joel, Kenneth, Robin):

| `avatar_size` | horizontal | horizontal, `show_view = false` | vertical | vertical, `show_view = false` |
|---|---|---|---|---|
| 48 (default) | 300 × 117 | 252 × 72 | 104 × 432 | 72 × 252 |
| 64 | 400 × 156 | 336 × 96 | 133 × 576 | 96 × 336 |
| 96 | 600 × 234 | 504 × 144 | 198 × 864 | 144 × 504 |

So for the default look a 900 × 350 px backdrop is plenty; `backdrop.example.png` is one to start from. If the panel's shape differs from the picture's, the edges are cropped, never stretched.

### How it decides

- **Whose view**: for each frame, the topmost visible video track showing a player's clip wins.
  - Clips that belong to no player (green screens, namecards, titles, effects) never count, on any track.
  - The overlay fades out over the intro video and the outro card, which kuliss places itself.
  - Views shorter than 1 s are treated as flashes: they get no switch and no sound.
- **Who talks**: [Silero VAD](https://github.com/snakers4/silero-vad) runs on each voice track, following your cuts. Two thresholds (hysteresis), a 200 ms hangover and a 60 ms minimum burst stop it from flickering on clicks, while short words ("ja", "nä") still count; the marker lights up 64 ms before the detected onset. If a mic still misses words, lower `speech_threshold` in the theme (default 0.35); raise it if noise triggers the marker.
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
    ├── kortisar/                         ← YouTube shorts & TikToks (not processed,
    │                                        even with a kortisar.kdenlive in it)
    ├── avsnitt207/
    │   ├── avsnitt207.kdenlive          ← episode project with notes ✓
    │   └── ...
    └── avsnitt208/
        ├── avsnitt208.kdenlive          ← episode project with notes ✓
        └── ...
```

The rule is simple: a subdirectory whose name starts with `avsnitt` is an
episode. Its project is the same-named `.kdenlive` file or, when there is none,
the only `.kdenlive` file in it (a project not yet renamed from the
`avsnittXX<nr>` placeholder). Everything else is left alone. Episodes are
sorted naturally (`avsnitt9` before `avsnitt10`).

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
the session's Kdenlive project `session_<nr>_<date>.kdenlive` (1080p60).
The project starts empty, with only the `Assets` tracks: `kuliss sync` adds
the players' tracks and `kuliss finish` the intro and outro.

The mixer settings of new tracks come from the crew file
`_assets/kuliss.toml` next to the session folders (see `crew.example.toml`):
each player's voice volume, pan and voice contrast, the game audio and
`Assets` volumes, and the master volume. They are set when a track is created;
change them in Kdenlive afterwards as you like. Without a crew file every
track starts at 0 dB, centred.

The crew file can also list each game's software versions under `[software]`
(see `crew.example.toml`). `kuliss new` asks which game the session is (or none)
and starts the notes file's `Mjukvaruversioner` with that game's lines, then OBS,
Kdenlive and kuliss, which every session gets.

## `kuliss sync`: recordings in sync

Copy everyone's recordings into the session's `sources/`, close the project in
Kdenlive, and run `kuliss sync` inside the session. It puts each recording on
the project's tracks, lined up so everyone's audio and video is in sync, with
the earliest recording starting at 0. It creates each player's tracks the
first time, with the mixer settings from the crew file.

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

**Someone missing?** Sync whoever recorded; the absent player gets no
tracks. `kuliss finish` leaves anyone without clips on their voice track out
of the overlay, so they get no avatar.

**Guests** record to the same OBS standard and name the file after themselves:
`<date>_jesper.mkv`. `kuliss sync` gives them `Jesper Comms`, `Jesper Voice`,
`Jesper Game` (audio) and a `Jesper Game` video track, after the crew's. For the overlay, add the
guest as a `[[player]]` in that game's `theme.toml`. A crew member may also use
their full name (`_kenneth.mkv`).

`kuliss sync` refuses to touch a track that already has clips, so it can never
disturb an edit in progress; clear the recordings' tracks to sync again. Like
`kuliss finish`, it saves a timestamped `.bak` first.

Safety details:

* Before the session file is modified, the previous version is saved next to it
  as `<name>.md.YYYYmmdd-HHMMSS.bak` (one per changed run, so none is ever
  overwritten by the next), and the write itself is atomic (a crash can never leave a
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
| `cli.py` | The `kuliss` command: the only place that parses arguments and prints |
| `finish.py` | `kuliss finish`: `analyse()`, `render_overlay()`, `apply()` |
| `config.py` | Theme loading and validation |
| `timeline.py` | Reading and patching the Kdenlive XML |
| `vad.py` | Speech detection and voice level |
| `render.py` | Drawing and encoding the overlay |
| `notes.py` | `kuliss notes`: `process_session()`, the checklist, YouTube chapters |
| `kdnotes.py` | Reading the Document Notes out of a `.kdenlive` file |
| `mdoc.py` | The session Markdown file as a tree of heading blocks |
| `scaffold.py` | `kuliss new`: `scaffold_session()` |
| `sync.py` | Lining recordings up by their audio |
| `session.py` | `kuliss sync`: `sync_session()`, and the project `kuliss new` creates |
| `errors.py` | `VoiceError`, the one expected-failure type |

Every module but `cli.py` is a library: functions return their results and never print, so
they can be used from Python:

```python
from kuliss import finish

a = finish.analyse("avsnitt217/avsnitt217.kdenlive")
print(a.stats())  # (name, % on screen, % talking) per player
finish.apply(a, finish.render_overlay(a))
```

## License

GNU Affero General Public License v3.0 or later. See [LICENSE](LICENSE).
