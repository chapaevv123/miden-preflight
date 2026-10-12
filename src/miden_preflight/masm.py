from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


DECL = re.compile(r"(?m)^\s*(?:pub\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:;|$)")


@dataclass(frozen=True)
class MasmProblem:
    kind: str
    path: Path
    line: int | None
    detail: str


def _ignored(path: Path) -> bool:
    return any(part in {"target", "node_modules", ".git", "dist", "build", "vendor"} for part in path.parts)


def _resolve(parent: Path, name: str) -> Path | None:
    candidates = (parent / f"{name}.masm", parent / name / "mod.masm")
    return next((p for p in candidates if p.exists()), None)


def inspect(root: Path) -> list[MasmProblem]:
    files = {p.resolve() for p in root.rglob("*.masm") if not _ignored(p.relative_to(root))}
    roots = sorted(p for p in files if p.name in {"lib.masm", "mod.masm"})
    # Nested mod.masm files are children, not independent package roots.
    roots = [p for p in roots if p.name == "lib.masm" or not any(q.parent in p.parents for q in roots if q != p)]
    if not roots:
        return []
    reachable: set[Path] = set()
    missing: list[MasmProblem] = []
    queue = list(roots)
    while queue:
        source = queue.pop()
        if source in reachable:
            continue
        reachable.add(source)
        text = source.read_text(encoding="utf-8", errors="replace")
        for match in DECL.finditer(text):
            child = _resolve(source.parent, match.group(1))
            if child is None:
                missing.append(MasmProblem("missing", source, text.count("\n", 0, match.start()) + 1,
                                           f"module `{match.group(1)}` has no resolvable source"))
            elif child.resolve() not in reachable:
                queue.append(child.resolve())
    # A repository may also contain independent compiler fixtures, binary
    # entrypoints, or Rust-embedded component sources. An explicit module root
    # establishes authority only over its own directory tree; files elsewhere
    # cannot be proven unreachable from that root.
    scoped_files = {
        p for p in files if any(root_file.parent in p.parents for root_file in roots)
    }
    unreachable = [MasmProblem("unreachable", p, None, "not reachable from an explicit MASM root")
                   for p in sorted(scoped_files - reachable) if p.name != "mod.masm"]
    return missing + unreachable
