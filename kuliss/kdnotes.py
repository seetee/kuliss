"""Timestamped notes from a Kdenlive project's Document Notes panel. Stdlib only."""

import re
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

ORPHAN_SECTION = 'Other comments without a home'
_ATTRIBUTION_RE = re.compile(r'\s+-[a-zA-Z]+$')   # a trailing speaker token like ' -h'


class _NotesParser(HTMLParser):
    """Parse Kdenlive Qt-richtext HTML into {section: [(timestamp, text)]}."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections: dict[str, list[tuple[str, str]]] = {}
        self.chapters: list[tuple[str, str]] = []
        self._section: str | None = None
        self._in_a = False
        self._a_text = ''
        self._p_text = ''
        self._timestamp: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag == 'p':
            self._p_text = ''
            self._timestamp = None
        elif tag == 'a':
            self._in_a = True
            self._a_text = ''

    def handle_endtag(self, tag):
        if tag == 'a':
            self._in_a = False
            m = re.search(r'(\d{2}):(\d{2}):(\d{2}):\d+', self._a_text)
            if m:
                h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
                self._timestamp = f'{h:02d}:{mi:02d}:{s:02d}' if h else f'{mi:02d}:{s:02d}'
        elif tag == 'p':
            # Collapse internal whitespace: embedded newlines would otherwise
            # produce lines the merge logic no longer recognizes as managed.
            text = re.sub(r'\s+', ' ', self._p_text).strip()
            if not text:
                return
            m = re.match(r'^#{1,6}\s+(.+)', text)
            if m:
                name = m.group(1).strip()
                self._section = name
                self.sections.setdefault(name, [])
            else:
                # A '*' right after the timestamp flags the note as a chapter.
                if self._timestamp and text.startswith('*'):
                    text = text.lstrip('*').strip()
                    if not text:
                        return
                    self.chapters.append((self._timestamp, _ATTRIBUTION_RE.sub('', text)))
                section = self._section if self._section is not None else ORPHAN_SECTION
                self.sections.setdefault(section, []).append((self._timestamp or '', text))

    def handle_data(self, data):
        if self._in_a:
            self._a_text += data
        else:
            self._p_text += data


def _ts_seconds(ts: str) -> float:
    if not ts:
        return float('inf')  # untimestamped notes sort after timestamped ones
    seconds = 0
    for part in ts.split(':'):
        seconds = seconds * 60 + int(part)
    return seconds


def _extract_project(
    kdenlive_path: Path,
) -> tuple[dict[str, list[tuple[str, str]]], list[tuple[str, str]], str | None]:
    """Return (notes, starred_chapters, kdenlive_version) from a .kdenlive file."""
    root = ET.parse(kdenlive_path).getroot()

    version = None
    vprop = root.find(".//property[@name='kdenlive:docproperties.kdenliveversion']")
    if vprop is not None and vprop.text and vprop.text.strip():
        version = vprop.text.strip()

    notes: dict[str, list[tuple[str, str]]] = {}
    starred: list[tuple[str, str]] = []
    prop = root.find(".//property[@name='kdenlive:documentnotes']")
    if prop is not None and prop.text:
        parser = _NotesParser()
        parser.feed(prop.text)
        notes = {
            section: sorted(entries, key=lambda e: _ts_seconds(e[0]))
            for section, entries in parser.sections.items() if entries
        }
        starred = sorted(parser.chapters, key=lambda c: _ts_seconds(c[0]))
    return notes, starred, version
