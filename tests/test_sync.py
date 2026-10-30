"""uv run pytest   (synthetic speech: noise bursts, so no media files are needed)"""

from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest

from kuliss import session, sync, timeline as T
from kuliss.config import VoiceError

RNG = np.random.default_rng(67)


def bursts(seconds, rate=sync.ENV_RATE):
    """Talk-like on/off pattern: 100 ms blocks, on about a third of the time."""
    return np.repeat(RNG.random(int(seconds * 10)) < 0.35, rate // 10).astype(float)


def z(x):
    return (x - x.mean()) / x.std()


def test_offset_cancels_the_call_delay():
    a, b = bursts(600), bursts(600)          # what two people say, on true time
    off, delay = 7.3, 0.25                    # b's recording starts 7.3 s in; the call adds 0.25 s
    o, d = round(off * 100), round(delay * 100)
    ref_voice, ref_comms = a[:500 * 100], np.roll(b, d)[:500 * 100]
    voice, comms = b[o:o + 500 * 100], np.roll(a, d)[o:o + 500 * 100]
    s, conf = sync.offset(z(ref_voice), z(ref_comms), z(voice), z(comms), "B")
    assert abs(s - off) < 0.011 and conf > sync.MIN_CONFIDENCE
    assert abs(sync.lag(z(ref_comms), z(voice))[0] - (off + delay)) < 0.011   # one way is late


def test_unrelated_audio_is_refused():
    with pytest.raises(VoiceError, match="cannot find"):
        sync.offset(*(z(bursts(300)) for _ in range(4)), "Stranger")


# --- end to end on a tiny template and tiny recordings -----------------------

def track(tid, name, audio, body=""):
    at = '<property name="kdenlive:audio_track">1</property>' if audio else ""
    hide = "video" if audio else "audio"
    return (f'<playlist id="{tid}_a">{at}{body}</playlist><playlist id="{tid}_b">{at}</playlist>'
            f'<tractor id="{tid}" in="0">{at}<property name="kdenlive:track_name">{name}</property>'
            f'<track hide="{hide}" producer="{tid}_a"/><track hide="{hide}" producer="{tid}_b"/>'
            '</tractor>')


NAMES = [("A", "Assets", True), ("A1", "J Comms", True), ("A2", "K Comms", True),
         ("A3", "Joel Voice", True), ("A4", "Kenneth Voice", True), ("A5", "J Game", True),
         ("A6", "K Game", True), ("V1", "Joel Game", False), ("V2", "Kenneth Game", False),
         ("VA", "Assets", False)]
TEMPLATE = f"""<?xml version='1.0' encoding='utf-8'?>
<mlt LC_NUMERIC="C" producer="main_bin" root="ROOT" version="7.41.0">
 <profile frame_rate_num="10" frame_rate_den="1" width="1920" height="1080"/>
 <producer id="black"><property name="resource">black</property></producer>
 <chain id="intro" out="49"><property name="resource">media/intro.mp3</property>
  <property name="kdenlive:id">2</property></chain>
 {"".join(track(t, n, a, '<entry producer="intro" in="0" out="49"/>' if t == "A" else "")
          for t, n, a in NAMES)}
 <tractor id="seq" in="0" out="49">
  <property name="kdenlive:uuid">{{u}}</property>
  <property name="kdenlive:sequenceproperties.tracksCount">{len(NAMES)}</property>
  <track producer="black"/>{"".join(f'<track producer="{t}"/>' for t, _, _ in NAMES)}
 </tractor>
 <playlist id="main_bin">
  <property name="kdenlive:docproperties.version">1.1</property>
  <property name="kdenlive:docproperties.activetimeline">{{u}}</property>
  <property name="kdenlive:docproperties.documentid">1</property>
  <entry producer="intro"/><entry producer="seq"/>
 </playlist>
 <tractor id="project" in="0" out="49"><track producer="seq"/></tractor>
</mlt>
"""


def recording(path, voice, comms, seconds):
    """An .mkv laid out like the crew's OBS recordings (Full mix, Game, Voice, Comms)."""
    sr = 8000
    noise = RNG.standard_normal(seconds * sr).astype(np.float32) * 0.3
    voice, comms = (np.repeat(e, sr // sync.ENV_RATE)[:seconds * sr] * noise for e in (voice, comms))
    tracks = {"Full mix": voice, "Game audio": noise * 0.01, "Voice audio": voice, "Comms": comms}
    with av.open(str(path), "w") as c:
        vs = c.add_stream("ffv1", rate=1)
        vs.width, vs.height, vs.pix_fmt = 16, 16, "yuv420p"
        streams = []
        for title in tracks:
            st = c.add_stream("pcm_s16le", rate=sr, layout="mono")
            st.metadata["title"] = title
            streams.append(st)
        for i in range(seconds):
            f = av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), np.uint8), format="rgb24")
            f.pts, f.time_base = i, Fraction(1, 1)
            c.mux(vs.encode(f))
        c.mux(vs.encode(None))
        for st, pcm in zip(streams, tracks.values()):
            for i in range(0, len(pcm), sr):
                f = av.AudioFrame.from_ndarray((pcm[i:i + sr] * 32767).astype(np.int16)[None, :],
                                               format="s16", layout="mono")
                f.sample_rate, f.pts, f.time_base = sr, i, Fraction(1, sr)
                c.mux(st.encode(f))
            c.mux(st.encode(None))


def make_session(tmp_path):
    assets = tmp_path / "_assets"
    (assets / "media").mkdir(parents=True)
    (assets / "media" / "intro.mp3").write_bytes(b"")
    template = assets / "template.kdenlive"
    template.write_text(TEMPLATE.replace("ROOT", str(assets)))
    sdir = tmp_path / "session_1_2026-10-30"
    (sdir / "sources").mkdir(parents=True)
    project = sdir / f"{sdir.name}.kdenlive"
    session.create_project(template, project)

    j, k = bursts(120), bursts(120)           # Kenneth starts recording 12 s after Joel
    recording(sdir / "sources" / "2026-10-30_j.mkv", j[:9000], k[:9000], 90)
    recording(sdir / "sources" / "2026-10-30_k.mkv", k[1200:10200], j[1200:10200], 90)
    return sdir, project


def test_create_project_makes_paths_absolute(tmp_path):
    sdir, project = make_session(tmp_path)
    root = T.ET.parse(project).getroot()
    assert root.get("root") == str(sdir)
    res = {T.props(e).get("resource") for e in root if e.tag in ("chain", "producer")}
    assert res == {"black", str(tmp_path / "_assets" / "media" / "intro.mp3")}
    assert T.props(root.find("playlist[@id='main_bin']"))["kdenlive:docproperties.documentid"] != "1"


def test_sync_places_recordings_and_refuses_a_second_run(tmp_path, capsys):
    sdir, project = make_session(tmp_path)
    session.sync_session(sdir)
    p = T.load(project)
    tracks = {t.name: t for t in p.tracks}
    joel, kenneth = 50, 50 + 120               # after the 5 s intro; Kenneth 12 s later
    for name, start, stream in [("J Comms", joel, 4), ("Joel Voice", joel, 3),
                                ("J Game", joel, 2), ("K Comms", kenneth, 4),
                                ("Kenneth Voice", kenneth, 3), ("K Game", kenneth, 2)]:
        (e,) = tracks[name].entries
        assert (e.start, e.length, e.audio_index) == (start, 900, stream), name
        assert Path(e.resource).name.endswith(f"_{name[0].lower()}.mkv")
    assert tracks["Kenneth Game"].entries[0].start == kenneth and p.length == kenneth + 900
    assert "+12.00 s" in capsys.readouterr().out

    with pytest.raises(VoiceError, match="already has clips"):
        session.sync_session(sdir)


def test_recording_without_the_standard_streams_is_refused(tmp_path):
    sdir, _ = make_session(tmp_path)
    bad = sdir / "sources" / "2026-10-30_r.mkv"
    with av.open(str(bad), "w") as c:
        st = c.add_stream("pcm_s16le", rate=8000, layout="mono")
        st.metadata["title"] = "Track1"
        f = av.AudioFrame.from_ndarray(np.zeros((1, 800), np.int16), format="s16", layout="mono")
        f.sample_rate, f.pts, f.time_base = 8000, 0, Fraction(1, 8000)
        c.mux(st.encode(f))
        c.mux(st.encode(None))
    with pytest.raises(VoiceError, match="titled Comms, Voice audio, Game audio"):
        session.sync_session(sdir)


def test_guest_gets_own_tracks_and_crew_may_use_full_names(tmp_path, capsys):
    sdir, project = make_session(tmp_path)
    src = sdir / "sources"
    for f in src.glob("*.mkv"):
        f.unlink()
    j, k, g = bursts(120), bursts(120), bursts(120)   # Kenneth starts 12 s in, Jesper 5 s in
    recording(src / "2026-10-30_j.mkv", j[:9000], np.maximum.reduce([k, g])[:9000], 90)
    recording(src / "2026-10-30_kenneth.mkv", k[1200:10200], np.maximum.reduce([j, g])[1200:10200], 90)
    recording(src / "2026-10-30_jesper.mkv", g[500:9500], np.maximum.reduce([j, k])[500:9500], 90)
    session.sync_session(sdir)

    p = T.load(project)
    tracks = {(t.name, t.audio): t for t in p.tracks}
    for name, audio in [("Jesper Comms", True), ("Jesper Voice", True), ("Jesper Game", True),
                        ("Jesper Game", False)]:
        assert tracks[name, audio].entries[0].start == 50 + 50, name
    assert tracks["Kenneth Voice", True].entries[0].start == 50 + 120
    order = [t.name for t in p.tracks if not t.audio]
    assert order.index("Jesper Game") == order.index("Assets") - 1   # under intro and namecards
    assert "added the video track 'Jesper Game'" in capsys.readouterr().out
