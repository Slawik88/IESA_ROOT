#!/usr/bin/env python3
"""Stop risky Django migrations before they reach prod (master = deploy, `migrate` runs on start).

A NEW migration is refused when it contains an operation that can lose data or break the running
old code during the deploy:

    RunSQL                       raw SQL: nobody reviewed what it does to prod data
    RemoveField / DeleteModel    drops a column / table (data gone; old instances still query it)
    RenameField / RenameModel    old code still running during the rollout uses the old name

…unless the file carries a deliberate marker with a reason, anywhere in it:

    # migration-safe: column unused since 0031, backed up in the release notes

Usage:  python IESA_ROOT/scripts/check_migration_safety.py <migration.py> [...]
Exit 1 with a report when something is unmarked; 0 otherwise. Used by the pre-push hook for the
migrations added in the push (`git diff --diff-filter=A origin/master...HEAD -- '*/migrations/*.py'`).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

RISKY = {
    "RunSQL": "raw SQL",
    "RemoveField": "drops a column",
    "DeleteModel": "drops a table",
    "RenameField": "renames a column",
    "RenameModel": "renames a table",
}
MARKER = re.compile(r"#[ \t]*migration-safe:[ \t]*\S")


def risky_operations(source: str) -> list[tuple[int, str, str]]:
    """(line, operation, detail) for every risky call in the module."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else None
        if name not in RISKY:
            continue
        bits = [f"{k.arg}={k.value.value}" for k in node.keywords
                if k.arg in ("model_name", "name", "old_name", "new_name") and isinstance(k.value, ast.Constant)]
        found.append((node.lineno, name, RISKY[name] + (f" ({', '.join(bits)})" if bits else "")))
    return sorted(found)


def check(paths: list[str]) -> list[str]:
    problems = []
    for p in paths:
        path = Path(p)
        if not path.exists() or path.name == "__init__.py" or "migrations" not in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if MARKER.search(source):
            continue
        for line, op, detail in risky_operations(source):
            problems.append(f"{p}:{line}: {op}: {detail}")
    return problems


def main(argv: list[str]) -> int:
    problems = check(argv)
    if not problems:
        return 0
    sys.stderr.write(
        "RISKY MIGRATION (data loss / breaks old code during the deploy):\n  " + "\n  ".join(problems) +
        "\n\nIf it is intended: back up or make it two-step (stop using the field first, drop it in a later release),"
        "\nthen add a line with the reason to the migration file:\n    # migration-safe: <why this is fine>\n")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
