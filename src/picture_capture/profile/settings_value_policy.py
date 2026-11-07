"""Canonical AppSettings assignment policy and static compatibility aliases.

Root models retain dataclass field ordering, constructor and pickle identity.
All normalization and validation branches execute here. Historical module
patch points are supplied by the original methods at call time.
"""
from __future__ import annotations

from typing import Any, Callable


def normalize_display_opacity(value: object, default: float = 40.0, *, math_module: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not math_module.isfinite(number):
        number = float(default)
    return max(0.0, min(100.0, number))


def app_settings_storage_alias(storage_name: str) -> property:
    """Return a static compatibility alias backed by an existing dataclass slot."""
    def getter(settings):
        return getattr(settings, storage_name)

    def setter(settings, value):
        setattr(settings, storage_name, value)

    return property(getter, setter)


def assign_setting_value(
    settings: Any, name: str, value: object, *,
    opacity_normalizer: Callable[[object], float],
) -> None:
    """Validate canonical setting assignments before mutating slotted fields."""
    # Preserve the former runtime-property contract now that these values
    # are native dataclass fields: construction and later assignments are
    # both normalized immediately rather than only at render/save time.
    if name in {"guide_opacity", "headword_marker_opacity", "illustration_fill_opacity"}:
        value = opacity_normalizer(value)
    if name == "crop_width_percent":
        try:
            ratio = float(value)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("切图宽度须在1–100%之间") from exc
        if not 1.0 <= ratio <= 100.0:
            raise ValueError("切图宽度须在1–100%之间")
        value = ratio
    if name == "physical_row_projection_width_percent":
        try:
            value = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("物理行墨迹投影采样宽度必须是 10–100% 的数字。") from exc
        if not 10.0 <= value <= 100.0:  # also rejects NaN/infinity
            raise ValueError("物理行墨迹投影采样宽度必须在 10–100% 单栏宽之间。")
    if name.startswith("separator_y_ink_safe_") and name != "separator_y_ink_safe_gap":
        allowed = {
            "separator_y_ink_safe_max_fraction": (0.01, 0.30),
            "separator_y_ink_safe_ink_threshold": (0.0, 255.0),
            "separator_y_ink_safe_existing_ink_ratio": (0.0, 0.20),
            "separator_y_ink_safe_gap_ink_ratio": (0.0, 0.10),
        }
        if name in allowed:
            try:
                numeric = float(value)
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError(f"{name} 必须是数字。") from exc
            low, high = allowed[name]
            if not low <= numeric <= high:
                raise ValueError(f"{name} 必须在 {low}–{high} 之间。")
            if name == "separator_y_ink_safe_ink_threshold":
                if not numeric.is_integer():
                    raise ValueError(f"{name} 必须是整数。")
                value = int(numeric)
            else:
                value = numeric
    object.__setattr__(settings, name, value)
