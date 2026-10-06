from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from picture_capture import paddle_headwords, processing, processing_core
from picture_capture.models import AppSettings
from picture_capture import separator_y_refinement as shared_y


class _IdentityTransform:
    def canonical_to_source_point(self, x: int, y: int, _size):
        return int(x), int(y)


def test_paddle_public_and_core_refiners_use_shared_module() -> None:
    assert paddle_headwords.refine_separator_y is shared_y.refine_separator_y
    assert paddle_headwords._core.refine_separator_y is shared_y.refine_separator_y


def test_existing_pdic_refinement_reaches_shared_api() -> None:
    source = inspect.getsource(processing_core.refine_existing_entries)
    assert "from .paddle_headwords import refine_separator_y" in source
    assert "refine_separator_y(" in source
    assert paddle_headwords.refine_separator_y is shared_y.refine_separator_y


def test_layout_materialization_uses_shared_y_adapter() -> None:
    # Entry classification is now attached inside the canonical materializer,
    # so its separator-Y contract no longer depends on installer order.
    source = Path(processing.__file__).read_text(encoding="utf-8")
    assert "refined_layout_entry_y_by_line(" in source
    assert 'getattr(line, "role"' in source


def test_layout_adapter_refines_only_entry_rows(monkeypatch) -> None:
    calls: list[int] = []

    def fake_refiner(_gray, coarse_y, _line_height, _settings, *args, **kwargs):
        calls.append(int(coarse_y))
        return int(coarse_y) - 3, {"refiner": "test"}

    monkeypatch.setattr(shared_y, "refine_separator_y", fake_refiner)
    monkeypatch.setattr(
        __import__("picture_capture.dictionary_page_design", fromlist=["_analysis_page"]),
        "_analysis_page",
        lambda image, settings, page_index: (
            image,
            image,
            None,
            settings,
        ),
    )

    body = SimpleNamespace(y0=20, y1=35, role="body")
    entry = SimpleNamespace(y0=50, y1=65, role="entry")
    layout = SimpleNamespace(
        body_top=100,
        body_bottom=300,
        ordinary_line_height=20,
        columns=[SimpleNamespace(left=10, right=190, lines=[body, entry])],
    )
    understanding = SimpleNamespace(
        layout=layout,
        page_settings=AppSettings(character_height=20),
    )

    result = shared_y.refined_layout_entry_y_by_line(
        Image.new("RGB", (200, 320), "white"),
        understanding,
        page_index=0,
    )

    assert calls == [150]
    assert id(body) not in result
    assert result[id(entry)] == 147
    assert body.role == "body"
    assert entry.role == "entry"


def test_shared_refiner_keeps_legacy_settings_contract() -> None:
    signature = inspect.signature(shared_y.refine_separator_y)
    assert "gray" in signature.parameters
    assert "coarse_y" in signature.parameters
    assert "line_height" in signature.parameters
    assert "settings" in signature.parameters
    assert np is not None
