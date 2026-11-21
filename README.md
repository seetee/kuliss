# kuliss

[![Tests](https://github.com/seetee/kuliss/actions/workflows/test.yml/badge.svg)](https://github.com/seetee/kuliss/actions/workflows/test.yml)
[![vibe coded](https://img.shields.io/badge/vibe_coded-%E2%9C%A8-ff69b4?style=flat-square)](https://en.wikipedia.org/wiki/Vibe_coding)
[![coded with Claude](https://img.shields.io/badge/coded_with-Claude_Code-CC785C?style=flat-square&logo=anthropic)](https://claude.ai/code)
[![license: AGPL v3](https://img.shields.io/badge/license-AGPL_v3-blue?style=flat-square)](LICENSE)

Tools for the boring parts of producing a multi-player let's play in Kdenlive, built for **Samkväm**. *Kuliss* is Swedish for the scenery behind the stage.

| Command | What it does |
|---|---|
| `kuliss gui` | A window that walks you through a session, step by step. |
| `kuliss new` | Creates the next session folder, with its Kdenlive project. |
| `kuliss sync` | Puts everyone's recordings on the session project, in sync. |
| `kuliss finish` | Finishes an episode: the who-we-watch / who-talks overlay, switch sounds, intro and outro. |
| `kuliss notes` | Copies Kdenlive's Document Notes into the session's Markdown file, with YouTube chapters. |

**Contents:** [Install](#install) · [A session, step by step](#a-session-step-by-step) · [Where files live](#where-files-live) · [The commands](#the-commands) · [Themes](#themes) · [Development](#development)

---

## Install

You need [uv](https://docs.astral.sh/uv/). It fetches Python 3.12+ and every dependency as a ready-made wheel, so nothing is compiled and no system ffmpeg is needed. You also need **Kdenlive 26.08 or newer**: the projects `kuliss new` writes use its format.

### Linux

```bash
uv tool install "kuliss[gui] @ git+https://github.com/seetee/kuliss.git"
kuliss gui ~/myshow/mygame
```

Update later with `uv tool upgrade kuliss`. Leave out `[gui]` if you only want the commands.

### Windows 10 and 11

The tests run on Windows on every change, but no session has been edited there yet. Treat the first one as a test and check every result.

1. **Install uv.** Open PowerShell (not as administrator), run this, then open a new PowerShell:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **Install kuliss.** git is not needed:

   ```powershell
   uv tool install "kuliss[gui] @ https://github.com/seetee/kuliss/archive/refs/heads/main.zip"
   ```

   If `kuliss` is not found, run `uv tool update-shell` and open a new PowerShell. To update, run the same command with `--force`.

3. **Copy the show folder**, keeping its layout (see [Where files live](#where-files-live)):
   - `_assets/kuliss.toml`, the crew file;
   - the files the theme names: avatars, intro and outro (about 200 MB);
   - the game's folder with its `theme.toml`, e.g. `samkvam.online\plateup\`.

4. **Open the window** on the game's folder:

   ```powershell
   kuliss gui "D:\samkvam.online\plateup"
   ```

<details>
<summary>Good to know on Windows</summary>

- Windows has no program for `.toml` files, so the window's links to them do nothing at first. Right-click a `.toml` file → *Open with* → Notepad → tick *Always*.
- If the crew file names an `archive` folder that isn't on this computer, `kuliss new` warns. Check the session number in the *New session* dialog.
- Theme paths are relative and use `/`, so the same theme works on Linux and Windows.
- Don't move a project between Linux and Windows halfway through an edit: Kdenlive may not find its clips. That hasn't been tested.

</details>

---

## A session, step by step

`kuliss gui` shows these steps as a list, with ✓ on what is done and ▶ on the next step. It works that out from the files every time the window gets focus. Each step's page says what to do, shows what is there, and has the step's buttons. Below the steps, *Settings* shows the theme and the crew file: what they hold, any problems, and for the theme a preview of the overlay. Edit them in your text editor; the page follows when you come back to the window. Every command is also on the command line:

| | Step | What you do | Command |
|---|---|---|---|
| 1 | **Session folder** | Before recording, in the game's folder: give the date and software versions. | `kuliss new` |
| 2 | **Recordings** | Copy everyone's OBS `.mkv` into `sources/`, named `<date>_<initial>.mkv` (guests: `<date>_<name>.mkv`). | |
| 3 | **Sync** | Close the project in Kdenlive and sync. Check the confidences (well above 10), then delete the `Comms` clips. | `kuliss sync` |
| 4 | **Mark the episodes** | In the session project, put a marker named `avsnitt<nr>` where each episode starts ([G] in Kdenlive). | |
| 5 | **Edit each episode** | Rename the `avsnittXX<nr>` folder, *Copy to…* the session project as `avsnitt<nr>/avsnitt<nr>.kdenlive`, cut away the other episodes, choose the views, and jot notes in Document Notes (`*` after a timestamp = a YouTube chapter). Then Finish it and render. | `kuliss finish` |
| 6 | **Notes** | Fill the session `.md` from everyone's notes and see what's missing before YouTube. | `kuliss notes` |

Every command saves a backup next to the file it changes (`<name>.<date>-<time>.bak`) and writes atomically, so a crash never leaves a half-written file. Close a project in Kdenlive before kuliss changes it, or reopen it afterwards without saving.

---

## Where files live

One folder holds the whole show, for Samkväm `samkvam.online/`. Move, copy or sync that folder; nothing outside it is used.

```
samkvam.online/
├── _assets/                 shared by every game
│   ├── kuliss.toml          the crew file: mixer levels, each game's software, the archive
│   ├── avatars/             one picture per player
│   ├── episode-media/       intro and outro music and video
│   └── design-system/, …    outro card, logos, fonts, sounds
├── po3/                     one folder per game
│   ├── theme.toml           this game's look
│   └── session_28_2025-10-24/
│       ├── session_28_2025-10-24.md         notes, titles, chapters
│       ├── session_28_2025-10-24.kdenlive   the session project
│       ├── sources/                         the raw recordings
│       ├── kortisar/                        shorts and TikToks
│       └── avsnitt228/avsnitt228.kdenlive   an episode
└── plateup/                 another game, numbered from 01
```

- **Each game has its own folder**, with its own `theme.toml` and session numbers. A new game starts at `session_01` once its folder has a `theme.toml`.
- **Shared files go in `_assets/`.** kuliss finds the crew file there from any game.
- **Sessions moved to another drive still count** when `kuliss new` numbers the next one: set `archive = "/path/to/show.archive"` in the crew file, with the same game folders inside.
- **Clips Kdenlive can't find** on another computer (namecards and the like, placed by hand): let Kdenlive's dialog search the show folder. kuliss's own clips get their current path on every `kuliss finish`.

---

## The commands

### `kuliss new`

Run it in the game's folder before recording. It asks for the recording date (Enter = today), which game it is, and the software versions (Enter keeps each). It creates:

- `session_<nr>_<date>/` with `sources/`, `kortisar/` and a placeholder episode folder `avsnittXX<nr>` (rename it once you know the episode number);
- the session `.md`, with the chosen game's software lines plus OBS, Kdenlive and kuliss;
- the session project `session_<nr>_<date>.kdenlive` (1080p60), empty except for the `Assets` tracks.

<details>
<summary>The crew file</summary>

`_assets/kuliss.toml` in the show folder (see [`crew.example.toml`](kuliss/crew.example.toml)) holds:

- the mixer settings of new tracks: each player's voice volume, pan and contrast, the game audio, `Assets` and master volume. They are set once, when a track is created. Without a crew file every track starts at 0 dB, centred;
- each game's software versions under `[software]`, for `kuliss new`;
- `archive`, where old sessions live.

</details>

### `kuliss sync`

Run it inside the session, with the project closed in Kdenlive. It puts each recording on the project's tracks, lined up so everyone is in sync, the earliest starting at 0. It creates each player's tracks the first time.

The recordings follow the crew's OBS standard. Streams are found by title, not position:

| Stream | Title | Goes on track |
|---|---|---|
| video | | `<Name> Game` (video) |
| audio 1 | `Full mix` | not used (backup) |
| audio 2 | `Game audio` | `<I> Game` |
| audio 3 | `Voice audio` | `<Name> Voice` |
| audio 4 | `Comms` | `<I> Comms` |

It listens for each person's voice in the others' `Comms` (the call as they heard it), in both directions, which cancels the call's delay. It prints each offset with a confidence.

- **Grouped:** all `Voice` clips form one group, and each player's video forms a group with their `Game` audio. Ungroup with Ctrl+Shift+G to move one alone.
- **Never over an edit:** it refuses to touch a track that already has clips. Clear them to sync again.
- **Someone missing?** Sync whoever recorded. The absent player gets no tracks, and `kuliss finish` gives them no avatar.
- **Guests** name the file after themselves, `<date>_alice.mkv`, and get `Alice Comms`, `Alice Voice` and `Alice Game` tracks. Add them as a `[[player]]` in the theme for the overlay.

<details>
<summary>A recording that doesn't follow the standard</summary>

It doesn't stop the others; each problem is a warning and the rest is synced.

- A missing stream or video gets no track.
- Without `Comms`, the recording is synced one way only, so it may be a fraction of a second late. Check it by ear.
- A file with neither `Voice audio` nor `Comms`, one that can't be read, or one whose voice isn't found is left out. Place it by hand.

The window's *Recordings* step shows all of this before you sync.

</details>

### `kuliss finish`

Run it on an edited episode. It adds a small overlay that shows:

- **who is who:** every player's name under their avatar, muted, and bright while they talk;
- **whose view we watch:** that avatar is enlarged, and its name becomes a label in the player's colour;
- **who talks:** a ring and a sound-bars badge that move with the voice, so the cue never relies on colour alone;
- **every switch:** the label slides to the new player and a sound plays.

With `show_view = false` in the theme it shows only who talks: same-size avatars, no label, no switch sounds. With `avatars = false` it shows names only: a talking name fills with the player's colour, the viewed one gets an outline and a camera. It also places the show's intro and outro.

| Command | What it does |
|---|---|
| `kuliss finish P.kdenlive --dry-run` | Reports switches and screen and talk time per player. Writes nothing. |
| `kuliss finish P.kdenlive --preview 90` | Renders the first 90 s to `P-overlay-preview.mkv`. The project is untouched. |
| `kuliss finish P.kdenlive --still` | Draws the overlay over one frame of the episode, as silent, someone talking and the viewed player talking, to `P-overlay-still.png`. Takes a second; the project is untouched. |
| `kuliss finish P.kdenlive` | Renders the overlay and **updates the project**. Run it again after every re-edit. |
| `--theme path/to/theme.toml` | Uses this theme instead of the nearest `theme.toml`. |

Everything comes from the project itself: your cuts, which clip is whose, and which audio stream is each voice. There is nothing to configure per episode.

**End your edit where the outro card should end**, with about 20 s of footage for the card to sit on.

<details>
<summary>What it changes in your project</summary>

- A video track named `kuliss`, on top, holding `P-overlay.mkv` (FFV1 with alpha: lossless and open; `codec = "qtrle"` gives a QuickTime `.mov` instead).
- On your `Assets` tracks: the switch sounds, the intro music and video, and the outro music and card. Your own clips there are never moved; anything of kuliss's that would overlap one is left out, with a warning. A missing `Assets` track is created (audio at −24 dB).
- Bin clips named `kuliss speaker …`.
- The intro music is lowered 15 dB where the first voice clip starts. The outro card covers the last 20 s, and the overlay hides during the intro video and outro card.
- Re-runs reuse the same tracks and clips. If you moved the overlay's Transform effect, your placement is kept.
- To remove it: delete the `kuliss` track, its clips on `Assets` and its bin clips. Projects finished before 2026-11-18 have old `kuliss` audio or `Assets Kuliss` tracks; a re-run empties them and says so.

</details>

<details>
<summary>How it decides</summary>

- **Whose view:** for each frame, the topmost visible video track showing a player's clip. Clips that are no player's (green screens, namecards, titles) never count. Views under 1 s are flashes: no switch, no sound.
- **Who talks:** [Silero VAD](https://github.com/snakers4/silero-vad) on each voice track, following your cuts, smoothed so clicks don't flicker but short words ("ja", "nä") count. If a mic misses words, lower `speech_threshold` in the theme (default 0.35); raise it if noise lights the marker.
- **Contrast:** label text is black or white, whichever contrasts more with the colour, always at least 4.5:1 (WCAG AA). Any colour is safe.

</details>

### `kuliss notes`

Write timestamped notes in Kdenlive's **Document Notes** panel while you edit. `kuliss notes` copies them into the session `.md`, under the right episode, as often as you like:

```bash
kuliss notes                    # anywhere inside a session
kuliss notes path/to/po3/       # every session below
kuliss notes --dry-run          # show the changes as a diff, write nothing
kuliss notes --show avsnitt207  # print one episode, for copy-pasting
```

- Timestamps become `MM:SS`, sorted. A heading typed in Document Notes becomes a `####` section; notes without one go at the end of `Noteworthy`.
- `J+1`, `R+1`, `H+1`, `K+1` notes are counted in the **Bryggpromenader** tally.
- A `*` right after a timestamp (`00:06:29:32* Grottan öppnas -h`) makes it a **YouTube chapter** in `#### Kapitel`.
- It ends with a checklist of what's missing per episode, including YouTube pitfalls: a title over 100 characters, or fewer than 3 chapters.
- Only kuliss's own lines are rewritten. Everything you wrote by hand stays where you put it.

<details>
<summary>The session file</summary>

Created and repaired on every run. Missing headings and fields are added; values you filled in are never touched.

```markdown
# Session 26 - 2025-06-30

## Mjukvaruversioner

* Project Ozone 3 3.4.10
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

* a note typed without a heading

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

- An episode is a folder starting with `avsnitt` holding a same-named `.kdenlive` (or exactly one `.kdenlive`). `kortisar/` never counts.
- `Kapitel` always opens with `00:00 Äventyret börjar!` and has one chapter per Bryggpromenader entry, plus every starred note. YouTube needs at least 3 chapters, each 10 s or longer.
- The exit code is 1 when a warning was printed: an unreadable project, or a `### avsnitt…` section with no folder (after a rename, say).

</details>

---

## Themes

Each game's look is a `theme.toml` in its folder. Start from [`theme.example.toml`](kuliss/theme.example.toml): every key is explained there.

1. Copy `theme.example.toml` into the game's folder as `theme.toml` (or in the window: *Settings → Theme → Create theme.toml*).
2. Set `assets = "../_assets"`, so the other paths are relative to the shared folder.
3. Add a `[[player]]` per player (1–8) with `name`, `colour` (`"#rrggbb"`) and `avatar` (left out: a tile in the player's colour with their initial, handy for a guest).
4. Keep *Settings → Theme* open in the window: it redraws the overlay each time you save in the editor and come back. Then run `kuliss finish P.kdenlive --still` (the *Still* button on an episode's page) to see it on a real frame, and check the motion once with `--preview 30` on a copy.

The main keys:

- `position`: a corner (`top-left`, …) or an edge (`top`, `left`, …). `margin` and `offset = [x, y]` fine-tune it.
- `orientation`: `"horizontal"` (a row, the default) or `"vertical"` (a column).
- `show_view = false`: only who talks, for games where everyone shares one view.
- `avatars = false`: names only, no pictures. Works with either `show_view`.
- `voice_track` (per player): the audio track with that voice. It defaults to the name; `<name> Voice`, as `kuliss sync` names it, is found too.
- Unknown keys warn (usually a typo); wrong values stop with a message saying what's expected.

<details>
<summary>The theme's files: formats and sizes</summary>

| Key | What | Format | Size and length |
|---|---|---|---|
| `avatar` | The player's picture | PNG, JPEG or WebP | Square, at least 128×128 px (pixel art may be tiny). Non-square is cropped to the centre. |
| `backdrop` | Behind the avatars | PNG, JPEG or WebP | At least twice the panel size (below). Cropped, rounded and darkened 35%; keep it calm. Leave out for a plain dark panel. |
| `font` | The names | TTF or OTF | Bold works best. Needs å, ä, ö. Leave out for the system's bold sans-serif. |
| `sound` | Each view switch | FLAC, WAV, OGG or MP3 | Under a second. Not needed with `show_view = false`. |
| `intro_audio` | Intro music | FLAC, WAV, OGG or MP3 | Played from 1.5 s into the file, up to 18 s. |
| `intro_video` | Intro animation | `.mov` (QuickTime Animation or ProRes 4444) or `.mkv` (FFV1), with transparency | 1920×1080. The first 6 s, from 0.6 s in. WebM transparency doesn't survive in Kdenlive. |
| `outro_audio` | Outro music | FLAC, WAV, OGG or MP3 | From 1.7 s into the file, up to 37 s, ending with the episode. |
| `outro_image` | End card | PNG, transparent where the footage shows | 1920×1080, the last 20 s. |

The intro and outro timings are Samkväm's, copied from its hand-edited episodes.

**Panel size** with four players, so you know how big a backdrop to make:

| `avatar_size` | horizontal | horizontal, no view | vertical | vertical, no view | names, horizontal | names, vertical |
|---|---|---|---|---|---|---|
| 48 (default) | 444 × 117 | 444 × 105 | 104 × 432 | 104 × 384 | 444 × 51 | 120 × 168 |
| 64 | 580 × 156 | 580 × 140 | 133 × 576 | 133 × 512 | 580 × 68 | 157 × 224 |
| 96 | 880 × 234 | 880 × 210 | 198 × 864 | 198 × 768 | 880 × 102 | 238 × 336 |

(Measured with four names of 4 to 7 letters in the system font; a row is as wide as four of its longest name.)

A 900 × 350 px backdrop is plenty for the default look; [`backdrop.example.png`](backdrop.example.png) is one to start from.

</details>

---

## Development

```bash
uv run pytest                  # no media files needed
uv run --extra gui kuliss gui  # the window, from a clone
```

Only `cli.py` and `gui.py` print or prompt. Every other module is a library that returns its results, so it can be used from Python:

```python
from kuliss import finish

a = finish.analyse("avsnitt217/avsnitt217.kdenlive")
print(a.stats())  # (name, % on screen, % talking) per player
finish.apply(a, finish.render_overlay(a))
```

<details>
<summary>The modules</summary>

| File | Contents |
|---|---|
| `cli.py`, `gui.py` | The command line and the window |
| `steps.py` | Where a session stands, read from disk, and the report texts |
| `scaffold.py` | `kuliss new` |
| `session.py`, `sync.py` | `kuliss sync`, and lining recordings up by their audio |
| `finish.py` | `kuliss finish`: `analyse()`, `render_overlay()`, `apply()` |
| `config.py` | The theme and the crew file |
| `timeline.py` | Reading, patching and creating Kdenlive projects |
| `vad.py`, `render.py` | Speech detection, and drawing the overlay |
| `notes.py`, `kdnotes.py`, `mdoc.py` | `kuliss notes`, Document Notes, the Markdown tree |
| `files.py`, `errors.py` | Backups and atomic writes, `VoiceError` |

`vad.py`, `sync.py` and `render.py` don't depend on Kdenlive, so [Klatch](https://github.com/seetee/klatch) can reuse them.

</details>

## License

GNU Affero General Public License v3.0 or later. See [LICENSE](LICENSE).
