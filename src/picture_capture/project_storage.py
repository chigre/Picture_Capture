from __future__ import annotations

"""Project-local storage layout for Picture Capture.

The user-selected project directory belongs to the user: scans and user-owned
reference files stay there.  Picture Capture keeps its own settings, caches,
intermediate files and generated outputs below one managed directory:
``_PictureCapture``.

Legacy projects remain readable.  The GUI can migrate them explicitly; helper
functions below choose the legacy locations until a v2 manifest exists.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import json
import shutil

from .runtime_environment import case_insensitive_child


STORAGE_DIRNAME = "_PictureCapture"
MANIFEST_FILENAME = "project.json"
PROJECT_FORMAT = "picture_capture_project"
PROJECT_FORMAT_VERSION = 2
SETTINGS_FILENAME = "settings.json"
PROFILE_FILENAME = "dictionary_profile.json"
LEGACY_SETTINGS_FILENAME = "picture_capture_settings.json"
LEGACY_INI_FILENAME = "_Mysettings.ini"


def storage_root(project_root: Path) -> Path:
    return Path(project_root) / STORAGE_DIRNAME


def manifest_path(project_root: Path) -> Path:
    return storage_root(project_root) / MANIFEST_FILENAME


def is_managed_project(project_root: Path) -> bool:
    path = manifest_path(project_root)
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return (
        isinstance(payload, dict)
        and payload.get("format") == PROJECT_FORMAT
        and int(payload.get("format_version", 0) or 0) >= PROJECT_FORMAT_VERSION
    )


def settings_path(project_root: Path) -> Path:
    root = Path(project_root)
    return storage_root(root) / SETTINGS_FILENAME if is_managed_project(root) else root / LEGACY_SETTINGS_FILENAME


def legacy_ini_path(project_root: Path) -> Path:
    root = Path(project_root)
    if is_managed_project(root):
        return storage_root(root) / "legacy" / LEGACY_INI_FILENAME
    return root / LEGACY_INI_FILENAME


def profile_path(project_root: Path) -> Path:
    root = Path(project_root)
    return storage_root(root) / PROFILE_FILENAME if is_managed_project(root) else root / PROFILE_FILENAME


def rules_root(project_root: Path) -> Path:
    root = Path(project_root)
    return storage_root(root) / "rules" if is_managed_project(root) else root


def replace_rules_path(project_root: Path) -> Path:
    return rules_root(project_root) / "_Replace.txt"


def headword_filter_rules_path(project_root: Path, filename: str = "headword_filter_rules.txt") -> Path:
    return rules_root(project_root) / filename


def qt_root(project_root: Path) -> Path:
    root = Path(project_root)
    return storage_root(root) / "QT" if is_managed_project(root) else root / "QT"


def data_root(project_root: Path) -> Path:
    root = Path(project_root)
    return storage_root(root) / "data" if is_managed_project(root) else root


def output_root(project_root: Path) -> Path:
    root = Path(project_root)
    return storage_root(root) / "output" if is_managed_project(root) else root


def exports_root(project_root: Path) -> Path:
    path = output_root(project_root) / "exports" if is_managed_project(project_root) else Path(project_root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def training_exports_root(project_root: Path) -> Path:
    path = output_root(project_root) / "TrainingExports" if is_managed_project(project_root) else Path(project_root) / "TrainingExports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pdic_path_for_image(image_path: Path) -> Path:
    image_path = Path(image_path)
    root = image_path.parent
    if is_managed_project(root):
        return storage_root(root) / "data" / "PDIC" / f"{image_path.stem}.pdic"
    expected = image_path.with_suffix(".pdic")
    match = case_insensitive_child(root, expected.name)
    return match if match is not None and match.is_file() else expected




def simplified_review_path_for_image(image_path: Path) -> Path:
    """Return the per-page saved simplified-headword sidecar path.

    The PDIC 8-field format stays unchanged for downstream compatibility.
    Editable simplified review text therefore lives in a dedicated JSON
    sidecar, inside the managed project storage tree (or legacy QT folder).
    """
    image_path = Path(image_path)
    root = image_path.parent
    if is_managed_project(root):
        return storage_root(root) / "data" / "Simplified" / f"{image_path.stem}.json"
    return root / "QT" / "Simplified" / f"{image_path.stem}.json"

def ppp_write_path_for_image(image_path: Path) -> Path:
    image_path = Path(image_path)
    root = image_path.parent
    if is_managed_project(root):
        return storage_root(root) / "data" / "PPP" / f"{image_path.stem}.ppp"
    return image_path.with_suffix(".ppp")


def ppp_read_path_for_image(image_path: Path) -> Path:
    image_path = Path(image_path)
    root = image_path.parent
    if is_managed_project(root):
        return ppp_write_path_for_image(image_path)
    lower = image_path.with_suffix(".ppp")
    match = case_insensitive_child(image_path.parent, lower.name)
    return match if match is not None and match.is_file() else lower


def word_fill_status_path(project_root: Path) -> Path:
    return qt_root(project_root) / "_WordFillStatus.json"


def crop_settings_path(project_root: Path, filename: str) -> Path:
    return qt_root(project_root) / filename


def special_pages_path(project_root: Path) -> Path:
    return qt_root(project_root) / "_SpecialPages.txt"


def crop_log_path(project_root: Path) -> Path:
    return qt_root(project_root) / "_file_log.txt"


def ocr_cache_root(project_root: Path) -> Path:
    return qt_root(project_root) / "PaddleOCR"


def words_of_pages_default_path(project_root: Path) -> Path:
    """Return the default generated legacy words-of-pages file location.

    Existing user-owned/root files remain discoverable by callers. New managed
    projects keep a generated copy under the software data root.
    """
    root = Path(project_root)
    legacy = case_insensitive_child(root, "_WordsOfPages.txt") or (root / "_WordsOfPages.txt")
    if is_managed_project(root):
        # A root-level file can be user-supplied legacy data; do not relocate it
        # implicitly. Prefer it when it already exists, otherwise keep new
        # generated/default data below the software-owned storage root.
        return legacy if legacy.exists() else storage_root(root) / "data" / "_WordsOfPages.txt"
    return legacy


def _manifest_payload(project_root: Path, software_version: str) -> dict:
    return {
        "format": PROJECT_FORMAT,
        "format_version": PROJECT_FORMAT_VERSION,
        "project_name": Path(project_root).name,
        "created_with": str(software_version),
        "last_opened_with": str(software_version),
        "storage_root": STORAGE_DIRNAME,
        "settings": SETTINGS_FILENAME,
    }


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def ensure_project_storage(project_root: Path, software_version: str) -> Path:
    """Create/update the managed v2 storage tree for a clean/new project."""
    root = Path(project_root).expanduser().resolve()
    target = storage_root(root)
    for rel in (
        "data/PDIC", "data/PPP", "data/Simplified", "rules", "QT/PaddleOCR", "QT/PSW", "QT/PWW",
        "QT/PIC", "QT/PicDic", "output/TrainingExports", "output/exports", "logs", "legacy",
    ):
        (target / rel).mkdir(parents=True, exist_ok=True)
    manifest = manifest_path(root)
    if manifest.exists():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = _manifest_payload(root, software_version)
        except Exception:
            payload = _manifest_payload(root, software_version)
        payload.update({
            "format": PROJECT_FORMAT,
            "format_version": PROJECT_FORMAT_VERSION,
            "project_name": root.name,
            "last_opened_with": str(software_version),
            "storage_root": STORAGE_DIRNAME,
            "settings": SETTINGS_FILENAME,
        })
    else:
        payload = _manifest_payload(root, software_version)
    _write_json_atomic(manifest, payload)
    return target


def _legacy_page_artifacts(project_root: Path) -> list[Path]:
    root = Path(project_root)
    found: list[Path] = []
    for path in root.iterdir() if root.is_dir() else ():
        if path.is_file() and path.suffix.lower() in {".pdic", ".ppp"}:
            found.append(path)
    return sorted(found, key=lambda p: p.name.casefold())


def has_legacy_project_data(project_root: Path) -> bool:
    """Whether the project contains software-managed files in the old layout."""
    root = Path(project_root)
    if is_managed_project(root):
        return False
    fixed = (
        LEGACY_SETTINGS_FILENAME, LEGACY_INI_FILENAME, PROFILE_FILENAME,
        "_Replace.txt", "headword_filter_rules.txt", "QT", "TrainingExports",
    )
    if any(case_insensitive_child(root, name) is not None for name in fixed):
        return True
    if _legacy_page_artifacts(root):
        return True
    if any(root.glob("PicDic_index_*.txt")) or any(root.glob("all_pdic_backup_*.txt")):
        return True
    return False


@dataclass(slots=True)
class MigrationReport:
    project_root: Path
    storage_root: Path
    files_copied: int = 0
    files_removed: int = 0
    directories_removed: int = 0
    warnings: list[str] = field(default_factory=list)


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
    elif path.is_dir():
        yield from (p for p in path.rglob("*") if p.is_file())


def _same_file_payload(source: Path, target: Path) -> bool:
    try:
        return source.is_file() and target.is_file() and source.stat().st_size == target.stat().st_size
    except OSError:
        return False


def migrate_legacy_project(project_root: Path, software_version: str) -> MigrationReport:
    """Safely migrate known legacy Picture Capture files into ``_PictureCapture``.

    Migration is copy -> verify -> publish -> cleanup.  The originals are not
    removed until every copied file has a verified destination, so an interrupted
    copy leaves the legacy project intact.
    """
    root = Path(project_root).expanduser().resolve()
    final = storage_root(root)
    report = MigrationReport(project_root=root, storage_root=final)
    if is_managed_project(root):
        ensure_project_storage(root, software_version)
        return report
    if final.exists():
        raise RuntimeError(
            f"发现未完成或非标准的 {STORAGE_DIRNAME} 目录。为避免覆盖数据，请先检查/重命名该目录后再整理项目。"
        )

    stage = root / f".{STORAGE_DIRNAME}.migrating"
    if stage.exists():
        raise RuntimeError(f"发现上次未完成的迁移目录：{stage.name}。请先检查或删除后重试。")

    copied_pairs: list[tuple[Path, Path]] = []
    cleanup_files: list[Path] = []
    cleanup_dirs: list[Path] = []

    def copy_file(source: Path, destination: Path) -> None:
        if not source.is_file():
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied_pairs.append((source, destination))
        cleanup_files.append(source)

    try:
        # Core project metadata/settings.
        copy_file(case_insensitive_child(root, LEGACY_SETTINGS_FILENAME) or (root / LEGACY_SETTINGS_FILENAME), stage / SETTINGS_FILENAME)
        copy_file(case_insensitive_child(root, PROFILE_FILENAME) or (root / PROFILE_FILENAME), stage / PROFILE_FILENAME)
        copy_file(case_insensitive_child(root, "_Replace.txt") or (root / "_Replace.txt"), stage / "rules" / "_Replace.txt")
        copy_file(case_insensitive_child(root, "headword_filter_rules.txt") or (root / "headword_filter_rules.txt"), stage / "rules" / "headword_filter_rules.txt")
        copy_file(case_insensitive_child(root, LEGACY_INI_FILENAME) or (root / LEGACY_INI_FILENAME), stage / "legacy" / LEGACY_INI_FILENAME)

        # Page-level sidecars that previously polluted the scan directory.
        for source in _legacy_page_artifacts(root):
            if source.suffix.lower() == ".pdic":
                target = stage / "data" / "PDIC" / f"{source.stem}.pdic"
            else:
                target = stage / "data" / "PPP" / f"{source.stem}.ppp"
            copy_file(source, target)

        # Preserve the historical QT tree intact; internal code now resolves it
        # below the managed root, so no downstream format changes are required.
        legacy_qt = case_insensitive_child(root, "QT") or (root / "QT")
        if legacy_qt.is_dir():
            target_qt = stage / "QT"
            shutil.copytree(legacy_qt, target_qt, dirs_exist_ok=True, copy_function=shutil.copy2)
            for source in _iter_files(legacy_qt):
                rel = source.relative_to(legacy_qt)
                copied_pairs.append((source, target_qt / rel))
            cleanup_dirs.append(legacy_qt)

        legacy_training = case_insensitive_child(root, "TrainingExports") or (root / "TrainingExports")
        if legacy_training.is_dir():
            target_training = stage / "output" / "TrainingExports"
            shutil.copytree(legacy_training, target_training, dirs_exist_ok=True, copy_function=shutil.copy2)
            for source in _iter_files(legacy_training):
                rel = source.relative_to(legacy_training)
                copied_pairs.append((source, target_training / rel))
            cleanup_dirs.append(legacy_training)

        # Generated root-level exports are software output, not source material.
        for pattern in ("PicDic_index_*.txt", "all_pdic_backup_*.txt"):
            for source in root.glob(pattern):
                copy_file(source, stage / "output" / "exports" / source.name)

        # Make a complete standard tree in staging and publish a manifest there.
        for rel in (
            "data/PDIC", "data/PPP", "data/Simplified", "rules", "QT/PaddleOCR", "QT/PSW", "QT/PWW",
            "QT/PIC", "QT/PicDic", "output/TrainingExports", "output/exports", "logs", "legacy",
        ):
            (stage / rel).mkdir(parents=True, exist_ok=True)
        _write_json_atomic(stage / MANIFEST_FILENAME, _manifest_payload(root, software_version))

        bad = [(s, d) for s, d in copied_pairs if not _same_file_payload(s, d)]
        if bad:
            sample = ", ".join(s.name for s, _ in bad[:5])
            raise RuntimeError(f"迁移验证失败，以下文件未完整复制：{sample}")

        stage.rename(final)
        report.files_copied = len(copied_pairs)

        # Cleanup only after the managed storage has been published successfully.
        # Files already covered by a directory cleanup are skipped here.
        covered_roots = [p.resolve() for p in cleanup_dirs if p.exists()]
        for source in cleanup_files:
            try:
                resolved = source.resolve()
                if any(parent == resolved or parent in resolved.parents for parent in covered_roots):
                    continue
                if source.exists():
                    source.unlink()
                    report.files_removed += 1
            except OSError as exc:
                report.warnings.append(f"未能删除旧文件 {source.name}: {exc}")
        for directory in cleanup_dirs:
            try:
                if directory.exists():
                    shutil.rmtree(directory)
                    report.directories_removed += 1
            except OSError as exc:
                report.warnings.append(f"未能删除旧目录 {directory.name}: {exc}")

        ensure_project_storage(root, software_version)
        return report
    except Exception:
        # If publication has not happened, staging is disposable and the legacy
        # source remains untouched. If publication succeeded, never remove it.
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise
