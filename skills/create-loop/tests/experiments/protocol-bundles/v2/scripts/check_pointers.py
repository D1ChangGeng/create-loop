#!/usr/bin/env python3
"""Check whether relative Markdown link targets exist on disk."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict
from urllib.parse import unquote

INLINE_LINK_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<!!)\[[^]\n]*\]\(\s*(?P<target><[^>\n]+>|[^\s)\n]+)"
)
REFERENCE_DEFINITION_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s{0,3}\[[^]\n]+\]:\s*(?P<target><[^>\n]+>|\S+)"
)
EXTERNAL_SCHEME_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z][A-Za-z0-9+.-]*:"
)
GENERATED_PROTOCOL_BUNDLES: Final[Path] = Path(
    "tests/experiments/protocol-bundles"
)


@dataclass(frozen=True, slots=True)
class Pointer:
    source: str
    line: int
    target: str

    @property
    def baseline_entry(self) -> str:
        return f"{self.source}:{self.line}:{self.target}"


class JsonEntry(TypedDict):
    source: str
    line: int
    target: str
    status: str


class JsonReport(TypedDict):
    links: int
    dangling: int
    known: int
    excluded_generated_bundle_markdown: int
    entries: list[JsonEntry]


def normalized_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return unquote(target)


def is_relative_file_target(target: str) -> bool:
    if not target or target.startswith("#"):
        return False
    if target.startswith(("http://", "https://", "mailto:")):
        return False
    return EXTERNAL_SCHEME_RE.match(target) is None


def extract_pointers(markdown: Path, root: Path) -> list[Pointer]:
    source = markdown.relative_to(root).as_posix()
    pointers: list[Pointer] = []
    with markdown.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            targets = [match.group("target") for match in INLINE_LINK_RE.finditer(line)]
            definition = REFERENCE_DEFINITION_RE.match(line)
            if definition is not None:
                targets.append(definition.group("target"))
            for raw_target in targets:
                target = normalized_target(raw_target)
                if is_relative_file_target(target):
                    pointers.append(Pointer(source, line_number, target))
    return pointers


def load_baseline(path: Path | None) -> set[str]:
    if path is None:
        return set()
    with path.open("r", encoding="utf-8") as handle:
        return {
            line.strip()
            for line in handle
            if line.strip() and not line.lstrip().startswith("#")
        }


def find_dangling(pointers: list[Pointer], root: Path) -> list[Pointer]:
    dangling: list[Pointer] = []
    for pointer in pointers:
        file_part = pointer.target.partition("#")[0]
        source_dir = (root / pointer.source).parent
        if not (source_dir / file_part).exists():
            dangling.append(pointer)
    return sorted(dangling, key=lambda item: (item.source, item.line, item.target))


def json_report(
    link_count: int,
    dangling: list[Pointer],
    baseline: set[str],
    excluded_generated_bundle_markdown: int,
) -> JsonReport:
    entries: list[JsonEntry] = []
    known_count = 0
    unresolved_count = 0
    for pointer in dangling:
        status = "KNOWN" if pointer.baseline_entry in baseline else "DANGLING"
        if status == "KNOWN":
            known_count += 1
        else:
            unresolved_count += 1
        entries.append(
            {
                "source": pointer.source,
                "line": pointer.line,
                "target": pointer.target,
                "status": status,
            }
        )
    return {
        "links": link_count,
        "dangling": unresolved_count,
        "known": known_count,
        "excluded_generated_bundle_markdown": excluded_generated_bundle_markdown,
        "entries": entries,
    }


def is_generated_protocol_bundle_markdown(markdown: Path, root: Path) -> bool:
    """Keep frozen evaluator bundles outside the live documentation graph.

    Canonical Skill Markdown is pointer-checked before freezing. Generated
    protocol bundles are then authenticated by their bundle manifest and file
    hashes; their historical links to repository-only tests or root documents
    are not installed-documentation pointers and must not be repaired in place.
    """

    relative = markdown.relative_to(root)
    return relative.is_relative_to(GENERATED_PROTOCOL_BUNDLES)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether relative Markdown link targets exist."
    )
    parser.add_argument(
        "--baseline", type=Path, help="File of known dangling source:line:target entries."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    try:
        baseline = load_baseline(args.baseline)
        markdown_files = sorted(root.rglob("*.md"))
        generated_bundle_markdown = [
            markdown
            for markdown in markdown_files
            if is_generated_protocol_bundle_markdown(markdown, root)
        ]
        pointers = [
            pointer
            for markdown in markdown_files
            if markdown not in generated_bundle_markdown
            for pointer in extract_pointers(markdown, root)
        ]
    except (OSError, UnicodeError) as exc:
        print(f"error: could not check Markdown pointers: {exc}", file=sys.stderr)
        return 2

    dangling = find_dangling(pointers, root)
    report = json_report(
        len(pointers),
        dangling,
        baseline,
        len(generated_bundle_markdown),
    )
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        for entry in report["entries"]:
            if entry["status"] == "KNOWN":
                print(
                    f"KNOWN: {entry['source']}:{entry['line']}: {entry['target']}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[POINTER DANGLING] {entry['source']}:{entry['line']}: "
                    f"does not resolve: {entry['target']}",
                    file=sys.stderr,
                )
        if report["dangling"] == 0:
            print(f"POINTERS OK: {report['links']} links, 0 dangling")
        print(
            "POINTERS NOTE: excluded "
            f"{report['excluded_generated_bundle_markdown']} generated protocol-bundle "
            "Markdown files; bundle manifests and hashes validate those snapshots."
        )
    return 1 if report["dangling"] else 0


if __name__ == "__main__":
    sys.exit(main())
