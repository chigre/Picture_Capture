from __future__ import annotations

"""Make the Layout diagnostic overlay show the geometry ordinary drawing uses.

The detector path resolves per-page geometry through Page Understanding.  The
visual overlay must consume that exact policy result rather than run a second,
independent reliable-layout detector, otherwise the user can see one C2/gutter
while ordinary VB scans another.
"""

from typing import Any

from .dictionary_page_layout_policy import resolve_page_layout_policy
from .image_utils import build_analysis_image
from .page_understanding import understand_page
from .processing import ORDINARY_AUTO_LAYOUT_FIELDS, _geometry_from_page_understanding


def shared_snapshot_for_app(app: Any) -> Any:
    """Return a LayoutVisualizationSnapshot from the ordinary shared geometry."""
    from . import layout_visualization_ui as ui

    if getattr(app, "image", None) is None:
        raise RuntimeError("没有可显示的页面图像")

    key = ui._layout_cache_key(app)
    if (
        getattr(app, "_layout_visualization_snapshot_key", None) == key
        and getattr(app, "_layout_visualization_snapshot", None) is not None
    ):
        return app._layout_visualization_snapshot

    effective = app._current_effective_profile_settings()
    page_index = max(0, int(getattr(app, "current_index", 0)))
    analysis = build_analysis_image(app.image, effective)
    try:
        understanding = understand_page(
            analysis,
            effective,
            page_index=page_index,
        )
        geometry = _geometry_from_page_understanding(understanding)
        used = understanding.page_settings

        # Re-read the policy estimate only for diagnostics (raw/method/confidence).
        # This is the same projection policy used by understand_page, not the
        # unrelated reliable-fusion detector that used to power the overlay.
        _policy_settings, estimate, _policy_applied = resolve_page_layout_policy(
            analysis,
            effective,
            page_index=page_index,
        )

        raw: dict[str, int] = {}
        if estimate is not None:
            for field, _switch in ORDINARY_AUTO_LAYOUT_FIELDS:
                try:
                    raw[field] = int(getattr(estimate, field))
                except (AttributeError, TypeError, ValueError):
                    pass

        used_values = {
            "columns": int(getattr(used, "columns", len(geometry.column_starts))),
            "start_y": int(getattr(used, "start_y", geometry.top)),
            "manual_x": int(
                getattr(
                    used,
                    "manual_x",
                    geometry.column_starts[0] if geometry.column_starts else 0,
                )
            ),
            "column_width": int(
                getattr(
                    used,
                    "column_width",
                    geometry.column_widths[0] if geometry.column_widths else 0,
                )
            ),
            "gutter": int(getattr(used, "gutter", 0)),
            "character_height": int(getattr(used, "character_height", 0)),
            "row_padding": int(getattr(used, "row_padding", 0)),
            "bottom_y": int(getattr(geometry, "bottom", 0)),
        }

        method = "page_understanding"
        if estimate is not None:
            estimate_method = str(getattr(estimate, "method", "projection") or "projection")
            method = f"page_understanding:{estimate_method}"

        confidence = None
        if estimate is not None and getattr(estimate, "confidence", None) is not None:
            try:
                confidence = float(getattr(estimate, "confidence"))
            except (TypeError, ValueError):
                confidence = None

        snapshot = ui.LayoutVisualizationSnapshot(
            geometry=geometry,
            method=method,
            confidence=confidence,
            auto_enabled=bool(getattr(effective, "ordinary_auto_layout", False)),
            applied_fields=dict(understanding.applied_layout_fields),
            raw_estimate=raw,
            used_values=used_values,
        )
        app._layout_visualization_snapshot_key = key
        app._layout_visualization_snapshot = snapshot
        return snapshot
    finally:
        try:
            analysis.close()
        except Exception:
            pass


def install_shared_layout_visualization_source() -> None:
    """Patch the existing overlay before the v3 summary wrapper imports it."""
    from . import layout_visualization_ui as ui

    ui._snapshot_for_app = shared_snapshot_for_app
