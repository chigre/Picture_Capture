from __future__ import annotations

"""Fast physical Layout understanding shared by display and ordinary drawing.

This module deliberately stops after physical page layout and final line roles.
It does not run sampled-symbol evidence, semantic entry enrichment, OCR, or
candidate fusion.  The result is cached by analysis-image content and settings
so 【显示Layout】 and 【普通画线】 can reuse exactly the same role assignment.
"""

from collections import OrderedDict
import hashlib
import math
from typing import Any

from PIL import Image

from .dictionary_page_layout_policy import infer_dictionary_page_layout
from .layout_physical_indent import (
    _body_semantic_modes,
    _suppress_display_head_duplicate_entries,
    normalize_layout_roles,
)
from .models import AppSettings
from .page_understanding import (
    PageUnderstanding,
    _apply_explicit_indent_semantics,
    _generic_body_indent_is_proven,
    _physical_reliable,
    uses_cjk_role_model,
)
from .symbol_evidence import SymbolEvidenceResult


_CACHE_LIMIT = 6
_LAYOUT_CACHE: "OrderedDict[tuple[Any, ...], PageUnderstanding]" = OrderedDict()


def _image_fingerprint(image: Image.Image) -> tuple[Any, ...]:
    """Content key that survives rebuilding the same denoised PIL image."""
    digest = hashlib.blake2b(image.tobytes(), digest_size=16).digest()
    return (str(image.mode), tuple(image.size), digest)


def _settings_fingerprint(settings: AppSettings) -> str:
    # AppSettings is a dataclass-like configuration object. repr() intentionally
    # over-invalidates: changing an unrelated setting may miss the cache, but it
    # can never make stale Layout geometry look valid.
    return repr(settings)


def clear_layout_understanding_cache() -> None:
    _LAYOUT_CACHE.clear()


def _resolve_near_tied_body_lanes(layout: Any) -> None:
    """Use explicit indent polarity to break ties between stable physical lanes.

    Physical clustering is intentionally independent of semantics.  A problem
    remains when two stable lanes have almost equal support: choosing body by
    support alone can flip the meaning of a whole column because of a one-row
    count difference.  In that near-tie case the Profile's explicit polarity is
    authoritative: 正文缩进 => the inward/larger-indent stable lane is body;
    词头缩进 => the outer/smaller-indent stable lane is body.

    Sparse/singleton lanes stay fully eligible as entry evidence, but are not
    allowed to steal the body seed from a well-supported lane.
    """
    indent_type = str(getattr(layout, "indent_type", "body") or "body")
    if indent_type == "none":
        return

    reference = float(getattr(layout, "ordinary_line_height", 0.0) or 0.0)
    reference_arg = reference if reference > 0 else None

    for column in list(getattr(layout, "columns", []) or []):
        modes = list(getattr(column, "indent_modes", []) or [])
        if len(modes) < 2:
            continue

        supports = [int(getattr(mode, "support", 0) or 0) for mode in modes]
        max_support = max(supports, default=0)
        if max_support < 2:
            continue

        major_threshold = max(2, int(math.ceil(float(max_support) * 0.72)))
        major_modes = [
            mode for mode in modes
            if int(getattr(mode, "support", 0) or 0) >= major_threshold
        ]
        if len(major_modes) < 2:
            continue

        if indent_type == "body":
            desired_body = max(
                major_modes,
                key=lambda mode: float(getattr(mode, "center", 0.0) or 0.0),
            )
        else:
            desired_body = min(
                major_modes,
                key=lambda mode: float(getattr(mode, "center", 0.0) or 0.0),
            )

        if desired_body is getattr(column, "body_mode", None):
            continue

        body_ids = _body_semantic_modes(column, desired_body, reference_arg)
        body_centers = [
            float(getattr(mode, "center", 0.0) or 0.0)
            for mode in modes
            if id(mode) in body_ids
        ]
        body_min = min(body_centers)
        body_max = max(body_centers)

        for line in list(getattr(column, "lines", []) or []):
            line.role = "body"
        for mode in modes:
            mode.role = "body"

        if indent_type == "headword":
            entry_modes = [
                mode for mode in modes
                if id(mode) not in body_ids
                and float(getattr(mode, "center", 0.0) or 0.0) > body_max
            ]
        else:
            entry_modes = [
                mode for mode in modes
                if id(mode) not in body_ids
                and float(getattr(mode, "center", 0.0) or 0.0) < body_min
            ]

        for mode in entry_modes:
            mode.role = "entry"
            for line in list(getattr(mode, "lines", []) or []):
                line.role = "entry"

        column.body_mode = desired_body
        column.entry_modes = list(entry_modes)

    _suppress_display_head_duplicate_entries(layout)


def understand_layout_core(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
) -> PageUnderstanding:
    """Return physical Layout + final line roles, with no semantic/OCR layers."""
    key = (
        _image_fingerprint(image),
        _settings_fingerprint(settings),
        int(page_index),
    )
    cached = _LAYOUT_CACHE.get(key)
    if cached is not None:
        _LAYOUT_CACHE.move_to_end(key)
        return cached

    layout, page_settings, applied = infer_dictionary_page_layout(
        image,
        settings,
        page_index=int(page_index),
    )
    _apply_explicit_indent_semantics(layout, page_settings)
    # The policy finalizer normally does this too. Calling it explicitly here
    # makes the fast path independent of installer order and guarantees that the
    # cached object contains the same final entry/body roles ordinary drawing uses.
    normalize_layout_roles(layout)
    _resolve_near_tied_body_lanes(layout)

    physical = _physical_reliable(layout)
    cjk = uses_cjk_role_model(page_settings)
    generic_body = bool(
        not cjk
        and physical
        and _generic_body_indent_is_proven(layout)
    )
    role_model = "cjk" if cjk else "generic"
    layout.reason += (
        f"; page_understanding={role_model}:layout_core"
        f" physical_reliable={int(physical)}"
        f" semantic_reliable=0"
        f" generic_body_indent={int(generic_body)}"
        f" indent_semantics={layout.indent_type}"
        f" symbol_markers=0"
    )
    result = PageUnderstanding(
        layout=layout,
        page_settings=page_settings,
        applied_layout_fields=dict(applied),
        role_model=role_model,
        physical_reliable=physical,
        semantic_reliable=False,
        semantic_entries=[],
        generic_body_indent_reliable=generic_body,
        family_offset_ratio=None,
        symbol_evidence=SymbolEvidenceResult(markers=[]),
    )

    _LAYOUT_CACHE[key] = result
    _LAYOUT_CACHE.move_to_end(key)
    while len(_LAYOUT_CACHE) > _CACHE_LIMIT:
        _LAYOUT_CACHE.popitem(last=False)
    return result