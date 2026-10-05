from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tests/test_core.py"
text = PATH.read_text(encoding="utf-8")
start_marker = "def test_v21110_backup_pdic_is_background_and_streaming():\n"
end_marker = "def test_v21111_illustration_button_is_renamed_to_edit_only():\n"
assert text.count(start_marker) == 1
assert text.count(end_marker) == 1
start = text.index(start_marker)
end = text.index(end_marker, start)
old = text[start:end]
for required in (
    "assert 'self._start_batch_task(' in body",
    'assert "refresh_page_quality=False" in body',
    'assert "Image.open" not in body',
):
    assert required in old, required

new = r'''def _phase4r_backup_source_blocks():
    root = Path(__file__).parents[1] / "src" / "picture_capture"
    app_text = (root / "app.py").read_text(encoding="utf-8")
    controller_text = (root / "ui" / "controllers" / "export.py").read_text(encoding="utf-8")
    start = app_text.index("    def backup_pdic(self) -> None:")
    end = app_text.index("    def restore_from_pdic_backup", start)
    wrapper = app_text[start:end]
    start = controller_text.index("    def backup_pdic(self) -> None:")
    body = controller_text[start:]
    return app_text, wrapper, body


def test_v21110_backup_pdic_is_background_and_streaming():
    _app_text, wrapper, body = _phase4r_backup_source_blocks()
    assert "self._export_controller_for_call().backup_pdic()" in wrapper
    assert 'app._start_batch_task(' in body
    assert 'temp.open("w", encoding="utf-8", newline="\\n")' in body
    assert 'source.read_text(encoding="utf-8-sig").splitlines()' in body
    assert 'stream.write("\\n".join(page_lines))' in body
    assert 'os.replace(temp, target)' in body
    assert 'lines: list[str]' not in body
    assert '"\\n".join(lines)' not in body


def test_v21110_backup_pdic_does_not_touch_page_images():
    _app_text, _wrapper, body = _phase4r_backup_source_blocks()
    assert "normalize_page_rgb" not in body
    assert "Image.open" not in body
    assert "derive_geometry" not in body


def test_v21110_backup_skips_unrelated_full_page_metadata_refresh():
    app_text, _wrapper, body = _phase4r_backup_source_blocks()
    assert "refresh_page_quality=False" in body
    finish_start = app_text.index("    def _finish_batch_task")
    finish_end = app_text.index("    def _hide_batch_bar_if_idle", finish_start)
    finish = app_text[finish_start:finish_end]
    assert 'getattr(self, "_batch_refresh_page_quality", True)' in finish


'''
text = text[:start] + new + text[end:]
PATH.write_text(text, encoding="utf-8")
