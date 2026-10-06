from __future__ import annotations

from pathlib import Path

path = Path(__file__).with_name("phase5p_apply.py")
text = path.read_text(encoding="utf-8")
start = text.index("# Add help next to other opacity help entries.\n")
end = text.index("\n# 4. Direct app ownership.\n", start)
replacement = '''# Add help next to the existing single-line static opacity help entry.\nreplace_once(\n    "src/picture_capture/ui/settings/schema.py",\n    '        "headword_marker_opacity": "作用：控制主画布词头/词条横线覆盖在扫描图片上的不透明度，只改变显示。100% 为完全不透明，0% 为完全透明；不会改变横线 Y 坐标、PDIC、OCR、校对或切图。\\\\n\\\\n调整：横线遮挡字形时降低；需要快速检查漏线、错线时提高。",\\n',\n    '        "headword_marker_opacity": "作用：控制主画布词头/词条横线覆盖在扫描图片上的不透明度，只改变显示。100% 为完全不透明，0% 为完全透明；不会改变横线 Y 坐标、PDIC、OCR、校对或切图。\\\\n\\\\n调整：横线遮挡字形时降低；需要快速检查漏线、错线时提高。",\\n        "illustration_fill_opacity": "作用：控制主画布插图区域背景填充覆盖在扫描图片上的真实不透明度，只改变显示。默认 40%；100% 为完全不透明，0% 为完全透明。插图轮廓线不受此值影响，也不会改变 PPP 区域坐标、插图切图范围或识别结果。",\\n',\n)\n'''
path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
print("Phase 5P migration helper aligned to current static schema")
