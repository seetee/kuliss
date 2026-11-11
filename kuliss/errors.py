"""Expected failures: raised with die(), printed once by the CLI as `ERROR: ...`."""

from typing import NoReturn


class VoiceError(Exception):
    """An expected failure; the CLI prints it as a one-line error."""


def die(msg: str) -> NoReturn:
    raise VoiceError(msg)
