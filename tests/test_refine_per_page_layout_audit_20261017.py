"""Regression: every auto-layout refinement page is independently measured.

A persistent Windows-spawn worker must not reuse first-page layout provenance.
"""
from dataclasses import replace

from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.refinement import parallel as batch


def test_two_pages_both_get_separate_physical_layout_measurements(tmp_path, monkeypatch):
    from picture_capture import processing_core
    from picture_capture.design import layout_policy as policy
    from picture_capture.refinement import analysis as prep

    pages = []
    for index in (0, 1):
        page = tmp_path / f"page_{index}.png"
        Image.new("RGB", (100, 120), "white").save(page)
        page.with_suffix(".pdic").write_text(
            f"word{index}#12#30#12#30#page{index}#@#@\n", encoding="utf-8",
        )
        pages.append(page)

    settings = AppSettings()
    settings.ordinary_auto_layout = True
    for _field, switch in policy.AUTO_LAYOUT_FIELDS:
        setattr(settings, switch, False)
    settings.ordinary_auto_column_width = True
    seen = []

    def page_policy(image, current, *, page_index):
        seen.append(page_index)
        return replace(current, column_width=42 + page_index), object(), {
            "column_width": 42 + page_index,
        }

    monkeypatch.setattr(policy, "resolve_page_layout_policy", page_policy)

    def fake_refine(image, entries, config, *, profile_page_index,
                    source_image_path):
        source, effective, analysis = prep.prepare_refinement_analysis(
            image, config, profile_page_index,
            source_image_path=source_image_path,
        )
        try:
            assert effective.column_width == 42 + profile_page_index
        finally:
            source.close()
            analysis.close()
        return list(entries), {
            "total": len(entries), "moved": 0, "limited": 0,
            "unverified": 0, "max_delta": 5,
        }

    monkeypatch.setattr(processing_core, "refine_existing_entries", fake_refine)
    for index, page in enumerate(pages):
        calculated = batch.refine_page_job(str(page), settings, index)
        assert not calculated.get("skipped"), calculated.get("reason")
        assert calculated["layout_measured"] == 1
        assert calculated["mode"] == "per_page_layout"
        publication = batch.commit_refined_page_result(index, calculated)
        assert publication["saved"] == 0
        assert publication["layout_measured"] == 1

    assert seen == [0, 1]


def test_missing_per_page_layout_is_reported_instead_of_silent_success(
    tmp_path, monkeypatch,
):
    from picture_capture import processing_core
    from picture_capture.design import layout_policy as policy

    page = tmp_path / "scan.png"
    Image.new("RGB", (100, 120), "white").save(page)
    page.with_suffix(".pdic").write_text(
        "word#12#30#12#30#scan#@#@\n", encoding="utf-8",
    )
    settings = AppSettings()
    settings.ordinary_auto_layout = True
    for _field, switch in policy.AUTO_LAYOUT_FIELDS:
        setattr(settings, switch, False)
    settings.ordinary_auto_column_width = True
    monkeypatch.setattr(
        processing_core, "refine_existing_entries",
        lambda image, entries, settings, **kwargs: (
            list(entries),
            {"total": len(entries), "moved": 0, "limited": 0,
             "unverified": 0, "max_delta": 5},
        ),
    )
    result = batch.refine_page_job(str(page), settings, 0)
    assert result["skipped"] == 1
    assert result["mode"] == "per_page_layout"
    assert "实际执行 0 次" in result["reason"]
    assert batch.commit_refined_page_result(0, result)["skipped"] == 1
