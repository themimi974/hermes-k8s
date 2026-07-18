"""Merge budget group settings for multi-group friend assignment.

When a friend belongs to multiple budget groups, the effective settings
are computed by merging all group configs:
  - models: union of all model lists
  - max_budget: sum across groups
  - tpm_limit: max across groups
  - rpm_limit: max across groups
  - max_parallel: max across groups
  - budget_duration: shortest duration (most restrictive)
"""
from __future__ import annotations

from typing import Optional
from models import BudgetGroupRecord


DURATION_ORDER = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}


def merge_groups(groups: list[BudgetGroupRecord]) -> dict:
    """Merge multiple budget groups into a single effective config.

    Returns dict with keys: models, tpm_limit, rpm_limit,
    max_parallel, max_budget, budget_duration.
    """
    if not groups:
        return {
            "models": ["gpt-3.5-turbo"],
            "tpm_limit": 100000,
            "rpm_limit": 1000,
            "max_parallel": 5,
            "max_budget": 50.0,
            "budget_duration": "30d",
        }

    # Union of all models (deduplicated)
    all_models: list[str] = []
    seen = set()
    for g in groups:
        for m in (g.models or []):
            if m not in seen:
                all_models.append(m)
                seen.add(m)

    if not all_models:
        all_models = ["gpt-3.5-turbo"]

    # Sum budgets, max limits
    total_budget = sum(g.max_budget for g in groups)
    max_tpm = max(g.tpm_limit for g in groups)
    max_rpm = max(g.rpm_limit for g in groups)
    max_parallel = max(g.max_parallel for g in groups)

    # Shortest duration (most restrictive)
    shortest_duration = min(
        groups,
        key=lambda g: DURATION_ORDER.get(g.budget_duration, 30),
    ).budget_duration

    return {
        "models": all_models,
        "tpm_limit": max_tpm,
        "rpm_limit": max_rpm,
        "max_parallel": max_parallel,
        "max_budget": total_budget,
        "budget_duration": shortest_duration,
    }


def get_friend_merged_settings(
    friend_groups: list[BudgetGroupRecord],
    resource_overrides: Optional[dict] = None,
) -> dict:
    """Get full effective settings for a friend including resource overrides.

    Args:
        friend_groups: list of BudgetGroupRecord the friend belongs to
        resource_overrides: optional dict with cpu_request, cpu_limit,
            memory_request, memory_limit, storage_size overrides
    """
    merged = merge_groups(friend_groups)

    # Apply per-friend resource overrides (None = use defaults from settings)
    if resource_overrides:
        for key in ("cpu_request", "cpu_limit", "memory_request", "memory_limit", "storage_size"):
            val = resource_overrides.get(key)
            if val is not None:
                merged[key] = val

    return merged
