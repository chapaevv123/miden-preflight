from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class Confidence(StrEnum):
    CONFIRMED = "CONFIRMED"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class Evidence:
    source_url: str
    source_section: str
    source_version: str
    evidence_note: str


@dataclass(frozen=True)
class Rule:
    rule_id: str
    title: str
    severity: Severity
    confidence: Confidence
    category: str
    applies_to: tuple[str, ...]
    miden_version: str
    evidence_source: Evidence
    detection_method: str
    message: str
    why_it_matters: str
    remediation: str
    false_positive_boundary: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["severity"] = self.severity.value
        value["confidence"] = self.confidence.value
        return value


@dataclass(frozen=True)
class Finding:
    rule: Rule
    path: Path | None
    line: int | None
    detail: str
    declared_version: str | None = None
    resolved_version: str | None = None
    expected_version_family: str | None = None

    def to_dict(self, root: Path) -> dict[str, Any]:
        path = None
        if self.path:
            try:
                path = str(self.path.resolve().relative_to(root.resolve()))
            except ValueError:
                path = str(self.path)
        return {
            "rule_id": self.rule.rule_id,
            "title": self.rule.title,
            "severity": self.rule.severity.value,
            "confidence": self.rule.confidence.value,
            "category": self.rule.category,
            "path": path,
            "line": self.line,
            "detail": self.detail,
            "declared_version": self.declared_version,
            "resolved_version": self.resolved_version,
            "expected_version_family": self.expected_version_family,
            "message": self.rule.message,
            "why_it_matters": self.rule.why_it_matters,
            "remediation": self.rule.remediation,
            "evidence": asdict(self.rule.evidence_source),
        }
