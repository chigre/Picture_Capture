from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "tests/test_next_stage_regressions.py"
text = path.read_text(encoding="utf-8")
old = '''    picdic_start = text.index("    def build_picdic(", app_start)\n    picdic_end = text.index("\\n    def _order_key", picdic_start)\n    picdic_block = text[picdic_start:picdic_end]\n    assert "self._start_batch_task(" in picdic_block\n    assert "should_stop=self._batch_stop_event.is_set" in picdic_block\n'''
new = '''    picdic_start = text.index("    def build_picdic(", app_start)\n    picdic_end = text.index("\\n    def _order_key", picdic_start)\n    picdic_block = text[picdic_start:picdic_end]\n    assert "self._export_controller_for_call().build_picdic()" in picdic_block\n\n    export_controller = (\n        Path(__file__).resolve().parents[1]\n        / "src" / "picture_capture" / "ui" / "controllers" / "export.py"\n    ).read_text(encoding="utf-8")\n    controller_start = export_controller.index("    def build_picdic(")\n    controller_block = export_controller[controller_start:]\n    assert "app._start_batch_task(" in controller_block\n    assert "should_stop=app._batch_stop_event.is_set" in controller_block\n'''
assert text.count(old) == 1, "stale PicDic source-shape block not found"
path.write_text(text.replace(old, new, 1), encoding="utf-8")
