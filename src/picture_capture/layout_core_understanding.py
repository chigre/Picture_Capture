from __future__ import annotations

"""Fast physical Layout understanding shared by display and ordinary drawing.

The core resolves physical page geometry and final line roles once, then adds
OCR-independent ordinary evidence from sampled structural symbols and oversized
display heads.  It never runs OCR or semantic parser fusion.  The result is
cached by analysis-image content and settings so 【显示Layout】 and 【普通画线】
reuse exactly the same final role assignment.
"""

from collections import OrderedDict
import hashlib
import math
from typing import Any

from PIL import Image

from .dictionary_page_layout_policy import infer_dictionary_page_layout
from .layout_physical_indent import (
    _suppress_display_head_duplicate_entries,
    normalize_layout_roles,
)
from .models import AppSettings
from .ordinary_evidence_fusion import promote_evidence_to_layout_roles
from .ordinary_large_head_evidence import detect_ordinary_large_head_entries
from .ordinary_symbol_evidence import detect_ordinary_symbol_entries
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


def _mode_interval(mode: Any) -> tuple[float, float]:
    """Return one physical lane interval in the same normalized-X space."""
    center = float(getattr(mode, "center", 0.0) or 0.0)
    tolerance = max(1.0, float(getattr(mode, "tolerance", 1.0) or 1.0))
    return center - tolerance, center + tolerance


def _body_lane_ids(
    modes: list[Any],
    body: Any,
    reference: float | None,
) -> set[int]:
    """Absorb lanes genuinely adjacent to body in physical-indent space."""
    body_center = float(getattr(body, "center", 0.0) or 0.0)
    body_lo, body_hi = _mode_interval(body)
    ref = max(6.0, float(reference)) if reference is not None else 40.0
    gap_limit = max(4.0, min(12.0, ref * 0.18))
    max_extension = max(14.0, min(28.0, ref * 0.50))

    absorbed: set[int] = {id(body)}
    changed = True
    while changed:
        changed = False
        for mode in modes:
            mode_id = id(mode)
            if mode_id in absorbed:
                continue
            lo, hi = _mode_interval(mode)
            if hi < body_lo:
                gap = body_lo - hi
            elif lo > body_hi:
                gap = lo - body_hi
            else:
                gap = 0.0
            proposed_lo = min(body_lo, lo)
            proposed_hi = max(body_hi, hi)
            if (
                gap <= gap_limit
                and proposed_lo >= body_center - max_extension
                and proposed_hi <= body_center + max_extension
            ):
                absorbed.add(mode_id)
                body_lo, body_hi = proposed_lo, proposed_hi
                changed = True
    return absorbed


def _resolve_directional_body_lanes(layout: Any) -> None:
    """Choose the body family from explicit indent polarity, not row counts."""
    indent_type = str(getattr(layout, "indent_type", "body") or "body")
    if indent_type == "none":
        # No-indent pages deliberately leave directional indentation out of the
        # entry decision.  Visual-symbol and large-head evidence can still
        # promote rows later in this module.
        for column in list(getattr(layout, "columns", []) or []):
            for line in list(getattr(column, "lines", []) or []):
                line.role = "body"
            for mode in list(getattr(column, "indent_modes", []) or []):
                mode.role = "body"
            column.entry_modes = []
        return

    reference = float(getattr(layout, "ordinary_line_height", 0.0) or 0.0)
    reference_arg = reference if reference > 0 else None

    for column in list(getattr(layout, "columns", []) or []):
        modes = list(getattr(column, "indent_modes", []) or [])
        if not modes:
            continue

        supports = [int(getattr(mode, "support", 0) or 0) for mode in modes]
        max_support = max(supports, default=0)
        if max_support <= 0:
            continue

        stable_threshold = max(2, int(math.ceil(float(max_support) * 0.25)))
        stable_modes = [
            mode
            for mode in modes
            if int(getattr(mode, "support", 0) or 0) >= stable_threshold
        ]
        if not stable_modes:
            stable_modes = [max(modes, key=lambda mode: int(getattr(mode, "support", 0) or 0))]

        if indent_type == "body":
            desired_body = max(
                stable_modes,
                key=lambda mode: float(getattr(mode, "center", 0.0) or 0.0),
            )
        else:
            desired_body = min(
                stable_modes,
                key=lambda mode: float(getattr(mode, "center", 0.0) or 0.0),
            )

        body_ids = _body_lane_ids(modes, desired_body, reference_arg)
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
                mode
                for mode in modes
                if id(mode) not in body_ids
                and float(getattr(mode, "center", 0.0) or 0.0) > body_max
            ]
        else:
            entry_modes = [
                mode
                for mode in modes
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


def _apply_universal_ordinary_evidence(
    image: Image.Image,
    understanding: PageUnderstanding,
    settings: AppSettings,
) -> tuple[int, int]:
    """OR-promote sampled-symbol and oversized-head evidence onto Layout rows."""
    symbol_entries = detect_ordinary_symbol_entries(image, understanding, settings)
    large_entries = detect_ordinary_large_head_entries(image, understanding, settings)
    symbol_promoted = promote_evidence_to_layout_roles(understanding, symbol_entries)
    large_promoted = promote_evidence_to_layout_roles(understanding, large_entries)
    # A large display glyph may occupy more than one recovered logical row.
    # Keep one entry boundary per display head after all evidence is promoted.
    _suppress_display_head_duplicate_entries(understanding.layout)
    return symbol_promoted, large_promoted


def understand_layout_core(
    image: Image.Image,
    settings: AppSettings,
    *,
    page_index: int = 0,
) -> PageUnderstanding:
    """Return physical Layout + final universal ordinary-mode line roles."""
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
    normalize_layout_roles(layout)
    _resolve_directional_body_lanes(layout)

    physical = _physical_reliable(layout)
    cjk = uses_cjk_role_model(page_settings)
    generic_body = bool(
        not cjk
        and physical
        and _generic_body_indent_is_proven(layout)
    )
    role_model = "cjk" if cjk else "generic"

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

    symbol_promoted, large_promoted = _apply_universal_ordinary_evidence(
        image,
        result,
        page_settings,
    )
    layout.reason += (
        f"; page_understanding={role_model}:layout_core"
        f" physical_reliable={int(physical)}"
        f" semantic_reliable=0"
        f" generic_body_indent={int(generic_body)}"
        f" indent_semantics={layout.indent_type}"
        f" ordinary_symbol_promoted={int(symbol_promoted)}"
        f" ordinary_large_head_promoted={int(large_promoted)}"
    )

    _LAYOUT_CACHE[key] = result
    _LAYOUT_CACHE.move_to_end(key)
    while len(_LAYOUT_CACHE) > _CACHE_LIMIT:
        _LAYOUT_CACHE.popitem(last=False)
    return result
