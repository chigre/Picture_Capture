from __future__ import annotations

import os
from pathlib import Path
import site


_DLL_DIR_HANDLES: list[object] = []


def _site_package_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        roots.extend(Path(item) for item in site.getsitepackages())
    except AttributeError:
        pass
    try:
        user_site = site.getusersitepackages()
        if isinstance(user_site, str):
            roots.append(Path(user_site))
    except AttributeError:
        pass
    return list(dict.fromkeys(roots))


def configure_windows_nvidia_dlls() -> list[Path]:
    """Expose NVIDIA pip-wheel DLL directories to the current Windows process.

    NVIDIA's cuDNN Python wheels keep runtime DLLs under
    site-packages/nvidia/<component>/bin.  Native consumers such as Paddle do
    not automatically search those directories on Windows, so add every
    installed NVIDIA bin directory before Paddle/PaddleOCR is imported.
    """
    if os.name != "nt":
        return []

    discovered: list[Path] = []
    for root in _site_package_roots():
        nvidia_root = root / "nvidia"
        if not nvidia_root.is_dir():
            continue
        for bin_dir in sorted(nvidia_root.glob("*/bin")):
            if not bin_dir.is_dir() or not any(bin_dir.glob("*.dll")):
                continue
            discovered.append(bin_dir)

    if not discovered:
        return []

    current_path = os.environ.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []
    for bin_dir in discovered:
        value = str(bin_dir)
        if value not in path_parts:
            path_parts.insert(0, value)
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is not None:
            try:
                _DLL_DIR_HANDLES.append(add_dll_directory(value))
            except OSError:
                pass
    os.environ["PATH"] = os.pathsep.join(path_parts)
    return discovered
