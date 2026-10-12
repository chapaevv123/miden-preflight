from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .catalog import RULES
from .engine import scan
from .output import json_text, sarif, text_report


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="miden-preflight", description="Offline Miden v0.16 conformance gate")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="scan a project")
    s.add_argument("path", type=Path)
    s.add_argument("--target", default="miden-0.16", choices=["miden-0.16"])
    fmt = s.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true")
    fmt.add_argument("--sarif", action="store_true")
    e = sub.add_parser("explain", help="explain one rule")
    e.add_argument("rule_id")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "explain":
        rule = RULES.get(args.rule_id.upper())
        if not rule:
            print(f"Unknown rule: {args.rule_id}", file=sys.stderr)
            return 2
        print(json_text(rule.to_dict()))
        return 0
    report = scan(args.path, args.target)
    print(json_text(sarif(report) if args.sarif else report) if (args.json or args.sarif) else text_report(report))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
