"""Semantic compatibility report derived from canonical feature masks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from twinops.research.contracts import FeaturePolicy, SignalWindow
from twinops.research.features import extract_views


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    full_features: tuple[str, ...]
    aggregate_features: tuple[str, ...]
    forzy_features: tuple[str, ...]
    missing_semantics: Mapping[str, str]
    feature_policy_id: str | None


def compatibility(
    window: SignalWindow, *, policy: FeaturePolicy | None = None
) -> CompatibilityReport:
    views = extract_views(window, policy=policy)
    return CompatibilityReport(
        full_features=tuple(views.full),
        aggregate_features=tuple(views.aggregate),
        forzy_features=tuple(views.forzy),
        missing_semantics=views.unconfirmed_semantics,
        feature_policy_id=views.feature_policy_id,
    )
