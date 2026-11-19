"""kuliss gui: one window that walks through a session in the order of the session workflow.

Each step shows whether it is done (steps.state, read from disk whenever the window gets
focus), a button that runs it, and links that open the files involved in their default
program (QDesktopServices: xdg-open on Linux, the file associations on Windows).
Like cli.py, this is a front end: it calls the library and shows what comes back.
"""

import logging
from collections.abc import Callable
from html import escape
from pathlib import Path

from PySide6.QtCore import QDate, QObject, QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import steps
from .errors import VoiceError
from .notes import SOFTWARE_DEFAULTS

PREVIEW = 90  # s, as in the README's first check
REPO = "https://github.com/seetee/kuliss"
Work = Callable[[Callable[[int, int], None]], tuple[list[str], Path | None]]


def link(path: Path, text: str | None = None) -> str:
    """An HTML link that opens `path` in its default program, or plain text if it's missing."""
    label = escape(text or path.name)
    if not path.exists():
        return f"{label} <i>(missing)</i>"
    return f'<a href="{QUrl.fromLocalFile(str(path)).toString()}">{label}</a>'


def rich(html: str) -> QLabel:
    label = QLabel(html)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)  # file:// links go to QDesktopServices.openUrl
    label.setWordWrap(True)
    return label


class Job(QThread):
    """Runs one command off the GUI thread; widgets are only touched through the signals."""

    progress = Signal(int, int)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, work: Work):
        super().__init__()
        self.work = work

    def run(self) -> None:
        try:
            self.succeeded.emit(self.work(self.progress.emit))
        except VoiceError as e:
            self.failed.emit(str(e))
        except Exception as e:  # a bug: show it rather than lose it in a thread
            logging.getLogger(__name__).exception("unexpected error")
            self.failed.emit(f"{type(e).__name__}: {e}")


class LogBridge(QObject):
    line = Signal(str)


class LogHandler(logging.Handler):
    """Library warnings (from any thread) into the log pane."""

    def __init__(self, bridge: LogBridge):
        super().__init__(logging.WARNING)
        self.bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        self.bridge.line.emit(f"WARNING: {record.getMessage()}")


class NewSessionDialog(QDialog):
    def __init__(self, parent: QWidget, number: int, presets: dict[str, list[str]]):
        super().__init__(parent)
        self.setWindowTitle(f"New session {number}")
        form = QFormLayout(self)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Recording date", self.date)
        self.software = QPlainTextEdit()
        if presets:  # the game's own lines, from the crew file
            game = QComboBox()
            game.addItems([*presets, "None"])
            game.currentTextChanged.connect(
                lambda name: self.software.setPlainText(
                    "\n".join(presets.get(name, []) + SOFTWARE_DEFAULTS)
                )
            )
            form.addRow("Game", game)
        self.software.setPlainText("\n".join(next(iter(presets.values()), []) + SOFTWARE_DEFAULTS))
        form.addRow("Software versions", self.software)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def answers(self) -> tuple[str, list[str]]:
        lines = [line.rstrip() for line in self.software.toPlainText().splitlines()]
        return self.date.date().toString("yyyy-MM-dd"), [line for line in lines if line]


class Window(QMainWindow):
    def __init__(self, start: Path):
        super().__init__()
        self.settings = QSettings("kuliss", "kuliss")
        self.job: Job | None = None
        self.session: Path | None = None
        self.root = start

        self.title = QLabel()
        choose = QPushButton("Choose session…")
        choose.clicked.connect(self.choose)
        top = QHBoxLayout()
        top.addWidget(self.title, 1)
        top.addWidget(choose)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.links = rich("")
        self.links.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.links.setMinimumWidth(220)
        middle = QSplitter()
        middle.addWidget(self.scroll)
        middle.addWidget(self.links)
        middle.setStretchFactor(0, 1)

        self.bar = QProgressBar()
        self.bar.hide()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        lower = QWidget()
        lower_box = QVBoxLayout(lower)
        lower_box.setContentsMargins(0, 0, 0, 0)
        lower_box.addWidget(self.bar)
        lower_box.addWidget(self.log)
        split = self.split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(middle)
        split.addWidget(lower)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([1, 0])  # the log starts minimized; its handle stays to drag it open
        self.log_opened = False

        central = QWidget()
        box = QVBoxLayout(central)
        box.addLayout(top)
        box.addWidget(split, 1)
        self.setCentralWidget(central)
        self.resize(1000, 750)

        self.bridge = LogBridge()
        self.bridge.line.connect(self.say)
        self.handler = LogHandler(self.bridge)
        logging.getLogger().addHandler(self.handler)
        self.open(start)

    # ── session ──────────────────────────────────────────────────────────────

    def open(self, start: Path) -> None:
        self.session = steps.pick_session(start)
        self.root = self.session.parent if self.session else start
        if self.session:
            self.settings.setValue("session", str(self.session))
        self.refresh()

    def choose(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Session folder", str(self.root))
        if folder:
            self.open(Path(folder))

    def new_session(self) -> None:
        from . import scaffold  # numpy, for the project; only when asked

        try:
            root, number = scaffold.next_session(self.root)
            dialog = NewSessionDialog(self, number, scaffold.software_presets(root))
            if not dialog.exec():
                return
            session_date, software = dialog.answers()
            made = scaffold.scaffold_session(root, number, session_date, software)
        except VoiceError as e:
            self.error(str(e))
            return
        self.say("\n".join(steps.new_report(made)))
        self.say("Next: copy the recordings into sources/, then Sync.")
        self.open(made.dir)

    # ── the steps ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        if self.job:  # a command is writing; its end refreshes
            return
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setColumnStretch(2, 1)
        grid.setVerticalSpacing(14)
        self.row = 0

        def step(done: bool | None, title: str, detail: str, *buttons, sub=False) -> None:
            mark = {True: "✓", False: "○", None: ""}[done]
            grid.addWidget(QLabel(f"<b>{mark}</b>"), self.row, 0, Qt.AlignmentFlag.AlignTop)
            name = QLabel(escape(title) if sub else f"<b>{escape(title)}</b>")
            name.setIndent(24 if sub else 0)  # an episode, under its step
            grid.addWidget(name, self.row, 1, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(rich(detail), self.row, 2)
            row_buttons = QHBoxLayout()
            for text, action, enabled in buttons:
                button = QPushButton(text)
                button.clicked.connect(action)
                button.setEnabled(enabled)
                row_buttons.addWidget(button)
            grid.addLayout(row_buttons, self.row, 3, Qt.AlignmentFlag.AlignTop)
            self.row += 1

        s = steps.state(self.session) if self.session else None
        if s is None:
            self.setWindowTitle("kuliss")
            self.title.setText(f"<b>No session_* folder in {escape(str(self.root))}</b>")
            step(False, "1. New session", "", ("New session…", self.new_session, True))
        else:
            self.setWindowTitle(f"kuliss – {s.session.name}")
            self.title.setText(f"<b>{escape(s.session.name)}</b>")
            self._steps(s, step)
        grid.setRowStretch(self.row, 1)
        self.scroll.setWidget(grid_widget)
        self.links.setText(self._links(s))

    def _steps(self, s: steps.State, step) -> None:
        folder = link(s.session, "the session folder")
        main = link(s.project, "the session project")
        step(
            True,
            "1. Create the session",
            f"Made {folder} with sources/, kortisar/, an avsnittXX… folder, the notes file "
            "and the session project. Recording a new session? Start here.",
            ("New session…", self.new_session, True),
        )
        found = ", ".join(escape(name) for name in s.recordings) or "none yet"
        step(
            bool(s.recordings),
            "2. Add the recordings",
            f"Copy everyone's .mkv into {link(s.session / 'sources', 'sources/')}, named "
            f"&lt;date&gt;_&lt;initial&gt;.mkv. Found: {found}",
        )
        step(
            s.synced,
            "3. Sync",
            f"Puts every recording on {main} so they share one timeline: Voice clips grouped, "
            "each game video grouped with its game audio, every track slimmed down. Then "
            "listen in Kdenlive that the voices line up. Synced by hand? This shows ✓ as "
            "soon as the project has clips.",
            ("Sync", lambda: self.sync(s.session), bool(s.recordings) and not s.synced),
        )
        marked = ", ".join(
            f"{escape(e.name)} {steps.clock(e.start, s.fps)}"
            for e in s.episodes
            if e.start is not None
        )
        step(
            s.marked,
            "4. Mark the episodes",
            f"In {main}, add a guide where each episode starts, named after it "
            "(avsnitt230, avsnitt231, …). Look about 20 minutes ahead, then for a joke or "
            "a natural break; 20–25 minutes each, or what the flow needs. From now on the "
            "session project is the single source of truth: fix sound and episode borders "
            f"there. Marked: {marked or 'none yet'}",
        )
        step(
            None,
            "5–9. Each episode, in order",
            "<ol start=5 style='margin-left:-20px'>"
            f"<li><b>Make its project.</b> Rename the avsnittXX… folder in {folder} to the "
            "episode (or add a folder for the next one). In the session project, "
            "<i>Copy to…</i> that folder as avsnitt&lt;nr&gt;.kdenlive and <b>open the "
            "copy</b>. Cut at the episode's guides and delete everything outside, including "
            "the Comms tracks.</li>"
            "<li><b>Choose the views.</b> Show the four game videos side by side and keep one "
            "at a time: cut between words, and switch a moment before someone starts on "
            "something new. Jot moments in Document Notes as you go (a * after the timestamp "
            "makes a YouTube chapter).</li>"
            "<li><b>Finish</b> (below): intro and outro, ducked under the first and last "
            "voice, a swoosh at every switch and the overlay showing whose view it is. Run it "
            "again after any change to the edit, then reopen the project in Kdenlive.</li>"
            "<li><b>Notes</b> (below): fill in the Titel and the other fields.</li>"
            "<li><b>Render</b> in Kdenlive.</li></ol>",
        )
        if not s.episodes:
            step(
                False, "      no episodes yet", "They show up here once marked (step 4).", sub=True
            )
        for e in s.episodes:
            has = e.project is not None
            where = "" if e.start is None else f" · starts at {steps.clock(e.start, s.fps)}"
            step(
                e.finished,
                e.name,
                (link(e.project, "its project") if has else "no project yet (step 5)") + where,
                ("Analyse", lambda _=False, p=e.project: self.finish(p, "analyse"), has),
                (
                    f"Preview {PREVIEW} s",
                    lambda _=False, p=e.project: self.finish(p, "preview"),
                    has,
                ),
                ("Finish", lambda _=False, p=e.project: self.finish(p, "finish"), has),
                sub=True,
            )
        made = [e for e in s.episodes if e.project]
        step(
            s.notes_current if made else False,
            "8. Notes",
            f"Gathers every episode's Document Notes into {link(s.md, 'the notes file')} "
            "(chapters, Bryggpromenader, the checklist). Then fill in the Titel and the other "
            "fields there.",
            ("Update notes", lambda: self.notes(s.session, False), bool(made)),
            ("Dry run", lambda: self.notes(s.session, True), bool(made)),
        )

    def _links(self, s: steps.State | None) -> str:
        html = ""
        if s:
            theme = s.theme
            show = [
                link(theme, "Theme")
                if theme
                else f'Theme: none (see <a href="{REPO}/blob/main/theme.example.toml">'
                "theme.example.toml</a>)",
                link(s.crew_file, "Crew file (mixer, game software)"),
                link(s.root / "_assets", "_assets/ folder"),
            ]
            mine = [
                link(s.session, "Folder"),
                link(s.md, "Notes file (.md)"),
                link(s.project, "Kdenlive project"),
            ]
            html += "<b>This session</b><br>" + "<br>".join(mine) + "<br><br>"
            html += "<b>Every session</b><br>" + "<br>".join(show) + "<br><br>"
        html += f'<a href="{REPO}#readme">README</a>'
        if s and s.problems:
            html += "<br><br><b>Problems</b><br>" + "<br>".join(escape(p) for p in s.problems)
        return html

    # ── running commands ─────────────────────────────────────────────────────

    def sync(self, session: Path) -> None:
        def work(progress):
            from . import session as sync_mod

            return steps.sync_report(sync_mod.sync_session(session)), None

        self.start("Sync", work)

    def notes(self, session: Path, dry_run: bool) -> None:
        def work(progress):
            from . import notes

            return notes.process_session(session, dry_run=dry_run).lines, None

        self.start("Notes (dry run)" if dry_run else "Notes", work)

    def finish(self, project: Path, mode: str) -> None:
        def work(progress):
            from . import finish

            analysis = finish.analyse(project)
            lines = steps.analysis_report(analysis)
            if mode == "analyse":
                return lines, None
            preview = PREVIEW if mode == "preview" else None
            overlay = finish.render_overlay(analysis, preview, progress)
            if preview:
                return lines + [f"Preview written: {overlay}"], overlay
            backup = finish.apply(analysis, overlay)
            return lines + [f"Updated {project.name} (backup: {backup.name}). {steps.REOPEN}"], None

        self.start(f"{mode.capitalize()} {project.parent.name}", work)

    def start(self, title: str, work: Work) -> None:
        self.say(f"── {title}")
        self.centralWidget().setEnabled(False)
        self.bar.setRange(0, 0)  # busy until the first progress report
        self.bar.show()
        self.job = Job(work)
        self.job.progress.connect(self.progress)
        self.job.succeeded.connect(self.succeeded)
        self.job.failed.connect(self.failed)
        self.job.finished.connect(self.ended)
        self.job.start()

    def progress(self, done: int, total: int) -> None:
        self.bar.setRange(0, total)
        self.bar.setValue(done)

    def succeeded(self, result: tuple[list[str], Path | None]) -> None:
        lines, to_open = result
        self.say("\n".join(lines))
        if to_open:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(to_open)))

    def failed(self, message: str) -> None:
        self.say(f"ERROR: {message}")
        self.error(message)

    def ended(self) -> None:
        self.job = None
        self.bar.hide()
        self.centralWidget().setEnabled(True)
        self.refresh()

    # ── output ───────────────────────────────────────────────────────────────

    def say(self, text: str) -> None:
        if not self.log_opened:  # open it for the first output; after that it's yours
            self.log_opened = True
            top, bottom = self.split.sizes()
            if not bottom:
                self.split.setSizes([(top + bottom) * 3 // 4, (top + bottom) // 4])
        self.log.appendPlainText(text)

    def error(self, message: str) -> None:
        QMessageBox.warning(self, "kuliss", message)

    def closeEvent(self, event) -> None:
        if self.job:  # a half-written render or project; let it end
            self.say("Wait for the running command to end before closing.")
            event.ignore()
            return
        logging.getLogger().removeHandler(self.handler)
        event.accept()


def run(start: Path | None) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("kuliss")
    if start is None:
        last = Path(str(QSettings("kuliss", "kuliss").value("session", "")))
        start = last if last.name and last.is_dir() else Path.cwd()
    window = Window(start)
    app.applicationStateChanged.connect(
        lambda state: state == Qt.ApplicationState.ApplicationActive and window.refresh()
    )
    window.show()
    return app.exec()
