"""uv run pytest   (synthetic speech: noise bursts, so no media files are needed)"""

import json
import os
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest

from kuliss import session, sync
from kuliss import timeline as T
from kuliss.config import CREW_FILE, load_crew
from kuliss.errors import VoiceError

RNG = np.random.default_rng(67)


def bursts(seconds, rate=sync.ENV_RATE):
    """Talk-like on/off pattern: 100 ms blocks, on about a third of the time."""
    return np.repeat(RNG.random(int(seconds * 10)) < 0.35, rate // 10).astype(float)


def z(x):
    return (x - x.mean()) / x.std()


def test_offset_cancels_the_call_delay():
    a, b = bursts(600), bursts(600)  # what two people say, on true time
    off, delay = 7.3, 0.25  # b's recording starts 7.3 s in; the call adds 0.25 s
    o, d = round(off * 100), round(delay * 100)
    ref_voice, ref_comms = a[: 500 * 100], np.roll(b, d)[: 500 * 100]
    voice, comms = b[o : o + 500 * 100], np.roll(a, d)[o : o + 500 * 100]
    s, conf = sync.offset(z(ref_voice), z(ref_comms), z(voice), z(comms), "B")
    assert abs(s - off) < 0.011 and conf > sync.MIN_CONFIDENCE
    assert abs(sync.lag(z(ref_comms), z(voice))[0] - (off + delay)) < 0.011  # one way is late


def test_unrelated_audio_is_refused():
    with pytest.raises(VoiceError, match="cannot find"):
        sync.offset(*(z(bursts(300)) for _ in range(4)), "Stranger")


# --- end to end on a generated project and tiny recordings -------------------

CREW = """master_gain = 10.0
assets_gain = -21.0
game_gain = -20.5
[voice.Joel]
gain = 9.5
pan = 0.56
contrast = 33
"""


def recording(path, voice, comms, seconds, drop=()):
    """An .mkv laid out like the crew's OBS recordings (Full mix, Game, Voice, Comms),
    without the streams titled in `drop`."""
    sr = 8000
    noise = RNG.standard_normal(seconds * sr).astype(np.float32) * 0.3
    voice, comms = (
        np.repeat(e, sr // sync.ENV_RATE)[: seconds * sr] * noise for e in (voice, comms)
    )
    tracks = {"Full mix": voice, "Game audio": noise * 0.01, "Voice audio": voice, "Comms": comms}
    tracks = {title: pcm for title, pcm in tracks.items() if title not in drop}
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
        for st, pcm in zip(streams, tracks.values(), strict=True):
            for i in range(0, len(pcm), sr):
                f = av.AudioFrame.from_ndarray(
                    (pcm[i : i + sr] * 32767).astype(np.int16)[None, :], format="s16", layout="mono"
                )
                f.sample_rate, f.pts, f.time_base = sr, i, Fraction(1, sr)
                c.mux(st.encode(f))
            c.mux(st.encode(None))


def make_session(tmp_path):
    (tmp_path / "_assets").mkdir()
    (tmp_path / "_assets" / "kuliss.toml").write_text(CREW)
    sdir = tmp_path / "session_1_2026-10-30"
    (sdir / "sources").mkdir(parents=True)
    project = sdir / f"{sdir.name}.kdenlive"
    T.create_project(project, load_crew(tmp_path / CREW_FILE))

    j, k = bursts(120), bursts(120)  # Kenneth starts recording 12 s after Joel
    recording(sdir / "sources" / "2026-10-30_j.mkv", j[:9000], k[:9000], 90)
    recording(sdir / "sources" / "2026-10-30_k.mkv", k[1200:10200], j[1200:10200], 90)
    return sdir, project


def mixer(proj, name, audio=True):
    """{service: properties} of a track's filters."""
    t = T._find_track(proj, name, audio)
    return {T.props(f)["mlt_service"]: T.props(f) for f in t.findall("filter")}


def test_create_project_builds_an_empty_session(tmp_path):
    sdir, project = make_session(tmp_path)
    p = T.load(project)
    assert p.root.get("root") == str(sdir) and (p.fps, p.width, p.height) == (60, 1920, 1080)
    assert [(t.name, t.audio) for t in p.tracks] == [("Assets", True), ("Assets", False)]
    assert mixer(p, "Assets")["volume"]["level"] == "-21.0"
    master = {T.props(f)["mlt_service"]: T.props(f) for f in p.seq.findall("filter")}
    assert master["volume"]["level"] == "10.0"
    bin_props = T.props(p.root.find("playlist[@id='main_bin']"))
    assert bin_props["kdenlive:docproperties.activetimeline"] == T.props(p.seq)["kdenlive:uuid"]


def test_sync_places_recordings_and_refuses_a_second_run(tmp_path):
    sdir, project = make_session(tmp_path)
    result = session.sync_session(sdir)
    p = T.load(project)
    tracks = {t.name: t for t in p.tracks}
    joel, kenneth = 0, 12 * 60  # from 0 (60 fps); Kenneth 12 s later
    for name, start, stream in [
        ("J Comms", joel, 4),
        ("Joel Voice", joel, 3),
        ("J Game", joel, 2),
        ("K Comms", kenneth, 4),
        ("Kenneth Voice", kenneth, 3),
        ("K Game", kenneth, 2),
    ]:
        (e,) = tracks[name].entries
        assert (e.start, e.length, e.audio_index) == (start, 90 * 60, stream), name
        assert Path(e.resource).name.endswith(f"_{name[0].lower()}.mkv")
    assert tracks["Kenneth Game"].entries[0].start == kenneth and p.length == kenneth + 90 * 60
    assert round(result.offsets["Kenneth"][0], 2) == 12.0
    # tracks grouped by kind, in crew order; mixers from the crew file
    assert [(t.name, t.audio) for t in p.tracks] == [
        ("Assets", True),
        ("J Comms", True),
        ("K Comms", True),
        ("Joel Voice", True),
        ("Kenneth Voice", True),
        ("J Game", True),
        ("K Game", True),
        ("Joel Game", False),
        ("Kenneth Game", False),
        ("Assets", False),
    ]
    joel_voice = mixer(p, "Joel Voice")
    assert (
        joel_voice["volume"]["level"],
        joel_voice["panner"]["start"],
        joel_voice["avfilter.acontrast"]["av.contrast"],
    ) == ("9.5", "0.56", "33")
    assert mixer(p, "Kenneth Voice")["volume"]["level"] == "0.0"  # not in the crew file
    assert mixer(p, "K Game")["volume"]["level"] == "-20.5"
    assert mixer(p, "J Comms") == {}

    collapsed = {
        T.props(t).get("kdenlive:collapsed")
        for t in p.root.iter("tractor")
        if "kdenlive:track_name" in T.props(t)
    }
    assert collapsed == {"28"}  # every track in the slimmed-down view
    # grouped as the crew does: all Voice clips; each player's game video with its audio
    groups = json.loads(T.props(p.seq)["kdenlive:sequenceproperties.groups"])
    assert [(g["type"], [c["data"] for c in g["children"]]) for g in groups] == [
        ("Normal", ["3:0:-1", "4:720:-1"]),  # Joel Voice, Kenneth Voice (no black track)
        ("Normal", ["7:0:-1", "5:0:-1"]),  # Joel Game video, J Game
        ("Normal", ["8:720:-1", "6:720:-1"]),  # Kenneth Game video, K Game
    ]

    with pytest.raises(VoiceError, match="already has clips"):
        session.sync_session(sdir)


def test_unusable_recording_is_skipped_and_the_rest_synced(tmp_path, caplog):
    sdir, project = make_session(tmp_path)
    bad = sdir / "sources" / "2026-10-30_r.mkv"
    with av.open(str(bad), "w") as c:
        st = c.add_stream("pcm_s16le", rate=8000, layout="mono")
        st.metadata["title"] = "Track1"
        f = av.AudioFrame.from_ndarray(np.zeros((1, 800), np.int16), format="s16", layout="mono")
        f.sample_rate, f.pts, f.time_base = 8000, 0, Fraction(1, 8000)
        c.mux(st.encode(f))
        c.mux(st.encode(None))
    (sdir / "sources" / "2026-10-30_h.mkv").write_bytes(b"not a video")
    result = session.sync_session(sdir)
    assert "2026-10-30_r.mkv: no audio stream titled Voice audio or Comms" in caplog.text
    assert "2026-10-30_h.mkv: cannot read it" in caplog.text
    assert list(result.offsets) == ["Kenneth"]
    assert result.left_out == ["2026-10-30_h.mkv", "2026-10-30_r.mkv"]
    assert not any(
        t.name.startswith(("R ", "Robin", "H ", "Henrik")) for t in T.load(project).tracks
    )


def test_missing_comms_syncs_one_way_and_gets_no_comms_track(tmp_path, caplog):
    sdir, project = make_session(tmp_path)
    k = sdir / "sources" / "2026-10-30_k.mkv"
    j, kk = bursts(120), bursts(120)
    for f in (sdir / "sources").glob("*.mkv"):
        f.unlink()
    recording(sdir / "sources" / "2026-10-30_j.mkv", j[:9000], kk[:9000], 90)
    recording(k, kk[1200:10200], j[1200:10200], 90, drop=("Comms", "Game audio"))
    result = session.sync_session(sdir)
    assert result.reference == "Joel"  # the one with both streams
    assert round(result.offsets["Kenneth"][0], 1) == 12.0
    assert "2026-10-30_k.mkv: no Comms, Game audio" in caplog.text
    assert "Kenneth: synced one way only" in caplog.text
    names = {t.name for t in T.load(project).tracks}
    assert {"Kenneth Voice", "Kenneth Game", "J Comms"} <= names
    assert not names & {"K Comms", "K Game"}


def test_unmatched_recording_is_left_out(tmp_path, caplog):
    sdir, project = make_session(tmp_path)
    stranger = bursts(120)
    recording(sdir / "sources" / "2026-10-30_r.mkv", stranger[:9000], stranger[:9000], 90)
    result = session.sync_session(sdir)
    assert result.left_out == ["2026-10-30_r.mkv"]
    assert "Robin: cannot find their voice" in caplog.text
    assert "Robin Voice" not in {t.name for t in T.load(project).tracks}


def test_two_recordings_of_one_player_are_refused(tmp_path):
    sdir, _ = make_session(tmp_path)
    src = sdir / "sources"
    (src / "2026-10-30b_kenneth.mkv").write_bytes((src / "2026-10-30_k.mkv").read_bytes())
    with pytest.raises(VoiceError, match="Kenneth has 2 recordings"):
        session.sync_session(sdir)


def test_guest_gets_own_tracks_and_crew_may_use_full_names(tmp_path):
    sdir, project = make_session(tmp_path)
    src = sdir / "sources"
    for f in src.glob("*.mkv"):
        f.unlink()
    j, k, g = bursts(120), bursts(120), bursts(120)  # Kenneth starts 12 s in, Jesper 5 s in
    recording(src / "2026-10-30_j.mkv", j[:9000], np.maximum.reduce([k, g])[:9000], 90)
    recording(
        src / "2026-10-30_kenneth.mkv", k[1200:10200], np.maximum.reduce([j, g])[1200:10200], 90
    )
    recording(src / "2026-10-30_jesper.mkv", g[500:9500], np.maximum.reduce([j, k])[500:9500], 90)
    result = session.sync_session(sdir)

    p = T.load(project)
    tracks = {(t.name, t.audio): t for t in p.tracks}
    for name, audio in [
        ("Jesper Comms", True),
        ("Jesper Voice", True),
        ("Jesper Game", True),
        ("Jesper Game", False),
    ]:
        assert tracks[name, audio].entries[0].start == 5 * 60, name
    assert tracks["Kenneth Voice", True].entries[0].start == 12 * 60
    order = [t.name for t in p.tracks if not t.audio]
    assert order.index("Jesper Game") == order.index("Assets") - 1  # under intro and namecards
    assert ("Jesper Game", False) in result.added_tracks


def test_crew_file_is_checked(tmp_path):
    crew = tmp_path / "kuliss.toml"
    crew.write_text("[voice.Joel]\npan = 1.5\n")
    with pytest.raises(VoiceError, match="pan must be between 0"):
        load_crew(crew)
    crew.write_text("game_gain = -21\n")  # a whole number is fine
    assert load_crew(crew).game_gain == -21.0 and load_crew(crew).voice_of("Anna").gain == 0


def test_write_refuses_a_project_saved_meanwhile(tmp_path):
    project = tmp_path / "p.kdenlive"
    T.create_project(project, load_crew(tmp_path / "none.toml"))
    mtime = project.stat().st_mtime_ns
    proj = T.load(project)
    os.utime(project, ns=(mtime + 10**9, mtime + 10**9))  # Kdenlive saved it while we worked
    with pytest.raises(VoiceError, match="was saved while we worked"):
        T.write(proj, project, mtime)
    assert not list(tmp_path.glob("*.bak")) and not list(tmp_path.glob("*.partial"))
