from __future__ import annotations

"""Persistent physical-row cache and fast row-only recovery.

The cache deliberately stores *physical* page facts only: body bounds, column
geometry and recovered row boxes.  Entry/body semantics, symbol evidence and
large-head evidence are intentionally excluded so downstream QA can compute
"all physical rows - current PDIC markers" without inheriting stale semantic
classifications.

For unlined-row QA the fast path first reuses this sidecar.  On a cache miss it
recovers rows from the Project/Profile geometry with projection only.  The full
reliable Layout Core (and therefore Paddle layout detection) is reserved for the
rare case where that fixed-geometry physical recovery is clearly unreliable.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
import hashlib
import json
import os
import tempfile

import numpy as np
from PIL import Image, ImageOps

from .layout_transform import LayoutTransform
from .project_storage import data_root, is_managed_project, qt_root


CACHE_FORMAT = "picture-capture-layout-rows-v1"
CACHE_ALGORITHM_VERSION = 1
CACHE_DIRNAME = "LayoutRows"

# (project_root, image_path, page_index, settings)
_CAPTURE_TARGET: ContextVar[tuple[Path, Path, int, Any] | None] = ContextVar(
    "picture_capture_layout_rows_target",
    default=None,
)


def layout_rows_cache_path(project_root: Path, image_path: Path) -> Path:
    root = Path(project_root)
    base = data_root(root) if is_managed_project(root) else qt_root(root)
    return base / CACHE_DIRNAME / f"{Path(image_path).stem}.json"


def _settings_fingerprint(settings: Any) -> str:
    # Deliberately over-invalidates rather than under-invalidates.  A display-only
    # setting change may rebuild one cache entry, but a physical/Profile change
    # can never leave stale row geometry looking valid.
    text = repr(settings).encode("utf-8", errors="replace")
    return hashlib.blake2b(text, digest_size=16).hexdigest()


def _image_fingerprint(image_path: Path, source_size: tuple[int, int]) -> dict[str, Any]:
    path = Path(image_path)
    try:
        stat = path.stat()
        size_bytes = int(stat.st_size)
        mtime_ns = int(stat.st_mtime_ns)
    except OSError:
        size_bytes = -1
        mtime_ns = -1
    return {
        "name": path.name,
        "size_bytes": size_bytes,
        "mtime_ns": mtime_ns,
        "source_size": [int(source_size[0]), int(source_size[1])],
    }


def _same_image_fingerprint(
    payload: dict[str, Any],
    image_path: Path,
    source_size: tuple[int, int] | None,
) -> bool:
    image = payload.get("image")
    if not isinstance(image, dict):
        return False
    path = Path(image_path)
    # Different images may share a stem (e.g. page.png and page.jpg), hence
    # the same sidecar path. Never reuse geometry for another source name.
    if image.get("name") != path.name:
        return False
    try:
        stat = path.stat()
        if int(image.get("size_bytes", -2)) != int(stat.st_size):
            return False
        if int(image.get("mtime_ns", -2)) != int(stat.st_mtime_ns):
            return False
    except (OSError, TypeError, ValueError, OverflowError):
        return False
    if source_size is not None:
        raw = image.get("source_size")
        try:
            cached = (int(raw[0]), int(raw[1]))
        except (TypeError, ValueError, IndexError):
            return False
        if cached != (int(source_size[0]), int(source_size[1])):
            return False
    return True


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _layout_is_physically_reliable(layout: Any) -> bool:
    columns = list(getattr(layout, "columns", []) or [])
    if not columns:
        return False
    populated = sum(bool(list(getattr(column, "lines", []) or [])) for column in columns)
    line_count = sum(len(list(getattr(column, "lines", []) or [])) for column in columns)
    reference = float(getattr(layout, "ordinary_line_height", 0.0) or 0.0)
    return bool(
        populated >= max(1, len(columns) - 1)
        and line_count >= max(5, 3 * len(columns))
        and reference >= 4.0
    )


def _serialize_layout(layout: Any) -> dict[str, Any]:
    transform = getattr(getattr(layout, "transform", None), "kind", "identity")
    columns_payload: list[dict[str, Any]] = []
    for position, column in enumerate(list(getattr(layout, "columns", []) or [])):
        rows: list[dict[str, Any]] = []
        for line in list(getattr(column, "lines", []) or []):
            try:
                y0 = int(getattr(line, "y0"))
                y1 = int(getattr(line, "y1"))
            except (AttributeError, TypeError, ValueError):
                continue
            if y1 <= y0:
                continue
            anchor = getattr(line, "anchor_x", None)
            rows.append({
                "y0": y0,
                "y1": y1,
                "first_x": int(getattr(line, "first_x", 0) or 0),
                "anchor_x": None if anchor is None else int(anchor),
            })
        columns_payload.append({
            "index": int(getattr(column, "index", position) or position),
            "left": int(getattr(column, "left", 0) or 0),
            "right": int(getattr(column, "right", 1) or 1),
            "rows": rows,
        })

    source_size = tuple(getattr(layout, "source_size", (0, 0)) or (0, 0))
    canonical_size = tuple(getattr(layout, "canonical_size", source_size) or source_size)
    return {
        "transform": str(transform),
        "source_size": [int(source_size[0]), int(source_size[1])],
        "canonical_size": [int(canonical_size[0]), int(canonical_size[1])],
        "body_top": int(getattr(layout, "body_top", 0) or 0),
        "body_bottom": int(getattr(layout, "body_bottom", 1) or 1),
        "ordinary_line_height": float(getattr(layout, "ordinary_line_height", 1.0) or 1.0),
        "columns": columns_payload,
    }


def write_layout_rows_cache(
    project_root: Path,
    image_path: Path,
    page_index: int,
    settings: Any,
    layout: Any,
) -> Path | None:
    """Persist one reliable physical layout sidecar.

    Semantic roles are intentionally omitted.  A failed/unreliable layout never
    replaces a previously good cache file.
    """
    if not _layout_is_physically_reliable(layout):
        return None
    source_size = tuple(getattr(layout, "source_size", (0, 0)) or (0, 0))
    if len(source_size) != 2 or int(source_size[0]) <= 0 or int(source_size[1]) <= 0:
        return None
    path = layout_rows_cache_path(project_root, image_path)
    payload = {
        "format": CACHE_FORMAT,
        "algorithm_version": CACHE_ALGORITHM_VERSION,
        "page_index": int(page_index),
        "settings_fingerprint": _settings_fingerprint(settings),
        "image": _image_fingerprint(Path(image_path), (int(source_size[0]), int(source_size[1]))),
        "layout": _serialize_layout(layout),
    }
    _atomic_json(path, payload)
    return path


def _layout_from_payload(payload: dict[str, Any]) -> Any | None:
    raw = payload.get("layout")
    if not isinstance(raw, dict):
        return None
    try:
        source_size_raw = raw.get("source_size")
        canonical_size_raw = raw.get("canonical_size")
        source_size = (int(source_size_raw[0]), int(source_size_raw[1]))
        canonical_size = (int(canonical_size_raw[0]), int(canonical_size_raw[1]))
        transform = LayoutTransform(str(raw.get("transform") or "identity"))
        body_top = int(raw.get("body_top", 0))
        body_bottom = int(raw.get("body_bottom", body_top + 1))
        reference = float(raw.get("ordinary_line_height", 1.0))
    except (TypeError, ValueError, IndexError):
        return None

    columns: list[Any] = []
    for position, column_raw in enumerate(list(raw.get("columns") or [])):
        if not isinstance(column_raw, dict):
            continue
        try:
            left = int(column_raw.get("left", 0))
            right = int(column_raw.get("right", left + 1))
            index = int(column_raw.get("index", position))
        except (TypeError, ValueError):
            continue
        lines: list[Any] = []
        for row in list(column_raw.get("rows") or []):
            if not isinstance(row, dict):
                continue
            try:
                y0 = int(row.get("y0"))
                y1 = int(row.get("y1"))
                first_x = int(row.get("first_x", 0) or 0)
            except (TypeError, ValueError):
                continue
            if y1 <= y0:
                continue
            anchor_raw = row.get("anchor_x")
            try:
                anchor_x = None if anchor_raw is None else int(anchor_raw)
            except (TypeError, ValueError):
                anchor_x = None
            lines.append(SimpleNamespace(
                y0=y0,
                y1=y1,
                first_x=first_x,
                anchor_x=anchor_x,
                role="unknown",
            ))
        columns.append(SimpleNamespace(
            index=index,
            left=left,
            right=max(left + 1, right),
            lines=lines,
        ))

    layout = SimpleNamespace(
        transform=transform,
        source_size=source_size,
        canonical_size=canonical_size,
        body_top=body_top,
        body_bottom=max(body_top + 1, body_bottom),
        columns=columns,
        ordinary_line_height=max(1.0, reference),
        reliable=True,
        reason="layout_rows_cache",
    )
    return layout if _layout_is_physically_reliable(layout) else None


def load_layout_rows_cache(
    project_root: Path,
    image_path: Path,
    page_index: int,
    settings: Any,
    *,
    source_size: tuple[int, int] | None = None,
) -> Any | None:
    path = layout_rows_cache_path(project_root, image_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("format") != CACHE_FORMAT:
        return None
    try:
        version = int(payload.get("algorithm_version", 0) or 0)
        cached_page = int(payload.get("page_index", -1))
    except (TypeError, ValueError, OverflowError):
        return None
    if version != CACHE_ALGORITHM_VERSION:
        return None
    if cached_page != int(page_index):
        return None
    if str(payload.get("settings_fingerprint") or "") != _settings_fingerprint(settings):
        return None
    if not _same_image_fingerprint(payload, Path(image_path), source_size):
        return None
    return _layout_from_payload(payload)


def _profile_geometry(canonical_width: int, settings: Any) -> tuple[list[int], list[int]]:
    count = max(1, min(12, int(getattr(settings, "columns", 1) or 1)))
    width = max(8, int(getattr(settings, "column_width", 700) or 700))
    gutter = max(0, int(getattr(settings, "gutter", 0) or 0))
    x0 = max(0, int(getattr(settings, "manual_x", 0) or 0))
    raw_offsets = list(getattr(settings, "column_start_offsets", []) or [])
    starts: list[int] = []
    rights: list[int] = []
    for index in range(count):
        try:
            offset = int(round(float(raw_offsets[index]))) if index < len(raw_offsets) else 0
        except (TypeError, ValueError):
            offset = 0
        expected = x0 + index * (width + gutter) + offset
        left = max(0, min(max(0, canonical_width - 2), expected))
        right = max(left + 1, min(canonical_width, left + width))
        starts.append(left)
        rights.append(right)
    return starts, rights


def _robust_reference_from_runs(
    raw_runs: list[list[tuple[int, int]]],
    seed: float,
) -> float:
    prior = max(6.0, float(seed))
    heights = np.asarray([
        float(y1 - y0)
        for runs in raw_runs
        for y0, y1 in runs
        if y1 > y0 and prior * 0.60 <= (y1 - y0) <= prior * 2.20
    ], dtype=float)
    if heights.size >= 8:
        center = float(np.median(heights))
        deviation = np.abs(heights - center)
        mad = float(np.median(deviation)) if deviation.size else 0.0
        kept = heights[deviation <= max(2.0, 3.5 * mad)]
        if kept.size >= 8:
            center = float(np.median(kept))
            q10, q90 = (float(value) for value in np.percentile(kept, [10, 90]))
            if q90 - q10 <= max(4.0, center * 0.20):
                return max(6.0, center)
    return prior


def _fast_layout_geometry_is_plausible(layout: Any, settings: Any) -> bool:
    if not _layout_is_physically_reliable(layout):
        return False
    columns = list(getattr(layout, "columns", []) or [])
    expected = max(1, int(getattr(settings, "columns", len(columns)) or len(columns)))
    if len(columns) != expected:
        return False
    reference = max(6.0, float(getattr(layout, "ordinary_line_height", 1.0) or 1.0))
    for column in columns:
        lines = list(getattr(column, "lines", []) or [])
        if not lines:
            continue
        width = max(1, int(getattr(column, "right", 1)) - int(getattr(column, "left", 0)))
        fronts = np.asarray([
            max(0.0, float(getattr(line, "first_x", 0) or 0))
            for line in lines
        ], dtype=float)
        if fronts.size:
            # A fixed/Profile column whose median first ink is hundreds of pixels
            # inward is very likely translated relative to the scan.  That is the
            # signal to escalate to the reliable per-page detector.
            median_front = float(np.median(fronts))
            if median_front > max(reference * 3.2, width * 0.16):
                return False
    return True


def recover_physical_rows_fast(
    image: Image.Image,
    settings: Any,
    *,
    page_index: int = 0,
) -> Any | None:
    """Recover physical rows from Profile geometry without Paddle/semantic work."""
    from . import dictionary_page_design as base
    from .layout_detection import analysis_ink_mask
    from .layout_physical_indent import _credible_first_ink_x, projection_line_runs

    # projection_line_runs statically preserves long dense projection bands.

    source, canonical, transform, effective = base._analysis_page(
        image,
        settings,
        int(page_index),
    )
    try:
        gray = np.asarray(ImageOps.grayscale(canonical), dtype=np.uint8)
        page_ink = analysis_ink_mask(gray, effective)
        if page_ink.ndim != 2 or page_ink.size == 0 or not np.any(page_ink):
            return None

        top = max(0, min(canonical.height - 1, int(getattr(effective, "start_y", 0) or 0)))
        starts, rights = _profile_geometry(canonical.width, effective)
        seed = max(6.0, float(getattr(effective, "character_height", 26) or 26))

        def collect(scale: float, bottom: int) -> tuple[list[np.ndarray], list[list[tuple[int, int]]]]:
            strips: list[np.ndarray] = []
            runs: list[list[tuple[int, int]]] = []
            limit = max(top + 1, min(canonical.height, int(bottom)))
            for left, right in zip(starts, rights):
                column_width = max(1, int(right - left))
                lead_width = max(
                    24,
                    min(
                        column_width,
                        max(round(column_width * 0.42), round(max(6.0, scale) * 7.0), 96),
                    ),
                )
                strip = page_ink[top:limit, left:min(canonical.width, left + lead_width)]
                strips.append(strip)
                runs.append(projection_line_runs(strip, scale))
            return strips, runs

        strips, raw_runs = collect(seed, canonical.height)
        reference = _robust_reference_from_runs(raw_runs, seed)
        strips, raw_runs = collect(reference, canonical.height)
        last_ends = [int(y1) for runs in raw_runs for _y0, y1 in runs]
        if not last_ends:
            return None
        bottom = min(
            canonical.height,
            top + max(last_ends) + max(2, round(reference * 0.55)),
        )
        bottom = max(top + 1, int(bottom))
        strips, raw_runs = collect(reference, bottom)

        columns: list[Any] = []
        for position, (left, right, strip, runs) in enumerate(zip(starts, rights, strips, raw_runs)):
            lines: list[Any] = []
            for y0, y1 in runs:
                row = strip[int(y0):int(y1)]
                first_x = _credible_first_ink_x(row, reference)
                lines.append(SimpleNamespace(
                    y0=int(y0),
                    y1=int(y1),
                    first_x=int(first_x or 0),
                    anchor_x=None,
                    role="unknown",
                ))
            columns.append(SimpleNamespace(
                index=int(position),
                left=int(left),
                right=int(right),
                lines=lines,
            ))

        layout = SimpleNamespace(
            transform=transform,
            source_size=tuple(source.size),
            canonical_size=tuple(canonical.size),
            body_top=int(top),
            body_bottom=int(bottom),
            columns=columns,
            ordinary_line_height=float(reference),
            reliable=True,
            reason="fast_physical_rows:profile_projection",
        )
        return layout if _fast_layout_geometry_is_plausible(layout, effective) else None
    finally:
        try:
            canonical.close()
        except Exception:
            pass
        try:
            source.close()
        except Exception:
            pass


def resolve_physical_rows_layout(
    project_root: Path,
    image_path: Path,
    image: Image.Image,
    settings: Any,
    *,
    page_index: int = 0,
) -> tuple[Any | None, str]:
    """Resolve rows in priority order: persistent cache -> projection -> full Layout."""
    source_size = tuple(image.size)
    cached = load_layout_rows_cache(
        project_root,
        image_path,
        page_index,
        settings,
        source_size=source_size,
    )
    if cached is not None:
        return cached, "cache"

    fast = recover_physical_rows_fast(image, settings, page_index=page_index)
    if fast is not None:
        try:
            write_layout_rows_cache(project_root, image_path, page_index, settings, fast)
        except Exception:
            pass
        return fast, "fast_projection"

    # Rare fallback only.  This preserves correctness on pages whose scan drift,
    # unusual title geometry or damaged columns make fixed/Profile geometry
    # implausible.  Semantic evidence still is not needed by the caller, but the
    # reliable Layout Core owns the robust per-page geometry detector.
    from .image_utils import build_analysis_image
    from .layout_core_understanding import understand_layout_core

    analysis = build_analysis_image(image, settings)
    try:
        understanding = understand_layout_core(
            analysis,
            settings,
            page_index=int(page_index),
        )
    finally:
        try:
            analysis.close()
        except Exception:
            pass
    layout = getattr(understanding, "layout", None)
    if layout is None or not bool(getattr(understanding, "physical_reliable", False)):
        return None, "full_layout_unreliable"
    try:
        write_layout_rows_cache(project_root, image_path, page_index, settings, layout)
    except Exception:
        pass
    return layout, "full_layout"


@contextmanager
def capture_layout_rows(
    project_root: Path,
    image_path: Path,
    page_index: int,
    settings: Any,
) -> Iterator[None]:
    """Persist a full Layout Core result produced inside this context."""
    token = _CAPTURE_TARGET.set((
        Path(project_root),
        Path(image_path),
        int(page_index),
        settings,
    ))
    try:
        yield
    finally:
        _CAPTURE_TARGET.reset(token)


def publish_captured_layout(layout: Any, page_index: int) -> None:
    """Persist *layout* when the caller is inside an explicit capture context."""
    target = _CAPTURE_TARGET.get()
    if target is None:
        return
    project_root, image_path, target_index, target_settings = target
    if int(target_index) != int(page_index):
        return
    try:
        write_layout_rows_cache(
            project_root,
            image_path,
            target_index,
            target_settings,
            layout,
        )
    except Exception:
        # LayoutRows are a best-effort QA sidecar and must never make the
        # authoritative Layout calculation fail.
        pass


def install_layout_rows_persistence_runtime() -> None:
    """Compatibility no-op; Layout Core now publishes capture results statically."""
    return None


def install_layout_visualization_cache_context() -> None:
    """Compatibility no-op; visualization enters capture_layout_rows statically."""
    return None


__all__ = [
    "CACHE_ALGORITHM_VERSION",
    "CACHE_DIRNAME",
    "CACHE_FORMAT",
    "capture_layout_rows",
    "install_layout_rows_persistence_runtime",
    "install_layout_visualization_cache_context",
    "layout_rows_cache_path",
    "load_layout_rows_cache",
    "publish_captured_layout",
    "recover_physical_rows_fast",
    "resolve_physical_rows_layout",
    "write_layout_rows_cache",
]
