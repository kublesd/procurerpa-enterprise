"""Procurement-page model router based on page complexity estimation.

Routes simple pages to lightweight (cheaper/faster) models and complex
pages to large (more capable) models based on DOM characteristics.

Complexity factors:
- DOM element count
- iframe nesting depth
- Dynamic content indicators (AJAX, WebSocket, shadow DOM)
"""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ComplexityLevel(str, Enum):
    """Page complexity classification."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class ProcurementPageKind(str, Enum):
    """Synthetic procurement page types used by the first-phase demo."""

    SUPPLIER_CATALOG = "supplier_catalog"
    DYNAMIC_QUOTE_PORTAL = "dynamic_quote_portal"
    ERP_CONTRACT = "erp_contract"


class ModelTier(str, Enum):
    """LLM model tier."""

    LIGHT = "light"     # e.g., Claude Haiku, GPT-4o-mini
    STANDARD = "standard"  # e.g., Claude Sonnet
    HEAVY = "heavy"     # e.g., Claude Opus, GPT-4o


@dataclass
class PageFeatures:
    """DOM characteristics used for procurement-page complexity estimation."""

    element_count: int = 0
    has_iframe: bool = False
    iframe_depth: int = 0
    has_dynamic_content: bool = False
    has_shadow_dom: bool = False
    form_field_count: int = 0
    page_kind: ProcurementPageKind | str | None = None


@dataclass
class RoutingDecision:
    """Model routing decision with explicit first-phase provenance."""

    model_tier: ModelTier
    complexity: ComplexityLevel
    reason: str
    features: PageFeatures
    data_source: str = "demo_estimate"
    execution_mode: str = "simulated"
    connection_status: str = "not_connected"
    resolved_model_key: str | None = None
    resolved_model_name: str | None = None
    model_alias: str | None = None
    reason_code: str | None = None

    def to_task_model(self) -> dict[str, str]:
        if not self.resolved_model_key:
            raise ModelRoutingUnavailable("procurement_model_unavailable")
        return {
            "llm_key": self.resolved_model_key,
            "model_tier": self.model_tier.value,
            "reason_code": self.reason_code or "tier_selected",
        }


class ModelRoutingUnavailable(RuntimeError):
    """No configured Skyvern model can satisfy the procurement tier."""


# Thresholds for complexity classification
ELEMENT_THRESHOLD_SIMPLE = 100
ELEMENT_THRESHOLD_MODERATE = 500
FORM_FIELD_THRESHOLD_COMPLEX = 20


def estimate_complexity(features: PageFeatures) -> ComplexityLevel:
    """Estimate page complexity from DOM features.

    Classification logic:
    - COMPLEX: deep iframes, shadow DOM, many elements, or many form fields
    - MODERATE: iframes present, dynamic content, or moderate element count
    - SIMPLE: everything else
    """
    # Complex conditions
    if features.iframe_depth >= 2:
        return ComplexityLevel.COMPLEX
    if features.has_shadow_dom:
        return ComplexityLevel.COMPLEX
    if features.element_count > ELEMENT_THRESHOLD_MODERATE:
        return ComplexityLevel.COMPLEX
    if features.form_field_count >= FORM_FIELD_THRESHOLD_COMPLEX:
        return ComplexityLevel.COMPLEX

    # Moderate conditions
    if features.has_iframe:
        return ComplexityLevel.MODERATE
    if features.has_dynamic_content:
        return ComplexityLevel.MODERATE
    if features.element_count > ELEMENT_THRESHOLD_SIMPLE:
        return ComplexityLevel.MODERATE

    return ComplexityLevel.SIMPLE


# Complexity -> Model tier mapping
COMPLEXITY_TO_TIER: dict[ComplexityLevel, ModelTier] = {
    ComplexityLevel.SIMPLE: ModelTier.LIGHT,
    ComplexityLevel.MODERATE: ModelTier.STANDARD,
    ComplexityLevel.COMPLEX: ModelTier.HEAVY,
}


PROCUREMENT_PAGE_PROFILES: dict[ProcurementPageKind, PageFeatures] = {
    ProcurementPageKind.SUPPLIER_CATALOG: PageFeatures(
        element_count=80,
        form_field_count=4,
        page_kind=ProcurementPageKind.SUPPLIER_CATALOG,
    ),
    ProcurementPageKind.DYNAMIC_QUOTE_PORTAL: PageFeatures(
        element_count=220,
        has_dynamic_content=True,
        form_field_count=8,
        page_kind=ProcurementPageKind.DYNAMIC_QUOTE_PORTAL,
    ),
    ProcurementPageKind.ERP_CONTRACT: PageFeatures(
        element_count=720,
        has_iframe=True,
        iframe_depth=2,
        has_dynamic_content=True,
        has_shadow_dom=True,
        form_field_count=24,
        page_kind=ProcurementPageKind.ERP_CONTRACT,
    ),
}


def route_procurement_page(page_kind: ProcurementPageKind | str) -> RoutingDecision:
    """Route one of the fixed synthetic procurement page profiles."""
    kind = ProcurementPageKind(page_kind)
    profile = PROCUREMENT_PAGE_PROFILES[kind]
    return route_model(PageFeatures(**vars(profile)))


def resolve_procurement_page(
    page_kind: ProcurementPageKind | str,
    *,
    available_keys: set[str] | None = None,
    model_mapping: dict[str, dict[str, str]] | None = None,
) -> RoutingDecision:
    """Resolve a procurement tier to an actually configured native Skyvern model."""
    from skyvern.config import settings
    from skyvern.forge.sdk.api.llm.config_registry import LLMConfigRegistry

    decision = route_procurement_page(page_kind)
    tier_keys = {
        ModelTier.LIGHT: settings.PROCUREMENT_LIGHT_LLM_KEY or settings.LLM_KEY,
        ModelTier.STANDARD: settings.PROCUREMENT_STANDARD_LLM_KEY or settings.LLM_KEY,
        ModelTier.HEAVY: settings.PROCUREMENT_HEAVY_LLM_KEY or settings.LLM_KEY,
    }
    fallback_tiers = {
        ModelTier.LIGHT: (ModelTier.LIGHT,),
        ModelTier.STANDARD: (ModelTier.STANDARD, ModelTier.LIGHT),
        ModelTier.HEAVY: (ModelTier.HEAVY, ModelTier.STANDARD, ModelTier.LIGHT),
    }
    available = set(LLMConfigRegistry.get_model_names()) if available_keys is None else available_keys
    mapping = settings.get_model_name_to_llm_key() if model_mapping is None else model_mapping
    model_names = {item["llm_key"]: name for name, item in mapping.items() if item.get("llm_key")}

    for tier in fallback_tiers[decision.model_tier]:
        key = tier_keys[tier]
        if key and key in available:
            decision.resolved_model_key = key
            decision.resolved_model_name = model_names.get(key)
            decision.model_alias = f"procurement-{tier.value}"
            decision.reason_code = (
                "tier_selected"
                if tier == decision.model_tier
                else f"{decision.model_tier.value}_fallback_to_{tier.value}"
            )
            decision.data_source = "skyvern_llm_config"
            decision.execution_mode = "real"
            decision.connection_status = "connected"
            return decision

    raise ModelRoutingUnavailable("procurement_model_unavailable")


def route_model(features: PageFeatures) -> RoutingDecision:
    """Determine which LLM model tier to use based on page features.

    Args:
        features: DOM characteristics of the target page.

    Returns:
        RoutingDecision with model tier, complexity level, and reasoning.
    """
    complexity = estimate_complexity(features)
    tier = COMPLEXITY_TO_TIER[complexity]

    reasons = []
    if features.element_count > 0:
        reasons.append(f"elements={features.element_count}")
    if features.has_iframe:
        reasons.append(f"iframe_depth={features.iframe_depth}")
    if features.has_dynamic_content:
        reasons.append("dynamic_content")
    if features.has_shadow_dom:
        reasons.append("shadow_dom")
    if features.form_field_count > 0:
        reasons.append(f"form_fields={features.form_field_count}")

    labels = {
        ProcurementPageKind.SUPPLIER_CATALOG: "supplier catalog",
        ProcurementPageKind.DYNAMIC_QUOTE_PORTAL: "dynamic quote portal",
        ProcurementPageKind.ERP_CONTRACT: "ERP/contract page",
    }
    try:
        page_kind = ProcurementPageKind(features.page_kind) if features.page_kind else None
    except ValueError:
        page_kind = None
    page_label = labels.get(page_kind, "procurement page")
    reason = f"{page_label}: {complexity.value} page ({', '.join(reasons) or 'default'})"

    decision = RoutingDecision(
        model_tier=tier,
        complexity=complexity,
        reason=reason,
        features=features,
    )

    logger.info(
        "Model routing: %s -> %s (%s)",
        complexity.value,
        tier.value,
        reason,
    )

    return decision
