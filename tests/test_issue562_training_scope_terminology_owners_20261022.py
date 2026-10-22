"""Issue #562 physical owners for non-product legacy range parsing and UI wording."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import subprocess
import sys


def test_no_retired_root_shims_and_two_byte_exact_domain_owners() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    for old, new in (
        ("training_export_ui.py", "training/legacy_scope_ui.py"),
        ("ui_terminology.py", "ui/terminology_compat.py"),
    ):
        assert not (root / old).exists(), old
        assert (root / new).is_file(), new
        assert importlib.util.find_spec("picture_capture." + old.removesuffix(".py")) is None
        canonical = importlib.import_module(
            "picture_capture." + new.removesuffix(".py").replace("/", ".")
        )
        assert Path(canonical.__file__).resolve() == (root / new).resolve()
    # This cohort physically reduces the root, not just source lines.
    assert len(list(root.glob("*.py"))) <= 35


def test_legacy_range_parser_named_numeric_and_reverse_selection() -> None:
    from picture_capture.training.legacy_scope_ui import (
        resolve_export_indices, _resolve_exact_name,
    )

    pages = [Path(f"page_{n:06d}.tif") for n in (89, 90, 91, 92)]
    assert resolve_export_indices(pages, "") == ([0, 1, 2, 3], None)
    assert resolve_export_indices(pages, "page_000090.tif") == ([1], None)
    assert resolve_export_indices(pages, "92至90") == ([1, 2, 3], None)
    assert resolve_export_indices(pages, "000091") == ([2], None)
    assert _resolve_exact_name(pages, "PAGE_000092") == 3
    assert resolve_export_indices(pages, "unknown")[0] == []
    assert resolve_export_indices(pages, "89-999")[0] == []


def test_terminology_normalizer_keeps_text_and_noop_installer_behavior() -> None:
    from picture_capture.ui.terminology_compat import (
        normalize_ui_text, install_ui_terminology,
        install_app_tooltip_terminology,
    )
    before = "只对已有画线做局部 PaddleOCR 文字识别；单行高/行间参数"
    after = normalize_ui_text(before)
    assert "共享 OCR 通道" in after
    assert "普通字/行高/行间空" in after
    assert normalize_ui_text(after) == after
    sentinel = object()
    assert normalize_ui_text(sentinel) is sentinel
    assert install_ui_terminology() is None
    assert install_app_tooltip_terminology(sentinel) is None


def test_canonical_leaf_first_does_not_import_app_or_install_gui_hooks() -> None:
    script = """
import importlib
import sys
scope = importlib.import_module("picture_capture.training.legacy_scope_ui")
terms = importlib.import_module("picture_capture.ui.terminology_compat")
assert "picture_capture.app" not in sys.modules
assert "picture_capture.training_export_ui" not in sys.modules
assert "picture_capture.ui_terminology" not in sys.modules
assert scope.resolve_export_indices([], "") == ([], None)
assert terms.normalize_ui_text("单行高") == "普通字/行高"
"""
    done = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
