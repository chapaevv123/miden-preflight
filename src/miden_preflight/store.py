from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoreAssessment:
    status: str
    reason: str
    private_notes: bool
    export_plan: bool


def assess(config: dict) -> StoreAssessment:
    store = config.get("store", {}) if isinstance(config, dict) else {}
    kind = str(store.get("kind", "")).lower()
    version = str(store.get("source_version", ""))
    private = bool(store.get("private_notes", False))
    export = bool(store.get("export_plan", False) or store.get("recovery_tested", False))
    if not kind:
        return StoreAssessment("UNKNOWN", "No store declaration was provided.", private, export)
    if kind not in {"sqlite", "indexeddb", "memory", "none"}:
        return StoreAssessment("UNKNOWN", f"Unrecognized store kind: {kind}.", private, export)
    if kind in {"memory", "none"}:
        return StoreAssessment("SAFE", "No persistent pre-v0.16 client store is declared.", private, export)
    match = __import__("re").match(r"(\d+)\.(\d+)", version)
    if not match:
        return StoreAssessment("UNKNOWN", "Persistent store source_version is not declared.", private, export)
    if (int(match.group(1)), int(match.group(2))) < (0, 16):
        if private and not export:
            return StoreAssessment("EXPORT_REQUIRED", "Private-note recovery/export must precede recreation.", private, export)
        return StoreAssessment("RECREATE_REQUIRED", "Pre-v0.16 persistent stores are not migrated in place.", private, export)
    return StoreAssessment("SAFE", "Store is declared as originating on v0.16 or later.", private, export)
