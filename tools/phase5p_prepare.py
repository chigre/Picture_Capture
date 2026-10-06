from __future__ import annotations

from pathlib import Path

path = Path(__file__).with_name("phase5p_apply.py")
text = path.read_text(encoding="utf-8")

# Align the help migration with the current static schema's one-line help values.
start = text.index("# Add help next to other opacity help entries.\n")
end = text.index("\n# 4. Direct app ownership.\n", start)
replacement = '''# Add help next to the existing single-line static opacity help entry.\nreplace_once(\n    "src/picture_capture/ui/settings/schema.py",\n    '        "headword_marker_opacity": "作用：控制主画布词头/词条横线覆盖在扫描图片上的不透明度，只改变显示。100% 为完全不透明，0% 为完全透明；不会改变横线 Y 坐标、PDIC、OCR、校对或切图。\\\\n\\\\n调整：横线遮挡字形时降低；需要快速检查漏线、错线时提高。",\\n',\n    '        "headword_marker_opacity": "作用：控制主画布词头/词条横线覆盖在扫描图片上的不透明度，只改变显示。100% 为完全不透明，0% 为完全透明；不会改变横线 Y 坐标、PDIC、OCR、校对或切图。\\\\n\\\\n调整：横线遮挡字形时降低；需要快速检查漏线、错线时提高。",\\n        "illustration_fill_opacity": "作用：控制主画布插图区域背景填充覆盖在扫描图片上的真实不透明度，只改变显示。默认 40%；100% 为完全不透明，0% 为完全透明。插图轮廓线不受此值影响，也不会改变 PPP 区域坐标、插图切图范围或识别结果。",\\n',\n)\n'''
text = text[:start] + replacement + text[end:]

# Align the draw-site migration with the actual current redraw source shape.
needle = "polygon_item = self.canvas.create_polygon(\\n                    points,"
if needle not in text:
    raise SystemExit("phase5p_apply.py: expected original polygon replacement block not found")
block_start = text.rfind('replace_once(\n    "src/picture_capture/app.py",', 0, text.index(needle))
block_end = text.index('\nreplace_once(\n    "src/picture_capture/app.py",', text.index(needle))
polygon_replacement = '''replace_once(\n    "src/picture_capture/app.py",\n    \'\'\'                if show_shapes:\n                    polygon_item = self.canvas.create_polygon(\n                        coords, fill=self.settings.illustration_fill_color, stipple="gray50",\n                        outline=self.settings.illustration_outline_color,\n                        width=scaled_overlay_line_width(self.settings.illustration_outline_width, overlay_scale),\n                        tags=("ppp-overlay", f"ppp-region-{region_index}"),\n                    )\n\'\'\',\n    \'\'\'                if show_shapes:\n                    polygon_item = create_alpha_canvas_polygon(\n                        self,\n                        tuple(coords),\n                        outline=self.settings.illustration_outline_color,\n                        fill=self.settings.illustration_fill_color,\n                        width=scaled_overlay_line_width(self.settings.illustration_outline_width, overlay_scale),\n                        opacity=self.settings.illustration_fill_opacity,\n                        tags=("ppp-overlay", f"ppp-region-{region_index}"),\n                    )\n\'\'\',\n)\n'''
text = text[:block_start] + polygon_replacement + text[block_end:]

# Preserve the old wrapper timing exactly: the legacy runtime called fill
# refresh after the original geometry method returned, including when that
# method internally swallowed a tk.TclError.
old_refresh = '''                    self.canvas.coords(record["label_window"], label_x, label_y)\\n            refresh_alpha_polygon_fill(self, region_index)\\n        except tk.TclError:\\n            pass\\n\\n    def _persist_current_page_sections'''
new_refresh = '''                    self.canvas.coords(record["label_window"], label_x, label_y)\\n        except tk.TclError:\\n            pass\\n        refresh_alpha_polygon_fill(self, region_index)\\n\\n    def _persist_current_page_sections'''
if text.count(old_refresh) != 1:
    raise SystemExit(
        f"phase5p_apply.py: expected one geometry refresh insertion, found {text.count(old_refresh)}"
    )
text = text.replace(old_refresh, new_refresh, 1)

# This assertion is emitted from a triple-quoted migration template. Avoid
# nested quote escaping entirely while still proving the old gray50 path is gone.
stipple_assertions = [
    line for line in text.splitlines()
    if 'assert "stipple=' in line and "not in app" in line
]
if len(stipple_assertions) != 1:
    raise SystemExit(
        f"phase5p_apply.py: expected one generated stipple assertion, found {len(stipple_assertions)}"
    )
text = text.replace(
    stipple_assertions[0],
    '    assert "gray50" not in app',
    1,
)

path.write_text(text, encoding="utf-8")
print("Phase 5P migration helper aligned to current schema, PPP draw site, refresh timing, and generated test assertion")
