"""uv run pytest   (no media files needed: a hand-built project mirrors avsnitt217's structure)"""

import itertools
import xml.etree.ElementTree as ET
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
import skia

from kuliss import cli, render, vad
from kuliss import timeline as T
from kuliss.config import Player, VoiceError, load_theme

PLAYERS = tuple(Player(n, (200, 60, 90), Path("x.png"), (f"*_{n[0].lower()}.mkv",), n)
                for n in ("Henrik", "Kenneth"))


def chain(cid, kid, resource, audio_index=-1, service="avformat-novalidate", video_index=0):
    return (f'<chain id="{cid}" out="99999"><property name="resource">{resource}</property>'
            f'<property name="mlt_service">{service}</property>'
            f'<property name="audio_index">{audio_index}</property>'
            f'<property name="video_index">{video_index}</property>'
            f'<property name="kdenlive:id">{kid}</property></chain>')


def track(tid, name, audio, body, hide=None):
    hide = hide or ("video" if audio else "audio")
    at = '<property name="kdenlive:audio_track">1</property>' if audio else ""
    return (f'<playlist id="{tid}_a">{at}{body}</playlist><playlist id="{tid}_b">{at}</playlist>'
            f'<tractor id="{tid}" in="0" out="999">{at}'
            f'<property name="kdenlive:track_name">{name}</property>'
            f'<track hide="{hide}" producer="{tid}_a"/><track hide="{hide}" producer="{tid}_b"/></tractor>')


# frames at 10 fps: Kenneth's clip sits on the track named "Henrik" (as in avsnitt217)
PROJECT = f"""<?xml version='1.0' encoding='utf-8'?>
<mlt LC_NUMERIC="C" producer="main_bin" version="7.40.0">
 <profile frame_rate_num="10" frame_rate_den="1" width="1920" height="1080"/>
 {chain("c_h", 1, "/src/2025-08-23_h.mkv", 2)}
 {chain("c_k", 2, "/src/2025-08-23_k.mkv", 2)}
 {chain("c_intro", 3, "/a/intro.mov")}
 {chain("c_card", 4, "/a/card.png", service="qimage")}
 <producer id="black"><property name="mlt_service">color</property></producer>
 {track("t_voice", "Henrik", True, '<entry producer="c_h" in="100" out="299"/>')}
 {track("t_vh", "Henrik", False,
        '<entry producer="c_h" in="0" out="99"/><entry producer="c_k" in="0" out="49"/>'
        '<entry producer="c_h" in="0" out="3"/><entry producer="c_k" in="0" out="45"/>')}
 {track("t_top", "Assets", False,
        '<entry producer="c_intro" in="0" out="19"/><blank length="100"/>'
        '<entry producer="c_card" in="0" out="29"><filter><property name="mlt_service">qtblend</property></filter></entry>')}
 <tractor id="seq" in="0" out="199">
  <property name="kdenlive:uuid">{{u}}</property>
  <property name="kdenlive:sequenceproperties.tracksCount">3</property>
  <property name="kdenlive:sequenceproperties.videoTarget">1</property>
  <property name="kdenlive:sequenceproperties.groups">[{{"data": "0:10:-1"}}, {{"data": "2:50:-1"}}]</property>
  <track producer="black"/><track producer="t_voice"/><track producer="t_vh"/><track producer="t_top"/>
  <transition id="x1"><property name="a_track">0</property><property name="b_track">1</property><property name="mlt_service">mix</property></transition>
  <transition id="x2"><property name="a_track">0</property><property name="b_track">2</property><property name="mlt_service">qtblend</property></transition>
  <transition id="x3"><property name="a_track">0</property><property name="b_track">3</property><property name="mlt_service">qtblend</property></transition>
 </tractor>
 <playlist id="main_bin">
  <property name="kdenlive:docproperties.version">1.1</property>
  <property name="kdenlive:docproperties.activetimeline">{{u}}</property>
  <entry producer="c_h"/><entry producer="seq"/>
 </playlist>
 <tractor id="project"><track producer="seq"/></tractor>
</mlt>
"""


def load(tmp_path):
    p = tmp_path / "ep.kdenlive"
    p.write_text(PROJECT)
    return T.load(p)


def test_parse_and_view(tmp_path):
    proj = load(tmp_path)
    assert (proj.fps, proj.length) == (10, 200)
    assert [(t.name, t.audio) for t in proj.tracks] == [
        ("Henrik", True), ("Henrik", False), ("Assets", False)]
    view = T.view_map(proj, PLAYERS)
    assert (view[:20] == -1).all()              # full-screen intro covers Henrik
    assert (view[20:100] == 0).all()
    assert (view[100:150] == 1).all()           # identity comes from the clip, not the track name
    assert (view[120:150] == 1).all()           # a placed card (qtblend) does not cover
    spans = T.view_spans(view, 10)              # the 4-frame Henrik flash is absorbed
    assert spans == [(0, 20, -1), (20, 100, 0), (100, 200, 1)]
    assert T.cuts(spans) == [100]               # no swoosh for the first view after the intro
    assert [(e.start, e.src_in, e.audio_index) for e in T.voice_entries(proj, PLAYERS[0])] == [
        (0, 100, 2)]


def test_source_defaults_to_the_voice_tracks_files(tmp_path):
    proj = load(tmp_path)
    bare = (replace(PLAYERS[0], source=()), PLAYERS[1])
    players = T.with_sources(proj, bare)
    assert players[0].source == ("2025-08-23_h.mkv",)
    assert (T.view_map(proj, players) == T.view_map(proj, PLAYERS)).all()


def test_patch_adds_tracks_once_and_renumbers(tmp_path):
    proj = load(tmp_path)
    T.patch(proj, tmp_path / "overlay.mkv", (24, 24, 304, 171), tmp_path / "s.flac", 25, [100, 190])
    out = tmp_path / "out.kdenlive"
    T.save(proj, out)
    first = out.read_bytes()

    seq = T.load(out).seq
    refs = [r.get("producer") for r in seq.findall("track")]
    assert refs == ["black", "kuliss_speaker_audio", "t_voice", "t_vh", "t_top", "kuliss_speaker_video"]
    b = {t.get("id"): T.props(t)["b_track"] for t in seq.findall("transition")}
    assert b == {"kuliss_speaker_audio_transition": "1", "x1": "2", "x2": "3", "x3": "4",
                 "kuliss_speaker_video_transition": "5"}
    p = T.props(seq)
    assert p["kdenlive:sequenceproperties.groups"] == '[{"data": "1:10:-1"}, {"data": "3:50:-1"}]'
    assert p["kdenlive:sequenceproperties.tracksCount"] == "5"
    assert p["kdenlive:sequenceproperties.videoTarget"] == "2"

    root = ET.parse(out).getroot()
    byid = {e.get("id"): e for e in root if e.get("id")}
    sounds = byid["kuliss_speaker_audio_pl0"].findall("entry")
    assert [(e.get("in"), e.get("out")) for e in sounds] == [("0", "24"), ("0", "9")]  # last one trimmed
    assert byid["kuliss_speaker_audio_pl0"].find("blank").get("length") == "100"
    rect = [T.props(f)["rect"] for f in byid["kuliss_speaker_video_pl0"].iter("filter")]
    assert rect == ["0=24 24 304 171 1.000000"]
    assert T.props(byid["kuliss_speaker_audio"].find("filter"))["level"] == str(T.SOUND_LEVEL)

    # a project patched under the old track name: found, renamed, nothing added
    out.write_text(out.read_text().replace(">kuliss</property>", ">kuliss speaker</property>"))
    old = T.load(out)
    T.patch(old, tmp_path / "overlay.mkv", (24, 24, 304, 171), tmp_path / "s.flac", 25, [100, 190])
    T.save(old, out)
    assert out.read_bytes() == first

    again = T.load(out)                        # a re-run reuses everything we own
    T.patch(again, tmp_path / "overlay.mkv", (24, 24, 304, 171), tmp_path / "s.flac", 25, [100, 190])
    T.save(again, out)
    assert out.read_bytes() == first

    # what the editor set on our bin clip in Kdenlive (a bin folder) survives a re-run
    clip = next(e for e in again.root if e.get("id") == "kuliss_speaker_overlay_bin")
    T.set_prop(clip, "kdenlive:folderid", 7)
    T.set_prop(clip, "meta.stale", "x")
    T.patch(again, tmp_path / "overlay.mkv", (24, 24, 304, 171), tmp_path / "s.flac", 25, [100, 190])
    assert T.props(clip)["kdenlive:folderid"] == "7" and "meta.stale" not in T.props(clip)


def test_label_text_contrast_always_passes_wcag_aa():
    for rgb in itertools.product(range(0, 256, 17), repeat=3):
        assert render.contrast(rgb, render.on_colour(rgb)) >= 4.5


def test_canvas_matches_frame_aspect():
    from kuliss.config import Theme
    for n, orientation in itertools.product((1, 4, 8), ("horizontal", "vertical")):
        theme = Theme(players=PLAYERS[:1] * n, sound=Path("s.flac"), position="bottom-right",
                      orientation=orientation)
        lay = render.layout(theme, 1920, 1080)
        assert lay.W * 1080 == lay.H * 1920
        assert lay.panel.width() <= lay.W and lay.panel.height() <= lay.H
        assert all(lay.panel.contains(x, y) for x, y in lay.slots)
        x, y, w, h = render.placement(theme, lay, 1920, 1080)
        # the panel sits at the margin; the canvas reaches past it by the shadow's inset
        assert (x + lay.panel.right(), y + lay.panel.bottom()) == (1920 - theme.margin,
                                                                   1080 - theme.margin)
        assert lay.panel.left() >= lay.inset and lay.panel.top() >= lay.inset


def test_decode_trims_from_the_asked_start(tmp_path):
    """A seek can land at pts 0; decode must still return the asked window."""
    from fractions import Fraction

    import av
    sr, n = 48000, 48000 * 6
    ts = np.arange(n) / sr
    pcm = (0.3 * np.sin(2 * np.pi * 440 * ts) * (ts >= 3)).astype(np.float32)   # tone from 3 s
    path = tmp_path / "voice.mkv"
    with av.open(str(path), "w") as c:
        st = c.add_stream("pcm_s16le", rate=sr, layout="mono")
        for i in range(0, n, 4800):
            f = av.AudioFrame.from_ndarray((pcm[i:i + 4800] * 32767).astype(np.int16)[None, :],
                                           format="s16", layout="mono")
            f.sample_rate, f.pts, f.time_base = sr, i, Fraction(1, sr)
            c.mux(st.encode(f))
        c.mux(st.encode(None))

    loud = vad.decode(str(path), 0, 3.0, 2.0)
    quiet = vad.decode(str(path), 0, 0.0, 2.0)
    assert len(loud) == 2 * vad.RATE and np.abs(loud).mean() > 0.1
    assert np.abs(quiet).max() < 0.01


def test_vad_smoothing():
    hang = round(vad.HANGOVER * vad.RATE / vad.WINDOW)
    probs = np.zeros(100)
    probs[10:40] = 0.9          # speech
    probs[40:43] = 0.3          # dip between the thresholds: stays on
    probs[43:45] = 0.9
    probs[70:71] = 0.9          # a click: shorter than MIN_BURST once the hangover is discounted
    probs[85:88] = 0.9          # a short word ("ja", 96 ms) is kept
    on = vad.smooth(probs)
    assert on[10 - vad.LEAD:45 + hang - 1].all()        # lit a little before the onset
    assert not on[:10 - vad.LEAD].any() and not on[45 + hang:85 - vad.LEAD].any()
    assert on[85:88].all()
    assert not vad.smooth(probs, 0.95).any()            # the theme's speech_threshold


def test_voice_level_follows_loudness_and_clips_get_a_warmup(monkeypatch):
    pcm = np.zeros(4 * vad.WINDOW, np.float32)
    pcm[:vad.WINDOW], pcm[vad.WINDOW:2 * vad.WINDOW] = 0.3, 0.03     # loud, 20 dB quieter
    pcm[3 * vad.WINDOW:] = 0.3                                       # loud, but not speech
    level = vad.window_levels(pcm, np.array([True, True, True, False]))
    assert level[0] > 0.9 and 0.2 < level[1] < 0.5 and level[2] == np.float32(0.05)
    assert level[3] == 0

    asked = []

    def decode(path, stream, start, dur):
        asked.append((start, dur))
        return np.full(round(dur * vad.RATE), 0.1, np.float32)
    monkeypatch.setattr(vad, "decode", decode)
    monkeypatch.setattr(vad, "speech_windows", lambda pcm, on_at: np.ones(len(pcm) // vad.WINDOW, bool))
    out = vad.talking([T.Entry(10, 50, "x", 100, 1, False), T.Entry(70, 20, "x", 2, 1, False)],
                      10.0, 100)
    assert asked == [(9.5, 5.5), (0.0, 2.2)]            # 0.5 s before the clip, when there is any
    assert (out[10:60] > 0).all() and (out[70:90] > 0).all()
    assert not out[:10].any() and not out[60:70].any() and not out[90:].any()


def test_rerun_after_kdenlive_renamed_our_ids(tmp_path):
    proj = load(tmp_path)
    T.patch(proj, tmp_path / "overlay.mkv", (24, 24, 304, 171), tmp_path / "s.flac", 25, [100])
    out = tmp_path / "out.kdenlive"
    T.save(proj, out)
    out.write_text(out.read_text().replace("kuliss_speaker_", "kd"))   # Kdenlive renumbers ids on save

    again = T.load(out)
    T.patch(again, tmp_path / "overlay.mkv", (24, 24, 304, 171), tmp_path / "s.flac", 30, [100])
    T.save(again, out)
    root = ET.parse(out).getroot()
    byid = {e.get("id"): e for e in root if e.get("id")}
    names = [T.props(t).get("kdenlive:track_name") for t in root.iter("tractor")]
    assert names.count("kuliss") == 2
    ours = [e for e in root if e.tag == "chain"
            and T.props(e).get("kdenlive:clipname", "").startswith("kuliss speaker")]
    assert len(ours) == 4                                  # bin + timeline copy, twice
    sound_entries = [e for pl in root.iter("playlist") for e in pl.findall("entry")
                     if T.props(byid[e.get("producer")]).get("kdenlive:clipname") == "kuliss speaker sound"]
    assert [e.get("out") for e in sound_entries] == ["29", "29"]   # bin entry + the one sound, both refreshed


# --- theme, assets and robustness --------------------------------------------



def write_theme(tmp_path, extra="", player_extra=""):
    for name in ("a.png", "s.flac"):
        (tmp_path / name).write_bytes(b"x")
    avatar = skia.Surface(8, 8)
    avatar.getCanvas().clear(skia.ColorRED)
    avatar.makeImageSnapshot().save(str(tmp_path / "a.png"))
    theme = tmp_path / "theme.toml"
    theme.write_text(f'sound = "s.flac"\n{extra}\n[[player]]\nname = "Kenneth-the-long"\n'
                     f'colour = "#c83c5a"\navatar = "a.png"\n{player_extra}\n')
    return theme


@pytest.mark.parametrize("extra, message", [
    ("margin = \"abc\"", "margin must be 0-500"),
    ("avatar_size = 4", "avatar_size must be 16-256"),
    ("codec = \"vp9\"", "codec must be one of ffv1, qtrle"),
    ("orientation = true", "orientation must be one of"),
    ("offset = [1]", "offset must be \\[x, y\\]"),
    ("position = \"middle\"", "position must be one of"),
])
def test_bad_theme_values_are_clear_errors(tmp_path, extra, message):
    with pytest.raises(VoiceError, match=message):
        load_theme(write_theme(tmp_path, extra))


def test_theme_warns_about_typos_and_takes_source_lists(tmp_path, caplog):
    theme = load_theme(write_theme(tmp_path, 'orientaton = "vertical"',
                                   'source = ["*_k.mkv", "*_k2.mkv"]'))
    assert "unknown key 'orientaton'" in caplog.text
    assert theme.orientation == "horizontal" and theme.players[0].source == ("*_k.mkv", "*_k2.mkv")


def test_unreadable_assets_are_clear_errors(tmp_path):
    theme = load_theme(write_theme(tmp_path, 'font = "s.flac"'))
    with pytest.raises(VoiceError, match="not a font file"):
        render.layout(theme, 1920, 1080)
    theme = load_theme(write_theme(tmp_path, 'backdrop = "s.flac"'))
    with pytest.raises(VoiceError, match="backdrop .* is not an image"):
        render.Painter(theme, render.layout(theme, 1920, 1080))


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_long_name_fits_inside_the_panel(tmp_path, orientation):
    theme = load_theme(write_theme(tmp_path, f'orientation = "{orientation}"'))
    lay = render.layout(theme, 1920, 1080)
    width = render.load_font(theme, lay.font_size).measureText("Kenneth-the-long") + lay.label_h
    assert width + 8 <= lay.panel.width() <= lay.W


@pytest.mark.parametrize("codec", ["ffv1", "qtrle"])
def test_render_is_lossless_with_alpha(tmp_path, codec):
    import av
    theme = load_theme(write_theme(tmp_path, f'codec = "{codec}"'))
    painter = render.Painter(theme, render.layout(theme, 1920, 1080))
    out = tmp_path / ("o" + render.CODECS[codec][0])
    render.render(painter, codec, [(0, 12, 0)], [np.r_[np.zeros(6, bool), np.ones(6, bool)]],
                  Fraction(30), 12, out)
    with av.open(str(out)) as c:
        frames = [f.to_ndarray(format="bgra") for f in c.decode(video=0)]
    assert len(frames) == 12 and not (tmp_path / (out.name + ".partial")).exists()
    want = painter.draw(1.0, -1, 0, 1.0, (1.0,))       # last frame: fully faded in, talking
    assert (frames[-1] == want).all()
    quiet = painter.draw(1.0, -1, 0, 1.0, (1.0,), (0.25,))
    assert (quiet != want).any()                       # glow and bars follow the voice level
    assert frames[-1][..., 3].min() == 0 and frames[-1][..., 3].max() == 255   # real alpha


def test_new_clip_ids_avoid_sequence_ids(tmp_path):
    p = tmp_path / "ep.kdenlive"
    p.write_text(PROJECT.replace('<tractor id="seq" in="0" out="199">',
                                 '<tractor id="seq" in="0" out="199">'
                                 '<property name="kdenlive:id">40</property>'))
    proj = T.load(p)
    T.patch(proj, tmp_path / "o.mkv", (0, 0, 16, 9), tmp_path / "s.flac", 5, [100])
    ids = {T.props(e).get("kdenlive:clipname"): T.props(e).get("kdenlive:id")
           for e in proj.root if e.tag == "chain"}
    assert ids["kuliss speaker overlay"] == "41" and ids["kuliss speaker sound"] == "42"


def test_malformed_project_is_a_clear_error(tmp_path):
    p = tmp_path / "ep.kdenlive"
    p.write_text(PROJECT.replace('<track hide="audio" producer="t_vh_a"/>',
                                 '<track hide="audio" producer="missing"/>'))
    with pytest.raises(VoiceError, match="unexpected project structure"):
        T.load(p)


@pytest.mark.parametrize("position, orientation", [
    ("left", "vertical"), ("right", "vertical"), ("top", "horizontal"), ("bottom", "horizontal"),
    ("bottom", "vertical"), ("left", "horizontal")])
def test_edge_centred_positions(tmp_path, position, orientation):
    theme = load_theme(write_theme(tmp_path, f'position = "{position}"\n'
                                             f'orientation = "{orientation}"\noffset = [5, -7]'))
    lay = render.layout(theme, 1920, 1080)
    x, y, w, h = render.placement(theme, lay, 1920, 1080)
    cx, cy = x + lay.panel.centerX(), y + lay.panel.centerY()   # panel centre in the frame
    m = theme.margin
    if position in ("left", "right"):
        assert abs(cy - (540 - 7)) <= 1
        edge = x + lay.panel.left() if position == "left" else x + lay.panel.right()
        assert edge == (m + 5 if position == "left" else 1920 - m + 5)
    else:
        assert abs(cx - (960 + 5)) <= 1
        edge = y + lay.panel.top() if position == "top" else y + lay.panel.bottom()
        assert edge == (m - 7 if position == "top" else 1080 - m - 7)


def test_preview_must_be_positive():
    assert cli.positive("1.5") == 1.5
    for bad in ("0", "-3", "abc"):
        with pytest.raises(Exception, match="above 0"):
            cli.positive(bad)


def test_voice_track_may_carry_a_voice_suffix(tmp_path):
    """The session template names voice tracks "<Player> Voice"."""
    p = tmp_path / "ep.kdenlive"
    p.write_text(PROJECT.replace(">Henrik</property>", ">Henrik Voice</property>", 1))
    assert len(T.voice_entries(T.load(p), PLAYERS[0])) == 1


def test_absent_player_is_left_out(tmp_path):
    """Someone missed the session: their voice track is empty, so no avatar for them."""
    p = tmp_path / "ep.kdenlive"
    p.write_text(PROJECT.replace('<entry producer="c_h" in="100" out="299"/>', ""))
    assert T.present(T.load(p), PLAYERS[:1]) == ()
    assert T.present(load(tmp_path), PLAYERS[:1]) == PLAYERS[:1]


def test_relative_sources_resolve_against_the_project_not_the_cwd(tmp_path, monkeypatch):
    """Kdenlive saves paths below the project folder relative to the root attribute."""
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / "2025-08-23_h.mkv").write_bytes(b"x")
    p = tmp_path / "ep.kdenlive"
    p.write_text(PROJECT.replace("/src/2025-08-23_h.mkv", "sources/2025-08-23_h.mkv"))
    monkeypatch.chdir(tmp_path.parent)
    voice = T.voice_entries(T.load(p), PLAYERS[0])
    assert voice[0].resource == str(tmp_path / "sources" / "2025-08-23_h.mkv")


def test_rerun_keeps_an_overlay_the_editor_moved(tmp_path):
    def rect(proj):
        return [T.props(f)["rect"] for f in proj.root.iter("filter")
                if T.props(f).get("mlt_service") == "qtblend" and T.PLACED in T.props(f)]

    def run(proj, r):
        T.patch(proj, tmp_path / "o.mkv", r, tmp_path / "s.flac", 25, [100])

    proj = load(tmp_path)
    run(proj, (24, 24, 304, 171))
    f = next(f for f in proj.root.iter("filter") if T.PLACED in T.props(f))
    T.set_prop(f, "rect", "00:00:00.000=24 24 304 171 1")     # Kdenlive's spelling of the same
    run(proj, (40, 40, 304, 171))                              # the theme changed: follow it
    assert rect(proj) == ["0=40 40 304 171 1.000000"]

    f = next(f for f in proj.root.iter("filter") if T.PLACED in T.props(f))
    T.set_prop(f, "rect", "00:00:00.000=500 300 304 171 1")   # dragged in Kdenlive: theirs now
    run(proj, (24, 24, 304, 171))
    assert rect(proj) == ["00:00:00.000=500 300 304 171 1"]


def test_intro_and_outro_go_on_an_assets_track(tmp_path):
    p = tmp_path / "ep.kdenlive"
    load(tmp_path)
    p.write_text(p.read_text().replace('<tractor id="seq" in="0" out="199">',
                                       '<tractor id="seq" in="0" out="999">'))   # 100 s
    media = {"intro_audio": (tmp_path / "i.mp3", 210), "intro_video": (tmp_path / "i.mov", 60),
             "outro_audio": (tmp_path / "o.mp3", 400), "outro_image": (tmp_path / "o.png", 200)}

    def run(duck=99.0):   # a first voice outside the intro: the default
        proj = T.load(p)
        T.patch(proj, tmp_path / "o.mkv", (0, 0, 16, 9), tmp_path / "s.flac", 5, [100], media, duck)
        T.save(proj, p)
        return T.load(p)

    proj = run()
    first = p.read_bytes()
    # the video Assets track holds the editor's clips, and there is no audio one: both are new
    assert [(t.name, t.audio) for t in proj.tracks] == [
        ("Assets Kuliss", True), ("kuliss", True), ("Henrik", True), ("Henrik", False),
        ("Assets", False), ("Assets Kuliss", False), ("kuliss", False)]
    audio, video = (next(t for t in proj.tracks if t.name == "Assets Kuliss" and t.audio == a)
                    for a in (True, False))
    assert [(e.start, e.src_in, e.length) for e in audio.entries] == [(0, 15, 180), (626, 17, 374)]
    assert [(e.start, e.src_in, e.length) for e in video.entries] == [(6, 0, 60), (798, 0, 200)]
    assert len(proj.tracks[4].entries) == 2          # the editor's Assets clips are untouched
    run()
    assert p.read_bytes() == first
    assert "00:00:06.967=0;00:00:07.450$=-15" in first.decode()   # no voice start given: 5.5 s

    # an Assets track holding nothing but our clips is used as it is
    p.write_text(first.decode().replace(">Assets Kuliss</property>", ">Assets</property>", 1))
    assert [(t.name, t.audio) for t in run(5.0).tracks][:3] == [
        ("Assets", True), ("kuliss", True), ("Henrik", True)]
    assert "00:00:06.467=0;00:00:06.950$=-15" in p.read_text()   # ducked where the voices start
