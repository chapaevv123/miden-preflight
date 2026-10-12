from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Iterable

from .catalog import RULES
from .lockfiles import Resolution, all_resolutions
from .masm import inspect as inspect_masm
from .matrix import TARGET, expected_family
from .models import Finding
from .role_model import infer_project_role
from .store import assess

IGNORED = {".git", "node_modules", "target", "dist", "build", "vendor", ".venv", "__pycache__", "versioned_docs"}
SOURCE_SUFFIXES = {".rs", ".ts", ".tsx", ".js", ".jsx", ".masm", ".md", ".sh", ".ps1", ".yml", ".yaml", ".toml"}


def _version(value: str) -> str | None:
    match = re.search(r"(?<!\d)(\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z.-]+)?)", value)
    return match.group(1) if match else None


def _family(version: str) -> str | None:
    match = re.match(r"(\d+\.\d+)", version)
    return match.group(1) if match else None


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES
                  and not any(part in IGNORED for part in p.relative_to(root).parts))


def _read_config(root: Path) -> dict:
    path = root / "miden-preflight.toml"
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _declared(root: Path) -> dict[str, tuple[str, Path]]:
    found: dict[str, tuple[str, Path]] = {}
    package = root / "package.json"
    if package.exists():
        data = json.loads(package.read_text(encoding="utf-8"))
        for group in ("dependencies", "devDependencies", "peerDependencies"):
            for name, version in data.get(group, {}).items():
                if name.startswith("@miden-sdk/"):
                    found[name] = (str(version), package)
    cargo = root / "Cargo.toml"
    if cargo.exists():
        data = tomllib.loads(cargo.read_text(encoding="utf-8"))
        for group in ("dependencies", "dev-dependencies", "build-dependencies"):
            for name, value in data.get(group, {}).items():
                if name.startswith("miden-"):
                    found[name] = (str(value if isinstance(value, str) else value.get("version", "")), cargo)
    return found


def _miden_evidence(files: list[Path], declared: dict) -> bool:
    return bool(declared or any("miden" in p.read_text(encoding="utf-8", errors="ignore").lower() for p in files[:200]))


def _version_findings(root: Path, declared: dict[str, tuple[str, Path]], resolutions: list[Resolution]) -> list[Finding]:
    out: list[Finding] = []
    resolved_by_name = {r.package: r for r in resolutions}
    effective: list[tuple[str, str, Path, str | None]] = []
    for name, (constraint, manifest) in declared.items():
        resolution = resolved_by_name.get(name)
        if resolution:
            effective.append((name, resolution.version, resolution.source, constraint))
        else:
            exact = _version(constraint)
            # Without a lockfile, only exact pins can establish incompatibility.
            if exact and not any(c in constraint for c in "^~*><|"):
                effective.append((name, exact, manifest, constraint))
    for name, version, path, constraint in effective:
        expected = expected_family(name)
        if expected and _family(version) != expected:
            rid = "MIDEN016-SDK-001" if name.startswith("@miden-sdk/") else "MIDEN016-DEP-001"
            out.append(Finding(RULES[rid], path, None, f"{name} resolves to {version}", constraint, version, expected))
        declared_version = _version(constraint or "")
        if (name.startswith("@miden-sdk/") and declared_version and
                _family(declared_version) != _family(version)):
            out.append(Finding(RULES["MIDEN016-SDK-002"], path, None,
                               f"{name} declares {constraint} but resolves to {version}",
                               constraint, version, _family(declared_version)))
    qualifiers = [(name, version, path) for name, version, path, _ in effective]
    has_rc = any(re.search(r"-(?:rc|beta|alpha)", v, re.I) for _, v, _ in qualifiers)
    has_stable = any(not re.search(r"-(?:rc|beta|alpha)", v, re.I) for _, v, _ in qualifiers)
    if has_rc and has_stable:
        path = next(p for _, _, p in qualifiers)
        out.append(Finding(RULES["MIDEN016-RC-001"], path, None, "resolved graph contains both prerelease and stable Miden artifacts"))
    return out


PATTERNS = {
    "MIDEN016-API-001": re.compile(r"\bwith_auth_component\b"),
    "MIDEN016-API-002": re.compile(r"\.account_delta\s*\("),
    "MIDEN016-PKG-001": re.compile(r"\b(?:link_(?:mast_)?library|KernelLibrary)\b"),
    "MIDEN016-NOTE-001": re.compile(r"\b(?:P2ID|P2IDR|SWAP|PSWAP|RPO_FALCON_512)Note::create\b"),
}


def _source_findings(root: Path, files: list[Path]) -> tuple[list[Finding], str]:
    out: list[Finding] = []
    chunks: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        chunks.append(text)
        for rid, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line_text = text.splitlines()[text.count("\n", 0, match.start())] if text.splitlines() else ""
                # Migration guides commonly retain removed code as a diff
                # deletion. That is evidence about the migration, not a live
                # sample instructing builders to call the removed API.
                if line_text.lstrip().startswith(("//", "#", "-")):
                    continue
                if rid == "MIDEN016-API-002" and "TransactionSummary" in line_text:
                    continue
                out.append(Finding(RULES[rid], path, text.count("\n", 0, match.start()) + 1, match.group(0)))
        # CLI aliases in executable/config files only; README prose is intentionally ignored.
        if path.suffix.lower() in {".sh", ".ps1", ".yml", ".yaml", ".toml"}:
            for match in re.finditer(r"(?m)^\s*(?:run:\s*)?(?:\.\\|\./)?miden\s+send\b", text):
                out.append(Finding(RULES["MIDEN016-CLI-001"], path, text.count("\n", 0, match.start()) + 1, "miden send"))
    return out, "\n".join(chunks)


def _toolchain(root: Path, files: list[Path], combined: str, config: dict, has_miden: bool) -> list[Finding]:
    if not has_miden:
        return []
    candidates = [root / "miden-toolchain.toml", root / "rust-toolchain.toml"]
    candidates += [p for p in files if p.suffix.lower() in {".sh", ".ps1", ".yml", ".yaml"}]
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in candidates if p.exists())
    has_masm = any(p.suffix.lower() == ".masm" for p in files)
    owns_toolchain = bool(
        any(p.exists() for p in candidates[:2])
        or re.search(r"(?<![-\w])(?:miden|midenup)(?:\.exe)?\s+(?:build|compile|install|toolchain|override|update)\b", text, re.I)
        or has_masm
        or (root / "Cargo.toml").exists()
        or "wallet" in root.name.lower()
    )
    # SDK-only applications and documentation sites do not own a Miden
    # toolchain merely because they mention or depend on Miden. This mirrors
    # the Step 2 role boundary; an explicit owned-toolchain signal still wins.
    if not owns_toolchain:
        return []
    target = str(config.get("project", {}).get("target", TARGET))
    explicit_016 = bool(re.search(r"(?:midenup\s+override\s+|channel\s*=\s*['\"]?|version\s*=\s*['\"]?)0\.16(?:\.\d+)?", text))
    out: list[Finding] = []
    if not explicit_016:
        out.append(Finding(RULES["MIDEN016-TOOL-001"], None, None, "no explicit 0.16 pin found"))
    if target == TARGET and (re.search(r"\bdevnet\b", text, re.I) or re.search(r"(?:channel|version)\s*=\s*['\"]?0\.17", text)):
        out.append(Finding(RULES["MIDEN016-TOOL-002"], None, None, "explicit devnet/0.17 configuration conflicts with miden-0.16 target"))
    return out


def scan(root: Path, target: str = TARGET) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    files = _files(root)
    role = infer_project_role(root)
    config = _read_config(root)
    declared = _declared(root)
    resolutions = all_resolutions(root)
    findings = _version_findings(root, declared, resolutions)
    source, combined = _source_findings(root, files)
    findings += source
    has_miden = _miden_evidence(files, declared)
    findings += _toolchain(root, files, combined, config, has_miden)
    for problem in inspect_masm(root):
        rid = "MIDEN016-MASM-002" if problem.kind == "missing" else "MIDEN016-MASM-001"
        findings.append(Finding(RULES[rid], problem.path, problem.line, problem.detail))
    store = assess(config)
    if store.status in {"RECREATE_REQUIRED", "EXPORT_REQUIRED"}:
        findings.append(Finding(RULES["MIDEN016-STORE-001"], root / "miden-preflight.toml", None, store.reason))
    if store.status == "EXPORT_REQUIRED":
        findings.append(Finding(RULES["MIDEN016-STORE-002"], root / "miden-preflight.toml", None, store.reason))
    lowered = combined.lower()
    if re.search(r"TransactionRequestBuilder|executeRequest|new_transaction|newTransaction", combined):
        fee_tokens = ("fee", "tx_fee", "fee_asset")
        if not all(token in lowered for token in fee_tokens):
            findings.append(Finding(RULES["MIDEN016-FEE-001"], None, None, "missing executable evidence for fee, TX_FEE and fee-asset readiness"))
    if re.search(r"TransactionSummary|execute_for_summary|executeForSummary", combined) and "ChainAnchor" not in combined:
        findings.append(Finding(RULES["MIDEN016-ANCHOR-001"], None, None, "summary code found without shared ChainAnchor evidence"))
    if re.search(r"\b(?:guardian|multisig|multi_sig)\b", lowered):
        if not ("ChainAnchor" in combined and "fee" in lowered):
            findings.append(Finding(RULES["MIDEN016-MULTI-001"], None, None, "Guardian/multisig flow lacks fee+anchor conformance evidence"))
    implementation_text = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in files
        if p.name != "miden-preflight.toml"
    ).lower()
    private_declared = bool(config.get("capabilities", {}).get("private_notes", False) or
                            re.search(r"\b(?:private_note|privateNote|PrivateNote)", implementation_text))
    if private_declared:
        required = {"delivery", "block_hint", "incremental_fetch", "sync_progress", "committed_application", "retry", "deduplication"}
        declared_checks = set(config.get("private_note", {}).get("checks", []))
        missing = sorted(required - declared_checks)
        if missing:
            findings.append(Finding(RULES["MIDEN016-PRIVATE-001"], root / "miden-preflight.toml" if config else None,
                                    None, "missing lifecycle proofs: " + ", ".join(missing)))
    findings.sort(key=lambda f: (f.rule.severity.value, f.rule.rule_id, str(f.path or ""), f.line or 0))
    counts = {"ERROR": 0, "WARNING": 0, "INFO": 0, "REVIEW": 0}
    for finding in findings:
        counts[finding.rule.severity.value] += 1
        if finding.rule.confidence.value == "REVIEW_REQUIRED":
            counts["REVIEW"] += 1
    status = "FAIL" if counts["ERROR"] else ("WARN" if counts["WARNING"] else "PASS")
    finding_dicts = []
    for finding in findings:
        item = finding.to_dict(root)
        if finding.rule.rule_id == "MIDEN016-TOOL-001":
            item.update({
                "applies_to_roles": ["contract", "wallet", "node", "tooling", "hybrid"],
                "excluded_roles": ["sdk-consumer"],
                "role_override_allowed": True,
                "role_reason": f"repository owns toolchain configuration; detected role is {role.role.value}",
            })
        else:
            item.update({
                "applies_to_roles": ["sdk-consumer", "contract", "wallet", "node", "tooling", "hybrid", "unknown"],
                "excluded_roles": [],
                "role_override_allowed": False,
                "role_reason": f"compatibility rule remains active for detected role {role.role.value}",
            })
        finding_dicts.append(item)
    return {
        "schema_version": "1.1", "product": "Miden Preflight", "product_version": "0.1.0",
        "created_by": "Pulse", "target": target, "project": str(root), "status": status,
        "project_role": role.role.value, "role_confidence": role.confidence.value,
        "role_evidence": list(role.evidence), "role_explicit": role.explicit,
        "owns_toolchain": role.owns_toolchain,
        "store_status": store.status, "counts": counts,
        "resolutions": [{"package": r.package, "version": r.version, "source": str(r.source.relative_to(root))} for r in resolutions],
        "findings": finding_dicts, "network_calls": 0, "wallet_actions": 0,
    }
