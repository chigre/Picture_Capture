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


def _read_optional_ocred_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _restore_ocred_bytes(
    path: Path,
    previous: bytes | None,
    *,
    expected_current: bytes | None | object = _UNSPECIFIED_OCRED_SNAPSHOT,
    verify_before_mutation: Callable[[], None] | None = None,
) -> None:
    """Stage compensation first, then recheck ownership just before mutation.

    Staging and fsync may be slow. A single check before staging lets a
    concurrent manual edit be overwritten by the eventual replace/unlink.
    This second check narrows that window but is not a filesystem CAS:
    non-cooperating writers can still race after the last read.
    """
    if previous is None:
        if (
            expected_current is not _UNSPECIFIED_OCRED_SNAPSHOT
            and _read_optional_ocred_bytes(path) != expected_current
        ):
            raise RuntimeError(
                "OCRed 在回滚前被其他操作修改；"
                "拒绝回滚覆盖人工校对内容，请人工核查两份文件"
            )
        # PDIC may change while an OCRed deletion is being prepared.
        # Recheck the other side of the pair immediately before unlinking.
        if verify_before_mutation is not None:
            verify_before_mutation()
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
        # A manual edit can land while the rollback temp file is written or
        # synced. Never replace it merely because the earlier read matched.
        if (
            expected_current is not _UNSPECIFIED_OCRED_SNAPSHOT
            and _read_optional_ocred_bytes(path) != expected_current
        ):
            raise RuntimeError(
                "OCRed 在回滚暂存期间被其他操作修改；"
                "拒绝回滚覆盖人工校对内容，请人工核查两份文件"
            )
        # Staging/fsync can outlast a concurrent PDIC write. Refuse to
        # restore old OCRed if the PDIC version is no longer established.
        if verify_before_mutation is not None:
            verify_before_mutation()
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _restore_ocred_if_unchanged(
    path: Path, previous: bytes | None, published: bytes | None,
    *,
    verify_before_mutation: Callable[[], None] | None = None,
) -> None:
    """Do not compensate over a sidecar edited after our export returned.

    This is an optimistic guard, not a cross-process compare-and-swap: an
    external writer can still race between this read and os.replace/unlink.
    """
    try:
        current = path.read_bytes()
    except FileNotFoundError:
        current = None
    if current != published:
        raise RuntimeError(
            "OCRed 在批量 OCR 发布后被其他操作修改；"
            "拒绝回滚覆盖人工校对内容，请人工核查两份文件"
        )
    # An exporter may succeed without changing the sidecar (or leave it
    # absent). In that case compensation has nothing to undo. In particular,
    # do not replace an identical file or unlink an absent one: a concurrent
    # editor could write after the version read but before that unnecessary
    # filesystem mutation. Still perform the read above to detect conflicts.
    if previous == published:
        return
    _restore_ocred_bytes(
        path, previous, expected_current=published,
        verify_before_mutation=verify_before_mutation,
    )


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
    expected_exported_ocred_bytes: bytes | None = None,
    validate_page_context: Callable[[], None] | None = None,
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

    # A page's SECTION sidecar may have changed during inference, altering
    # marker order / OCR reading lanes without changing PDIC itself. Validate
    # before touching OCRed, then again just before committing PDIC.
    if validate_page_context is not None:
        validate_page_context()
        # A full SECTION/source-image check may hash a large scan. Another
        # editor can replace either sidecar *during* that check, after our
        # initial snapshots but before OCRed export. In particular, never
        # overwrite a newly proofread OCRed file and then "restore" the stale
        # pre-check version. Check PDIC first and OCRed last to narrow the
        # window before export; this is still not a filesystem-level CAS.
        try:
            pdic_before_export = pdic_path.read_bytes()
        except FileNotFoundError:
            pdic_before_export = None
        except OSError as inspect_error:
            raise RuntimeError(
                "页面来源核验后无法再次读取 PDIC；"
                "未启动 OCRed 导出或 PDIC 保存，请人工核查"
            ) from inspect_error
        if pdic_before_export != previous_pdic:
            raise RuntimeError(
                "页面来源核验期间 PDIC 已被其他操作修改；"
                "未启动 OCRed 导出或 PDIC 保存，保留人工修改"
            )
        try:
            ocred_before_export = ocred_path.read_bytes()
        except FileNotFoundError:
            ocred_before_export = None
        except OSError as inspect_error:
            raise RuntimeError(
                "页面来源核验后无法再次读取 OCRed；"
                "未启动 OCRed 导出或 PDIC 保存，请人工核查"
            ) from inspect_error
        if ocred_before_export != previous:
            raise RuntimeError(
                "页面来源核验期间 OCRed 已被其他操作修改；"
                "未启动 OCRed 导出或 PDIC 保存，保留人工校对内容"
            )

    # An exporter can atomically replace OCRed and then raise from a later
    # hook. PDIC has not been called yet; restore this sidecar before letting
    # the failure escape, but only if its on-disk bytes actually changed.
    try:
        export_ocred(ocred_path, texts)
    except Exception as export_error:
        # A patchable exporter may have changed PDIC before raising. If so,
        # reverting only OCRed would leave an inconsistent committed pair.
        # Preserve both disk versions for manual recovery instead.
        try:
            pdic_after_failed_export = pdic_path.read_bytes()
        except FileNotFoundError:
            pdic_after_failed_export = None
        except OSError as inspect_error:
            raise RuntimeError(
                "OCRed 导出失败，且无法核验 PDIC 是否被修改；"
                "拒绝单侧回滚，请人工核查两份文件"
            ) from inspect_error
        if pdic_after_failed_export != previous_pdic:
            raise RuntimeError(
                "OCRed 导出失败，且导出期间 PDIC 已被修改；"
                "拒绝单侧回滚，请人工核查两份文件"
            ) from export_error
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
            # The worker supplies the canonical bytes for its own export.
            # If an external editor replaced OCRed before the exporter
            # raised, the observed bytes are not ours to compensate.
            # For legacy direct callers without an expectation, keep the
            # historical best-effort rollback but check again just before
            # replacing the sidecar.
            if (
                expected_exported_ocred_bytes is not None
                and current_ocred != expected_exported_ocred_bytes
            ):
                raise RuntimeError(
                    "OCRed 导出失败，磁盘内容与本次导出预期不符；"
                    "可能存在并发人工修改，拒绝回滚不明来源的 OCRed；"
                    f"导出={export_error!r}"
                ) from export_error
            # PDIC may change while OCRed is inspected or staged for
            # compensation. Recheck before any OCRed-only rollback.
            try:
                pdic_before_compensation = pdic_path.read_bytes()
            except FileNotFoundError:
                pdic_before_compensation = None
            except OSError as inspect_error:
                raise RuntimeError(
                    "OCRed 导出失败，回滚前无法核验 PDIC；"
                    "拒绝单侧回滚，请人工核查两份文件"
                ) from inspect_error
            if pdic_before_compensation != previous_pdic:
                raise RuntimeError(
                    "OCRed 导出失败，回滚前 PDIC 已被其他操作修改；"
                    "拒绝单侧回滚，请人工核查两份文件"
                ) from export_error
            try:
                _restore_ocred_if_unchanged(
                    ocred_path, previous, current_ocred,
                )
            except Exception as rollback_error:
                raise RuntimeError(
                    "OCRed 导出失败，且原文件回滚也失败；"
                    "未启动 PDIC 保存："
                    f"导出={export_error!r}；回滚={rollback_error!r}"
                ) from rollback_error
        raise

    # Capture the sidecar produced by this export. If an external editor
    # changes it while PDIC verification or saving is in progress, neither
    # a stale PDIC commit nor a compensating OCRed rollback may overwrite it.
    try:
        published_ocred = ocred_path.read_bytes()
    except FileNotFoundError:
        published_ocred = None
    except OSError as inspect_error:
        raise RuntimeError(
            "OCRed 导出后无法核验其文件版本；"
            "未启动 PDIC 保存，请人工核查 OCRed："
            f"核查={inspect_error!r}"
        ) from inspect_error

    # The worker knows the exact canonical bytes that its exporter must
    # produce. If a different value appears (including a manual edit inside
    # the export callback), refuse PDIC publication. Never roll back a
    # sidecar whose ownership cannot be established from these bytes.
    if (
        expected_exported_ocred_bytes is not None
        and published_ocred != expected_exported_ocred_bytes
    ):
        raise RuntimeError(
            "OCRed 导出后内容与预期不符，可能存在并发人工修改；"
            "未启动 PDIC 保存，未回滚不明来源的 OCRed，请人工核查"
        )

    # OCRed export can take time or invoke patched filesystem hooks.
    # If another editor writes PDIC during export, undo this OCRed sidecar
    # and refuse to overwrite their latest PDIC file.
    try:
        pdic_after_export = pdic_path.read_bytes()
    except FileNotFoundError:
        pdic_after_export = None
    except OSError as inspect_error:
        # A failed PDIC read does not establish whether the exporter (or a
        # concurrent editor) replaced PDIC before this check. Reverting only
        # OCRed could corrupt an already changed pair. Preserve both disk
        # versions for manual recovery, matching the failed-export and
        # uncertain-PDIC-save policies. Do not invoke the PDIC writer.
        raise RuntimeError(
            "OCRed 已导出，但无法核验导出后的 PDIC 是否被修改；"
            "拒绝单侧回滚，未启动 PDIC 保存，请人工核查两份文件："
            f"核查={inspect_error!r}"
        ) from inspect_error
    if pdic_after_export != previous_pdic:
        try:
            _restore_ocred_if_unchanged(ocred_path, previous, published_ocred)
        except Exception as rollback_error:
            raise RuntimeError(
                "PDIC 在 OCRed 导出期间被修改，且 OCRed 回滚失败："
                f"回滚={rollback_error!r}"
            ) from rollback_error
        raise RuntimeError(
            "PDIC 在 OCRed 导出期间被其他操作修改；"
            "已恢复原有 OCRed，未覆盖人工校对的 PDIC"
        )
    # The PDIC read itself can take time (or be monkeypatched in legacy
    # callers). Reject a concurrent OCRed correction before touching PDIC.
    try:
        current_ocred = ocred_path.read_bytes()
    except FileNotFoundError:
        current_ocred = None
    if current_ocred != published_ocred:
        raise RuntimeError(
            "OCRed 在导出后、PDIC 保存前被其他操作修改；"
            "未覆盖人工校对的 OCRed，未启动 PDIC 保存"
        )
    if validate_page_context is not None:
        try:
            validate_page_context()
        except Exception as context_error:
            # OCRed was already published; undo only our own unchanged export.
            # A concurrent manual OCRed edit must not be overwritten here.
            try:
                _restore_ocred_if_unchanged(
                    ocred_path, previous, published_ocred,
                )
            except Exception as rollback_error:
                raise RuntimeError(
                    "SECTION 发布前核验失败，且 OCRed 回滚失败；"
                    "未启动 PDIC 保存，请人工核查两份文件："
                    f"SECTION={context_error!r}；OCRed={rollback_error!r}"
                ) from context_error
            raise

    # The SECTION/source-image validator may hash a large scan. Another
    # window can update PDIC or OCRed while that last, expensive check runs.
    # Recheck both sidecars after it returns, immediately before the writer.
    # Legacy direct callers without a page-context validator retain their
    # existing call sequence and optional snapshot semantics.
    if validate_page_context is not None:
        try:
            final_pdic = pdic_path.read_bytes()
        except FileNotFoundError:
            final_pdic = None
        except OSError as inspect_error:
            # An unreadable PDIC does not prove it still matches our
            # pre-export snapshot. It may have been replaced during the
            # second, potentially slow page-context validation. Reverting
            # OCRed alone could then destroy the matching published pair.
            # Treat this as an indeterminate commit and preserve both files.
            raise RuntimeError(
                "页面来源核验后无法读取 PDIC，无法确认其版本；"
                "拒绝单侧回滚 OCRed，未启动 PDIC 保存，"
                "请人工核查两份文件："
                f"核查={inspect_error!r}"
            ) from inspect_error
        if final_pdic != previous_pdic:
            try:
                _restore_ocred_if_unchanged(
                    ocred_path, previous, published_ocred,
                )
            except Exception as rollback_error:
                raise RuntimeError(
                    "页面来源核验期间 PDIC 被修改，且 OCRed 回滚失败；"
                    "未启动 PDIC 保存，请人工核查两份文件："
                    f"OCRed={rollback_error!r}"
                ) from rollback_error
            raise RuntimeError(
                "页面来源核验期间 PDIC 已被其他操作修改；"
                "已恢复原有 OCRed，未覆盖人工校对的 PDIC"
            )
        try:
            final_ocred = ocred_path.read_bytes()
        except FileNotFoundError:
            final_ocred = None
        except OSError as inspect_error:
            raise RuntimeError(
                "页面来源核验后无法读取 OCRed；"
                "未启动 PDIC 保存，拒绝回滚无法确认归属的 OCRed："
                f"核查={inspect_error!r}"
            ) from inspect_error
        if final_ocred != published_ocred:
            raise RuntimeError(
                "页面来源核验期间 OCRed 已被其他操作修改；"
                "未启动 PDIC 保存，保留最新人工校对的 OCRed"
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
        def verify_pdic_before_rollback() -> None:
            # Restoring OCRed requires PDIC to remain at its pre-export
            # version, including while a rollback temp file is fsynced.
            # This is a final optimistic read, not a filesystem CAS.
            try:
                current = pdic_path.read_bytes()
            except FileNotFoundError:
                current = None
            except OSError as inspect_error:
                raise RuntimeError(
                    "OCRed 回滚即将写入时无法核验 PDIC；"
                    "拒绝单侧回滚，请人工核查两份文件"
                ) from inspect_error
            if current != previous_pdic:
                raise RuntimeError(
                    "OCRed 回滚暂存期间 PDIC 已被其他操作修改；"
                    "拒绝单侧回滚，请人工核查两份文件"
                )

        try:
            _restore_ocred_if_unchanged(
                ocred_path, previous, published_ocred,
                verify_before_mutation=verify_pdic_before_rollback,
            )
        except Exception as rollback_error:
            raise RuntimeError(
                "PDIC 保存失败，OCRed 回滚也失败："
                f"PDIC={pdic_error!r}；OCRed={rollback_error!r}"
            ) from rollback_error
        raise

    # Capture the committed PDIC before the potentially slow final source
    # image hash. Detect a later external PDIC edit without rolling back
    # either artifact once the PDIC writer has returned successfully.
    if validate_page_context is not None:
        try:
            committed_pdic = pdic_path.read_bytes()
        except FileNotFoundError:
            committed_pdic = None
        except OSError as inspect_error:
            raise RuntimeError(
                "PDIC 已保存，但无法核验提交后的 PDIC 版本；"
                "未执行单侧回滚，请人工核查两份文件："
                f"核查={inspect_error!r}"
            ) from inspect_error
        if committed_pdic is None:
            raise RuntimeError(
                "PDIC 保存函数已返回，但提交后的 PDIC 文件不存在；"
                "未执行单侧回滚，请人工核查两份文件"
            )

    # The PDIC writer can return successfully while another window edits or
    # removes OCRed during the save callback. A pre-save version check alone
    # cannot notice that race. PDIC is already committed here: report the
    # mismatched pair for recovery, never roll back either side independently.
    try:
        ocred_after_pdic = ocred_path.read_bytes()
    except FileNotFoundError:
        ocred_after_pdic = None
    except OSError as inspect_error:
        raise RuntimeError(
            "PDIC 已保存，但无法核验 OCRed 在保存期间是否被修改；"
            "未执行单侧回滚，请人工核查两份文件："
            f"核查={inspect_error!r}"
        ) from inspect_error
    if ocred_after_pdic != published_ocred:
        raise RuntimeError(
            "PDIC 已保存，但 OCRed 在保存期间被其他操作修改；"
            "保留已提交的 PDIC 和最新 OCRed，未执行单侧回滚；"
            "请人工核查两份文件"
        )

    # SECTION and source-image bytes can also change inside the PDIC writer
    # callback. The pre-commit context check cannot detect that race.
    # PDIC has already been committed: report stale page provenance without
    # rolling back either artifact or overwriting external source edits.
    if validate_page_context is not None:
        try:
            validate_page_context()
        except Exception as context_error:
            raise RuntimeError(
                "PDIC 已保存，但保存期间页面来源（SECTION/原始图像）"
                "已变化或无法核验；未执行单侧回滚，"
                "请人工核查 PDIC、OCRed 和页面来源："
                f"来源={context_error!r}"
            ) from context_error

        # Hashing the original scan can be slow. An external editor may
        # change OCRed *during* this post-commit provenance check, after the
        # first OCRed check above. Detect that late race without reverting
        # either already committed sidecar.
        try:
            final_ocred = ocred_path.read_bytes()
        except FileNotFoundError:
            final_ocred = None
        except OSError as inspect_error:
            raise RuntimeError(
                "PDIC 已保存，页面来源核验后无法再次读取 OCRed；"
                "未执行单侧回滚，请人工核查两份文件："
                f"核查={inspect_error!r}"
            ) from inspect_error
        if final_ocred != published_ocred:
            raise RuntimeError(
                "PDIC 已保存，但页面来源核验期间 OCRed 被其他操作修改；"
                "保留已提交的 PDIC 和最新 OCRed，未执行单侧回滚；"
                "请人工核查两份文件"
            )

        # The final provenance check can also outlast a concurrent PDIC edit.
        try:
            final_pdic = pdic_path.read_bytes()
        except FileNotFoundError:
            final_pdic = None
        except OSError as inspect_error:
            raise RuntimeError(
                "PDIC 已保存，页面来源核验后无法再次读取 PDIC；"
                "未执行单侧回滚，请人工核查两份文件："
                f"核查={inspect_error!r}"
            ) from inspect_error
        if final_pdic != committed_pdic:
            raise RuntimeError(
                "PDIC 已保存，但页面来源核验期间 PDIC 被其他操作修改；"
                "保留磁盘上的最新 PDIC 和 OCRed，未执行单侧回滚；"
                "请人工核查两份文件"
            )
