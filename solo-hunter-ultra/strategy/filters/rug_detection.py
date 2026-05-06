"""Layer 4 rule-based rug detection."""

from __future__ import annotations

from strategy.base import FilterResult


def validate_rug_risk(features: dict[str, object], max_tax_percent: float = 10.0) -> FilterResult:
    """Reject honeypots, high taxes, and suspicious developer histories."""
    if features.get("honeypot"):
        return FilterResult(False, "rug_detection", "honeypot")
    if features.get("hidden_mint_functions"):
        return FilterResult(False, "rug_detection", "hidden_mint_functions")
    if float(features.get("transfer_tax_percent", 0.0) or 0.0) > max_tax_percent:
        return FilterResult(False, "rug_detection", "excessive_transfer_tax")
    if features.get("dev_known_rugger"):
        return FilterResult(False, "rug_detection", "dev_known_rugger")
    if int(features.get("dev_cluster_rugs", 0) or 0) > 0:
        return FilterResult(False, "rug_detection", "cluster_rug_history")
    return FilterResult(True, "rug_detection")
