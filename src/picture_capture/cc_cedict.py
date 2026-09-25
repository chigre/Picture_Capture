from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
from .runtime_environment import legacy_user_data_roots, user_data_root
import re
import shutil
import threading
import unicodedata
import zipfile


DOWNLOAD_PAGE_URL = "https://www.mdbg.net/chinese/dictionary?page=cc-cedict"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
DATA_FILENAME = "cedict_ts.u8"
METADATA_FILENAME = "metadata.json"


@dataclass(frozen=True)
class CcCedictStatus:
    installed: bool
    path: Path
    entry_count: int = 0
    source_name: str = ""
    installed_at: str = ""
    error: str = ""


@dataclass(frozen=True)
class CcCedictMatch:
    word: str
    found: bool | None
    detail: str


@dataclass(frozen=True)
class CcCedictSimplifiedMatch:
    """Dictionary-backed simplified forms for one queried headword.

    ``candidates`` contains the Simplified field(s) from CC-CEDICT entries
    whose Traditional field exactly matches the query.  When the query itself
    is only present as a Simplified form, the query is returned as the sole
    candidate so an already-simplified headword can still be validated.
    """

    word: str
    found: bool | None
    candidates: tuple[str, ...]
    matched_as: str
    detail: str


_INDEX_LOCK = threading.Lock()
_INDEX_CACHE: set[str] | None = None
_INDEX_TRAD_TO_SIMP: dict[str, tuple[str, ...]] | None = None
_INDEX_SIMP_TO_TRAD: dict[str, tuple[str, ...]] | None = None
_INDEX_MTIME_NS: int | None = None
_INDEX_COUNT = 0
_INDEX_ERROR = ""


def data_root() -> Path:
    """Return the platform-native shared dictionary directory.

    Existing macOS installs from the historical Unix-style data directory remain
    readable; new installs use the native Application Support location.
    """
    current = user_data_root() / "dictionaries" / "cc-cedict"
    if (current / DATA_FILENAME).is_file() or (current / METADATA_FILENAME).is_file():
        return current
    for legacy in legacy_user_data_roots():
        candidate = legacy / "dictionaries" / "cc-cedict"
        if (candidate / DATA_FILENAME).is_file() or (candidate / METADATA_FILENAME).is_file():
            return candidate
    return current


def data_path() -> Path:
    return data_root() / DATA_FILENAME


def metadata_path() -> Path:
    return data_root() / METADATA_FILENAME


def _normalize_word(value: str) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip())


def _parse_entry_words(line: str) -> tuple[str, str] | None:
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    # CC-CEDICT: Traditional Simplified [pin1 yin1] /definition/.../
    match = re.match(r"^(\S+)\s+(\S+)\s+\[[^\]]*\]\s+/", text)
    if not match:
        return None
    return _normalize_word(match.group(1)), _normalize_word(match.group(2))


def _load_index() -> tuple[set[str] | None, int, str]:
    global _INDEX_CACHE, _INDEX_TRAD_TO_SIMP, _INDEX_SIMP_TO_TRAD
    global _INDEX_MTIME_NS, _INDEX_COUNT, _INDEX_ERROR
    path = data_path()
    if not path.is_file():
        return None, 0, "未安装"
    try:
        mtime = path.stat().st_mtime_ns
    except OSError as exc:
        return None, 0, str(exc)
    with _INDEX_LOCK:
        if _INDEX_CACHE is not None and _INDEX_MTIME_NS == mtime:
            return _INDEX_CACHE, _INDEX_COUNT, _INDEX_ERROR
        words: set[str] = set()
        trad_to_simp_sets: dict[str, set[str]] = {}
        simp_to_trad_sets: dict[str, set[str]] = {}
        count = 0
        try:
            with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
                for line in handle:
                    pair = _parse_entry_words(line)
                    if pair is None:
                        continue
                    count += 1
                    trad, simp = pair
                    if trad:
                        words.add(trad)
                    if simp:
                        words.add(simp)
                    if trad and simp:
                        trad_to_simp_sets.setdefault(trad, set()).add(simp)
                        simp_to_trad_sets.setdefault(simp, set()).add(trad)
        except OSError as exc:
            _INDEX_CACHE = None
            _INDEX_TRAD_TO_SIMP = None
            _INDEX_SIMP_TO_TRAD = None
            _INDEX_MTIME_NS = mtime
            _INDEX_COUNT = 0
            _INDEX_ERROR = str(exc)
            return None, 0, _INDEX_ERROR
        _INDEX_CACHE = words
        _INDEX_TRAD_TO_SIMP = {key: tuple(sorted(values)) for key, values in trad_to_simp_sets.items()}
        _INDEX_SIMP_TO_TRAD = {key: tuple(sorted(values)) for key, values in simp_to_trad_sets.items()}
        _INDEX_MTIME_NS = mtime
        _INDEX_COUNT = count
        _INDEX_ERROR = ""
        return words, count, ""


def clear_cache() -> None:
    global _INDEX_CACHE, _INDEX_TRAD_TO_SIMP, _INDEX_SIMP_TO_TRAD
    global _INDEX_MTIME_NS, _INDEX_COUNT, _INDEX_ERROR
    with _INDEX_LOCK:
        _INDEX_CACHE = None
        _INDEX_TRAD_TO_SIMP = None
        _INDEX_SIMP_TO_TRAD = None
        _INDEX_MTIME_NS = None
        _INDEX_COUNT = 0
        _INDEX_ERROR = ""


def lookup(word: str) -> CcCedictMatch:
    value = _normalize_word(word)
    if not value:
        return CcCedictMatch("", None, "空词条")
    index, count, error = _load_index()
    if index is None:
        return CcCedictMatch(value, None, error or "未安装")
    return CcCedictMatch(value, value in index, f"本地 CC-CEDICT · {count} 条")




def simplified_candidates(word: str) -> CcCedictSimplifiedMatch:
    """Return CC-CEDICT Simplified field candidates for *word*.

    This is intentionally a dictionary-evidence lookup, not a conversion
    engine.  The caller can compare these candidates with OpenCC output but
    should not treat a missing CC-CEDICT entry as proof that OpenCC is wrong.
    """
    value = _normalize_word(word)
    if not value:
        return CcCedictSimplifiedMatch("", None, tuple(), "", "空词条")
    index, count, error = _load_index()
    if index is None:
        return CcCedictSimplifiedMatch(value, None, tuple(), "", error or "未安装")
    trad_map = _INDEX_TRAD_TO_SIMP or {}
    simp_map = _INDEX_SIMP_TO_TRAD or {}
    direct = tuple(trad_map.get(value, ()))
    if direct:
        return CcCedictSimplifiedMatch(
            value, True, direct, "traditional", f"本地 CC-CEDICT · {count} 条 · 繁体字段精确匹配"
        )
    if value in simp_map:
        return CcCedictSimplifiedMatch(
            value, True, (value,), "simplified", f"本地 CC-CEDICT · {count} 条 · 简体字段精确匹配"
        )
    return CcCedictSimplifiedMatch(
        value, value in index, tuple(), "", f"本地 CC-CEDICT · {count} 条 · 未找到繁→简映射"
    )


def status() -> CcCedictStatus:
    path = data_path()
    if not path.is_file():
        return CcCedictStatus(False, path)
    index, count, error = _load_index()
    meta: dict[str, object] = {}
    try:
        if metadata_path().is_file():
            payload = json.loads(metadata_path().read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                meta = payload
    except (OSError, ValueError, json.JSONDecodeError):
        meta = {}
    return CcCedictStatus(
        installed=index is not None,
        path=path,
        entry_count=count,
        source_name=str(meta.get("source_name", "")),
        installed_at=str(meta.get("installed_at", "")),
        error=error,
    )


def _extract_payload(source: Path, temp_dir: Path) -> Path:
    suffix = source.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(source, "r") as archive:
            candidates = [
                name for name in archive.namelist()
                if not name.endswith("/") and Path(name).suffix.lower() in {".u8", ".txt", ""}
            ]
            if not candidates:
                candidates = [name for name in archive.namelist() if not name.endswith("/")]
            if not candidates:
                raise ValueError("ZIP 中未找到 CC-CEDICT 数据文件")
            # Prefer the canonical cedict_ts.u8 when present.
            candidates.sort(key=lambda name: ("cedict_ts" not in Path(name).name.lower(), len(name)))
            name = candidates[0]
            target = temp_dir / Path(name).name
            with archive.open(name, "r") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            return target
    if suffix == ".gz":
        target = temp_dir / DATA_FILENAME
        with gzip.open(source, "rb") as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        return target
    if suffix in {".txt", ".u8", ""}:
        return source
    raise ValueError("请选择 CC-CEDICT 的 ZIP、GZ、TXT 或 U8 文件")


def install_from_file(source: str | Path) -> CcCedictStatus:
    """Install a user-downloaded CC-CEDICT archive/data file locally.

    The program deliberately does not scrape or automatically download MDBG.
    The user downloads the official archive in a browser, then selects it here.
    """
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    temp_dir = root / ".install_tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        payload = _extract_payload(source_path, temp_dir)
        # Validate before replacing an existing dictionary.
        count = 0
        with payload.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for line in handle:
                if _parse_entry_words(line) is not None:
                    count += 1
        if count < 1000:
            raise ValueError(f"文件不像完整的 CC-CEDICT 数据库（仅识别到 {count} 条）")
        target = data_path()
        staged = root / (DATA_FILENAME + ".new")
        shutil.copy2(payload, staged)
        os.replace(staged, target)
        meta = {
            "format": "cc-cedict",
            "source_name": source_path.name,
            "source_page": DOWNLOAD_PAGE_URL,
            "license": "CC BY-SA 4.0",
            "license_url": LICENSE_URL,
            "entry_count": count,
            "installed_at": datetime.now(timezone.utc).isoformat(),
        }
        metadata_path().write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        clear_cache()
        return status()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
