"""The session Markdown file as a tree of heading blocks. Untouched blocks
round-trip byte for byte."""

import re
from dataclasses import dataclass, field

_HEADING_RE = re.compile(r'^(#{1,6})\s+(\S.*?)\s*$')


@dataclass(slots=True)
class _Block:
    """A heading and its content: verbatim body lines plus nested sub-blocks."""

    level: int
    title: str
    heading_line: str | None = None
    lines: list[str] = field(default_factory=list)
    children: list['_Block'] = field(default_factory=list)


def _parse(text: str) -> _Block:
    root = _Block(0, '')
    stack = [root]
    for line in text.splitlines(keepends=True):
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            while stack[-1].level >= level:
                stack.pop()
            block = _Block(level, m.group(2), line)
            stack[-1].children.append(block)
            stack.append(block)
        else:
            stack[-1].lines.append(line)
    return root


def _render(block: _Block) -> str:
    parts = []
    if block.heading_line:
        parts.append(block.heading_line)
    parts.extend(block.lines)
    parts.extend(_render(child) for child in block.children)
    return ''.join(parts)


def _new_block(level: int, title: str) -> _Block:
    block = _Block(level, title, f'{"#" * level} {title}\n')
    block.lines = ['\n']
    return block


def _find_block(block: _Block, level: int, title: str) -> _Block | None:
    for child in block.children:
        if child.level == level and child.title == title:
            return child
        found = _find_block(child, level, title)
        if found:
            return found
    return None


def _locate(block: _Block, target: _Block) -> tuple[_Block, int] | None:
    for i, child in enumerate(block.children):
        if child is target:
            return block, i
        found = _locate(child, target)
        if found:
            return found
    return None


def _insert_child(parent: _Block, pos: int, block: _Block) -> None:
    """Insert a child block, ensuring a blank line precedes its heading."""
    if pos == 0:
        if parent.lines and parent.lines[-1].strip() or not parent.lines and parent.heading_line:
            parent.lines.append('\n')
    else:
        prev = parent.children[pos - 1]
        while prev.children:
            prev = prev.children[-1]
        if not prev.lines or prev.lines[-1].strip():
            prev.lines.append('\n')
    parent.children.insert(pos, block)
