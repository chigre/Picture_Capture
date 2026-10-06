from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "picture_capture"
OLD = PACKAGE / "overlay_line_anchor_runtime.py"
NEW = PACKAGE / "overlay_line_anchor.py"
OPACITY = PACKAGE / "overlay_opacity_runtime.py"
GUI = PACKAGE / "bootstrap" / "gui.py"
GUARD = ROOT / "scripts" / "architecture_guard.py"
OPACITY_TEST = ROOT / "tests" / "test_overlay_opacity_runtime.py"
DIRECTION_TEST = ROOT / "tests" / "test_overlay_line_anchor_direction.py"


def replace_exact(path: Path, old: str, new: str, *, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found < count:
        raise SystemExit(
            f"expected marker not found enough times in {path}: {old!r} "
            f"(found {found}, need {count})"
        )
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def migrate_anchor_module() -> None:
    if not OLD.exists():
        raise SystemExit(f"missing runtime module: {OLD}")
    if NEW.exists():
        raise SystemExit(f"target already exists: {NEW}")
    OLD.rename(NEW)
    NEW.write_text(
        '''from __future__ import annotations

"""One-sided display-line anchoring shared by the opacity renderer.

Stored/detected coordinates are structural boundaries rather than visual centre
lines: marker Y is a top anchor, while a guide path is a left anchor.  Width=1
therefore stays unchanged; only added thickness is shifted inward/downward.
"""

from typing import Any


def one_sided_line_coordinates(
    coordinates: tuple[Any, ...] | list[Any],
    *,
    width: float,
    growth: str,
) -> tuple[float, ...]:
    values: tuple[Any, ...]
    if len(coordinates) == 1 and isinstance(coordinates[0], (list, tuple)):
        values = tuple(coordinates[0])
    else:
        values = tuple(coordinates)
    if len(values) < 4 or len(values) % 2:
        return tuple(float(value) for value in values)

    try:
        flattened = [float(value) for value in values]
        effective_width = max(1.0, float(width or 1.0))
    except (TypeError, ValueError):
        return tuple(float(value) for value in values)

    offset = max(0.0, (effective_width - 1.0) / 2.0)
    if offset <= 0.0:
        return tuple(flattened)

    normalized = str(growth or "").strip().lower()
    if normalized == "down":
        for index in range(1, len(flattened), 2):
            flattened[index] += offset
    elif normalized == "left":
        for index in range(0, len(flattened), 2):
            flattened[index] -= offset
    elif normalized == "right":
        for index in range(0, len(flattened), 2):
            flattened[index] += offset
    return tuple(flattened)


def add_line_anchor_help(dialog: Any) -> None:
    """Append directional anchor semantics to the existing display help."""
    help_map = dict(getattr(dialog, "SETTING_HELP", {}))
    additions = {
        "marker_height": (
            "粗细方向：词头横线的原始 Y 为上边界锚点；宽度增加时只向下方扩展，不向上遮挡词头。"
        ),
        "guide_width": (
            "粗细方向：栏左路径为左边界锚点；宽度增加时只向右侧扩展，不向栏外扩展。"
        ),
    }
    for name, suffix in additions.items():
        if name not in help_map:
            continue
        current = str(help_map[name]).rstrip()
        if suffix not in current:
            help_map[name] = current + "\\n\\n" + suffix
    dialog.SETTING_HELP = help_map


__all__ = ["add_line_anchor_help", "one_sided_line_coordinates"]
''',
        encoding="utf-8",
    )


def migrate_opacity_runtime() -> None:
    text = OPACITY.read_text(encoding="utf-8")
    import_marker = "from PIL import Image, ImageColor, ImageDraw, ImageTk\n\n\n"
    import_block = (
        "from PIL import Image, ImageColor, ImageDraw, ImageTk\n\n"
        "from .overlay_line_anchor import add_line_anchor_help, one_sided_line_coordinates\n\n\n"
    )
    if import_marker not in text:
        raise SystemExit("opacity import marker not found")
    text = text.replace(import_marker, import_block, 1)

    alpha_marker = '''def _alpha_canvas_line(
    owner: Any,
    original_create_line,
    coordinates: tuple[Any, ...],
    options: dict[str, Any],
    *,
    opacity: float,
) -> int:
    normalized = _normalize_opacity(opacity)
'''
    alpha_replacement = '''def _alpha_canvas_line(
    owner: Any,
    original_create_line,
    coordinates: tuple[Any, ...],
    options: dict[str, Any],
    *,
    opacity: float,
) -> int:
    growth = "right" if bool(options.get("smooth", False)) else "down"
    coordinates = one_sided_line_coordinates(
        coordinates,
        width=float(options.get("width") or 1.0),
        growth=growth,
    )
    normalized = _normalize_opacity(opacity)
'''
    if alpha_marker not in text:
        raise SystemExit("opacity alpha-line marker not found")
    text = text.replace(alpha_marker, alpha_replacement, 1)

    help_marker = '''    dialog.SETTING_HELP.update({
        "guide_opacity": (
            "作用：控制主画布【栏左垂线】覆盖在扫描图片上的不透明度，只改变显示。"
            "100% 为完全不透明，0% 为完全透明；不会改变栏位检测、栏左路径、画线结果或切图。\\n\\n"
            "调整：扫描文字较密时可适当降低，使参考垂线不遮挡原文；需要强调栏路径时再提高。"
        ),
        "headword_marker_opacity": (
            "作用：控制主画布词头/词条横线覆盖在扫描图片上的不透明度，只改变显示。"
            "100% 为完全不透明，0% 为完全透明；不会改变横线 Y 坐标、PDIC、OCR、校对或切图。\\n\\n"
            "调整：横线遮挡字形时降低；需要快速检查漏线、错线时提高。"
        ),
    })
'''
    if help_marker not in text:
        raise SystemExit("opacity help marker not found")
    text = text.replace(help_marker, help_marker + "    add_line_anchor_help(dialog)\n", 1)

    marker_control = '''        marker_check = _find_checkbutton(self, "词头横线")
        if marker_check is not None:
            _add_quick_opacity_control(
                self,
                marker_check.master,
                name="headword_marker_opacity",
            )
'''
    marker_replacement = '''        marker_check = _find_checkbutton(self, "词头横线")
        if marker_check is not None:
            row = marker_check.master
            before = _find_checkbutton(row, "插图标签：外框")
            _add_quick_opacity_control(
                self,
                row,
                name="headword_marker_opacity",
                before=before,
            )
'''
    if marker_control not in text:
        raise SystemExit("marker opacity control block not found")
    text = text.replace(marker_control, marker_replacement, 1)
    OPACITY.write_text(text, encoding="utf-8")


def migrate_bootstrap_and_guard() -> None:
    replace_exact(
        GUI,
        "    from ..overlay_line_anchor_runtime import install_overlay_line_anchor_runtime\n",
        "",
    )
    replace_exact(
        GUI,
        "    # Line anchoring patches the shared line renderer after opacity is installed.\n"
        "    install_overlay_line_anchor_runtime(app_module)\n",
        "",
    )
    replace_exact(GUARD, '    "overlay_line_anchor_runtime.py",\n', "")


def migrate_tests() -> None:
    text = OPACITY_TEST.read_text(encoding="utf-8")
    text = text.replace(
        "import json\nfrom pathlib import Path\n\n",
        "import json\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\nfrom PIL import Image\n\n",
        1,
    )
    text = text.replace(
        "from picture_capture.overlay_line_anchor_runtime import one_sided_line_coordinates\n",
        "from picture_capture.overlay_line_anchor import (\n"
        "    add_line_anchor_help, one_sided_line_coordinates,\n"
        ")\n"
        "import picture_capture.overlay_opacity_runtime as opacity_runtime\n",
        1,
    )
    text = text.replace(
        "    _install_settings_properties,\n",
        "    _alpha_canvas_line,\n    _install_settings_properties,\n",
        1,
    )

    insert_marker = "\n\nclass _FakeSettings:\n"
    addition = r'''

def test_alpha_canvas_line_anchors_full_opacity_before_native_render():
    calls = []

    def create_line(*coordinates, **options):
        calls.append((coordinates, dict(options)))
        return 17

    owner = SimpleNamespace(canvas=SimpleNamespace())
    result = _alpha_canvas_line(
        owner,
        create_line,
        (100.0, 10.0, 100.0, 90.0),
        {"width": 5.0, "smooth": True, "fill": "#000"},
        opacity=100.0,
    )
    assert result == 17
    assert calls == [((102.0, 10.0, 102.0, 90.0), {
        "width": 5.0, "smooth": True, "fill": "#000"
    })]


def test_alpha_canvas_line_anchors_hidden_path_before_native_render():
    calls = []

    def create_line(*coordinates, **options):
        calls.append((coordinates, dict(options)))
        return 18

    owner = SimpleNamespace(canvas=SimpleNamespace())
    result = _alpha_canvas_line(
        owner,
        create_line,
        (20.0, 50.0, 120.0, 50.0),
        {"width": 5.0, "smooth": False, "fill": "#000"},
        opacity=0.0,
    )
    assert result == 18
    assert calls[0][0] == (20.0, 52.0, 120.0, 52.0)
    assert calls[0][1]["state"] == "hidden"


def test_alpha_canvas_line_anchors_semitransparent_overlay(monkeypatch):
    seen = {}

    class Canvas:
        def create_image(self, left, top, **options):
            seen["image"] = (left, top, dict(options))
            return 19

    def fake_render(coordinates, **kwargs):
        seen["coordinates"] = list(coordinates)
        seen["render_kwargs"] = dict(kwargs)
        return Image.new("RGBA", (1, 1)), 3, 4

    monkeypatch.setattr(opacity_runtime, "render_alpha_line_overlay", fake_render)
    monkeypatch.setattr(opacity_runtime.ImageTk, "PhotoImage", lambda _image: object())
    owner = SimpleNamespace(canvas=Canvas())
    result = _alpha_canvas_line(
        owner,
        lambda *_args, **_kwargs: 99,
        (20.0, 50.0, 120.0, 50.0),
        {"width": 5.0, "smooth": False, "fill": "#000"},
        opacity=40.0,
    )
    assert result == 19
    assert seen["coordinates"] == [20.0, 52.0, 120.0, 52.0]
    assert seen["render_kwargs"]["opacity"] == 40.0


def test_line_anchor_help_is_owned_by_opacity_surface_without_duplication():
    class Dialog:
        SETTING_HELP = {
            "marker_height": "marker base",
            "guide_width": "guide base",
        }

    add_line_anchor_help(Dialog)
    add_line_anchor_help(Dialog)
    assert Dialog.SETTING_HELP["marker_height"].count("只向下方扩展") == 1
    assert Dialog.SETTING_HELP["guide_width"].count("只向右侧扩展") == 1
'''
    if insert_marker not in text:
        raise SystemExit("opacity test insertion marker not found")
    text = text.replace(insert_marker, addition + insert_marker, 1)

    old_composition = '''def test_gui_composition_installs_opacity_after_other_drawing_wrappers():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "bootstrap"
        / "gui.py"
    ).read_text(encoding="utf-8")
    assert "install_overlay_opacity_runtime" in source
    assert "install_overlay_line_anchor_runtime" in source
    opacity = source.index("install_overlay_opacity_runtime(app_module)")
    anchor = source.index("install_overlay_line_anchor_runtime(app_module)")
    layout = source.index("install_layout_visualization(app_module)")
    lanes = source.index("install_physical_lane_summary()")
    assert layout < opacity
    assert lanes < opacity
    assert opacity < anchor
'''
    new_composition = '''def test_gui_composition_keeps_opacity_after_other_drawing_wrappers_without_anchor_installer():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "bootstrap"
        / "gui.py"
    ).read_text(encoding="utf-8")
    assert "install_overlay_opacity_runtime" in source
    assert "install_overlay_line_anchor_runtime" not in source
    opacity = source.index("install_overlay_opacity_runtime(app_module)")
    layout = source.index("install_layout_visualization(app_module)")
    lanes = source.index("install_physical_lane_summary()")
    assert layout < opacity
    assert lanes < opacity
'''
    if old_composition not in text:
        raise SystemExit("old opacity composition test not found")
    text = text.replace(old_composition, new_composition, 1)

    old_source_test = '''def test_marker_opacity_control_is_moved_before_illustration_label_controls():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "overlay_line_anchor_runtime.py"
    ).read_text(encoding="utf-8")
    assert 'target = _find_checkbutton(row, "插图标签：外框")' in source
    assert 'widget.pack_configure(before=target)' in source
    assert 'growth = "right" if bool(options.get("smooth", False)) else "down"' in source
'''
    new_source_test = '''def test_marker_opacity_control_is_created_before_illustration_label_controls():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "picture_capture" / "overlay_opacity_runtime.py"
    ).read_text(encoding="utf-8")
    guard = (root / "scripts" / "architecture_guard.py").read_text(encoding="utf-8")
    assert 'before = _find_checkbutton(row, "插图标签：外框")' in source
    assert 'name="headword_marker_opacity",\\n                before=before,' in source
    assert 'growth = "right" if bool(options.get("smooth", False)) else "down"' in source
    assert not (root / "src" / "picture_capture" / "overlay_line_anchor_runtime.py").exists()
    assert '"overlay_line_anchor_runtime.py"' not in guard
'''
    if old_source_test not in text:
        raise SystemExit("old anchor source-shape test not found")
    OPACITY_TEST.write_text(text.replace(old_source_test, new_source_test, 1), encoding="utf-8")

    direction = DIRECTION_TEST.read_text(encoding="utf-8")
    direction = direction.replace(
        "from picture_capture.overlay_line_anchor_runtime import one_sided_line_coordinates",
        "from picture_capture.overlay_line_anchor import one_sided_line_coordinates",
        1,
    )
    DIRECTION_TEST.write_text(direction, encoding="utf-8")


def main() -> None:
    migrate_anchor_module()
    migrate_opacity_runtime()
    migrate_bootstrap_and_guard()
    migrate_tests()
    print("Phase 5N migration applied")


if __name__ == "__main__":
    main()
