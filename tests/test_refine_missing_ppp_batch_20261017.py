"""Missing per-page PPP must never abort explicit Y refinement in reuse mode."""
from dataclasses import replace

from PIL import Image
import pytest

from picture_capture.models import AppSettings
from picture_capture import marker_refinement_analysis as prep
from picture_capture import marker_refinement_parallel as parallel
from picture_capture import dictionary_page_layout_policy as policy


def test_refine_missing_ppp_still_measures_each_page(tmp_path, monkeypatch):
    from picture_capture import processing_core
    seen = []
    settings = AppSettings()
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = True
    settings.ordinary_auto_layout = True
    for _, switch in policy.AUTO_LAYOUT_FIELDS:
        setattr(settings, switch, False)
    settings.ordinary_auto_column_width = True

    def physical(image, current, *, page_index):
        seen.append(page_index)
        return replace(current, column_width=55 + page_index), object(), {}

    monkeypatch.setattr(policy, "resolve_page_layout_policy", physical)

    def compute(image, entries, current, *, profile_page_index, source_image_path):
        source, applied, analysis = prep.prepare_refinement_analysis(
            image, current, profile_page_index,
            source_image_path=source_image_path,
        )
        try:
            assert applied.column_width == 55 + profile_page_index
        finally:
            source.close()
            analysis.close()
        return entries, {"total":len(entries),"moved":0,"limited":0,"max_delta":8,"unverified":0}

    monkeypatch.setattr(processing_core, "refine_existing_entries", compute)

    for index in range(3):
        page = tmp_path / f"07000{index}.png"
        Image.new("RGB", (120, 160), "white").save(page)
        page.with_suffix(".pdic").write_text(
            f"test{index}#12#35#10#29#page#@#@\n", encoding="utf-8",
        )
        # No PPP file: page must be processed (but no PPP created).
        result = parallel.refine_page_job(str(page), settings, index)
        assert not result.get("skipped"), result.get("reason")
        assert result["layout_measured"] == 1
        assert parallel.commit_refined_page_result(index, result)["saved"] == 0
        assert not page.with_suffix(".ppp").exists()
    assert seen == [0, 1, 2]


def test_refine_existing_ppp_still_uses_existing_mask_and_does_not_redetect(
    tmp_path, monkeypatch,
):
    from picture_capture.layout import illustration_mask as layout_illustration_mask
    settings = AppSettings()
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = True
    page = tmp_path / "scan.png"
    image = Image.new("RGB", (120, 160), "white")
    page.write_bytes(b"unused")
    # Force a fake existing PPP path, maintaining strict reuse.
    ppp = tmp_path / "scan.ppp"
    ppp.write_text("not-real-ppp", encoding="utf-8")
    monkeypatch.setattr(
        "picture_capture.project_storage.ppp_read_path_for_image",
        lambda _: ppp,
    )
    calls = []
    def masker(*args, **kwargs):
        calls.append(kwargs["source_image_path"])
        return image.copy(), layout_illustration_mask.IllustrationMaskStats(masked=1)
    monkeypatch.setattr(layout_illustration_mask,
                        "mask_large_illustrations_for_layout", masker)
    masked = prep.whiten_illustrations_for_refinement(
        image, settings, 0, source_image_path=page,
    )
    assert calls == [page]
    assert masked is not image
    masked.close()
    image.close()


def test_missing_ppp_in_generic_layout_still_fails_closed(tmp_path):
    from picture_capture.layout.illustration_mask import mask_large_illustrations_for_layout
    settings = AppSettings()
    settings.layout_mask_illustrations = True
    settings.layout_mask_illustrations_use_existing = True
    page = tmp_path / "scan.png"
    with pytest.raises(FileNotFoundError):
        mask_large_illustrations_for_layout(
            Image.new("RGB", (120, 160), "white"), settings,
            source_image_path=page,
        )
