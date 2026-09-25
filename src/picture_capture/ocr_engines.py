from __future__ import annotations

from importlib import metadata, util
from pathlib import Path
from typing import Any
import asyncio
import os
import shutil
import subprocess
import tempfile

from PIL import Image

from .image_utils import normalize_page_rgb


def find_tesseract(executable: str = "tesseract") -> str | None:
    """Resolve Tesseract from an explicit value, PATH, and Windows defaults."""
    explicit = Path(executable).expanduser()
    if explicit.is_file():
        return str(explicit.resolve())
    found = shutil.which(executable)
    if found:
        return found
    candidates: list[Path] = []
    for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(key)
        if root:
            candidates.extend([
                Path(root) / "Tesseract-OCR" / "tesseract.exe",
                Path(root) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
            ])
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def tesseract_status(executable: str = "tesseract", language: str = "spa+eng") -> dict[str, Any]:
    resolved = find_tesseract(executable)
    wanted = [part.strip() for part in language.split("+") if part.strip()]
    result: dict[str, Any] = {
        "available": False,
        "configured": executable,
        "resolved": resolved or "",
        "version": "",
        "languages": [],
        "requested_languages": wanted,
        "missing_languages": wanted,
        "error": "",
    }
    if not resolved:
        result["error"] = "未找到 Tesseract 可执行程序"
        return result
    try:
        version_proc = subprocess.run(
            [resolved, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=12,
        )
        version_text = (version_proc.stdout or version_proc.stderr).decode("utf-8", errors="replace")
        result["version"] = version_text.splitlines()[0].strip() if version_text else ""
        langs_proc = subprocess.run(
            [resolved, "--list-langs"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=12,
        )
        if langs_proc.returncode:
            detail = langs_proc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or "--list-langs failed")
        lines = langs_proc.stdout.decode("utf-8", errors="replace").splitlines()
        languages = sorted(line.strip() for line in lines[1:] if line.strip())
        missing = [lang for lang in wanted if lang not in languages]
        result.update({
            "available": not missing,
            "languages": languages,
            "missing_languages": missing,
            "error": ("缺少语言数据：" + ", ".join(missing)) if missing else "",
        })
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        result["error"] = f"Tesseract 检测失败：{exc}"
    return result


def lens_status() -> dict[str, Any]:
    result: dict[str, Any] = {"available": False, "version": "", "error": ""}
    if util.find_spec("chrome_lens_py") is None:
        result["error"] = "未安装 chrome-lens-py"
        return result
    try:
        result["version"] = metadata.version("chrome-lens-py")
    except metadata.PackageNotFoundError:
        result["version"] = "unknown"
    try:
        from chrome_lens_py import LensAPI  # noqa: F401
        result["available"] = True
    except Exception as exc:
        try:
            protobuf_version = metadata.version("protobuf")
        except metadata.PackageNotFoundError:
            protobuf_version = "未安装"
        result["error"] = (
            f"Google Lens 依赖加载失败（protobuf={protobuf_version}）：{exc}"
        )
    return result


def _geometry_box(geometry: Any, width: int, height: int) -> tuple[int, int, int, int] | None:
    if not isinstance(geometry, dict):
        return None
    cx = geometry.get("center_x")
    cy = geometry.get("center_y")
    gw = geometry.get("width")
    gh = geometry.get("height")
    if None not in (cx, cy, gw, gh):
        x0 = float(cx) - float(gw) / 2.0
        y0 = float(cy) - float(gh) / 2.0
        x1 = float(cx) + float(gw) / 2.0
        y1 = float(cy) + float(gh) / 2.0
    elif all(key in geometry for key in ("left", "top", "width", "height")):
        x0 = float(geometry["left"]); y0 = float(geometry["top"])
        x1 = x0 + float(geometry["width"]); y1 = y0 + float(geometry["height"])
    else:
        return None
    normalized = str(geometry.get("coordinate_type", "")).upper() == "NORMALIZED"
    normalized = normalized or max(abs(x0), abs(y0), abs(x1), abs(y1)) <= 1.5
    if normalized:
        x0 *= width; x1 *= width; y0 *= height; y1 *= height
    box = (
        max(0, min(width, round(x0))), max(0, min(height, round(y0))),
        max(0, min(width, round(x1))), max(0, min(height, round(y1))),
    )
    return box if box[2] > box[0] and box[3] > box[1] else None


def _lens_payload_records(
    payload: dict[str, Any], width: int, height: int, confidence: float,
) -> tuple[list[tuple[str, float, tuple[int, int, int, int]]], str]:
    records: list[tuple[str, float, tuple[int, int, int, int]]] = []
    text_lines: list[str] = []
    detailed = payload.get("detailed_blocks") or []
    for block in detailed:
        for line in block.get("lines") or []:
            text = str(line.get("text") or "").strip()
            box = _geometry_box(line.get("geometry"), width, height)
            if text and box:
                records.append((text, confidence, box)); text_lines.append(text)
    if not records:
        for line in payload.get("line_blocks") or []:
            text = str(line.get("text") or "").strip()
            box = _geometry_box(line.get("geometry"), width, height)
            if text and box:
                records.append((text, confidence, box)); text_lines.append(text)
    if not records:
        for word in payload.get("word_data") or []:
            text = str(word.get("text") or word.get("word") or "").strip()
            box = _geometry_box(word.get("geometry"), width, height)
            if text and box:
                records.append((text, confidence, box)); text_lines.append(text)
    records.sort(key=lambda item: (item[2][1], item[2][0]))
    full_text = "\n".join(text_lines) or str(payload.get("ocr_text") or "")
    return records, full_text


def run_google_lens(
    image: Image.Image,
    *,
    language: str = "es",
    timeout: int = 60,
    default_confidence: float = 0.82,
) -> tuple[list[tuple[str, float, tuple[int, int, int, int]]], str, str]:
    """Run chrome-lens-py and return line records, text, and package version.

    Google Lens currently exposes text geometry but no stable bold flag or OCR
    confidence in the documented detailed result. The caller therefore applies
    a neutral confidence and computes typography from the original image bbox.
    """
    status = lens_status()
    if not status["available"]:
        raise RuntimeError(str(status["error"]))
    from chrome_lens_py import LensAPI

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp:
            normalize_page_rgb(image).save(temp, format="PNG")
            temp_path = temp.name

        async def call() -> dict[str, Any]:
            api = LensAPI(timeout=max(10, int(timeout)), max_concurrent=1)
            result = await api.process_image(
                image_path=temp_path,
                ocr_language=language.strip() or None,
                output_format="detailed",
            )
            if isinstance(result, dict):
                return result
            json_value = getattr(result, "json", None)
            if callable(json_value):
                converted = json_value()
                if isinstance(converted, dict):
                    return converted
            raise RuntimeError("Google Lens 返回了无法解析的结果格式")

        payload = asyncio.run(call())
        records, full_text = _lens_payload_records(
            payload, image.width, image.height,
            max(0.0, min(1.0, float(default_confidence))),
        )
        return records, full_text, str(status.get("version") or "")
    except Exception as exc:
        raise RuntimeError(f"Google Lens OCR 失败：{exc}") from exc
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink()
            except OSError:
                pass

