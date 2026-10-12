import json
from pathlib import Path

import pytest

from miden_preflight.role_model import (
    ALL_ROLES,
    RULES,
    ProjectRole,
    RoleConfidence,
    format_text,
    infer_project_role,
    rule_applies,
    scan_project,
    to_sarif,
)


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def package(root: Path, dependencies: dict[str, str], scripts: dict[str, str] | None = None) -> None:
    write(root / "package.json", json.dumps({"dependencies": dependencies, "scripts": scripts or {}}))


def test_pure_sdk_consumer_skips_toolchain_warning(tmp_path: Path) -> None:
    package(tmp_path, {"@miden-sdk/react": "0.16.0", "react": "19.0.0", "vite": "7.0.0"})
    write(tmp_path / "src/App.tsx", "export function App() { return null }")
    result = scan_project(tmp_path, verbose=True)
    assert result["project_role"] == "sdk-consumer"
    assert result["role_confidence"] == "HIGH"
    assert result["findings"] == []
    assert result["debug"][0]["event"] == "RULE_SKIPPED_BY_ROLE"


def test_hybrid_frontend_contract_applies_toolchain_rule(tmp_path: Path) -> None:
    package(tmp_path, {"@miden-sdk/react": "0.16.0", "react": "19.0.0", "vite": "7.0.0"})
    write(tmp_path / "contracts/vault.masm", "export.vault")
    result = scan_project(tmp_path)
    assert result["project_role"] == "hybrid"
    assert [item["rule_id"] for item in result["findings"]] == ["MIDEN016-TOOL-001"]


def test_contract_only_applies_toolchain_rule(tmp_path: Path) -> None:
    write(tmp_path / "contracts/vault.masm", "export.vault")
    write(tmp_path / "Cargo.toml", '[dependencies]\nmiden-objects = "0.16"')
    result = scan_project(tmp_path)
    assert result["project_role"] == "contract"
    assert result["findings"][0]["rule_id"] == "MIDEN016-TOOL-001"


def test_unknown_minimal_is_not_sdk_consumer(tmp_path: Path) -> None:
    write(tmp_path / "README.md", "hello")
    role = infer_project_role(tmp_path)
    assert role.role is ProjectRole.UNKNOWN
    assert role.confidence is RoleConfidence.LOW


def test_explicit_role_override_is_respected_and_reported(tmp_path: Path) -> None:
    package(tmp_path, {"@miden-sdk/react": "0.16.0", "react": "19.0.0"})
    write(tmp_path / "miden-preflight.toml", '[project]\nrole = "tooling"\n')
    role = infer_project_role(tmp_path)
    assert role.role is ProjectRole.TOOLING
    assert role.explicit is True
    assert role.confidence is RoleConfidence.HIGH
    assert "explicit project.role" in role.evidence[0]


def test_conflicting_evidence_is_hybrid_not_forced(tmp_path: Path) -> None:
    package(tmp_path, {"@miden-sdk/react": "0.16.0", "react": "19.0.0", "vite": "7.0.0"})
    write(tmp_path / "contracts/a.masm", "export.a")
    assert infer_project_role(tmp_path).role is ProjectRole.HYBRID


def test_sdk_consumer_with_explicit_toolchain_is_evaluated(tmp_path: Path) -> None:
    package(tmp_path, {"@miden-sdk/react": "0.16.0", "react": "19.0.0"})
    write(tmp_path / "miden-preflight.toml", '[project]\nrole = "sdk-consumer"\n')
    write(tmp_path / "miden-toolchain.toml", 'channel = "0.15"\n')
    result = scan_project(tmp_path)
    assert result["findings"][0]["rule_id"] == "MIDEN016-TOOL-001"


def test_sdk_consumer_with_cli_build_script_is_evaluated(tmp_path: Path) -> None:
    package(tmp_path, {"@miden-sdk/react": "0.16.0", "react": "19.0.0"}, {"contract": "miden build"})
    result = scan_project(tmp_path)
    assert result["findings"][0]["rule_id"] == "MIDEN016-TOOL-001"


def test_declared_client_cli_pin_is_toolchain_ownership(tmp_path: Path) -> None:
    write(
        tmp_path / "package.json",
        json.dumps({"dependencies": {"@miden-sdk/react": "0.16.0"}, "midenClientCliVersion": "0.17.1"}),
    )
    result = scan_project(tmp_path)
    assert result["owns_toolchain"] is True
    assert result["findings"][0]["rule_id"] == "MIDEN016-TOOL-001"


@pytest.mark.parametrize(
    "rule_id",
    [
        "MIDEN016-LOCK-001",
        "MIDEN016-SDK-001",
        "MIDEN016-NET-001",
        "MIDEN016-AUTH-001",
        "MIDEN016-MASM-001",
        "MIDEN016-STORE-001",
    ],
)
def test_high_severity_mutations_cannot_be_suppressed_by_role(rule_id: str, tmp_path: Path) -> None:
    package(tmp_path, {"@miden-sdk/react": "0.16.0", "react": "19.0.0"})
    assessment = infer_project_role(tmp_path)
    assert assessment.role is ProjectRole.SDK_CONSUMER
    assert rule_applies(RULES[rule_id], assessment)[0] is True
    assert RULES[rule_id].role_override_allowed is False


def test_explicit_wrong_toolchain_mutation_survives_role_filter(tmp_path: Path) -> None:
    package(tmp_path, {"@miden-sdk/react": "0.16.0", "react": "19.0.0"})
    write(tmp_path / "miden-toolchain.toml", 'channel = "0.15.0"\n')
    result = scan_project(tmp_path)
    assert result["findings"][0]["rule_id"] == "MIDEN016-TOOL-001"


def test_rule_metadata_is_complete() -> None:
    for rule in RULES.values():
        assert rule.applies_to_roles
        assert isinstance(rule.excluded_roles, tuple)
        assert isinstance(rule.role_override_allowed, bool)


def test_json_cli_fields_and_text_role_header(tmp_path: Path) -> None:
    package(tmp_path, {"@miden-sdk/react": "0.16.0", "react": "19.0.0"})
    result = scan_project(tmp_path)
    assert {"project_role", "role_confidence", "role_evidence"} <= result.keys()
    text = format_text(result)
    assert text.startswith("PROJECT ROLE:\nsdk-consumer (HIGH)\n\nROLE EVIDENCE:")


def test_sarif_has_role_metadata_and_no_skipped_results(tmp_path: Path) -> None:
    package(tmp_path, {"@miden-sdk/react": "0.16.0", "react": "19.0.0"})
    sarif = to_sarif(scan_project(tmp_path, verbose=True))
    run = sarif["runs"][0]
    assert run["properties"]["projectRole"] == "sdk-consumer"
    assert run["results"] == []
    assert run["tool"]["driver"]["rules"] == []
