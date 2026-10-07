from __future__ import annotations

"""Filesystem roots and transactional promotion for preprocessing outputs."""

import shutil
from pathlib import Path
from typing import Iterable

from PIL import Image

from .project_storage import image_preprocess_output_root


def preview_output_root(project_root: Path) -> Path:
    path = image_preprocess_output_root(project_root) / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def processed_output_root(project_root: Path) -> Path:
    path = image_preprocess_output_root(project_root) / "processed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def promote_processed_pages(
    project_root: Path,
    pages: Iterable[Path],
    *,
    backup_dirname: str = "__before__",
) -> tuple[Path, tuple[Path, ...]]:
    """Promote only the supplied processed pages to project working images.

    Promotion is intentionally range-based: a dictionary project may preprocess
    its multi-column body pages while leaving covers, tables, appendices or other
    layouts untouched. Original scans accumulate in __before__ across separate
    promotion batches. A filename already present in __before__ is never
    overwritten, which also prevents accidental repeated preprocessing of the
    same page from destroying the first-generation source scan.
    """
    root = Path(project_root).expanduser().resolve()
    page_list = [Path(page).expanduser().resolve() for page in pages]
    if not page_list:
        raise ValueError("所选范围没有可提升为工作图片的页面")
    for page in page_list:
        if page.parent != root:
            raise ValueError(f"工作页面不在项目根目录：{page}")
        if not page.is_file():
            raise FileNotFoundError(page)

    processed_root = processed_output_root(root)
    missing = [
        page.name
        for page in page_list
        if not (processed_root / page.name).is_file()
    ]
    if missing:
        sample = "、".join(missing[:8])
        suffix = "…" if len(missing) > 8 else ""
        raise RuntimeError(
            "所选范围的预处理导出不完整；请先对当前所选范围执行"
            "【导出预处理图片】。"
            f"缺少：{sample}{suffix}"
        )

    backup = root / str(backup_dirname or "__before__")
    if backup.exists() and not backup.is_dir():
        raise RuntimeError(f"原图备份路径不是文件夹：{backup}")
    conflicts = [
        page.name for page in page_list if (backup / page.name).exists()
    ]
    if conflicts:
        sample = "、".join(conflicts[:8])
        suffix = "…" if len(conflicts) > 8 else ""
        raise RuntimeError(
            "__before__ 中已存在这些页面的首代原图，不能覆盖："
            f"{sample}{suffix}。这些页面可能已经设为工作图片；"
            "如需重做，请先从原图恢复后再重新预处理。"
        )

    backup_stage = root / ".__preprocess_before__.staging"
    new_stage = root / ".__preprocess_working__.staging"
    if backup_stage.exists() or new_stage.exists():
        raise RuntimeError(
            "发现上次未完成的预处理切换暂存目录；请先检查项目目录后再重试。"
        )

    backup_preexisted = backup.exists()
    moved_originals: list[tuple[Path, Path]] = []
    finalized_backups: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        backup_stage.mkdir()
        new_stage.mkdir()

        # Copy + decode-verify every selected processed image before touching any
        # corresponding working image.
        for page in page_list:
            source = processed_root / page.name
            staged = new_stage / page.name
            shutil.copy2(source, staged)
            with Image.open(staged) as opened:
                opened.verify()

        # Temporarily remove only the selected originals from the project root.
        for page in page_list:
            stored = backup_stage / page.name
            page.replace(stored)
            moved_originals.append((page, stored))

        # Publish processed pages under the same filenames. Unselected project
        # pages remain exactly where they are and are not modified.
        for page in page_list:
            staged = new_stage / page.name
            target = root / page.name
            staged.replace(target)
            published.append(target)

        # Merge this batch's originals into the persistent backup folder only
        # after all processed working pages have been published successfully.
        backup.mkdir(exist_ok=True)
        for original, staged_backup in moved_originals:
            final_backup = backup / original.name
            staged_backup.replace(final_backup)
            finalized_backups.append((original, final_backup))

        shutil.rmtree(backup_stage, ignore_errors=True)
        shutil.rmtree(new_stage, ignore_errors=True)
        return backup, tuple(published)
    except Exception:
        # Remove newly published pages before restoring their originals.
        for target in reversed(published):
            try:
                if target.exists():
                    target.unlink()
            except OSError:
                pass

        # Originals already merged into __before__ are restored first.
        for original, final_backup in reversed(finalized_backups):
            try:
                if final_backup.exists() and not original.exists():
                    final_backup.replace(original)
            except OSError:
                pass

        # Originals still waiting in the transaction staging directory are also
        # restored. Pre-existing __before__ contents are never touched.
        for original, staged_backup in reversed(moved_originals):
            try:
                if staged_backup.exists() and not original.exists():
                    staged_backup.replace(original)
            except OSError:
                pass

        shutil.rmtree(backup_stage, ignore_errors=True)
        shutil.rmtree(new_stage, ignore_errors=True)
        if not backup_preexisted and backup.exists():
            try:
                if not any(backup.iterdir()):
                    backup.rmdir()
            except OSError:
                pass
        raise
