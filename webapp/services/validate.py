"""Inline validation summary for the home dashboard (no /validate page)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationReport:
    ok: bool = True
    count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_validation() -> ValidationReport:
    return ValidationReport()


class ValidationSaveError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(errors[0] if errors else "validation failed")


def entity_errors(_issues) -> list[str]:
    return []


def validate_character(*_args, **_kwargs):
    return []


def validate_act(*_args, **_kwargs):
    return []


def raise_validation_errors(_issues) -> None:
    pass
