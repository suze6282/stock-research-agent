from __future__ import annotations

import re

_ANSI_CONTROL_SEQUENCE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def normalize_cli_output(value: str) -> str:
    return _ANSI_CONTROL_SEQUENCE.sub("", value)
