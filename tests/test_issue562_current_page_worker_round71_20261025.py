"""Issue #562 Round 71: physical detection worker and combined OCR parity."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.detection.current_page_worker import detect_current_page
from picture_capture.models import Entry


@pytest.mark.parametrize(
    ("mode", "ordinary", "expected_fill"),
    [
        ("left_edge", True, False),
        ("paddleocr", False, False),
        ("combined", False, True),
    ],
)
def test_page_worker_preserves_mode_and_source_path_contract(
    tmp_path, mode, ordinary, expected_fill,
):
    page = tmp_path / "page.png"
    Image.new("RGB", (64, 48), "white").save(page)
    settings = SimpleNamespace(detection_method=mode)
    geometry = object()
    events = []
    entries = [Entry("original", 9, 12)]

    def fake_detect(image, received, **kwargs):
        assert received is settings
        assert image.mode == "RGB"
        assert image.size == (64, 48)
        events.append(("detect", kwargs))
        return entries, geometry

    def fake_fill(image, received_entries, received_settings, rules, **kwargs):
        assert image.size == (64, 48)
        assert received_entries is entries
        assert received_settings is settings
        assert rules == {"rules": True}
        assert kwargs == {
            "profile_page_index": 2,
            "page_sections": ["section"],
            "profile_path": tmp_path / "Profile.json",
            "only_blank": True,
        }
        events.append(("fill",))
        return [Entry("filled", 9, 12)], {"filled": 1}

    result = detect_current_page(
        page, tmp_path, settings,
        page_index=2,
        page_sections=["section"],
        cache_path=tmp_path / "page.json",
        filter_path=tmp_path / "headwords.json",
        force_paddle_refresh=True,
        deps={
            "Image": Image,
            "normalize_page_rgb": lambda opened: opened.convert("RGB"),
            "detect_entries": fake_detect,
            "detection_mask_source_path": (
                lambda received_page, _settings, *, ordinary:
                (events.append(("mask", received_page, ordinary)) or received_page)
            ),
            "ocr_existing_entry_words_from_markers": fake_fill,
            "load_replace_rules": lambda p: {"rules": p == tmp_path / "rules.json"},
            "replace_rules_path": lambda root: root / "rules.json",
            "project_profile_path": lambda root: root / "Profile.json",
        },
    )

    assert events[0] == ("mask", page, ordinary)
    assert events[1][0] == "detect"
    assert events[1][1] == {
        "paddle_cache_path": tmp_path / "page.json",
        "force_paddle_refresh": True,
        "paddle_filter_rules_path": tmp_path / "headwords.json",
        "profile_page_index": 2,
        "page_sections": ["section"],
        "source_image_path": page,
    }
    assert (len(events) == 3) is expected_fill
    assert result[1] is geometry
    if expected_fill:
        assert [(e.word, e.x, e.y) for e in result[0]] == [("filled", 9, 12)]
        assert result[2] == {"filled": 1}
    else:
        assert result == (entries, geometry, None)


def test_combined_text_fill_cannot_move_source_coordinates(tmp_path):
    page = tmp_path / "page.png"
    Image.new("RGB", (32, 32), "white").save(page)
    settings = SimpleNamespace(detection_method="combined")
    deps = {
        "Image": Image,
        "normalize_page_rgb": lambda opened: opened.convert("RGB"),
        "detect_entries": lambda *_args, **_kwargs: ([Entry("head", 4, 8)], object()),
        "detection_mask_source_path": lambda page, *_args, **_kwargs: page,
        "ocr_existing_entry_words_from_markers": lambda *_args, **_kwargs: (
            [Entry("text", 5, 8)], {"filled": 1},
        ),
        "load_replace_rules": lambda _p: {},
        "replace_rules_path": lambda root: root / "rules.json",
        "project_profile_path": lambda root: root / "Profile.json",
    }
    with pytest.raises(RuntimeError, match="融合画线自动补字不得修改任何画线坐标"):
        detect_current_page(
            page, tmp_path, settings,
            page_index=0, page_sections=[],
            cache_path=None, filter_path=None,
            force_paddle_refresh=False, deps=deps,
        )


def test_current_page_worker_owns_inference_not_tk_publication():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src/picture_capture"
    controller = (root / "ui/controllers/detection.py").read_text(encoding="utf-8")
    worker = (root / "detection/current_page_worker.py").read_text(encoding="utf-8")
    assert "from ...detection.current_page_worker import detect_current_page" in controller
    flow = (root / "ui/detection_current_page_flow.py").read_text(encoding="utf-8")
    assert "return run_current_page_detection(" in controller
    assert 'current["detect_current_page"](' in flow
    assert "def detect_current_page(" in worker
    assert 'deps["detect_entries"](' in worker
    assert 'deps["ocr_existing_entry_words_from_markers"](' in worker
    assert "app.redraw()" not in worker
    assert "write_pdic" not in worker
    assert "app._start_batch_task(" in flow
