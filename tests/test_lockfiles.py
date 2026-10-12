from pathlib import Path

from miden_preflight.lockfiles import all_resolutions

ROOT = Path(__file__).resolve().parents[1]


def test_supported_lockfiles_resolve_actual_versions(tmp_path):
    (tmp_path / "Cargo.lock").write_text('[[package]]\nname="miden-client"\nversion="0.16.1"\n', encoding="utf-8")
    (tmp_path / "package-lock.json").write_text('{"packages":{"node_modules/@miden-sdk/miden-sdk":{"version":"0.16.0"}}}', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("packages:\n  '@miden-sdk/react@0.16.0': {}\n", encoding="utf-8")
    (tmp_path / "yarn.lock").write_text('"@miden-sdk/shared@^0.16.0":\n  version "0.16.2"\n', encoding="utf-8")
    got = {(r.package, r.version) for r in all_resolutions(tmp_path)}
    assert {("miden-client", "0.16.1"), ("@miden-sdk/miden-sdk", "0.16.0"),
            ("@miden-sdk/react", "0.16.0"), ("@miden-sdk/shared", "0.16.2")} <= got
