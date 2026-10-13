"""Explicit physical-only Layout composition boundary.

This service does not call or install process-global Layout hooks. The
historical installers stay available to existing GUI/spawn consumers until
the separate Phase 13E cutover has passed parity validation.
"""
from __future__ import annotations

from typing import Any

from PIL import Image

from . import dictionary_page_design as base
from . import dictionary_page_layout_policy as policy
from .layout_physical_indent import (
    explicit_physical_layout_ops,
    normalize_layout_roles,
)
from .layout_profile_anchor import anchor_resolved_layout_to_profile
from .layout_step_trace import LayoutStepTrace


def infer_composed_physical_page_layout(
    image: Image.Image,
    settings: Any,
    *,
    page_index: int = 0,
    ops: base.LayoutPrimitiveOps | None = None,
    trace: LayoutStepTrace | None = None,
) -> tuple[base.DictionaryPageLayout, Any, dict[str, int]]:
    """Infer anchored physical page layout without installed policy wrappers.

    The raw policy remains public and unanchored, while this composed boundary
    applies Project/Profile anchoring once, followed by physical role
    normalization at the legacy policy-finalizer boundary.
    """
    selected_ops = explicit_physical_layout_ops() if ops is None else ops

    def anchored_policy(
        page_image: Image.Image,
        profile_settings: Any,
        *,
        page_index: int = 0,
        ops: base.LayoutPrimitiveOps | None = None,
    ):
        resolved, estimate, applied = policy._RAW_RESOLVE_PAGE_LAYOUT_POLICY(
            page_image,
            profile_settings,
            page_index=page_index,
            **({"ops": ops} if ops is not None else {}),
        )
        anchored, selected = anchor_resolved_layout_to_profile(
            profile_settings, resolved, applied,
            estimate=estimate,
        )
        if trace is not None:
            trace.add_policy(estimate, anchored, selected)
        return anchored, estimate, selected

    layout, page_settings, applied = policy._RAW_INFER_DICTIONARY_PAGE_LAYOUT(
        image,
        settings,
        page_index=page_index,
        ops=selected_ops,
        policy_resolver=anchored_policy,
    )
    if trace is not None:
        trace.add_layout("physical_rows", "物理行检测",
                         "Page Design 原始物理行与正文栏范围；角色尚未经过后续完整修正。", layout)
    normalize_layout_roles(layout)
    if trace is not None:
        trace.add_layout("initial_roles", "基础行角色",
                         "由物理行和初步缩进族得到的角色；尚未合并大字头和符号证据。", layout)
    return layout, page_settings, applied


def understand_composed_page(
    image: Image.Image,
    settings: Any,
    *,
    page_index: int = 0,
    page_sections: list[Any] | None = None,
):
    """Full Page Understanding with explicit physical and policy composition.

    This is an opt-in service in Phase 13E1. GUI and worker routing stays
    unchanged until the full parity and cache/persistence gates are green.
    """
    from . import page_understanding

    ops = explicit_physical_layout_ops()

    def infer_layout(page_image: Image.Image, page_settings: Any, *, page_index: int = 0):
        return infer_composed_physical_page_layout(
            page_image, page_settings, page_index=page_index, ops=ops,
        )

    understanding = page_understanding._RAW_UNDERSTAND_PAGE(
        image,
        settings,
        page_index=page_index,
        page_sections=page_sections,
        layout_infer=infer_layout,
        ops=ops,
    )
    # Match the historical page-understanding finalizer, not the earlier
    # policy-level normalization performed by infer_composed_physical_page_layout.
    normalize_layout_roles(understanding.layout)
    return understanding
