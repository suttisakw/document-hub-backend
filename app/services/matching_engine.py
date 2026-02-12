from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RuleCondition:
    left_field: str
    operator: str
    right_field: str


def _normalize(v: str | None) -> str:
    return (v or "").strip().lower()


def evaluate_operator(left: str | None, operator: str, right: str | None) -> bool:
    left_s = _normalize(left)
    right_s = _normalize(right)

    if operator == "equals":
        return left_s != "" and left_s == right_s
    if operator == "contains":
        return left_s != "" and right_s in left_s
    if operator == "starts_with":
        return left_s != "" and left_s.startswith(right_s)

    if operator in {"greater_than", "less_than"}:
        try:
            left_n = float(left_s.replace(",", ""))
            right_n = float(right_s.replace(",", ""))
        except ValueError:
            return False
        if operator == "greater_than":
            return left_n > right_n
        return left_n < right_n

    return False


def evaluate_pair(
    left_fields: dict[str, str | None],
    right_fields: dict[str, str | None],
    conditions: list[RuleCondition],
) -> bool:
    if not conditions:
        return False

    normalized_left = {_normalize(k): v for k, v in left_fields.items()}
    normalized_right = {_normalize(k): v for k, v in right_fields.items()}

    for cond in conditions:
        left_val = normalized_left.get(_normalize(cond.left_field))
        right_val = normalized_right.get(_normalize(cond.right_field))
        if not evaluate_operator(left_val, cond.operator, right_val):
            return False
    return True
