import json
import os
import shutil
import time

import pytest

from kuliss import scaffold, steps
from kuliss import timeline as T
from kuliss.errors import VoiceError


def _session(tmp_path):
    (tmp_path / "session_1_2025-01-01").mkdir()
    root, number = scaffold.next_session(tmp_path)
    return scaffold.scaffold_session(root, number, "2025-02-01", ["* OBS 32"]).dir


def test_state_follows_the_session_workflow(tmp_path):
    session = _session(tmp_path)
    assert steps.pick_session(tmp_path) == session  # the newest
    assert steps.pick_session(session / "sources") == session

    s = steps.state(session)
    assert (s.recordings, s.synced, s.episodes, s.marked) == ([], False, [], False)
    assert s.md.name == "session_02_2025-02-01.md" and s.project.is_file()

    (session / "sources" / "2025-02-01_K.mkv").touch()
    assert steps.state(session).recordings == ["2025-02-01_K.mkv"]

    # episodes marked with guides in the session project (other guides don't count)
    proj = T.load(s.project)
    guides = [
        {"comment": "avsnitt231", "duration": 0, "pos": 90000, "type": 0},
        {"comment": "avsnitt230", "duration": 0, "pos": 0, "type": 0},
        {"comment": "funny bit", "duration": 0, "pos": 500, "type": 0},
    ]
    T.set_prop(proj.seq, "kdenlive:sequenceproperties.guides", json.dumps(guides))
    T.save(proj, s.project)
    s = steps.state(session)
    assert s.marked and [(e.name, e.start, e.project) for e in s.episodes] == [
        ("avsnitt230", 0, None),
        ("avsnitt231", 90000, None),
    ]
    assert steps.clock(90000, s.fps) == "0:25:00"

    # the placeholder folder renamed to the first episode, with its copy of the project
    (session / "avsnittXX02").rename(session / "avsnitt230")
    shutil.copy(s.project, session / "avsnitt230" / "avsnitt230.kdenlive")
    s = steps.state(session)
    first = s.episodes[0]
    assert (first.name, first.start, first.finished) == ("avsnitt230", 0, False)
    assert first.project == session / "avsnitt230" / "avsnitt230.kdenlive"
    assert s.episodes[1].project is None
    assert not s.notes_current  # the project is newer than the .md

    later = time.time() + 10
    os.utime(s.md, (later, later))
    assert steps.state(session).notes_current


def test_finished_means_the_overlay_track_is_there(tmp_path):
    session = _session(tmp_path)
    episode = session / "avsnitt230"
    episode.mkdir()
    project = episode / "avsnitt230.kdenlive"
    shutil.copy(session / f"{session.name}.kdenlive", project)
    assert not steps.state(session).episodes[0].finished
    proj = T.load(project)
    T.ensure_track(proj, audio=False)  # what kuliss finish adds
    T.save(proj, project)
    assert steps.state(session).episodes[0].finished


def test_unreadable_project_is_a_problem_not_a_crash(tmp_path):
    session = _session(tmp_path)
    (session / "avsnitt230").mkdir()
    (session / "avsnitt230" / "avsnitt230.kdenlive").write_text("<mlt>", encoding="utf-8")
    s = steps.state(session)
    assert s.problems and not s.episodes[0].finished


def test_window_opens_and_closes(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")  # the gui extra
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from kuliss import gui

    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path))
    session = _session(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = gui.Window(session)
    assert window.windowTitle() == f"kuliss – {session.name}"
    assert "Theme: none" in window.links.text()
    window.show()
    assert window.split.sizes()[1] == 0  # the log starts minimized
    window.notes(session, dry_run=True)  # nothing to merge yet: the job ends at once
    while window.job:
        app.processEvents()
    assert "no episode subdirectories found" in window.log.toPlainText()
    assert window.split.sizes()[1] > 0  # and opens for the first output
    dialog = gui.NewSessionDialog(window, 3, {"Ozone": ["* Minecraft 1.12.2"]})
    assert dialog.answers()[1][0] == "* Minecraft 1.12.2"  # the first game by default
    dialog.findChild(gui.QComboBox).setCurrentText("None")
    assert "Minecraft" not in "".join(dialog.answers()[1])
    assert window.close()
    window.deleteLater()
    app.shutdown()  # now, not at interpreter exit: a late teardown crashes on Linux CI


def test_game_folders_share_the_show_crew_file(tmp_path, caplog):
    """show/_assets/kuliss.toml serves every game; each game folder has its own theme."""
    (tmp_path / "_assets").mkdir()
    (tmp_path / "_assets" / "kuliss.toml").write_text(
        'master_gain = 3.0\n[software]\n"Blue Prince" = ["* Blue Prince 1.0"]\n', encoding="utf-8"
    )
    game = tmp_path / "blue_prince"
    game.mkdir()
    with pytest.raises(VoiceError, match="give it a folder with its theme.toml"):
        scaffold.next_session(game)
    with pytest.raises(VoiceError, match="Run it in a game's folder"):
        scaffold.next_session(tmp_path)  # the show folder itself
    (game / "theme.toml").write_text("", encoding="utf-8")
    root, number = scaffold.next_session(game)
    assert (root, number) == (game, 1)
    assert scaffold.software_presets(root) == {"Blue Prince": ["* Blue Prince 1.0"]}
    made = scaffold.scaffold_session(root, number, "2026-01-02", ["* OBS 32"])
    assert made.dir == game / "session_01_2026-01-02" and made.episode == "avsnittXX01"
    assert "no crew file" not in caplog.text
    master = {
        T.props(f)["mlt_service"]: T.props(f) for f in T.load(made.project).seq.findall("filter")
    }
    assert master["volume"]["level"] == "3.0"  # the show's crew file, two folders up
    assert steps.state(made.dir).crew_file == tmp_path / "_assets" / "kuliss.toml"
    assert scaffold.next_session(made.dir) == (game, 2)
