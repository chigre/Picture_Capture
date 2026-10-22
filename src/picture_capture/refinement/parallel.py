"""Spawn-safe page computations and single-coordinator PDIC commits for Y refinement.

Workers are strictly read-only: original pixels/PDIC/PPP/SECTION/Profile and
human review companions are snapshotted before computing. The parent GUI's
batch-runner thread alone validates and atomically commits the page.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from ..models import AppSettings


def refinement_uses_page_layout(settings: AppSettings) -> bool:
    """Whether explicit Y refinement needs per-page physical fields (JSON or GPU)."""
    if not bool(getattr(settings, "ordinary_auto_layout", False)):
        return False
    from .layoutrows import requested_refinement_fields

    return bool(requested_refinement_fields(settings))


def _page_has_usable_refinement_json(page: Path, page_index: int,
                                    settings: AppSettings) -> bool:
    """Cheap parent-side preflight; no decoding scan pixels or launching Paddle."""
    from PIL import Image
    from .layoutrows import cached_refinement_settings

    try:
        with Image.open(page) as opened:
            size = opened.size
        return cached_refinement_settings(
            page, size, settings, int(page_index),
        ) is not None
    except (OSError, ValueError, TypeError):
        return False


def configured_refine_workers(page_count: int, *, cpus: int | None = None,
                              configured: str | None = None,
                              settings: AppSettings | None = None,
                              fixed_half_gutter: bool = False,
                              cache_pages: tuple[tuple[Path, int], ...] | None = None) -> int:
    """Bound GPU model ownership and full-page illustration masking.

    A Paddle-backed per-page Auto Layout estimate can allocate a full GPU
    detector in *each* spawned worker. Keep one persistent worker for that
    path; fixed half-gutter bypasses Layout and may still use two CPU workers
    for disposable illustration masks. No subprocess ever writes PDIC.
    """
    if configured is None:
        from ..runtime_environment import runtime_setting
        configured = str(runtime_setting("paddle_cpu_workers", "auto") or "auto")
    try:
        requested = int(configured)
    except (TypeError, ValueError):
        requested = 2
    available = max(1, int(cpus if cpus is not None else os.cpu_count() or 1))
    workers = max(1, min(int(page_count) or 1, available, max(1, requested)))
    if settings is not None and not fixed_half_gutter and refinement_uses_page_layout(settings):
        # The optional illustration auto-detection can own GPU resources too.
        mask_enabled = bool(getattr(settings, "layout_mask_illustrations", False))
        mask_reuse = bool(getattr(settings, "layout_mask_illustrations_use_existing", False))
        if mask_enabled and not mask_reuse:
            return 1
        # Check EVERY selected page; mixed cache misses still use one persistent
        # GPU worker. Fully cached batches never enter the heavy detector.
        if not cache_pages or not all(
            _page_has_usable_refinement_json(page, index, settings)
            for page, index in cache_pages
        ):
            return 1
        # Existing JSON + optional existing PPP: safe to dispatch 4 by default
        # or honor the explicit Environment Center 8-worker configuration.
        if str(configured).lower() in ("auto", "", "none"):
            workers = min(max(1, int(page_count)), available, 4)
        return workers
    if fixed_half_gutter or bool(getattr(settings, "layout_mask_illustrations", False)):
        return min(workers, 2)
    return workers


def _inputs_for_page(page: Path) -> tuple[Path, ...]:
    from ..project_storage import (
        pdic_path_for_image, ppp_read_path_for_image,
        ppp_write_path_for_image, profile_path, settings_path,
        page_sections_path_for_image, page_sections_read_path_for_image,
        simplified_review_path_for_image, manifest_path,
    )
    paths = (
        page, pdic_path_for_image(page),
        ppp_read_path_for_image(page), ppp_write_path_for_image(page),
        page_sections_path_for_image(page), page_sections_read_path_for_image(page),
        simplified_review_path_for_image(page),
        profile_path(page.parent), settings_path(page.parent),
        manifest_path(page.parent),
    )
    return tuple(dict.fromkeys(paths))


def _fingerprints(paths: tuple[Path, ...]) -> tuple[tuple[str, str | None], ...]:
    result = []
    for path in paths:
        try:
            payload = path.read_bytes()
        except FileNotFoundError:
            digest = None
        else:
            digest = hashlib.sha256(payload).hexdigest()
        result.append((str(path), digest))
    return tuple(result)


def refine_page_job(image_path: str, settings: AppSettings, page_index: int,
                    fixed_half_gutter: bool = False,
                    require_cached_layout: bool = False) -> dict[str, Any]:
    """Compute on one page in a Windows-spawned worker. NEVER write any file."""
    page = Path(image_path)
    from ..formats import read_pdic, pdic_path
    from ..image_utils import normalize_page_rgb
    from ..processing_core import refine_existing_entries
    from .analysis import (
        reset_refinement_layout_audit, read_refinement_layout_audit,
        finish_refinement_layout_audit,
        reset_refinement_layout_source, read_refinement_layout_source,
        finish_refinement_layout_source,
    )
    from PIL import Image

    expects_layout = (
        not fixed_half_gutter and refinement_uses_page_layout(settings)
    )
    mode = ("fixed_half_gutter" if fixed_half_gutter else
            "per_page_layout" if expects_layout else "profile_geometry")
    try:
        inputs = _inputs_for_page(page)
        before_hashes = _fingerprints(inputs)
        entries = read_pdic(pdic_path(page))
        if not entries:
            return {"page": image_path, "index": int(page_index),
                    "skipped": 1, "mode": mode,
                    "reason": "当前页没有已有 PDIC 词条；版面测量未执行"}
        with Image.open(page) as opened:
            image = normalize_page_rgb(opened)
        try:
            if require_cached_layout and not _page_has_usable_refinement_json(
                page, page_index, settings,
            ):
                raise RuntimeError(
                    "并行模式所需 LayoutRows 缓存已失效；拒绝在 CPU 并行进程中启动 GPU 重评估"
                )
            kwargs = {"fixed_half_gutter": True} if fixed_half_gutter else {}
            token = reset_refinement_layout_audit()
            source_token = reset_refinement_layout_source()
            try:
                refined, stats = refine_existing_entries(
                    image, entries, settings, profile_page_index=int(page_index),
                    source_image_path=page, **kwargs,
                )
                measured = read_refinement_layout_audit()
                layout_source = read_refinement_layout_source()
            finally:
                finish_refinement_layout_source(source_token)
                finish_refinement_layout_audit(token)
            if expects_layout and measured != 1:
                raise RuntimeError(
                    f"本页应执行一次版面参数测量，实际执行 {measured} 次；拒绝提交"
                )
            size = image.size
        finally:
            image.close()
        if _fingerprints(inputs) != before_hashes:
            return {"page": image_path, "index": int(page_index),
                    "skipped": 1, "mode": mode,
                    "reason": "计算期间原图或相关文件发生变化"}
        return {
            "page": image_path, "index": int(page_index),
            "mode": mode, "layout_measured": int(measured),
            "layout_source": layout_source,
            "fingerprints": before_hashes,
            "before": tuple((e.word, int(e.x), int(e.y)) for e in entries),
            "after": tuple((int(e.x), int(e.y)) for e in refined),
            "size": size, "stats": stats,
        }
    except Exception as exc:
        # Other pages can finish; this page has not written anything.
        return {"page": image_path, "index": int(page_index),
                "skipped": 1, "mode": mode,
                "reason": f"{type(exc).__name__}: {exc}"}


def _edit_original_pdic(raw: bytes, before: tuple, after: tuple,
                        image_width: int) -> bytes:
    """Change only saved coordinate fields, preserving all other original bytes.

    No BOM, encoding, newline, extra PDIC columns, word or page-link
    normalization is permitted. Unsupported encodings fail closed.
    """
    from ..text.encoding import decode_text_bytes

    decoded, encoding = decode_text_bytes(raw)
    if decoded.encode(encoding) != raw:
        raise ValueError("PDIC 编码无法无损往返，已拒绝改写")
    tokens = re.split(r"(\r\n|\n|\r)", decoded)
    output: list[str] = []
    index = 0
    for offset in range(0, len(tokens), 2):
        line = tokens[offset]
        ending = tokens[offset + 1] if offset + 1 < len(tokens) else ""
        if not line.strip():
            output.extend((line, ending))
            continue
        if index >= len(before):
            raise ValueError("PDIC 行数比计算快照更多")
        fields = line.split("#")
        if len(fields) < 3:
            raise ValueError("无法安全解析原始 PDIC 坐标字段")
        word, old_x, old_y = before[index]
        if (fields[0] != word or int(float(fields[1])) != old_x
                or int(float(fields[2])) != old_y):
            raise ValueError("PDIC 源记录与计算快照不匹配")
        new_x, new_y = after[index]
        if (old_x, old_y) != (new_x, new_y):
            fields[1], fields[2] = str(new_x), str(new_y)
            # Existing percentage fields follow the historic PDIC width basis.
            if len(fields) >= 5:
                fields[3] = f"{round(new_x / image_width * 100, 2):g}"
                fields[4] = f"{round(new_y / image_width * 100, 2):g}"
            line = "#".join(fields)
        output.extend((line, ending))
        index += 1
    if index != len(before) or index != len(after):
        raise ValueError("PDIC 行数与原始快照不匹配")
    return "".join(output).encode(encoding)


def _atomic_bytes(path: Path, payload: bytes, *, expected_sha: str) -> bool:
    """Atomic one-file publication with last-moment source revalidation."""
    from ..project_storage import note_page_artifact_edit

    original = path.read_bytes()
    if hashlib.sha256(original).hexdigest() != expected_sha:
        raise ValueError("PDIC 提交前被修改，取消覆盖")
    if original == payload:
        return False
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
            delete=False,
        ) as file:
            temp = Path(file.name)
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
            raise ValueError("PDIC 提交前出现并发修改，取消覆盖")
        os.replace(temp, path)
        temp = None
        note_page_artifact_edit(path)
        return True
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def commit_refined_page_result(page_index: int, result: dict[str, Any],
                               ownership_check=None) -> dict[str, Any]:
    """Called ONLY in parent batch runner, never from a child process.

    Related files are read-only. Existing cross-file XY-linked review data
    vetoes a coordinate move instead of being partially migrated.
    """
    page = Path(result["page"])
    if result.get("skipped"):
        return {"index": int(page_index), "page": page.name,
                "skipped": 1, "mode": result.get("mode"),
                "reason": result.get("reason", "跳过")}
    if int(page_index) != int(result["index"]):
        return {"index": int(page_index), "page": page.name,
                "skipped": 1, "reason": "页面身份不符"}

    from ..formats import pdic_path, read_pdic
    from .guard import validate_refined_markers
    from ..models import Entry
    try:
        if ownership_check is not None and not ownership_check(int(page_index)):
            raise ValueError("当前页已由人工操作占用")
        snapshot = tuple(result["fingerprints"])
        if _fingerprints(tuple(Path(p) for p, _ in snapshot)) != snapshot:
            raise ValueError("源文件、PPP、SECTION 或 Profile 已变化")
        old = tuple(result["before"])
        new = tuple(result["after"])
        if len(old) != len(new):
            raise ValueError("词条数发生变化")
        stored = read_pdic(pdic_path(page))
        if tuple((x.word, int(x.x), int(x.y)) for x in stored) != old:
            raise ValueError("PDIC 文字或坐标发生变化")
        refined = [Entry(word=entry.word, x=int(x), y=int(y),
                         current_page=entry.current_page,
                         previous_page=entry.previous_page,
                         next_page=entry.next_page)
                   for entry, (x, y) in zip(stored, new)]
        validate_refined_markers(page, stored, refined, tuple(result["size"]))
        if not any((a.x, a.y) != (b.x, b.y) for a, b in zip(stored, refined)):
            return {"index": int(page_index), "page": page.name,
                    **result["stats"], "skipped": 0, "saved": 0,
                    "mode": result.get("mode"),
                    "layout_measured": int(result.get("layout_measured", 0)),
                    "layout_source": result.get("layout_source", "unknown")}
        pdic = pdic_path(page)
        raw = pdic.read_bytes()
        expected = dict(snapshot).get(str(pdic))
        if expected is None or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("PDIC 提交时源版本不符")
        payload = _edit_original_pdic(raw, old, new, max(1, int(result["size"][0])))
        # The page must remain worker-owned until this coordinator finishes.
        if ownership_check is not None and not ownership_check(int(page_index)):
            raise ValueError("提交期间页面归属变化")
        if _fingerprints(tuple(Path(p) for p, _ in snapshot)) != snapshot:
            raise ValueError("提交前关联文件版本变化")
        saved = _atomic_bytes(pdic, payload, expected_sha=expected)
        return {"index": int(page_index), "page": page.name,
                **result["stats"], "skipped": 0, "saved": int(saved),
                "mode": result.get("mode"),
                "layout_measured": int(result.get("layout_measured", 0)),
                "layout_source": result.get("layout_source", "unknown")}
    except (ValueError, OSError, UnicodeError) as exc:
        return {"index": int(page_index), "page": page.name,
                "skipped": 1, "reason": str(exc)}
