import os
import shutil
import time

import pytest

from kuliss import scaffold, steps
from kuliss import timeline as T


def _session(tmp_path):
    (tmp_path / "session_1_2025-01-01").mkdir()
    root, number = scaffold.next_session(tmp_path)
    return scaffold.scaffold_session(root, number, "2025-02-01", ["* OBS 32"]).dir


def test_state_follows_the_session_workflow(tmp_path):
    session = _session(tmp_path)
    assert steps.pick_session(tmp_path) == session  # the newest
    assert steps.pick_session(session / "sources") == session

    s = steps.state(session)
    assert (s.recordings, s.synced, s.episodes, s.cut) == ([], False, [], False)
    assert s.md.name == "session_2_2025-02-01.md" and s.project.is_file()

    (session / "sources" / "2025-02-01_K.mkv").touch()
    assert steps.state(session).recordings == ["2025-02-01_K.mkv"]

    # the placeholder episode gets a project, then is renamed: cut
    shutil.copy(s.project, session / "avsnittXX2" / "avsnittXX2.kdenlive")
    s = steps.state(session)
    assert [e.name for e in s.episodes] == ["avsnittXX2"] and not s.cut
    (session / "avsnittXX2").rename(session / "avsnitt230")
    s = steps.state(session)
    assert s.cut and not s.episodes[0].finished
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
    pytest.importorskip("PySide6", exc_type=ImportError)  # the gui extra
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
    window.notes(session, dry_run=True)  # nothing to merge yet: the job ends at once
    while window.job:
        app.processEvents()
    assert "no episode subdirectories found" in window.log.toPlainText()
    dialog = gui.NewSessionDialog(window, 3, {"Ozone": ["* Minecraft 1.12.2"]})
    assert dialog.answers()[1][0] == "* Minecraft 1.12.2"  # the first game by default
    dialog.findChild(gui.QComboBox).setCurrentText("None")
    assert "Minecraft" not in "".join(dialog.answers()[1])
    assert window.close()
