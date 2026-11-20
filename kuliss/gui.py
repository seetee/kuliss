"""kuliss gui: one window that walks through a session in the order of the session workflow.

The steps are a tree on the left (status first, episodes under their step); the selected
step's page is on the right: what to do, a picture or list of what's there, its buttons,
its problems and its own output. Done or not comes from steps.state, read from disk
whenever the window gets focus. Links open files in their default program
(QDesktopServices: xdg-open on Linux, the file associations on Windows).
Like cli.py, this is a front end: it calls the library and shows what comes back.
"""

import logging
from collections.abc import Callable
from html import escape
from pathlib import Path

from PySide6.QtCore import QDate, QObject, QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import steps
from .errors import VoiceError
from .notes import EPISODE_PREFIX, SOFTWARE_DEFAULTS

PREVIEW = 90  # s, as in the README's first check
REPO = "https://github.com/seetee/kuliss"
ART = Path(__file__).parent / "art"
KEY = Qt.ItemDataRole.UserRole  # a tree item's step key, or a folder tree item's path
Work = Callable[[Callable[[int, int], None]], tuple[list[str], Path | None]]
MESSAGE = {  # inline message colours (KDE HIG): background, border; text is always dark
    "info": ("#dbe9f7", "#3daee9"),
    "positive": ("#dcf2e3", "#27ae60"),
    "warning": ("#fbeacc", "#f67400"),
    "error": ("#f7d7d9", "#da4453"),
}


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


def message(text: str, kind: str = "warning") -> QLabel:
    """An inline message bar, for a problem on the step it concerns."""
    label = rich(text)
    background, border = MESSAGE[kind]
    label.setStyleSheet(
        f"QLabel {{ background: {background}; color: #232627; border-left: 4px solid {border};"
        " padding: 6px; }"
    )
    return label


def art(name: str) -> QSvgWidget:
    picture = QSvgWidget(str(ART / name))
    picture.setFixedSize(picture.renderer().defaultSize())
    return picture


class Roomy(QStyledItemDelegate):
    """Rows with some air: the default ones are tight."""

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(size.height() + 10)
        return size


def roomy(view: QAbstractItemView) -> None:
    view.setItemDelegate(Roomy(view))


def fit(view: QAbstractItemView, rows: int) -> None:
    """No inner scrollbars: the page scrolls, not the list."""
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    if isinstance(view, QTreeWidget):
        header, body = view.header(), rows * max(view.sizeHintForRow(0), 18)
    else:
        view.resizeRowsToContents()
        header, body = view.horizontalHeader(), view.verticalHeader().length()
    view.setFixedHeight(header.sizeHint().height() + body + 2 * view.frameWidth())


def table(headers: list[str], rows: list[list[str]], note=False) -> QTableWidget:
    """A read-only list. `note`: the last column takes the rest of the width, its long
    texts cut short with the whole text as a tooltip."""
    view = QTableWidget(len(rows), len(headers))
    view.setHorizontalHeaderLabels(headers)
    view.verticalHeader().hide()
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setWordWrap(False)
    roomy(view)
    for r, cells in enumerate(rows):
        for c, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            view.setItem(r, c, item)
    view.resizeColumnsToContents()
    if note:
        view.horizontalHeader().setStretchLastSection(True)
    else:  # as wide as its columns, not the page
        width = view.horizontalHeader().length() + 2 * view.frameWidth()
        view.setMaximumWidth(width)
    fit(view, len(rows))
    return view


def mark(done: bool) -> str:
    return "✓" if done else "○"


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
        self.setWindowTitle("New session")
        form = QFormLayout(self)
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Recording date", self.date)
        self.number = QSpinBox()
        self.number.setRange(1, 9999)
        self.number.setValue(number)
        form.addRow("Session number", self.number)
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

    def answers(self) -> tuple[str, int, list[str]]:
        lines = [line.rstrip() for line in self.software.toPlainText().splitlines()]
        date = self.date.date().toString("yyyy-MM-dd")
        return date, self.number.value(), [line for line in lines if line]


class Window(QMainWindow):
    def __init__(self, start: Path):
        super().__init__()
        self.settings = QSettings("kuliss", "kuliss")
        self.job: Job | None = None
        self.job_key: str | None = None  # the step the running command belongs to
        self.outputs: dict[str, list[str]] = {}  # each step's command output, this session
        self.session: Path | None = None
        self.s: steps.State | None = None
        self.selected: str | None = None  # the step on show, kept across refreshes
        self.root = start

        self.title = QLabel()
        self.done = QLabel()
        choose = QPushButton("Choose session…")
        choose.clicked.connect(self.choose)
        top = QHBoxLayout()
        top.addWidget(self.title, 1)
        top.addWidget(self.done)
        top.addWidget(choose)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(18)
        roomy(self.tree)
        self.tree.currentItemChanged.connect(
            lambda item, _: item and self.show_page(item.data(0, KEY))
        )
        self.links = rich("")
        self.links.setAlignment(Qt.AlignmentFlag.AlignTop)
        left = QWidget()
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.addWidget(self.tree, 1)
        left_box.addWidget(self.links)
        self.page = QScrollArea()
        self.page.setWidgetResizable(True)
        middle = QSplitter()
        middle.addWidget(left)
        middle.addWidget(self.page)
        middle.setStretchFactor(1, 1)
        middle.setSizes([260, 740])

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
        self.resize(1100, 780)

        self.bridge = LogBridge()
        self.bridge.line.connect(self.say)
        self.handler = LogHandler(self.bridge)
        logging.getLogger().addHandler(self.handler)
        self.open(start)

    # ── session ──────────────────────────────────────────────────────────────

    def open(self, start: Path) -> None:
        found = steps.pick_session(start)
        if found != self.session:
            self.selected, self.outputs = None, {}
        self.session = found
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
            session_date, number, software = dialog.answers()
            made = scaffold.scaffold_session(root, number, session_date, software)
        except VoiceError as e:
            self.error(str(e))
            return
        self.say("\n".join(steps.new_report(made)))
        self.open(made.dir)

    # ── the step tree ────────────────────────────────────────────────────────

    def refresh(self) -> None:
        if self.job:  # a command is writing; its end refreshes
            return
        if self.session and not self.session.is_dir():  # moved away, e.g. to the archive
            self.open(self.root if self.root.is_dir() else Path.home())
            return
        s = self.s = steps.state(self.session) if self.session else None
        self.tree.blockSignals(True)
        self.tree.clear()
        if s is None:
            self.setWindowTitle("kuliss")
            self.title.setText(f"<b>No session_* folder in {escape(str(self.root))}</b>")
            self.done.setText("")
            self._item(self.tree, "session", False, "1  Session folder")
            current = "session"
        else:
            self.setWindowTitle(f"kuliss – {s.session.name}")
            self.title.setText(f"<big><b>{escape(s.session.name)}</b></big>")
            current = self._fill_tree(s)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        keys = {
            self.tree.topLevelItem(i).data(0, KEY) for i in range(self.tree.topLevelItemCount())
        }
        keys |= {key for key, _ in self._children()}
        if self.selected not in keys:
            self.selected = current
        self._select(self.selected)
        self.links.setText(self._links(s))

    def _item(self, parent, key: str, done: bool, text: str, current=False) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [f"{'▶' if current else mark(done)}  {text}"])
        item.setData(0, KEY, key)
        if current:
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
        if key in self.problems_by_step():
            item.setText(0, item.text(0) + "  ⚠")
        return item

    def _fill_tree(self, s: steps.State) -> str:
        """The tree of steps; returns the first one not done (the current one)."""
        made = [e for e in s.episodes if e.project]
        episodes_done = bool(s.episodes) and all(e.finished for e in s.episodes)
        notes_done = bool(made) and s.notes_current
        order = [
            ("session", True, "1  Session folder"),
            ("recordings", bool(s.recordings), "2  Recordings"),
            ("sync", s.synced, "3  Sync"),
            ("marked", s.marked, "4  Mark the episodes"),
            ("episodes", episodes_done, "5  Edit each episode"),
            ("notes", notes_done, "6  Notes"),
        ]
        current = next((key for key, done, _ in order if not done), "notes")
        if current == "episodes":
            current = next((f"ep:{e.name}" for e in s.episodes if not e.finished), current)
        for key, done, text in order:
            item = self._item(self.tree, key, done, text, key == current)
            if key == "episodes":
                for e in s.episodes:
                    k = f"ep:{e.name}"
                    self._item(item, k, e.finished, e.name, k == current)
        count = sum(done for _, done, _ in order)
        self.done.setText(f"{count} of {len(order)} steps done")
        return current

    def _children(self):
        if not self.s:
            return []
        return [(f"ep:{e.name}", e) for e in self.s.episodes]

    def _select(self, key: str) -> None:
        items = self.tree.findItems("*", Qt.MatchFlag.MatchWildcard | Qt.MatchFlag.MatchRecursive)
        item = next(i for i in items if i.data(0, KEY) == key)
        self.tree.setCurrentItem(item)  # shows its page
        if self.tree.currentItem() is item:
            self.show_page(key)  # already current: currentItemChanged doesn't fire

    def go(self, key: str) -> None:
        self.selected = key
        self._select(key)

    def problems_by_step(self) -> dict[str, list[str]]:
        """Each problem on the step it concerns: an episode's own project, the session
        project (sync and markers), anything else the session folder."""
        found: dict[str, list[str]] = {}
        s = self.s
        if not s:
            return found
        for problem in s.problems:
            episode = next((e for e in s.episodes if e.name in problem), None)
            if episode:
                keys = [f"ep:{episode.name}"]
            elif s.project.name in problem:
                keys = ["sync", "marked"]
            else:
                keys = ["session"]
            for key in keys:
                found.setdefault(key, []).append(problem)
        return found

    # ── the pages ────────────────────────────────────────────────────────────

    def show_page(self, key: str) -> None:
        self.selected = key
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.setSpacing(10)
        s = self.s
        if s is None:
            self._no_session(box)
        elif key.startswith("ep:"):
            self._episode_page(box, s, next(e for e in s.episodes if f"ep:{e.name}" == key))
        else:
            getattr(self, f"_{key}_page")(box, s)
        for problem in self.problems_by_step().get(key, []):
            box.addWidget(message(escape(problem), "error"))
        if self.outputs.get(key):
            box.addWidget(QLabel("<b>Output</b>"))
            out = QPlainTextEdit("\n".join(self.outputs[key]))
            out.setReadOnly(True)
            out.setMinimumHeight(140)
            box.addWidget(out)
        box.addStretch(1)
        self.page.setWidget(widget)

    def _heading(self, box: QVBoxLayout, title: str, goal: str) -> None:
        heading = QLabel(escape(title))
        font = heading.font()
        font.setPointSizeF(font.pointSizeF() * 1.4)
        font.setWeight(QFont.Weight.Bold)
        heading.setFont(font)
        box.addWidget(heading)
        box.addWidget(rich(goal))

    def _buttons(self, box: QVBoxLayout, *specs) -> None:
        row = QHBoxLayout()
        for text, action, enabled in specs:
            button = QPushButton(text)
            button.clicked.connect(action)
            button.setEnabled(enabled)
            row.addWidget(button)
        row.addStretch(1)
        box.addLayout(row)

    def _no_session(self, box: QVBoxLayout) -> None:
        self._heading(
            box,
            "1  Session folder",
            f"There is no session_* folder in {escape(str(self.root))}. Choose one above, or "
            "make the next one here: in a game's folder (e.g. po3/), next to its theme.toml.",
        )
        self._buttons(box, ("New session…", self.new_session, True))

    def _session_page(self, box: QVBoxLayout, s: steps.State) -> None:
        self._heading(
            box,
            "1  Session folder",
            "Every session gets a folder like this one, made by <b>New session…</b>. "
            "Grey lines are missing. Double-click a line to open it.",
        )
        box.addWidget(self._folder_tree(s))
        self._buttons(box, ("New session…", self.new_session, True))

    def _folder_tree(self, s: steps.State) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(["Name", "What it is"])
        roomy(tree)
        tree.itemActivated.connect(
            lambda item, _: (
                item.data(0, KEY)
                and Path(item.data(0, KEY)).exists()
                and QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(0, KEY)))
            )
        )
        count = 0

        def add(parent, path: Path, what: str) -> QTreeWidgetItem:
            nonlocal count
            count += 1
            name = path.name + ("/" if path.is_dir() or not path.suffix else "")
            item = QTreeWidgetItem(parent, [name, what])
            item.setData(0, KEY, str(path))
            if not path.exists():
                item.setText(1, f"{what} (missing)")
                for column in (0, 1):
                    item.setForeground(column, self.palette().placeholderText())
            return item

        game, crew = s.session.parent, s.crew_file
        show = crew.parent.parent
        top = (
            add(tree, show, "the show: every game, and the _assets/ they share")
            if game.parent == show
            else None
        )
        if top:
            assets = add(top, crew.parent, "shared by every game: avatars, sounds, the crew file")
            add(assets, crew, "crew file: mixer levels, game software, where the archive is")
        else:
            add(tree, crew, "crew file: mixer levels, game software, where the archive is")
        g = add(top or tree, game, "the game: its sessions and its theme")
        add(g, s.theme or game / "theme.toml", "the game's look: avatars, overlay, intro and outro")
        session = add(g, s.session, "this session: one recording, cut into episodes")
        n = len(s.recordings)
        add(
            session,
            s.session / "sources",
            f"everyone's recordings ({n}), synced onto the session project",
        )
        add(session, s.session / "kortisar", "shorts and TikToks cut from this session")
        folders = sorted(
            d for d in s.session.iterdir() if d.is_dir() and d.name.startswith(EPISODE_PREFIX)
        )
        for folder in folders:
            episode = next((e for e in s.episodes if e.name == folder.name), None)
            if folder.name.startswith(f"{EPISODE_PREFIX}XX"):
                what = "placeholder: rename it to the first episode, e.g. avsnitt230"
            elif episode and episode.start is not None:
                what = f"episode, from {steps.clock(episode.start, s.fps)} in the session project"
            else:
                what = "episode folder (no marker for it in the session project)"
            item = add(session, folder, what)
            if episode and episode.project:
                state = "finished by kuliss" if episode.finished else "not finished by kuliss yet"
                add(item, episode.project, f"the episode's own edit, {state}")
        add(session, s.md, "notes: titles, chapters and the checklist for YouTube")
        add(session, s.project, "session project: every recording in sync, a marker per episode")
        tree.expandAll()
        tree.resizeColumnToContents(0)
        fit(tree, count)
        return tree

    def _recordings_page(self, box: QVBoxLayout, s: steps.State) -> None:
        self._heading(
            box,
            "2  Recordings",
            f"Copy everyone's OBS recording into {link(s.session / 'sources', 'sources/')}, "
            "named &lt;date&gt;_&lt;initial&gt;.mkv (a guest: &lt;date&gt;_&lt;name&gt;.mkv). "
            "Sync uses the streams titled Voice audio, Comms and Game audio, and the video.",
        )
        rows = steps.recordings(s.session)
        if not rows:
            box.addWidget(message("No recordings in sources/ yet.", "info"))
            return
        cells = [
            [
                r.file,
                r.player or "?",
                *(mark(t in r.streams) for t in ("Voice audio", "Comms", "Game audio", "video")),
                steps.clock(round(r.seconds * 100), 100) if r.seconds else "",
                r.note,
            ]
            for r in rows
        ]
        headers = ["File", "Player", "Voice", "Comms", "Game", "Video", "Length", "Note"]
        box.addWidget(table(headers, cells, note=True))

    def _sync_page(self, box: QVBoxLayout, s: steps.State) -> None:
        self._heading(
            box,
            "3  Sync",
            f"Puts every recording on {link(s.project, 'the session project')}, lined up "
            "on the call audio.<ol><li>Voice clips are grouped, and each game video with "
            "its game audio; every track is slimmed down.</li><li>Then listen in Kdenlive "
            "that the voices line up.</li></ol>Synced by hand? This step is done as soon as "
            "the session project has clips.",
        )
        if s.synced:
            box.addWidget(message("The session project has clips: synced.", "positive"))
        elif not s.recordings:
            box.addWidget(message("Add the recordings first (step 2).", "info"))
        else:
            for r in steps.recordings(s.session):
                if r.note:
                    box.addWidget(message(f"{escape(r.file)}: {escape(r.note)}"))
        self._buttons(
            box, ("Sync", lambda: self.sync(s.session), bool(s.recordings) and not s.synced)
        )

    def _marked_page(self, box: QVBoxLayout, s: steps.State) -> None:
        self._heading(
            box,
            "4  Mark the episodes",
            f"In {link(s.project, 'the session project')}, add a marker where each episode "
            "starts, named after it: avsnitt230, avsnitt231, … Put the playhead there and "
            "press <b>[G]</b> to add a marker (or remove the one under it), then name it.",
        )
        box.addWidget(art("markers.svg"))
        box.addWidget(
            rich(
                "<ol><li>Look about 20 minutes ahead, then for a joke or a natural break: "
                "20–25 minutes each, or what the flow needs.</li><li>From now on the session "
                "project is the single source of truth: fix sound and episode borders "
                "there.</li></ol>"
            )
        )
        marked = [e for e in s.episodes if e.start is not None]
        if marked:
            box.addWidget(
                table(
                    ["Episode", "Starts at"],
                    [[e.name, steps.clock(e.start, s.fps)] for e in marked],
                )
            )
        else:
            box.addWidget(message("No markers named avsnitt… in the session project yet.", "info"))

    def _episodes_page(self, box: QVBoxLayout, s: steps.State) -> None:
        self._heading(
            box,
            "5  Edit each episode",
            "This is the part kuliss can't do for you: turning one stretch of the session "
            "into an episode. Take one episode at a time, in order, through 5a–5d; kuliss "
            "takes over at 5c. Double-click an episode for its page, with its buttons.",
        )
        if not s.episodes:
            box.addWidget(message("Episodes show up here once marked (step 4).", "info"))
        else:
            rows = [
                [
                    e.name,
                    steps.clock(e.start, s.fps) if e.start is not None else "no marker",
                    e.project.name if e.project else "not made yet",
                    mark(e.finished),
                ]
                for e in s.episodes
            ]
            view = table(["Episode", "Starts at", "5a  Its project", "5c  Finished"], rows)
            view.cellDoubleClicked.connect(lambda r, _: self.go(f"ep:{s.episodes[r].name}"))
            box.addWidget(view)
        self._substeps(box, s, None)

    def _episode_page(self, box: QVBoxLayout, s: steps.State, e: steps.Episode) -> None:
        where = (
            f"Starts at {steps.clock(e.start, s.fps)} in the session project."
            if e.start is not None
            else "Has no marker in the session project."
        )
        project = link(e.project, f"Open {e.project.name}") if e.project else ""
        self._heading(box, f"5  {e.name}", f"{where} {project}")
        if not e.project:
            box.addWidget(message(f"No {escape(e.name)}.kdenlive yet: start with 5a.", "info"))
        self._substeps(box, s, e)

    def _substeps(self, box: QVBoxLayout, s: steps.State, e: steps.Episode | None) -> None:
        """5a–5d, the same on step 5's page and on each episode's (with its name, its
        status and the Finish buttons)."""
        name = e.name if e else "avsnitt230"
        has = bool(e and e.project)

        def part(label: str, title: str, html: str, done: bool | None = None) -> None:
            status = "" if e is None or done is None else f"{mark(done)}  "
            heading = QLabel(f"<b>{status}{label}  {escape(title)}</b>")
            font = heading.font()
            font.setPointSizeF(font.pointSizeF() * 1.15)
            heading.setFont(font)
            box.addSpacing(8)
            box.addWidget(heading)
            box.addWidget(rich(html))

        part(
            "5a",
            "Make the episode's project",
            "<ol>"
            f"<li>Rename the avsnittXX… placeholder folder to <b>{name}</b>. For the next "
            "episodes, make a new folder with the number one up.</li>"
            "<li>In the session project, use <i>Copy to…</i> and save the copy in that "
            f"folder as <b>{name}.kdenlive</b>.</li>"
            "<li><b>Open the copy.</b> Important: from here on you edit the copy; the session "
            "project stays whole, as the single source of truth.</li>"
            "<li>Cut at this episode's marker and at the next one, and delete everything "
            "before and after.</li>"
            "<li>Delete what the episode doesn't use: the Comms tracks, and anything else "
            "only the session needs.</li>"
            "</ol>",
            has,
        )
        box.addWidget(art("copy.svg"))
        part(
            "5b",
            "Choose the views",
            "<ol>"
            "<li>Show the Project Monitor on your second screen: <b>Monitor → Switch Monitor "
            "Fullscreen [F11]</b>. Then <b>Monitor → Multitrack view [F12]</b> shows the "
            "players' game videos side by side. Hide Assets and the other tracks "
            "meanwhile.</li>"
            "<li>Go through the episode and choose whose view is shown; cut away the other "
            "game videos there.</li>"
            "<li>Cut between words or sentences when you can, and switch to someone a moment "
            "before or after they start talking about something new.</li>"
            "<li>Done when exactly one view is left all through the episode. Only one view "
            "in this game (one plays, the others comment)? Nothing to do here.</li>"
            "<li>Jot good moments in Kdenlive's Document Notes as you go. A * right after "
            "the timestamp makes it a YouTube chapter.</li>"
            "</ol>",
        )
        box.addWidget(art("views.svg"))
        part(
            "5c",
            "Finish (kuliss)",
            "What used to be done by hand: the intro and outro, picture and sound, ducked "
            "under the first and last voice; a swoosh at every switch of view; and the name "
            "tag showing whose view it is, for as long as it is shown. <i>Analyse</i> only "
            f"counts the switches; <i>Preview {PREVIEW} s</i> renders the start to look at. "
            "Run Finish again after any change to the edit, then reopen the project in "
            "Kdenlive without saving it first.",
            bool(e and e.finished),
        )
        if e:
            self._buttons(
                box,
                ("Analyse", lambda: self.finish(e.project, "analyse"), has),
                (f"Preview {PREVIEW} s", lambda: self.finish(e.project, "preview"), has),
                ("Finish", lambda: self.finish(e.project, "finish"), has),
            )
        part(
            "5d",
            "Render",
            "Render the episode in Kdenlive. Then on to the next episode, back to 5a. When "
            "every episode is done: step 6, Notes.",
        )

    def _notes_page(self, box: QVBoxLayout, s: steps.State) -> None:
        self._heading(
            box,
            "6  Notes",
            f"Gathers every episode's Document Notes into {link(s.md, 'the notes file')}: "
            "chapters, Bryggpromenader, the checklist. Then fill in the Titel and the other "
            "fields there. Dry run shows what would change.",
        )
        made = [e for e in s.episodes if e.project]
        if not made:
            box.addWidget(message("No episode projects yet (step 5).", "info"))
        elif s.notes_current:
            box.addWidget(
                message("The notes file is newer than every episode project.", "positive")
            )
        self._buttons(
            box,
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
                link(s.crew_file, "Crew file"),
                link(s.crew_file.parent, "_assets/ folder"),
            ]
            mine = [
                link(s.session, "Folder"),
                link(s.md, "Notes file (.md)"),
                link(s.project, "Session project"),
            ]
            html += "<b>This session</b><br>" + "<br>".join(mine) + "<br><br>"
            html += "<b>Every session</b><br>" + "<br>".join(show) + "<br><br>"
        return html + f'<a href="{REPO}#readme">README</a>'

    # ── running commands ─────────────────────────────────────────────────────

    def sync(self, session: Path) -> None:
        def work(progress):
            from . import session as sync_mod

            return steps.sync_report(sync_mod.sync_session(session)), None

        self.start("sync", "Sync", work)

    def notes(self, session: Path, dry_run: bool) -> None:
        def work(progress):
            from . import notes

            return notes.process_session(session, dry_run=dry_run).lines, None

        self.start("notes", "Notes (dry run)" if dry_run else "Notes", work)

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
                return lines + [steps.preview_report(overlay)], overlay
            backup = finish.apply(analysis, overlay)
            return lines + [steps.updated_report(project, backup)], None

        name = project.parent.name
        self.start(f"ep:{name}", f"{mode.capitalize()} {name}", work)

    def start(self, key: str, title: str, work: Work) -> None:
        self.job_key = key
        self.outputs[key] = []  # this run's output replaces the last one's
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
        self.job = self.job_key = None
        self.bar.hide()
        self.centralWidget().setEnabled(True)
        self.refresh()

    # ── output ───────────────────────────────────────────────────────────────

    def say(self, text: str) -> None:
        """Into the log (the whole history) and, during a command, its step's output."""
        if self.job_key:
            self.outputs[self.job_key].append(text)
        if not self.log_opened and not self.job_key:  # the step's page shows its output
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
