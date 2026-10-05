from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tests/test_core.py"
text = PATH.read_text(encoding="utf-8")
old = '''def test_v21111_picdic_index_export_is_background_streaming_and_exact_format():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app_text.index("    def export_picdic_index(self) -> None:")
    end = app_text.index("    def backup_pdic", start)
    body = app_text[start:end]
    assert '("导出PicDic索引", self.export_picdic_index)' in app_text
    assert 'read_picdic_index_records(pdic_path(page), fallback_page=page.stem)' in body
    assert 'stream.write("\\\\n".join(records))' in body
    assert 'self._start_batch_task(' in body
    assert 'refresh_page_quality=False' in body
    assert 'Image.open' not in body
    assert 'derive_geometry' not in body
    assert 'PicDic_index_{stamp}.txt' in body
    assert 'WORD<TAB>xx.xx<TAB>yy.yy<TAB>page' in body
'''
new = '''def test_v21111_picdic_index_export_is_background_streaming_and_exact_format():
    root = Path(__file__).parents[1] / "src" / "picture_capture"
    app_text = (root / "app.py").read_text(encoding="utf-8")
    controller_text = (root / "ui" / "controllers" / "export.py").read_text(encoding="utf-8")
    start = app_text.index("    def export_picdic_index(self) -> None:")
    end = app_text.index("    def backup_pdic", start)
    wrapper = app_text[start:end]
    start = controller_text.index("    def export_picdic_index(self) -> None:")
    body = controller_text[start:]
    assert '("导出PicDic索引", self.export_picdic_index)' in app_text
    assert "self._export_controller_for_call().export_picdic_index()" in wrapper
    assert 'read_picdic_index_records(' in body
    assert 'pdic_path(page), fallback_page=page.stem' in body
    assert 'stream.write("\\\\n".join(records))' in body
    assert 'app._start_batch_task(' in body
    assert 'refresh_page_quality=False' in body
    assert 'Image.open' not in body
    assert 'derive_geometry' not in body
    assert 'PicDic_index_{stamp}.txt' in body
    assert 'WORD<TAB>xx.xx<TAB>yy.yy<TAB>page' in body
'''
assert old in text
PATH.write_text(text.replace(old, new, 1), encoding="utf-8")
