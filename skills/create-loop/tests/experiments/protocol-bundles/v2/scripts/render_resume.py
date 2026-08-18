#!/usr/bin/env python3
"""Render create-loop v2 resume.json atomically from immutable sources."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from project_loop import ProjectionError, project


def write_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("loop_dir", type=Path)
    parser.add_argument("--check", action="store_true", help="Compare with resume.json without writing")
    args = parser.parse_args()
    try:
        projected = project(args.loop_dir)
    except (OSError, ValueError, ProjectionError) as exc:
        print(f"error: {exc}")
        return 1
    target = args.loop_dir / "resume.json"
    if args.check:
        if not target.exists():
            print("error: resume.json is missing")
            return 1
        current = json.loads(target.read_text(encoding="utf-8"))
        current["generated_at"] = projected["generated_at"]
        if current != projected:
            print("error: resume.json is stale")
            return 1
        return 0
    write_atomic(target, projected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
