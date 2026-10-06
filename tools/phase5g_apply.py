from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_all(path: str, old: str, new: str, *, min_count: int = 1) -> None:
    text = read(path)
    count = text.count(old)
    if count < min_count:
        raise SystemExit(f"{path}: expected at least {min_count} matches for {old!r}, got {count}")
    write(path, text.replace(old, new))


old_path = ROOT / "src/picture_capture/ordinary_action_runtime.py"
new_path = ROOT / "src/picture_capture/ordinary_quick_settings.py"
source = old_path.read_text(encoding="utf-8")
source = source.replace(
    '"""OCR-independent quick-setting helper for ordinary drawing/cropping paths.',
    '"""OCR-independent quick-setting helper for ordinary drawing/cropping paths.',
    1,
)
new_path.write_text(source, encoding="utf-8")
old_path.unlink()

for path in (
    "src/picture_capture/ui/controllers/crop.py",
    "src/picture_capture/ui/controllers/detection.py",
    "tests/test_runtime_entry_path_guards.py",
):
    replace_all(
        path,
        "ordinary_action_runtime import _apply_quick_settings_for_ordinary",
        "ordinary_quick_settings import _apply_quick_settings_for_ordinary",
    )

replace_all(
    "tests/test_ui_detection_controller.py",
    'ROOT / "src/picture_capture/ordinary_action_runtime.py"',
    'ROOT / "src/picture_capture/ordinary_quick_settings.py"',
)

replace_all(
    "scripts/architecture_guard.py",
    '    "ordinary_action_runtime.py",\n',
    "",
)

print("Phase 5G migration applied")
