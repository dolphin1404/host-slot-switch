from __future__ import annotations

import unicodedata


def terminal_safe(value: object) -> str:
    """Escape terminal controls and Unicode formatting controls in plain output."""
    result: list[str] = []
    for character in str(value):
        if unicodedata.category(character).startswith("C"):
            codepoint = ord(character)
            escape = "x" if codepoint <= 0xFF else "u"
            width = 2 if escape == "x" else 4
            result.append(f"\\{escape}{codepoint:0{width}x}")
        else:
            result.append(character)
    return "".join(result)
