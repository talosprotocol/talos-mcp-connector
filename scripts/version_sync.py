from __future__ import annotations

import re
import subprocess
from pathlib import Path

PYPROJECT = Path("pyproject.toml")


def bump_patch(v: str) -> str:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)?$", v)
    if not m:
        raise ValueError(f"Invalid semver: {v}")
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3)) + 1
    suffix = m.group(4) or ""
    return f"{major}.{minor}.{patch}{suffix}"


def main() -> None:
    if not PYPROJECT.exists():
        print("ℹ️  pyproject.toml not found, skipping version sync")
        return

    # Check if pyproject.toml is already staged for commit
    # If so, we assume the version is already handled/bumped to avoid infinite pre-commit loop
    try:
        # Check if file has staged changes
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "pyproject.toml"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()

        if staged == "pyproject.toml":
            print("ℹ️  pyproject.toml has staged changes, skipping auto-bump")
            return
    except FileNotFoundError:
        # git not found or not in git repo, proceed or warn
        pass

    text = PYPROJECT.read_text(encoding="utf-8")
    # Supports common patterns: version = "x.y.z"
    m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"\s*$', text)
    if not m:
        print("ℹ️  version field not found in pyproject.toml")
        return
    old = m.group(1)
    new = bump_patch(old)
    updated = text[: m.start(1)] + new + text[m.end(1) :]
    PYPROJECT.write_text(updated, encoding="utf-8")
    print(f"📦 Version bumped: {old} -> {new}")


if __name__ == "__main__":
    main()
