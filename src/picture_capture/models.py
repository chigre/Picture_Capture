from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import math
import os
import re
import tempfile
import threading

from PIL import Image

from .geometry.layout_transform import LayoutTransform
from .project import page_discovery as _page_discovery
from .project import state_opening as _project_state_opening
from .profile import settings_storage_io as _settings_storage_io
from .profile import settings_value_policy as _settings_value_policy
from .runtime.environment import portable_project_file
from .profile.settings_migrations import (
    canonicalize_app_settings_payload,
    migrate_app_settings_payload,
    normalize_app_settings_compat_keys,
)


IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"}
PROJECT_COVER_STEMS = ("_cover", "_project_cover")
PROJECT_COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

# Windows can deny overlapping os.replace calls on the same live settings file.
# Serialize in-process publications without changing the JSON schema or owner.
_APP_SETTINGS_SAVE_LOCK = threading.Lock()


def _normalize_display_opacity(value: object, default: float = 40.0) -> float:
    """Preserve root monkeypatch seam; normalization lives in Profile value policy."""
    return _settings_value_policy.normalize_display_opacity(value, default, math_module=math)

def is_project_cover_image(path: Path) -> bool:
    return _page_discovery.is_project_cover_image(path, cover_stems=PROJECT_COVER_STEMS, cover_extensions=PROJECT_COVER_EXTENSIONS)


def project_cover_path(root: Path, *, candidates: tuple[Path, ...] | None = None) -> Path | None:
    return _page_discovery.project_cover_path(root, candidates=candidates, cover_stems=PROJECT_COVER_STEMS, cover_extensions=PROJECT_COVER_EXTENSIONS)


def project_page_images(root: Path, *, candidates: tuple[Path, ...] | None = None) -> list[Path]:
    return _page_discovery.project_page_images(root, candidates=candidates, image_extensions=IMAGE_EXTENSIONS, is_cover_fn=is_project_cover_image, natural_key_fn=natural_text_key)


def natural_text_key(value: object) -> tuple:
    return _page_discovery.natural_text_key(value)


class _WeakrefableEntry:
    """Support lifetime-safe sidecar metadata even on Python 3.10.

    Dataclass weakref_slot was only added in Python 3.11; using a slotted base
    adds weak references without giving each Entry an instance __dict__.
    """
    __slots__ = ("__weakref__",)


@dataclass(slots=True)
class Entry(_WeakrefableEntry):
    """A dictionary headword marker in original-image pixel coordinates."""

    word: str
    x: int
    y: int
    current_page: str = ""
    previous_page: str = "@"
    next_page: str = "@"
    # Runtime OCR metadata. PDIC stays backward-compatible and does not persist
    # these fields; the GUI restores them from QT/PaddleOCR/<page>.json when
    # available.
    confidence: float | None = None
    ocr_source: str = ""
    alphabetical_warning: str = ""
    # v2.0 OCR fusion/review metadata (runtime only; PDIC remains unchanged).
    candidate_id: str = ""
    final_engine: str = ""
    issue_type: str = ""
    parser_score: float | None = None
    manually_selected: bool = False
    # OCR geometry used only by combined-mode arbitration. These fields are
    # intentionally runtime-only so PDIC remains byte-for-byte compatible.
    ocr_box_height: float | None = None
    ocr_line_height_reference: float | None = None
    ocr_visual_run_height: float | None = None
    ocr_leading_height_ratio: float | None = None
    ocr_single_cjk: bool = False
    ocr_oversized_cjk: bool = False

    # Canonical structural-classification metadata is registry-backed so the
    # legacy PDIC dataclass layout remains unchanged. Local imports avoid a
    # models <-> entry_classification import cycle while making the descriptors
    # available on every Entry without bootstrap-time class mutation.
    @property
    def entry_source(self) -> str:
        from .proofreading.entry_classification_fields import entry_source_get
        return entry_source_get(self)

    @entry_source.setter
    def entry_source(self, value: object) -> None:
        from .proofreading.entry_classification_fields import entry_source_set
        entry_source_set(self, value)

    @property
    def entry_scale(self) -> str:
        from .proofreading.entry_classification_fields import entry_scale_get
        return entry_scale_get(self)

    @entry_scale.setter
    def entry_scale(self, value: object) -> None:
        from .proofreading.entry_classification_fields import entry_scale_set
        entry_scale_set(self, value)

    @property
    def detected_head_height(self) -> float:
        from .proofreading.entry_classification_fields import detected_head_height_get
        return detected_head_height_get(self)

    @detected_head_height.setter
    def detected_head_height(self, value: object) -> None:
        from .proofreading.entry_classification_fields import detected_head_height_set
        detected_head_height_set(self, value)

    @property
    def entry_scale_manual(self) -> bool:
        from .proofreading.entry_classification_fields import entry_scale_manual_get
        return entry_scale_manual_get(self)

    @entry_scale_manual.setter
    def entry_scale_manual(self, value: object) -> None:
        from .proofreading.entry_classification_fields import entry_scale_manual_set
        entry_scale_manual_set(self, value)


@dataclass(slots=True)
class PolygonRegion:
    label: str
    points: list[tuple[int, int]] = field(default_factory=list)


def _app_settings_storage_alias(storage_name: str) -> property:
    """Preserve the historical field descriptor factory for the native dataclass."""
    return _settings_value_policy.app_settings_storage_alias(storage_name)

# One native dataclass object is exported under its historical import and
# pickle path; subclasses or duplicated class definitions change saved data.
from .profile.settings_model import AppSettings, _AppSettingsMeta

AppSettings.__module__ = __name__
_AppSettingsMeta.__module__ = __name__



@dataclass
class ProjectState:
    root: Path
    images: list[Path]
    settings: AppSettings
    words: list[str] = field(default_factory=list)

    @classmethod
    def open(cls, root: Path) -> "ProjectState":
        """Compatibility entrypoint; the actual project bootstrap lives in project/."""
        return _project_state_opening.open_project_state(cls, root, deps={
            "project_page_images": project_page_images,
            "AppSettings": AppSettings,
            "resolve_wordslist_path": resolve_wordslist_path,
            "read_noncomment_lines": read_noncomment_lines,
        })



def resolved_tesseract_language(settings: AppSettings) -> str:
    """Use the engine-specific language pack, falling back for old projects."""
    return str(settings.tesseract_language or settings.ocr_language or "eng").strip()


def resolve_wordslist_path(root: Path, configured: str | Path | None) -> Path:
    """Resolve a portable wordslist path and survive project moves across OSes."""
    return portable_project_file(Path(root), configured, fallback_name="wordslist.txt")


def read_noncomment_lines(path: Path) -> list[str]:
    """Read one-word-per-line reference files with bounded decode memory.

    Large wordslist files can contain hundreds of thousands of entries. Encoding
    is detected from a bounded prefix and the file is then consumed line by line,
    avoiding a second full-file text buffer alongside the returned list.
    """
    from .text.encoding import iter_text_lines_detected
    rows: list[str] = []
    for raw in iter_text_lines_detected(path):
        line = raw.strip()
        if line and not raw.lstrip().startswith("'"):
            rows.append(line)
    return rows
