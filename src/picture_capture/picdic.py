from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Callable
import os
import re
import zipfile
import uuid

from .project_storage import qt_root
from .runtime_environment import case_insensitive_child


_LANGUAGE_NAMES = {
    "eng": "English", "en": "English",
    "spa": "Spanish", "es": "Spanish",
    "ita": "Italian", "it": "Italian",
    "fra": "French", "fr": "French",
    "por": "Portuguese", "pt": "Portuguese",
    "deu": "German", "de": "German",
    "chi_sim": "Chinese", "chi_tra": "Chinese", "ch": "Chinese",
}


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip())
    return cleaned.strip("._-") or "PictureDictionary"


def _language_name(ocr_language: str) -> str:
    first = next((part.strip() for part in ocr_language.split("+") if part.strip()), "eng")
    return _LANGUAGE_NAMES.get(first.casefold(), "English")


class PicDicBuildCancelled(RuntimeError):
    """Raised when a cooperative PicDic build stop is requested."""


def build_picdic_package(
    root: Path, ocr_language: str = "eng", *, should_stop: Callable[[], bool] | None = None,
) -> tuple[Path, Path, int, int]:
    """Build a GoldenDict/ABBYY DSL picture dictionary from PWW crops.

    The whole-entry crop manifests are treated as the source of truth. Top-of-page
    continuation pieces (``_上页末词条_``) are attached to the previous real
    headword so multi-page entries remain continuous.
    """
    pww_dir = qt_root(root) / "PWW"
    if not pww_dir.is_dir():
        raise RuntimeError("尚未找到项目数据目录中的 PWW；请先执行“词条切图”。")
    manifests = sorted((path for path in pww_dir.iterdir() if path.is_file() and path.suffix.casefold() == ".pwwords"), key=lambda path: path.name.casefold())
    if not manifests:
        raise RuntimeError("项目数据目录的 PWW 中没有 .PWWords 清单；请先执行“词条切图”。")

    def check_stop() -> None:
        if should_stop is not None and should_stop():
            raise PicDicBuildCancelled("PicDic 制作已停止")

    entries: "OrderedDict[str, list[str]]" = OrderedDict()
    last_word = ""
    used_files: list[str] = []
    missing: list[str] = []
    for manifest in manifests:
        check_stop()
        for raw in manifest.read_text(encoding="utf-8-sig").splitlines():
            check_stop()
            if not raw.strip():
                continue
            parts = raw.split("|", 3)
            if len(parts) < 4:
                continue
            _page, _index, word, filename = parts
            word = word.strip()
            filename = filename.strip()
            if not filename:
                continue
            if word == "_上页末词条_":
                word = last_word
            if not word:
                continue
            last_word = word
            image_path = case_insensitive_child(pww_dir, filename) or (pww_dir / filename)
            if not image_path.is_file():
                missing.append(filename)
                continue
            entries.setdefault(word, []).append(filename)
            used_files.append(filename)

    if not entries:
        detail = f"；缺失图片 {len(missing)} 张" if missing else ""
        raise RuntimeError(f"没有可用于 PicDic 的词条切图{detail}。")

    output_dir = qt_root(root) / "PicDic"
    output_dir.mkdir(parents=True, exist_ok=True)
    base = f"PicDic_{_safe_name(root.name)}"
    dsl_path = output_dir / f"{base}.dsl"
    zip_path = output_dir / f"{base}.dsl.files.zip"
    language = _language_name(ocr_language)

    lines = [
        f'#NAME "{base}"',
        f'#INDEX_LANGUAGE "{language}"',
        f'#CONTENTS_LANGUAGE "{language}"',
        "",
    ]
    for word, filenames in entries.items():
        # Backslash is the DSL escape character; protect it in user-edited lemmas.
        lemma = word.replace("\\", "\\\\")
        lines.append(lemma)
        for filename in filenames:
            lines.append(f"    [s]{filename}[/s]")
        lines.append("")
    token = uuid.uuid4().hex
    temp_dsl = dsl_path.with_name(f".{dsl_path.name}.{token}.tmp")
    temp_zip = zip_path.with_name(f".{zip_path.name}.{token}.tmp")
    backup_dsl = dsl_path.with_name(f".{dsl_path.name}.{token}.bak")
    backup_zip = zip_path.with_name(f".{zip_path.name}.{token}.bak")
    unique_files = list(dict.fromkeys(used_files))
    had_dsl = dsl_path.exists()
    had_zip = zip_path.exists()
    try:
        check_stop()
        temp_dsl.write_text("\n".join(lines), encoding="utf-8-sig")
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_STORED) as archive:
            for filename in unique_files:
                check_stop()
                archive.write(pww_dir / filename, arcname=filename)
        check_stop()

        # Preserve the previous complete pair until both new files have been
        # published. A failure during the second replace rolls the pair back.
        if had_dsl:
            os.replace(dsl_path, backup_dsl)
        if had_zip:
            os.replace(zip_path, backup_zip)
        try:
            os.replace(temp_dsl, dsl_path)
            os.replace(temp_zip, zip_path)
        except Exception:
            dsl_path.unlink(missing_ok=True)
            zip_path.unlink(missing_ok=True)
            if had_dsl and backup_dsl.exists():
                os.replace(backup_dsl, dsl_path)
            if had_zip and backup_zip.exists():
                os.replace(backup_zip, zip_path)
            raise
        backup_dsl.unlink(missing_ok=True)
        backup_zip.unlink(missing_ok=True)
    except Exception:
        temp_dsl.unlink(missing_ok=True)
        temp_zip.unlink(missing_ok=True)
        # Also recover if the exception happened while creating backups.
        if had_dsl and backup_dsl.exists() and not dsl_path.exists():
            os.replace(backup_dsl, dsl_path)
        if had_zip and backup_zip.exists() and not zip_path.exists():
            os.replace(backup_zip, zip_path)
        backup_dsl.unlink(missing_ok=True)
        backup_zip.unlink(missing_ok=True)
        raise

    return dsl_path, zip_path, len(entries), len(unique_files)
