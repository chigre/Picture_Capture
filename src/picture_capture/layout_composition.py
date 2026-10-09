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


def infer_composed_physical_page_layout(
    image: Image.Image,
    settings: Any,
    *,
    page_index: int = 0,
    ops: base.LayoutPrimitiveOps | None = None,
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
        )
        return anchored, estimate, selected

    layout, page_settings, applied = policy._RAW_INFER_DICTIONARY_PAGE_LAYOUT(
        image,
        settings,
        page_index=page_index,
        ops=selected_ops,
        policy_resolver=anchored_policy,
    )
    normalize_layout_roles(layout)
    return layout, page_settings, applied
