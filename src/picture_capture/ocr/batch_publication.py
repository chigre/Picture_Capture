from __future__ import annotations

"""Compensating publication for OCRed and PDIC in an existing-marker OCR job.

OCRed is an auxiliary text sidecar; PDIC is the marker source of truth.
Both individual writers are atomic, but the filesystem does not commit the
two files together. If the PDIC writer raises *without changing PDIC*, undo
the already published OCRed sidecar to its exact previous bytes (or remove
a newly created one). If PDIC changed despite throwing, never revert only
OCRed: report the ambiguous commit for explicit recovery.
Power loss, process termination, concurrent external writers and a failed
compensation remain outside this best-effort guarantee.
If the OCRed exporter raises after its own atomic replacement, the same
byte-exact OCRed compensation runs before PDIC publication is attempted.
"""

import os
from pathlib import Path
import tempfile
from typing import Any, Callable


_UNSPECIFIED_PDic_SNAPSHOT = object()
_UNSPECIFIED_OCRED_SNAPSHOT = object()


def _restore_ocred_bytes(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temp_path = Path(file.name)
            file.write(previous)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def publish_existing_pdic_ocr(
    ocred_path: Path,
    pdic_path: Path,
    texts: list[str],
    entries: list[Any],
    image_width: int,
    pages_info: tuple[str, str, str],
    *,
    export_ocred: Callable[..., Any],
    write_pdic: Callable[..., Any],
    expected_pdic_bytes: bytes | None | object = _UNSPECIFIED_PDic_SNAPSHOT,
    expected_ocred_bytes: bytes | None | object = _UNSPECIFIED_OCRED_SNAPSHOT,
) -> None:
    """Publish OCRed then PDIC, compensating OCRed on PDIC write errors."""
    try:
        previous = ocred_path.read_bytes()
    except FileNotFoundError:
        previous = None
    # A worker may spend minutes on OCR inference. Preserve manual OCRed
    # proofreading from another window/process that happened meanwhile.
    # Check before either sidecar export or PDIC write; direct callers can
    # omit this optional optimistic snapshot for backward compatibility.
    if (
        expected_ocred_bytes is not _UNSPECIFIED_OCRED_SNAPSHOT
        and previous != expected_ocred_bytes
    ):
        raise RuntimeError(
            "批量 OCR 发布前 OCRed 已被其他操作修改；"
            "未改写 OCRed 或 PDIC，避免覆盖人工校对内容"
        )
    # The PDIC writer can atomically publish bytes and subsequently raise.
    # In that case undoing only OCRed would create a mismatched pair.
    try:
        previous_pdic = pdic_path.read_bytes()
    except FileNotFoundError:
        previous_pdic = None
    # A long-running batch captured its source PDIC before OCR inference.
    # Refuse to publish if a new manual edit arrived after its last check.
    if (
        expected_pdic_bytes is not _UNSPECIFIED_PDic_SNAPSHOT
        and previous_pdic != expected_pdic_bytes
    ):
        raise RuntimeError(
            "批量 OCR 发布前 PDIC 已被其他操作修改；"
            "未改写 OCRed 或 PDIC，避免覆盖人工校对内容"
        )

    # An exporter can atomically replace OCRed and then raise from a later
    # hook. PDIC has not been called yet; restore this sidecar before letting
    # the failure escape, but only if its on-disk bytes actually changed.
    try:
        export_ocred(ocred_path, texts)
    except Exception as export_error:
        try:
            current_ocred = ocred_path.read_bytes()
        except FileNotFoundError:
            current_ocred = None
        except OSError as inspect_error:
            raise RuntimeError(
                "OCRed 导出报错，且无法核验 OCRed 是否已写入；"
                "未启动 PDIC 保存，请核查 OCRed："
                f"导出={export_error!r}；核查={inspect_error!r}"
            ) from export_error
        if current_ocred != previous:
            try:
                _restore_ocred_bytes(ocred_path, previous)
            except Exception as rollback_error:
                raise RuntimeError(
                    "OCRed 导出失败，且原文件回滚也失败；"
                    "未启动 PDIC 保存："
                    f"导出={export_error!r}；回滚={rollback_error!r}"
                ) from rollback_error
        raise

    # OCRed export can take time or invoke patched filesystem hooks.
    # If another editor writes PDIC during export, undo this OCRed sidecar
    # and refuse to overwrite their latest PDIC file.
    try:
        pdic_after_export = pdic_path.read_bytes()
    except FileNotFoundError:
        pdic_after_export = None
    except OSError as inspect_error:
        # The PDIC writer has not run: do not strand a freshly exported
        # OCRed beside an unverified PDIC. Best-effort compensation still
        # cannot make concurrent external sidecar writers transactional.
        try:
            _restore_ocred_bytes(ocred_path, previous)
        except Exception as rollback_error:
            raise RuntimeError(
                "无法核验导出后的 PDIC，且 OCRed 回滚失败；"
                "未启动 PDIC 保存，请人工核查两份文件："
                f"核查={inspect_error!r}；回滚={rollback_error!r}"
            ) from inspect_error
        raise RuntimeError(
            "无法核验导出后的 PDIC；已恢复原有 OCRed，"
            "未启动 PDIC 保存，请核查 PDIC："
            f"核查={inspect_error!r}"
        ) from inspect_error
    if pdic_after_export != previous_pdic:
        try:
            _restore_ocred_bytes(ocred_path, previous)
        except Exception as rollback_error:
            raise RuntimeError(
                "PDIC 在 OCRed 导出期间被修改，且 OCRed 回滚失败："
                f"回滚={rollback_error!r}"
            ) from rollback_error
        raise RuntimeError(
            "PDIC 在 OCRed 导出期间被其他操作修改；"
            "已恢复原有 OCRed，未覆盖人工校对的 PDIC"
        )
    try:
        write_pdic(pdic_path, entries, image_width, pages_info)
    except Exception as pdic_error:
        try:
            current_pdic = pdic_path.read_bytes()
        except FileNotFoundError:
            current_pdic = None
        except OSError as inspect_error:
            raise RuntimeError(
                "PDIC 保存报错，且无法读取 PDIC 确认是否已提交；"
                "不执行仅 OCRed 回滚，以免造成文件版本不一致："
                f"PDIC={pdic_error!r}；核查={inspect_error!r}"
            ) from pdic_error
        if current_pdic != previous_pdic:
            raise RuntimeError(
                "PDIC 保存报错，但磁盘 PDIC 已发生变化；"
                "未单独回滚 OCRed，请核查两份文件："
                f"PDIC={pdic_error!r}"
            ) from pdic_error
        try:
            _restore_ocred_bytes(ocred_path, previous)
        except Exception as rollback_error:
            raise RuntimeError(
                "PDIC 保存失败，OCRed 回滚也失败："
                f"PDIC={pdic_error!r}；OCRed={rollback_error!r}"
            ) from rollback_error
        raise
