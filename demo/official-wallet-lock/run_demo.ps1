$ErrorActionPreference = "Stop"
$packageRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$env:PYTHONPATH = Join-Path $packageRoot "src"

@'
from pathlib import Path
from miden_preflight.engine import scan

root = Path(r"__DEMO_ROOT__")
for label in ("before", "fixed"):
    report = scan(root / label, "miden-0.16")
    drift = [f for f in report["findings"] if f["rule_id"] == "MIDEN016-SDK-002"]
    print(f"{label.upper()}: {'FAIL' if drift else 'PASS'}")
    for finding in drift:
        print(f"  {finding['detail']}")
    target_only = [f for f in report["findings"] if f["rule_id"] == "MIDEN016-SDK-001"]
    if label == "fixed" and target_only:
        print("  Expected target note: current 0.17 example is not a v0.16 testnet build.")
'@.Replace("__DEMO_ROOT__", $PSScriptRoot.Replace("\", "\\")) | python -
