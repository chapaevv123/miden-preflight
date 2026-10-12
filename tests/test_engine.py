import json
from pathlib import Path

from miden_preflight.catalog import RULES
from miden_preflight.engine import scan
from miden_preflight.output import sarif

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_has_complete_versioned_evidence():
    assert len(RULES) >= 19
    for key, rule in RULES.items():
        assert key == rule.rule_id
        assert rule.miden_version == "0.16"
        assert rule.evidence_source.source_url.startswith("https://")
        assert rule.false_positive_boundary


def test_broken_demo_finds_confirmed_and_review_risks():
    report = scan(ROOT / "demo" / "broken")
    ids = {f["rule_id"] for f in report["findings"]}
    assert {"MIDEN016-SDK-001", "MIDEN016-DEP-001", "MIDEN016-MASM-001",
            "MIDEN016-API-001", "MIDEN016-STORE-001", "MIDEN016-STORE-002",
            "MIDEN016-FEE-001", "MIDEN016-ANCHOR-001"} <= ids
    assert report["store_status"] == "EXPORT_REQUIRED"
    assert report["status"] == "FAIL"
    sdk = next(f for f in report["findings"] if f["rule_id"] == "MIDEN016-SDK-001")
    assert sdk["declared_version"] == "^0.16.0"
    assert sdk["resolved_version"] == "0.17.3"


def test_fixed_demo_passes():
    report = scan(ROOT / "demo" / "fixed")
    assert report["status"] == "PASS", report["findings"]
    assert report["store_status"] == "SAFE"
    assert not report["findings"]


def test_sarif_is_v21_and_has_locations():
    report = scan(ROOT / "demo" / "broken")
    output = sarif(report)
    assert output["version"] == "2.1.0"
    assert output["runs"][0]["results"]
    assert any("locations" in r for r in output["runs"][0]["results"])


def test_masm_missing_child_is_confirmed_but_nested_child_is_reachable(tmp_path):
    asm = tmp_path / "asm"
    asm.mkdir()
    (asm / "lib.masm").write_text("pub mod present\nmod missing\n", encoding="utf-8")
    (asm / "present.masm").write_text("export.ok\n  push.1\nend\n", encoding="utf-8")
    report = scan(tmp_path)
    missing = [f for f in report["findings"] if f["rule_id"] == "MIDEN016-MASM-002"]
    assert len(missing) == 1
    assert "missing" in missing[0]["detail"]
    assert not any(f["rule_id"] == "MIDEN016-MASM-001" for f in report["findings"])


def test_v016_asset_constructors_are_not_legacy_api_findings(tmp_path):
    """Stable v0.16 first-party code still uses these constructors."""
    (tmp_path / "src.rs").write_text(
        "let asset = FungibleAsset::new(faucet_id, 100u64)?;\n"
        "let nft = NonFungibleAsset::new(faucet_id, data)?;\n",
        encoding="utf-8",
    )
    report = scan(tmp_path)
    assert not any(f["rule_id"] == "MIDEN016-ASSET-001" for f in report["findings"])


def test_masm_root_does_not_claim_unrelated_fixture_is_unreachable(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "lib.masm").write_text("export.ok\n  push.1\nend\n", encoding="utf-8")
    fixture = tmp_path / "tests" / "expected"
    fixture.mkdir(parents=True)
    (fixture / "snapshot.masm").write_text("begin\n  push.2\nend\n", encoding="utf-8")
    report = scan(tmp_path)
    assert not any(f["rule_id"] == "MIDEN016-MASM-001" for f in report["findings"])


def test_sdk_only_project_does_not_receive_toolchain_pin_warning(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"@miden-sdk/react": "^0.16.0", "react": "^18.0.0"}}),
        encoding="utf-8",
    )
    report = scan(tmp_path)
    assert not any(f["rule_id"] == "MIDEN016-TOOL-001" for f in report["findings"])
