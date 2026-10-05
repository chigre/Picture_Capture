from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app_path = ROOT / "src" / "picture_capture" / "app.py"
text = app_path.read_text(encoding="utf-8")

start_marker = "    def run_normal_draw_action(self) -> None:\n"
start = text.index(start_marker)
end = text.index("\n    def ", start + len(start_marker))
wrapper = (
    "    def run_normal_draw_action(self) -> None:\n"
    "        self._detection_controller_for_call().run_normal_draw_action()\n"
)
text = text[:start] + wrapper + text[end:]
app_path.write_text(text, encoding="utf-8")

updated = app_path.read_text(encoding="utf-8")
assert updated.count("    def run_normal_draw_action(self) -> None:\n") == 1
assert "self._detection_controller_for_call().run_normal_draw_action()" in updated
