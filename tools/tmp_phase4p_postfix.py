from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tests/test_ui_export_controller.py"
text = path.read_text(encoding="utf-8")
old = '        "词头：7\\n图片：9\\n\\nDSL：book.dsl\\n图片包：book.dsl.files.zip\\n目录：/project/QT/PicDic",\n'
new = '        f"词头：7\\n图片：9\\n\\nDSL：book.dsl\\n图片包：book.dsl.files.zip\\n目录：{dsl.parent}",\n'
assert text.count(old) == 1, "expected generated dialog assertion not found"
path.write_text(text.replace(old, new, 1), encoding="utf-8")
