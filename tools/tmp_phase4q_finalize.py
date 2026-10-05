from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
controller_path = ROOT / "src/picture_capture/ui/controllers/export.py"
controller = controller_path.read_text(encoding="utf-8")
old_doc = '''        """Export a project-wide four-column text index from saved PDIC records.

        The persisted PDIC coordinates are passed through unchanged. Large
        projects are streamed through a temporary file and atomically published
        only after the batch finishes successfully.
        """
'''
new_doc = '''        """Export a project-wide four-column text index from saved PDIC records.

        The output is intentionally simple for downstream PicDic conversion::

            WORD<TAB>xx.xx<TAB>yy.yy<TAB>page

        Percentages are taken from the persisted PDIC percentage fields rather
        than recalculated from pixels.  This preserves the coordinate semantics
        of the source PDIC, including legacy projects.  Large projects are
        streamed in the background and never accumulated into one giant string.
        """
'''
assert old_doc in controller
controller_path.write_text(controller.replace(old_doc, new_doc, 1).rstrip() + "\n", encoding="utf-8")

for relative in ("tests/test_ui_export_controller.py",):
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
