"""Implementation owner for historical run_tesseract workflow.

Core supplies current collaborators per call and preserves public signatures.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import Image


def run_tesseract_impl(image: Image.Image, language: str, executable: str = "tesseract", psm: int = 7, *, deps: dict[str, Any]) -> str:
    find_tesseract = deps["find_tesseract"]
    BytesIO = deps["BytesIO"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    subprocess = deps["subprocess"]
    resolved = find_tesseract(executable)
    if not resolved:
        raise RuntimeError(
            "未找到 Tesseract OCR。请在环境中心安装/选择 Tesseract 可执行程序，并检查当前项目所需语言包。"
        )
    payload = BytesIO()
    normalize_page_rgb(image).save(payload, format="PNG")
    command = [str(resolved), "stdin", "stdout", "-l", language, "--psm", str(psm)]
    try:
        result = subprocess.run(
            command, input=payload.getvalue(), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Tesseract OCR 超时（120 秒）；已终止本次识别。") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Tesseract OCR 失败：{detail}")
    return result.stdout.decode("utf-8", errors="replace")
