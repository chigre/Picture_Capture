from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import tempfile
from typing import Any


APP_DIRNAME = "PictureCapture"
RUNTIME_SETTINGS_FILENAME = "runtime.json"


def user_data_root(*, system: str | None = None, environ: dict[str, str] | None = None, home: Path | None = None) -> Path:
    env = environ if environ is not None else os.environ
    home_path = Path(home) if home is not None else Path.home()
    system_name = (system or platform.system()).strip()
    if system_name == "Windows":
        base = env.get("LOCALAPPDATA") or env.get("APPDATA")
        return (Path(base).expanduser() if base else home_path / "AppData" / "Local") / APP_DIRNAME
    if system_name == "Darwin":
        return home_path / "Library" / "Application Support" / APP_DIRNAME
    base = env.get("XDG_DATA_HOME")
    return (Path(base).expanduser() if base else home_path / ".local" / "share") / APP_DIRNAME


def user_config_root(*, system: str | None = None, environ: dict[str, str] | None = None, home: Path | None = None) -> Path:
    env = environ if environ is not None else os.environ
    home_path = Path(home) if home is not None else Path.home()
    system_name = (system or platform.system()).strip()
    if system_name == "Windows":
        base = env.get("APPDATA") or env.get("LOCALAPPDATA")
        return (Path(base).expanduser() if base else home_path / "AppData" / "Roaming") / APP_DIRNAME
    if system_name == "Darwin":
        return home_path / "Library" / "Application Support" / APP_DIRNAME
    base = env.get("XDG_CONFIG_HOME")
    return (Path(base).expanduser() if base else home_path / ".config") / APP_DIRNAME


def runtime_settings_path() -> Path:
    return user_config_root() / RUNTIME_SETTINGS_FILENAME


def legacy_user_config_files(filename: str, *, system: str | None = None) -> tuple[Path, ...]:
    """Return pre-portability locations that may still contain user state."""
    system_name = (system or platform.system()).strip()
    candidates: list[Path] = []
    if system_name == "Windows":
        for key in ("APPDATA", "LOCALAPPDATA"):
            base = os.environ.get(key)
            if base:
                candidates.append(Path(base).expanduser() / APP_DIRNAME / filename)
    else:
        candidates.append(Path.home() / ".picture_capture" / filename)
    current = user_config_root(system=system_name) / filename
    return tuple(path for path in dict.fromkeys(candidates) if path != current)


def legacy_user_data_roots(*, system: str | None = None) -> tuple[Path, ...]:
    """Return historical data roots used before native macOS paths were added."""
    system_name = (system or platform.system()).strip()
    candidates: list[Path] = []
    if system_name == "Darwin":
        candidates.append(
            Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            / APP_DIRNAME
        )
    current = user_data_root(system=system_name)
    return tuple(path for path in dict.fromkeys(candidates) if path != current)


def load_runtime_settings(path: Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else runtime_settings_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_runtime_setting(name: str, value: Any, path: Path | None = None) -> Path:
    target = Path(path) if path is not None else runtime_settings_path()
    payload = load_runtime_settings(target)
    if value is None or value == "":
        payload.pop(name, None)
    else:
        payload[name] = value
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return target


def runtime_setting(name: str, default: Any = None) -> Any:
    return load_runtime_settings().get(name, default)


def effective_tesseract_configured(project_value: str | None = None) -> str:
    env_override = str(os.environ.get("PICTURE_CAPTURE_TESSERACT") or "").strip()
    if env_override:
        return env_override
    local = str(runtime_setting("tesseract_executable", "") or "").strip()
    return local or str(project_value or "tesseract").strip() or "tesseract"


def _windows_absolute(value: str) -> bool:
    try:
        return PureWindowsPath(value).is_absolute()
    except (TypeError, ValueError):
        return False


def _posix_absolute(value: str) -> bool:
    try:
        return PurePosixPath(value).is_absolute()
    except (TypeError, ValueError):
        return False


def is_foreign_absolute_path(value: str | os.PathLike[str], *, system: str | None = None) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    system_name = (system or platform.system()).strip()
    win_abs = _windows_absolute(raw)
    posix_abs = _posix_absolute(raw)
    if system_name == "Windows":
        return posix_abs and not win_abs
    return win_abs


def case_insensitive_child(parent: Path, name: str) -> Path | None:
    """Resolve one child by exact spelling first, then unique case-insensitive match."""
    parent = Path(parent)
    exact = parent / name
    if exact.exists():
        return exact
    try:
        matches = [item for item in parent.iterdir() if item.name.casefold() == name.casefold()]
    except OSError:
        return None
    return matches[0] if len(matches) == 1 else None


def portable_project_file(root: Path, configured: str | Path | None, *, fallback_name: str) -> Path:
    """Resolve project files without misreading stale/foreign absolute paths."""
    root = Path(root)
    raw = str(configured or fallback_name).strip() or fallback_name

    def local_fallback(preferred_name: str = "") -> Path:
        if preferred_name:
            match = case_insensitive_child(root, preferred_name)
            if match is not None:
                return match
        fallback = case_insensitive_child(root, fallback_name)
        return fallback if fallback is not None else root / fallback_name

    if is_foreign_absolute_path(raw):
        foreign_name = PureWindowsPath(raw).name or PurePosixPath(raw).name
        return local_fallback(foreign_name)

    path = Path(raw).expanduser()
    if path.is_absolute():
        if path.exists():
            return path
        return local_fallback(path.name)

    direct = root / path
    if direct.exists():
        return direct
    if len(path.parts) == 1:
        match = case_insensitive_child(root, path.name)
        if match is not None:
            return match
    return direct


@lru_cache(maxsize=1)
def resolve_paddle_device() -> str:
    """Choose this machine's Paddle device independently of project settings."""
    requested = str(
        os.environ.get("PICTURE_CAPTURE_PADDLE_DEVICE")
        or runtime_setting("paddle_device", "auto")
        or "auto"
    ).strip().lower()
    if requested in {"cpu", "gpu"}:
        return requested
    try:
        import paddle  # type: ignore
        if bool(paddle.device.is_compiled_with_cuda()):
            try:
                if int(paddle.device.cuda.device_count()) > 0:
                    return "gpu"
            except Exception:
                pass
    except Exception:
        pass
    return "cpu"


def clear_runtime_caches() -> None:
    resolve_paddle_device.cache_clear()
