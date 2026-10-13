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
from .profile_indent_ui import indent_type_label
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
    projection_batches: list[list[dict[str, Any]]] | None = (
        [] if trace is not None else None
    )

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
        **({"projection_trace": projection_batches} if trace is not None else {}),
    )
    if trace is not None:
        # The final bounded projection pass, not the seed/reference scans,
        # supplies the exact segments consumed to create the following rows.
        trace.add_projection_stages(
            projection_batches[-1] if projection_batches else [], layout,
            pass_count=len(projection_batches or []),
        )
        # Page Design's historical two-polarity builder emits temporary entry
        # labels even for a Profile explicitly configured as "no indent". The
        # real semantic reset happens in Layout Core after this composition
        # boundary; show geometry without falsely presenting those temporary
        # labels as meaningful headword decisions.
        neutral = indent_type_label(page_settings) == "无明显缩进"
        trace.add_layout(
            "physical_rows", "物理行检测",
            ("物理行与行首位置聚类，仅反映几何观察。当前为【无明显缩进】，"
             "临时 entry/body 不具词条含义，统一显示为未分类；"
             "原始临时标签保留在诊断数据中。" if neutral else
             "Page Design 原始物理行与正文栏范围；"
             "此时的 entry/body 为临时标签，尚未完成 Profile 语义和视觉复核。"),
            layout,
            details={
                "profile_indent_mode": indent_type_label(page_settings),
                "role_status": "not_classified" if neutral else "provisional",
                **({"skipped_semantic_stages": [
                    "基础行角色", "缩进语义判定", "正文缩进族调整",
                    "视觉一致性复核", "缺失缩进恢复",
                ], "next_visible_stage": "符号证据融合"} if neutral else {}),
            },
            provisional_no_indent=neutral,
        )
    normalize_layout_roles(layout)
    if trace is not None and not neutral:
        trace.add_layout(
            "initial_roles", "基础行角色",
            "由物理行和初步缩进族得到的临时角色；"
            "尚未合并大字头和符号证据。",
            layout,
            details={"profile_indent_mode": indent_type_label(page_settings),
                     "role_status": "provisional"},
        )
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
