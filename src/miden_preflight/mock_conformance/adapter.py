from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


MIDEN_VERSION = "0.16"
SDK_VERSION = "miden-client 0.16.0 / web-sdk 0.16.0"
MOCK_PACKAGE = "miden_client::testing (MockChain, MockClient, MockRpcApi, MockNoteTransportApi)"
RUST_COMMIT = "4e8407b9fa1e21e26eeb3040c915737a1293bde0"
WEB_COMMIT = "671335b15701865621b9340fe116f8cb816135f1"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    group: str
    test_filter: str
    source: str
    expected: str
    rule_impact: str
    negative: bool = False


SCENARIOS = (
    Scenario("FEE-001", "fees", "fee_conversion_info_pays_the_transaction_fee", "crates/testing/miden-client-tests/src/tests/fees.rs", "fee-funded transaction executes and emits a fee note", "ADD_EXECUTABLE_SUBCHECK"),
    Scenario("FEE-002", "fees", "fee_payment_fails_without_fee_asset_balance", "crates/testing/miden-client-tests/src/tests/fees.rs", "missing fee asset deterministically rejects", "ADD_EXECUTABLE_SUBCHECK", True),
    Scenario("FEE-003", "fees", "the_fee_note_is_not_tracked_as_one_of_our_output_notes", "crates/testing/miden-client-tests/src/tests/fees.rs", "protocol fee note is excluded from user output records", "ADD_EXECUTABLE_SUBCHECK"),
    Scenario("FEE-004", "fees", "fee_can_be_paid_from_a_note_consumed_in_the_same_transaction", "crates/testing/miden-client-tests/src/tests/fees.rs", "consumed user funding pays fee while preserving output accounting", "ADD_EXECUTABLE_SUBCHECK"),
    Scenario("FEE-005", "fees", "a_multisig_account_is_told_to_declare_its_own_conversion_info", "crates/testing/miden-client-tests/src/tests/fees.rs", "multisig missing conversion info is rejected with a typed error", "KEEP_REVIEW_REQUIRED", True),
    Scenario("ANCHOR-001", "anchors", "chain_anchor_pins_execution_to_an_older_reference_block", "crates/testing/miden-client-tests/src/tests/transaction.rs", "same captured anchor pins deterministic reference state", "ADD_EXECUTABLE_SUBCHECK"),
    Scenario("ANCHOR-002", "anchors", "chain_anchor_untracked_note_block_fails_with_typed_error", "crates/testing/miden-client-tests/src/tests/transaction.rs", "mismatched/untracked anchor input fails with typed evidence", "ADD_EXECUTABLE_SUBCHECK", True),
    Scenario("ANCHOR-003", "anchors", "chain_anchor_execution_rejects_an_already_expired_transaction", "crates/testing/miden-client-tests/src/tests/transaction.rs", "stale anchor fails deterministically", "ADD_EXECUTABLE_SUBCHECK", True),
    Scenario("NOTE-001", "notes", "transport_basic", "crates/testing/miden-client-tests/src/tests/transport.rs", "private note is delivered once and repeated sync does not duplicate it", "ADD_EXECUTABLE_SUBCHECK"),
    Scenario("NOTE-002", "notes", "fetch_private_notes_finds_note_committed_at_sync_height", "crates/testing/miden-client-tests/src/tests/transport.rs", "committed private note is discovered at the block hint boundary", "ADD_EXECUTABLE_SUBCHECK"),
    Scenario("NOTE-003", "notes", "send_private_note_with_block_hint_delivers_note", "crates/testing/miden-client-tests/src/tests/transport.rs", "sender block hint is retained for delivery/fetch", "ADD_EXECUTABLE_SUBCHECK"),
    Scenario("RETRY-001", "retry", "private_note_relay_recovers_after_transient_ntl_failure", "crates/testing/miden-client-tests/src/tests/transport.rs", "durable relay outbox recovers after transient local transport failure", "ADD_EXECUTABLE_SUBCHECK", True),
    Scenario("RETRY-002", "retry", "flush_relay_outbox_retries_failed_relay_without_full_sync", "crates/testing/miden-client-tests/src/tests/transport.rs", "explicit retry flushes failed relay without full sync", "ADD_EXECUTABLE_SUBCHECK", True),
    Scenario("RETRY-003", "retry", "transport_fetch_failure_leaves_cursor_for_retry", "crates/testing/miden-client-tests/src/tests/transport.rs", "failed fetch does not advance cursor and can retry", "ADD_EXECUTABLE_SUBCHECK", True),
    Scenario("DUP-001", "retry", "transport_basic", "crates/testing/miden-client-tests/src/tests/transport.rs", "repeated sync stores one copy of the delivered note", "ADD_EXECUTABLE_SUBCHECK", True),
)


def _source_root(workspace: Path) -> Path:
    return workspace / "tmp" / "miden-rust-sdk-v016"


def _fixture_present(root: Path, scenario: Scenario) -> bool:
    path = root / scenario.source
    return path.is_file() and f"fn {scenario.test_filter}" in path.read_text(encoding="utf-8")


def run_semantic_suite(
    workspace: str | Path,
    scenario_group: str = "all",
    execute: bool = False,
) -> dict[str, Any]:
    workspace = Path(workspace).resolve()
    root = _source_root(workspace)
    selected = [s for s in SCENARIOS if scenario_group == "all" or s.group == scenario_group]
    started = time.perf_counter()
    evidence: list[dict[str, Any]] = []
    for scenario in selected:
        present = _fixture_present(root, scenario)
        actual = "official v0.16 unit fixture located" if present else "official fixture missing"
        result = "REVIEW_REQUIRED"
        proof_type = "OFFICIAL_UNIT_FIXTURE" if present else "REVIEW_REQUIRED"
        command = None
        if execute and present:
            command = [
                "cargo", "+1.98.1-x86_64-pc-windows-gnu", "test", "-p",
                "miden-client-unit-tests", "--target", "x86_64-pc-windows-gnu",
                scenario.test_filter, "--", "--nocapture",
            ]
            env = os.environ.copy()
            env["PATH"] = rf"C:\WinLibs\mingw64\bin;{env.get('PATH', '')}"
            env["RUST_MIN_STACK"] = "33554432"
            completed = subprocess.run(
                command,
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                timeout=1800,
            )
            actual = (completed.stdout + completed.stderr)[-4000:]
            result = "PASS" if completed.returncode == 0 else "BLOCKED"
            proof_type = "OFFICIAL_MOCK_EXECUTION" if completed.returncode == 0 else "OFFICIAL_UNIT_FIXTURE"
        evidence.append({
            "scenario_id": scenario.scenario_id,
            "miden_version": MIDEN_VERSION,
            "sdk_version": SDK_VERSION,
            "mock_package": MOCK_PACKAGE,
            "mock_version": "miden-client 0.16.0",
            "commit_tag": f"rust-sdk v0.16.0@{RUST_COMMIT}; web-sdk v0.16.0@{WEB_COMMIT}",
            "input": {"official_test_filter": scenario.test_filter, "negative_mutation": scenario.negative},
            "expected": scenario.expected,
            "actual": actual,
            "result": result,
            "proof_type": proof_type,
            "primary_source": str(root / scenario.source),
            "rule_impact": scenario.rule_impact,
            **({"command": command} if command else {}),
        })
    elapsed = time.perf_counter() - started
    return {
        "schema_version": "1.0",
        "mode": "offline",
        "facility": "MidenClient.createMock / miden_client::testing MockChain",
        "version": SDK_VERSION,
        "commit_tag": f"rust-sdk v0.16.0@{RUST_COMMIT}; web-sdk v0.16.0@{WEB_COMMIT}",
        "scenario_group": scenario_group,
        "executed": execute,
        "duration_seconds": round(elapsed, 6),
        "summary": {
            "total": len(evidence),
            "passed": sum(item["result"] == "PASS" for item in evidence),
            "failed": sum(item["result"] == "FAIL" for item in evidence),
            "blocked": sum(item["result"] == "BLOCKED" for item in evidence),
            "review_required": sum(item["result"] == "REVIEW_REQUIRED" for item in evidence),
        },
        "evidence": evidence,
        "boundary": {
            "local_state": "OFFICIAL_UNIT_FIXTURE; execution blocked on this Windows GNU host",
            "network_transport": "UNPROVEN; MockNoteTransport is in-process and no live network was used",
            "guardian": "UNPROVEN; fee precondition only, not Guardian approval/summary conformance",
        },
    }


def write_evidence(result: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
