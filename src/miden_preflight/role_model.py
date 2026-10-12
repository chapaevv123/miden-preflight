from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class ProjectRole(str, Enum):
    SDK_CONSUMER = "sdk-consumer"
    CONTRACT = "contract"
    WALLET = "wallet"
    NODE = "node"
    TOOLING = "tooling"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class RoleConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class RoleAssessment:
    role: ProjectRole
    confidence: RoleConfidence
    evidence: tuple[str, ...]
    explicit: bool = False
    owns_toolchain: bool = False


@dataclass(frozen=True)
class RuleMetadata:
    rule_id: str
    title: str
    severity: str
    applies_to_roles: tuple[ProjectRole, ...]
    excluded_roles: tuple[ProjectRole, ...] = ()
    role_override_allowed: bool = True
    context_dependent: bool = False


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    message: str
    reason: str


ALL_ROLES = tuple(ProjectRole)
OWNED_TOOLCHAIN_ROLES = (
    ProjectRole.CONTRACT,
    ProjectRole.WALLET,
    ProjectRole.NODE,
    ProjectRole.TOOLING,
    ProjectRole.HYBRID,
)

RULES: dict[str, RuleMetadata] = {
    "MIDEN016-TOOL-001": RuleMetadata(
        "MIDEN016-TOOL-001",
        "Miden 0.16 toolchain pin",
        "LOW",
        OWNED_TOOLCHAIN_ROLES,
        (ProjectRole.SDK_CONSUMER,),
        True,
        True,
    ),
    "MIDEN016-LOCK-001": RuleMetadata(
        "MIDEN016-LOCK-001", "Stale lockfile", "HIGH", ALL_ROLES, role_override_allowed=False
    ),
    "MIDEN016-SDK-001": RuleMetadata(
        "MIDEN016-SDK-001", "Incompatible SDK family", "HIGH", ALL_ROLES, role_override_allowed=False
    ),
    "MIDEN016-NET-001": RuleMetadata(
        "MIDEN016-NET-001", "Network/version collision", "HIGH", ALL_ROLES, role_override_allowed=False
    ),
    "MIDEN016-AUTH-001": RuleMetadata(
        "MIDEN016-AUTH-001", "Removed authentication API", "HIGH", ALL_ROLES, role_override_allowed=False
    ),
    "MIDEN016-MASM-001": RuleMetadata(
        "MIDEN016-MASM-001", "Unreachable MASM source", "HIGH", ALL_ROLES, role_override_allowed=False
    ),
    "MIDEN016-STORE-001": RuleMetadata(
        "MIDEN016-STORE-001", "Unsafe store migration", "HIGH", ALL_ROLES, role_override_allowed=False
    ),
}

CONFIG_NAMES = ("miden-preflight.toml", ".miden-preflight.toml")
SKIP_DIRS = {".git", "node_modules", "target", "dist", "build", ".next", "coverage"}
TEXT_SUFFIXES = {
    ".json", ".toml", ".yaml", ".yml", ".js", ".jsx", ".ts", ".tsx", ".rs", ".masm",
    ".asm", ".md", ".sh", ".ps1", ".cmd", ".bat",
}


def _files(root: Path) -> list[Path]:
    result: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and (path.suffix.lower() in TEXT_SUFFIXES or path.name in CONFIG_NAMES):
            result.append(path)
    return result


def _read(path: Path, limit: int = 1_000_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _explicit_role(root: Path) -> ProjectRole | None:
    for name in CONFIG_NAMES:
        config = root / name
        if not config.is_file():
            continue
        try:
            value = tomllib.loads(config.read_text(encoding="utf-8")).get("project", {}).get("role")
            if value is None:
                return None
            return ProjectRole(value)
        except (OSError, tomllib.TOMLDecodeError, ValueError) as error:
            raise ValueError(f"invalid project.role in {config}: {error}") from error
    return None


def infer_project_role(root: str | Path) -> RoleAssessment:
    root = Path(root).resolve()
    files = _files(root)
    names = {path.name.lower() for path in files}
    rels = [path.relative_to(root).as_posix().lower() for path in files]
    manifests = "\n".join(
        _read(path) for path in files if path.name.lower() in {"package.json", "cargo.toml"}
    )
    scripts = "\n".join(
        _read(path)
        for path in files
        if path.suffix.lower() in {".json", ".yaml", ".yml", ".sh", ".ps1", ".cmd", ".bat"}
    )
    source_files = [path for path in files if path.suffix.lower() in {".rs", ".ts", ".tsx", ".js", ".jsx", ".masm", ".asm"}]
    source_sample = "\n".join(_read(path, 100_000) for path in source_files[:250])

    has_toolchain_file = any(name in names for name in {"miden-toolchain.toml", "rust-toolchain.toml"})
    cli_pattern = re.compile(r"(?<![-\w])(?:miden|midenup)(?:\.exe)?\s+(?:build|compile|install|run|toolchain|set|update)\b", re.I)
    has_cli_script = bool(cli_pattern.search(scripts))
    has_declared_cli_pin = bool(
        re.search(r'"midenClientCli(?:Version|Git|ProtocolVersion)"\s*:', manifests, re.I)
    )
    owns_toolchain = has_toolchain_file or has_cli_script or has_declared_cli_pin

    explicit = _explicit_role(root)
    if explicit is not None:
        return RoleAssessment(
            explicit,
            RoleConfidence.HIGH,
            (f"explicit project.role = {explicit.value}",),
            True,
            owns_toolchain,
        )

    evidence: dict[ProjectRole, list[str]] = {role: [] for role in ProjectRole}
    scores = {role: 0 for role in ProjectRole}
    has_sdk = bool(re.search(r'[@"]miden(?:-sdk|_client)|@miden-sdk/', manifests, re.I))
    frontend = bool(re.search(r'"(?:react|next|vite|vue|svelte|angular)"\s*:', manifests, re.I))
    masm_files = [rel for rel in rels if rel.endswith((".masm", ".asm"))]
    contract_dep = bool(re.search(r"miden-(?:objects|tx|assembly|lib|contracts?)", manifests, re.I))
    miden_build = bool(re.search(r"\bmiden(?:\.exe)?\s+(?:build|compile)\b", scripts, re.I))
    node_dep = bool(re.search(r"miden-(?:node|p2p|rpc)", manifests, re.I))
    tooling_dep = bool(re.search(r"miden-(?:compiler|assembly|up)|\bclap\b", manifests, re.I))

    if has_sdk:
        scores[ProjectRole.SDK_CONSUMER] += 3
        evidence[ProjectRole.SDK_CONSUMER].append("Miden SDK dependency")
    if frontend:
        scores[ProjectRole.SDK_CONSUMER] += 2
        evidence[ProjectRole.SDK_CONSUMER].append("frontend application framework")
    if has_sdk and not masm_files and not owns_toolchain and not contract_dep:
        scores[ProjectRole.SDK_CONSUMER] += 2
        evidence[ProjectRole.SDK_CONSUMER].append("no MASM, contract crate, CLI build script, or toolchain manifest")
    if masm_files:
        scores[ProjectRole.CONTRACT] += 4
        evidence[ProjectRole.CONTRACT].append(f"MASM source ({len(masm_files)} file(s))")
    if contract_dep or miden_build:
        scores[ProjectRole.CONTRACT] += 3
        evidence[ProjectRole.CONTRACT].append("Miden contract/build ownership")
    if node_dep or re.search(r"(?:validator|node runtime|network config)", source_sample, re.I):
        scores[ProjectRole.NODE] += 3
        evidence[ProjectRole.NODE].append("node/service runtime evidence")
    if tooling_dep and (has_cli_script or "src/main.rs" in rels):
        scores[ProjectRole.TOOLING] += 3
        evidence[ProjectRole.TOOLING].append("CLI/compiler/toolchain infrastructure")

    wallet_terms = len(re.findall(r"(?:signTransaction|transaction signing|note discovery|fee handling|wallet account)", source_sample, re.I))
    broad_wallet_repo = len(source_files) >= 40 and ("wallet" in root.name.lower() or "wallet" in manifests.lower())
    if broad_wallet_repo and wallet_terms >= 2:
        scores[ProjectRole.WALLET] += 5
        evidence[ProjectRole.WALLET].append("broad wallet implementation with account/transaction/note/fee behavior")

    strong = [role for role in (ProjectRole.CONTRACT, ProjectRole.WALLET, ProjectRole.NODE, ProjectRole.TOOLING) if scores[role] >= 3]
    if scores[ProjectRole.SDK_CONSUMER] >= 5 and strong:
        combined = strong + [ProjectRole.SDK_CONSUMER]
        combined_evidence = [item for role in combined for item in evidence[role]]
        return RoleAssessment(ProjectRole.HYBRID, RoleConfidence.HIGH, tuple(combined_evidence), False, owns_toolchain)
    if len(strong) >= 2:
        combined_evidence = [item for role in strong for item in evidence[role]]
        return RoleAssessment(ProjectRole.HYBRID, RoleConfidence.MEDIUM, tuple(combined_evidence), False, owns_toolchain)

    ranked = sorted(((score, role) for role, score in scores.items() if role not in {ProjectRole.UNKNOWN, ProjectRole.HYBRID}), reverse=True, key=lambda pair: pair[0])
    top_score, role = ranked[0]
    if top_score < 3:
        return RoleAssessment(ProjectRole.UNKNOWN, RoleConfidence.LOW, ("insufficient role evidence",), False, owns_toolchain)
    confidence = RoleConfidence.HIGH if top_score >= 5 else RoleConfidence.MEDIUM
    return RoleAssessment(role, confidence, tuple(evidence[role]), False, owns_toolchain)


def rule_applies(metadata: RuleMetadata, assessment: RoleAssessment) -> tuple[bool, str]:
    if metadata.rule_id == "MIDEN016-TOOL-001" and assessment.owns_toolchain:
        return True, "repository owns a Miden/Rust toolchain manifest or invokes Miden CLI tooling"
    if not metadata.role_override_allowed:
        return True, "role filtering is forbidden for this compatibility rule"
    if assessment.role in metadata.excluded_roles:
        return False, f"{assessment.role.value} does not own toolchain configuration"
    if assessment.role in metadata.applies_to_roles:
        return True, f"rule applies to {assessment.role.value} projects"
    if assessment.role is ProjectRole.UNKNOWN:
        return False, "insufficient evidence to assert toolchain ownership"
    return False, f"rule does not apply to {assessment.role.value} projects"


def _toolchain_is_016(root: Path) -> bool:
    for name in ("miden-toolchain.toml", "rust-toolchain.toml"):
        path = root / name
        if path.is_file() and re.search(r"(?:0\.16|1\.8[5-9]|1\.9\d)", _read(path)):
            return True
    package = root / "package.json"
    if package.is_file() and re.search(
        r'"midenClientCli(?:Version|ProtocolVersion)"\s*:\s*"0\.16(?:\.|\")',
        _read(package),
        re.I,
    ):
        return True
    return False


def scan_project(root: str | Path, verbose: bool = False) -> dict[str, Any]:
    root = Path(root).resolve()
    role = infer_project_role(root)
    findings: list[Finding] = []
    skipped: list[dict[str, str]] = []
    tool_rule = RULES["MIDEN016-TOOL-001"]
    applies, reason = rule_applies(tool_rule, role)
    if applies and not _toolchain_is_016(root):
        findings.append(Finding(tool_rule.rule_id, tool_rule.severity, "Project owns Miden tooling but has no confirmed 0.16 toolchain pin", reason))
    elif verbose and not applies:
        skipped.append({"rule_id": tool_rule.rule_id, "event": "RULE_SKIPPED_BY_ROLE", "reason": reason})
    return {
        "schema_version": "1.1",
        "project": str(root),
        "project_role": role.role.value,
        "role_confidence": role.confidence.value,
        "role_evidence": list(role.evidence),
        "role_explicit": role.explicit,
        "owns_toolchain": role.owns_toolchain,
        "findings": [asdict(finding) for finding in findings],
        **({"debug": skipped} if verbose else {}),
    }


def to_sarif(result: dict[str, Any]) -> dict[str, Any]:
    used = {finding["rule_id"] for finding in result["findings"]}
    rules = [
        {
            "id": rule.rule_id,
            "name": rule.title,
            "properties": {
                "appliesToRoles": [role.value for role in rule.applies_to_roles],
                "excludedRoles": [role.value for role in rule.excluded_roles],
                "roleOverrideAllowed": rule.role_override_allowed,
            },
        }
        for rule in RULES.values() if rule.rule_id in used
    ]
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": {"name": "Miden Preflight", "rules": rules}},
            "properties": {
                "projectRole": result["project_role"],
                "roleConfidence": result["role_confidence"],
                "roleEvidence": result["role_evidence"],
            },
            "results": [
                {"ruleId": finding["rule_id"], "level": finding["severity"].lower(), "message": {"text": finding["message"]}}
                for finding in result["findings"]
            ],
        }],
    }


def format_text(result: dict[str, Any], verbose: bool = False) -> str:
    lines = [
        "PROJECT ROLE:",
        f"{result['project_role']} ({result['role_confidence']})",
        "",
        "ROLE EVIDENCE:",
        *[f"- {item}" for item in result["role_evidence"]],
    ]
    if result["findings"]:
        lines.extend(["", "FINDINGS:"])
        lines.extend(f"- {item['rule_id']} [{item['severity']}]: {item['message']} ({item['reason']})" for item in result["findings"])
    else:
        lines.extend(["", "FINDINGS:", "None"])
    if verbose:
        lines.extend(["", "DEBUG:"])
        lines.extend(f"- {item['event']} {item['rule_id']}: {item['reason']}" for item in result.get("debug", []))
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Miden v0.16 preflight")
    parser.add_argument("command_or_path", nargs="?", default=".")
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--scenario", choices=("all", "fees", "anchors", "notes", "retry"), default="all")
    parser.add_argument("--execute", action="store_true", help="run pinned official mock tests")
    args = parser.parse_args(argv)
    if args.command_or_path == "semantic":
        from .mock_conformance import run_semantic_suite

        result = run_semantic_suite(args.path, args.scenario, args.execute)
        if args.format == "json":
            print(json.dumps(result, indent=2))
        elif args.format == "sarif":
            print(json.dumps({
                "version": "2.1.0",
                "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
                "runs": [{
                    "tool": {"driver": {"name": "Miden Preflight Semantic Conformance", "rules": []}},
                    "properties": {
                        "proofType": "OFFICIAL_UNIT_FIXTURE",
                        "sdkVersion": result["version"],
                        "mockVersion": "miden-client 0.16.0",
                        "scenarioIds": [item["scenario_id"] for item in result["evidence"]],
                        "semanticSummary": result["summary"],
                    },
                    "results": [],
                }],
            }, indent=2))
        else:
            summary = result["summary"]
            print("SEMANTIC CONFORMANCE (OFFLINE)")
            print(f"Official facility: {result['facility']}")
            print(f"Version: {result['version']}")
            print(
                f"Scenarios: {summary['total']} | pass {summary['passed']} | "
                f"blocked {summary['blocked']} | review {summary['review_required']}"
            )
            for item in result["evidence"]:
                print(f"{item['scenario_id']}: {item['result']} [{item['proof_type']}]")
            print(f"REVIEW: {result['boundary']['guardian']}")
        return 1 if result["summary"]["failed"] else 0
    target = args.command_or_path
    result = scan_project(target, args.verbose)
    if args.format == "json":
        print(json.dumps(result, indent=2))
    elif args.format == "sarif":
        print(json.dumps(to_sarif(result), indent=2))
    else:
        print(format_text(result, args.verbose))
    return 1 if result["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
