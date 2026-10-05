from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for relative in (
    "src/picture_capture/ui/controllers/export.py",
    "tests/test_ui_export_controller.py",
):
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
