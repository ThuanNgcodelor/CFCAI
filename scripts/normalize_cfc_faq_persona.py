from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/sources/cfc/faq/CFC_Co_Bay_FAQ.md"

REPLACEMENTS = (
    (re.compile(r"\bchúng tôi\b", re.IGNORECASE), "bên em"),
    (re.compile(r"\badmin\b", re.IGNORECASE), "nhân viên phụ trách"),
    (re.compile(r"\bBạn\b"), "Anh/chị"),
    (re.compile(r"\bbạn\b"), "anh/chị"),
)


def normalize_answer(answer: str) -> str:
    for pattern, replacement in REPLACEMENTS:
        answer = pattern.sub(replacement, answer)
    return answer


def normalize_document(document: str) -> str:
    output: list[str] = []
    for line in document.splitlines(keepends=True):
        if not line.lstrip().startswith("|") or line.count("|") < 4:
            output.append(line)
            continue
        newline = "\n" if line.endswith("\n") else ""
        cells = line.rstrip("\n").split("|")
        if len(cells) >= 6 and cells[1].strip().isdigit():
            cells[-2] = normalize_answer(cells[-2])
            line = "|".join(cells) + newline
        output.append(line)
    return "".join(output)


def main() -> None:
    current = SOURCE.read_text(encoding="utf-8")
    normalized = normalize_document(current)
    if normalized != current:
        SOURCE.write_text(normalized, encoding="utf-8")
    print(f"OK: {SOURCE}")


if __name__ == "__main__":
    main()
