from __future__ import annotations

import json


def text_report(report: dict) -> str:
    lines = [f"Miden Preflight 0.1.0 | {report['target']} | {report['status']}",
             f"Project: {report['project']}",
             f"Project role: {report['project_role']} ({report['role_confidence']})",
             "Role evidence: " + "; ".join(report["role_evidence"]),
             f"Store: {report['store_status']}", ""]
    if not report["findings"]:
        lines.append("PASS No v0.16 conformance findings.")
    for f in report["findings"]:
        outcome = "REVIEW" if f["confidence"] == "REVIEW_REQUIRED" else ("FAIL" if f["severity"] == "ERROR" else "WARN")
        location = f"{f['path'] or 'project'}" + (f":{f['line']}" if f["line"] else "")
        lines += [f"{outcome} {f['severity']} {f['rule_id']}  {f['title']}", f"At: {location}",
                  f"Why: {f['why_it_matters']}", f"Evidence: {f['evidence']['source_url']} — {f['evidence']['source_section']}",
                  f"Fix: {f['remediation']}"]
        if f.get("resolved_version"):
            lines.append(f"Versions: declared={f['declared_version']} resolved={f['resolved_version']} expected={f['expected_version_family']}")
        lines.append("")
    c = report["counts"]
    lines.append(f"Summary: {c['ERROR']} error, {c['WARNING']} warning, {c['REVIEW']} review")
    return "\n".join(lines)


def sarif(report: dict) -> dict:
    rules: dict[str, dict] = {}
    results: list[dict] = []
    levels = {"ERROR": "error", "WARNING": "warning", "INFO": "note"}
    for finding in report["findings"]:
        rid = finding["rule_id"]
        rules.setdefault(rid, {"id": rid, "name": finding["title"],
                              "helpUri": finding["evidence"]["source_url"],
                              "shortDescription": {"text": finding["message"]},
                              "help": {"text": finding["remediation"]},
                              "properties": {
                                  "appliesToRoles": finding["applies_to_roles"],
                                  "excludedRoles": finding["excluded_roles"],
                                  "roleOverrideAllowed": finding["role_override_allowed"],
                              }})
        result = {"ruleId": rid, "level": levels[finding["severity"]], "message": {"text": finding["detail"]}}
        if finding["path"]:
            region = {"startLine": finding["line"] or 1}
            result["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": finding["path"].replace("\\", "/")}, "region": region}}]
        results.append(result)
    return {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [{"tool": {"driver": {"name": "Miden Preflight", "version": report["product_version"],
                                            "informationUri": "https://docs.miden.xyz/builder/migration/",
                                            "rules": list(rules.values())}},
                      "properties": {"projectRole": report["project_role"],
                                     "roleConfidence": report["role_confidence"],
                                     "roleEvidence": report["role_evidence"]},
                      "results": results}]}


def json_text(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=False)
