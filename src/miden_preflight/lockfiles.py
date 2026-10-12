from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Resolution:
    package: str
    version: str
    source: Path


def cargo_lock(path: Path) -> list[Resolution]:
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [Resolution(str(p["name"]), str(p["version"]), path)
            for p in data.get("package", []) if str(p.get("name", "")).startswith("miden-")]


def package_lock(path: Path) -> list[Resolution]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for key, value in data.get("packages", {}).items():
        match = re.search(r"node_modules/(@miden-sdk/[^/]+)$", key)
        if match and isinstance(value, dict) and value.get("version"):
            found[match.group(1)] = str(value["version"])
    for name, value in data.get("dependencies", {}).items():
        if name.startswith("@miden-sdk/") and isinstance(value, dict) and value.get("version"):
            found.setdefault(name, str(value["version"]))
    return [Resolution(k, v, path) for k, v in sorted(found.items())]


def pnpm_lock(path: Path) -> list[Resolution]:
    if not path.exists():
        return []
    found: dict[str, str] = {}
    # Supports pnpm v6-v9 package/importer forms without requiring a YAML dependency.
    patterns = (
        r"^\s{2,}['\"]?@miden-sdk/([^'\":]+)@([^:'\"(\s]+)",
        r"^\s{4,}['\"]?@miden-sdk/([^'\":]+)['\"]?:\s*$\n(?:\s+.*\n){0,5}?\s+version:\s*['\"]?([^'\"\s(]+)",
    )
    text = path.read_text(encoding="utf-8", errors="replace")
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.MULTILINE):
            found[f"@miden-sdk/{match.group(1)}"] = match.group(2)
    return [Resolution(k, v, path) for k, v in sorted(found.items())]


def yarn_lock(path: Path) -> list[Resolution]:
    if not path.exists():
        return []
    found: dict[str, str] = {}
    current: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            current = re.findall(r"(@miden-sdk/[\w.-]+)@", line)
        elif current and re.match(r"\s+version\s+", line):
            version = line.split(None, 1)[1].strip(" \"'")
            for name in current:
                found[name] = version
            current = []
    return [Resolution(k, v, path) for k, v in sorted(found.items())]


def all_resolutions(root: Path) -> list[Resolution]:
    result = cargo_lock(root / "Cargo.lock")
    result += package_lock(root / "package-lock.json")
    result += pnpm_lock(root / "pnpm-lock.yaml")
    result += yarn_lock(root / "yarn.lock")
    return result
