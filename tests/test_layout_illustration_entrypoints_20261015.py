"""Regression: settings-center PPP reuse propagates source identity to Layout/OCR."""
from types import SimpleNamespace
from PIL import Image

from picture_capture.layout_mask_source_guard import (
    missing_saved_illustrations, saved_illustration_stamp, detection_mask_source_path,
)
from picture_capture import layout_step_replay_ui as replay
from picture_capture import processing


def test_replay_forwards_original_path_without_writing_pdic(monkeypatch, tmp_path):
    page = tmp_path / "scan.png"
    seen = {}
    def fake_detect(source, settings, **kwargs):
        seen.update(kwargs)
        kwargs["debug_trace"]["_layout_replay_trace"].add_note("test", "test", "diagnostic replay")
        return [], None
    # processing is a historical module-proxy: setattr mirrors into the core.
    # Inject into the local dictionary so pytest teardown cannot mutate core APIs.
    monkeypatch.setitem(processing.__dict__, "detect_entries", fake_detect)
    source = Image.new("RGB", (100, 150), "white")
    settings = SimpleNamespace(layout_mask_illustrations=True,
                               layout_mask_illustrations_use_existing=True)
    trace, previews = replay._run_replay(source, settings, 2, [], source_image_path=page)
    assert seen["source_image_path"] == page
    assert seen["profile_page_index"] == 2
    assert trace.stages
    settings.layout_mask_illustrations_use_existing = False
    second, previews2 = replay._run_replay(source, settings, 2, [], source_image_path=page)
    assert seen["source_image_path"] is None  # no PPP writes in read-only auto detection
    assert second.stages
    for preview in previews2.values():
        preview.close()
    for preview in previews.values():
        preview.close()
    source.close()


def test_missing_ppp_preflight_and_cache_invalidation(monkeypatch, tmp_path):
    import picture_capture.layout_mask_source_guard as guard
    monkeypatch.setattr(guard, "ppp_read_path_for_image",
                        lambda page: tmp_path / (page.stem + ".PPP"))
    page = tmp_path / "scan.png"
    settings = SimpleNamespace(layout_mask_illustrations=True,
                               layout_mask_illustrations_use_existing=True)
    assert missing_saved_illustrations((page,), settings) == [page]
    missing_stamp = saved_illustration_stamp(page, settings)
    assert missing_stamp[-1] == "missing"
    (tmp_path / "scan.PPP").write_text("test", encoding="utf-8")
    assert missing_saved_illustrations((page,), settings) == []
    assert saved_illustration_stamp(page, settings) != missing_stamp
    settings.layout_mask_illustrations_use_existing = False
    assert missing_saved_illustrations((page,), settings) == []
    assert saved_illustration_stamp(page, settings) is None


def test_replay_ocr_and_fusion_paths_receive_original_image_path():
    from pathlib import Path
    src = Path(__file__).parents[1] / "src" / "picture_capture"
    app = (src / "app.py").read_text(encoding="utf-8")
    controller = (src / "ui/controllers/detection.py").read_text(encoding="utf-8")
    replay_src = (src / "layout_step_replay_ui.py").read_text(encoding="utf-8")
    assert "source_image_path=detection_mask_source_path(" in app
    assert "source_image_path=detection_mask_source_path(" in controller
    assert "_run_replay, source, settings, page_index, page_sections, source_path," in replay_src
    assert app.index("missing_ppp = missing_saved_illustrations(") < app.index("batch_started_at = time.time()")


def test_ocr_auto_mask_is_memory_only_but_existing_ppp_is_read(tmp_path):
    page = tmp_path / "a.png"
    settings = SimpleNamespace(layout_mask_illustrations=True,
                               layout_mask_illustrations_use_existing=False)
    assert detection_mask_source_path(page, settings, ordinary=True) == page
    assert detection_mask_source_path(page, settings, ordinary=False) is None
    settings.layout_mask_illustrations_use_existing = True
    assert detection_mask_source_path(page, settings, ordinary=False) == page
