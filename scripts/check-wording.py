#!/usr/bin/env python3
"""Wording lint (issue #32): brand name (G2) and claim wording (G3).

Scans *.md, *.json, *.txt, *.html under concept/, content/, pitch/ and README.md.
Exit code 1 if any hit is found. Stdlib only.

Rule G2 (brand): the brand is written ЛАССАРД / LASSARD. Errors:
  - "Лассард", "Лассарда", "Lassard" (any case other than the two forms above);
  - ЛАССАРД with a lowercase ending ("ЛАССАРДа");
  - ЛАССАРД / LASSARD inside quotes («ЛАССАРД», "LASSARD").
  URLs, file paths and path-like `code spans` are ignored (lassard.ru, lassard_facts.md).
Rule G3 (claims): "100 %", "самый" (and forms), "лучший" (and forms), "№ 1",
  "лидер рынка", "30 видов станков".

For .json the check runs on string values (the number is the value index), except
values under the key "case" (a quote of the case); for .html on text without tags,
<style> and <script>. A G3 word in short quotes («100 %», "лучший") is a mention, not a claim.

Exception: a line that has the marker <!-- case-quote --> is skipped. Use it for
a quote from the case or for a claim that is explained on the same line.
G1/G14/T8 numeric source checks belong to scripts/check-content.py (issue #18).
"""
import json
import re
import sys
from pathlib import Path

MARKER = "<!-- case-quote -->"
ROOTS = ["concept", "content", "pitch", "README.md"]
EXTS = {".md", ".json", ".txt", ".html"}

# Remove URLs, markdown link targets, path-like code spans and path-like lassard tokens.
STRIP = re.compile(
    r"(?i:https?://\S+)|\]\([^)]*\)"
    r"|`[A-Za-z0-9./_-]+`"
    r"|[\w./-]*(?:lassard[-./_]\w|[-./_]lassard)[\w./-]*"
)
TAG = re.compile(r"<[^>]*>")
CODE_BLOCK = re.compile(r"<(style|script)\b.*?</\1>", re.S | re.I)
# A quoted span that holds only a G3 wording («100 %», "лучший") mentions it, not claims it.
QUOTED = re.compile(r"«([^«»]{1,60})»|\"([^\"]{1,60})\"|“([^“”]{1,60})”")
# «самый удалённый» is a normative fire-safety term (СП 1.13130), not a claim: exempt.
ADJ = r"(?!удал[её]нн)\w*(?:ый|ий|ой|ая|яя|ое|ее|ые|ие|ого|его|ому|ему|ым|им|ую|юю|ых|их|ыми|ими|ом|ем)"

BRAND = [
    ("brand: write ЛАССАРД / LASSARD", re.compile(r"Лассард\w*|Lassard\w*|(?<!\w)lassard(?!\w)")),
    ("brand: no lowercase ending after ЛАССАРД", re.compile(r"ЛАССАРД[-’'ʼ]?[а-яё]+")),
    ("brand: name in quotes", re.compile(r"[«\"“'„](?:ЛАССАРД|LASSARD)[»\"”'“]")),
]
CLAIMS = [
    ("claim: 100 %", re.compile(r"(?<!\w)100[\s  ]?%")),
    ("claim: superlative «самый»",
     re.compile(r"(?<!\w)сам(?:ый|ая|ое|ые|ого|ой|ому|ым|ых|ую|ыми|ом)"
                r"(?:[-–—]сам(?:ый|ая|ое|ые|ого|ой|ому|ым|ых|ую|ыми|ом)(?!\w)|\s+"
                + ADJ + r"(?!\w))", re.I)),
    ("claim: «лучший»",
     re.compile(r"(?<!\w)(?:наи)?лучш(?:ий|ая|ее|ие|его|ему|им|их|ую|ей|ем|ими)(?!\w)", re.I)),
    ("claim: «№ 1»", re.compile(r"№[\s ]?1(?!\d)")),
    ("claim: «лидер рынка»", re.compile(r"лидер\w*\s+рынка", re.I)),
    ("claim: «30 видов станков»", re.compile(r"(?<!\w)30\+?\s+видов\s+станков", re.I)),
]


def is_mention(quoted: str) -> bool:
    """True if the quoted text is one G3 wording alone, optionally after «более»."""
    core = re.sub(r"^более\s+", "", quoted.strip(), flags=re.I)
    return any(rx.fullmatch(core) for _, rx in CLAIMS)


def check_line(line: str) -> list[str]:
    """Return rule names broken by one line of plain text. Empty list means clean."""
    if MARKER in line:
        return []
    text = STRIP.sub(" ", line).replace("_", " ")
    claims_text = QUOTED.sub(lambda m: " " if is_mention(next(g for g in m.groups() if g)) else m.group(0), text)
    return ([name for name, rx in BRAND if rx.search(text)]
            + [name for name, rx in CLAIMS if rx.search(claims_text)])


def json_strings(node, skip_case: bool):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            if not (skip_case and k == "case"):
                yield from json_strings(v, skip_case)
    elif isinstance(node, list):
        for v in node:
            yield from json_strings(v, skip_case)


def text_lines(f: Path):
    """Yield (line number, text) to check. JSON: string values. HTML: text without tags."""
    raw = f.read_text(encoding="utf-8")
    if f.suffix == ".json":
        # "case" in facts.json is a quote of the case, not our wording.
        for i, v in enumerate(json_strings(json.loads(raw), f.name == "facts.json"), 1):
            yield i, v
        return
    if f.suffix == ".html":
        # Blank out CSS and JS, keep line numbers.
        raw = CODE_BLOCK.sub(lambda m: "\n" * m.group(0).count("\n"), raw)
    for n, line in enumerate(raw.splitlines(), 1):
        if f.suffix != ".html":
            yield n, line
        elif MARKER in line:  # TAG.sub would remove the marker
            yield n, ""
        else:
            yield n, TAG.sub(" ", line)


def files(base: Path):
    for root in ROOTS:
        p = base / root
        if p.is_file():
            yield p
        elif p.is_dir():
            yield from (f for f in sorted(p.rglob("*")) if f.is_file() and f.suffix in EXTS)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    base = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    hits = 0
    for f in files(base):
        for n, line in text_lines(f):
            for rule in check_line(line):
                print(f"{f.relative_to(base).as_posix()}:{n}: {rule}: {line.strip()[:100]}")
                hits += 1
    print(f"check-wording: {hits} hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
