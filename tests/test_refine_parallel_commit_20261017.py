"""Regression for read-only parallel refinement and single-parent guarded publication."""
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from picture_capture import marker_refinement_parallel as parallel
from picture_capture.models import AppSettings


def test_reuse_environment_worker_setting_with_refine_memory_cap():
    assert parallel.configured_refine_workers(50, cpus=12, configured="auto") == 2
    assert parallel.configured_refine_workers(50, cpus=12, configured="1") == 1
    assert parallel.configured_refine_workers(50, cpus=12, configured="4") == 4
    assert parallel.configured_refine_workers(50, cpus=12, configured="16") == 12
    assert parallel.configured_refine_workers(50, cpus=2, configured="4") == 2
    assert parallel.configured_refine_workers(1, cpus=8, configured="auto") == 1


def test_auto_layout_refinement_serializes_gpu_model_even_with_six_cpu_workers():
    from picture_capture.dictionary_page_layout_policy import AUTO_LAYOUT_FIELDS

    settings = AppSettings()
    settings.ordinary_auto_layout = True
    for _field, switch in AUTO_LAYOUT_FIELDS:
        setattr(settings, switch, False)

    assert not parallel.refinement_uses_page_layout(settings)
    assert parallel.configured_refine_workers(
        20, settings=settings, configured="4", cpus=16,
    ) == 4

    settings.ordinary_auto_column_width = True
    assert parallel.refinement_uses_page_layout(settings)
    for configured in ("auto", "1", "2", "3", "4", "6", "8", "12", "16", "24"):
        assert parallel.configured_refine_workers(
            20, settings=settings, configured=configured, cpus=16,
        ) == 1  # exactly one Paddle model-owning spawned process
    assert parallel.configured_refine_workers(
        3, settings=settings, configured="16", cpus=16,
    ) == 1
    # The quick fixed-band mode skips GPU layout, but caps image memory.
    assert parallel.configured_refine_workers(
        20, settings=settings, configured="6", cpus=16,
        fixed_half_gutter=True,
    ) == 2
    settings.layout_mask_illustrations = True
    assert parallel.configured_refine_workers(
        20, settings=settings, configured="6", cpus=16,
        fixed_half_gutter=True,
    ) == 2
    settings.ordinary_auto_layout = False
    assert not parallel.refinement_uses_page_layout(settings)
    assert parallel.configured_refine_workers(
        20, settings=settings, configured="4", cpus=16,
    ) == 2  # illustration masking alone is still memory intensive
    settings.layout_mask_illustrations = False
    assert parallel.configured_refine_workers(
        20, settings=settings, configured="4", cpus=16,
    ) == 4


def test_auto_layout_refinement_uses_547_multiworker_spawn_dispatcher():
    source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    scope = source.split("    def refine_lines_selected_scope(", 1)[1].split(
        "    def ocr_ordinary_lines_text_selected_scope(", 1
    )[0]
    assert "fixed_half_gutter=fixed_half_gutter" in scope
    assert "configured_refine_workers(" in scope
    assert "isolate_worker=True" in scope
    assert "max_workers=workers, respect_cpu_workers=True," in scope
    assert "single_process_model" not in scope
    assert "_start_parallel_batch_task(" in scope

    dispatcher = source.split("    def _start_parallel_batch_task(", 1)[1].split(
        "    def _poll_batch_queue(", 1
    )[0]
    assert "and not single_process_model" not in dispatcher
    assert "if respect_cpu_workers and int(max_workers) > 0" in dispatcher
    assert "ProcessPoolExecutor(max_workers=workers, mp_context=context)" in dispatcher
    assert 'multiprocessing.get_context("spawn")' in dispatcher
    assert "len(futures) < workers" in dispatcher
    assert 'wait(tuple(futures), timeout=0.10, return_when=FIRST_COMPLETED)' in dispatcher


def test_roundtrip_changes_only_coordinates_not_pdic_format():
    original = (b"word#10#30#1.00#3.000#page#prev#next#EXTRA\r\n"
                b"\r\n"
                b"other#11#60#7.7#8.8#page#prev#next\r\n")
    result = parallel._edit_original_pdic(
        original, (("word", 10, 30), ("other", 11, 60)),
        ((10, 32), (11, 60)), image_width=100,
    )
    assert result == (
        b"word#10#32#10#32#page#prev#next#EXTRA\r\n"
        b"\r\n"
        b"other#11#60#7.7#8.8#page#prev#next\r\n"
    )
    assert parallel._edit_original_pdic(
        original, (("word", 10, 30), ("other", 11, 60)),
        ((10, 30), (11, 60)), 100,
    ) == original


def test_pdic_utf8_bom_and_lf_are_preserved():
    original = b"\xef\xbb\xbf" + "词#10#30#1#3#A#@#@\n".encode()
    outcome = parallel._edit_original_pdic(
        original, (("词", 10, 30),), ((10, 33),), 100,
    )
    assert outcome.startswith(b"\xef\xbb\xbf")
    assert outcome.decode("utf-8-sig") == "词#10#33#10#33#A#@#@\n"


@pytest.fixture
def prepared_page(tmp_path, monkeypatch):
    from picture_capture import processing_core
    page = tmp_path / "scan.png"
    Image.new("RGB", (120, 160), "white").save(page)
    pdic = page.with_suffix(".pdic")
    payload = (
        "manual#10#30#9.9#9.9#scan#prev#next#custom\r\n"
        "ordinary#11#60#8.8#8.8#scan#prev#next\r\n"
    ).encode("utf-8")
    pdic.write_bytes(payload)

    def fake_refine(image, entries, settings, *, profile_page_index, source_image_path):
        assert profile_page_index == 7
        assert source_image_path == page
        assert len(entries) == 2
        return [replace(entry, y=entry.y + 3 if entry.word == "manual" else entry.y)
                for entry in entries], {
            "total": 2, "moved": 1, "limited": 0, "max_delta": 8,
            "unverified": 0,
        }

    monkeypatch.setattr(processing_core, "refine_existing_entries", fake_refine)
    return page, pdic, payload


def test_spawn_page_computes_without_writing_and_parent_preserves_text(prepared_page):
    page, pdic, original = prepared_page
    computed = parallel.refine_page_job(str(page), AppSettings(), 7)
    assert "fingerprints" in computed
    assert pdic.read_bytes() == original
    saved = parallel.commit_refined_page_result(
        7, computed, ownership_check=lambda index: index == 7,
    )
    assert saved["saved"] == 1 and saved["moved"] == 1
    assert pdic.read_bytes() == (
        b"manual#10#33#8.33#27.5#scan#prev#next#custom\r\n"
        b"ordinary#11#60#8.8#8.8#scan#prev#next\r\n"
    )
    assert parallel.commit_refined_page_result(7, computed)["skipped"] == 1


def test_changed_pdic_or_page_blocks_commit(prepared_page):
    page, pdic, original = prepared_page
    result = parallel.refine_page_job(str(page), AppSettings(), 7)
    pdic.write_bytes(original.replace(b"manual", b"human!"))
    outcome = parallel.commit_refined_page_result(7, result)
    assert outcome["skipped"] == 1
    assert pdic.read_bytes().startswith(b"human!")
    pdic.write_bytes(original)
    result = parallel.refine_page_job(str(page), AppSettings(), 7)
    image_bytes = page.read_bytes()
    page.write_bytes(image_bytes + b"external")
    assert parallel.commit_refined_page_result(7, result)["skipped"] == 1
    assert pdic.read_bytes() == original


def test_ppp_section_or_review_change_blocks_commit(prepared_page):
    from picture_capture.project_storage import (
        ppp_write_path_for_image, page_sections_path_for_image,
        simplified_review_path_for_image,
    )
    page, pdic, original = prepared_page
    for sidecar in (ppp_write_path_for_image(page),
                    page_sections_path_for_image(page),
                    simplified_review_path_for_image(page)):
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        if sidecar.exists():
            sidecar.unlink()
        result = parallel.refine_page_job(str(page), AppSettings(), 7)
        sidecar.write_text("human change", encoding="utf-8")
        assert parallel.commit_refined_page_result(7, result)["skipped"] == 1
        assert pdic.read_bytes() == original
        sidecar.unlink()


def test_manual_ownership_conflict_does_not_publish(prepared_page):
    page, pdic, original = prepared_page
    result = parallel.refine_page_job(str(page), AppSettings(), 7)
    out = parallel.commit_refined_page_result(
        7, result, ownership_check=lambda _: False,
    )
    assert out["skipped"] == 1
    assert pdic.read_bytes() == original


def test_no_existing_pdic_does_not_create_new_file(tmp_path):
    page = tmp_path / "empty.png"
    Image.new("RGB", (100, 120), "white").save(page)
    result = parallel.refine_page_job(str(page), AppSettings(), 0)
    assert result["skipped"] == 1
    assert parallel.commit_refined_page_result(0, result)["skipped"] == 1
    assert not page.with_suffix(".pdic").exists()


def test_same_coords_never_replace_original(prepared_page, monkeypatch):
    from picture_capture import processing_core
    page, pdic, original = prepared_page
    monkeypatch.setattr(
        processing_core, "refine_existing_entries",
        lambda image, entries, settings, **_: (
            list(entries), {"total": 2, "moved": 0, "max_delta": 8,
                            "limited": 0, "unverified": 0}
        ),
    )
    raw = parallel.refine_page_job(str(page), AppSettings(), 7)
    assert parallel.commit_refined_page_result(7, raw)["saved"] == 0
    assert pdic.read_bytes() == original


def test_parallel_parent_coordinator_gui_contract():
    path = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    code = path.read_text(encoding="utf-8")
    snippet = code.split("    def refine_lines_selected_scope(", 1)[1].split(
        "    def ocr_ordinary_lines_text_selected_scope(", 1
    )[0]
    assert "_start_parallel_batch_task(" in snippet
    assert "foreground_page_edit=True, allow_pdic_edits=True" in snippet
    assert "result_consumer" not in snippet or "save_result" in snippet
    assert "commit_refined_page_result" in snippet
    assert "write_pdic(" not in snippet
    assert "refine_page_job" in snippet



def test_replace_failure_does_not_modify_pdic_or_leave_temp(prepared_page, monkeypatch):
    from picture_capture import marker_refinement_parallel as module
    page, pdic, original = prepared_page
    computed = module.refine_page_job(str(page), AppSettings(), 7)

    def injected_failure(*_args, **_kwargs):
        raise PermissionError("injected atomic replace failure")

    monkeypatch.setattr(module.os, "replace", injected_failure)
    result = module.commit_refined_page_result(7, computed)
    assert result["skipped"] == 1
    assert pdic.read_bytes() == original
    assert not list(pdic.parent.glob(f".{pdic.name}.*.tmp"))


def test_unparseable_original_bytes_do_not_normalize_pdic():
    raw = b"word#10#30#1#3#scan#@#@\r\n"
    with pytest.raises(ValueError, match="不匹配"):
        parallel._edit_original_pdic(
            raw, (("other", 10, 30),), ((10, 35),), 120,
        )


def test_wrong_page_identity_refuses_commit(prepared_page):
    page, pdic, original = prepared_page
    computed = parallel.refine_page_job(str(page), AppSettings(), 7)
    assert parallel.commit_refined_page_result(8, computed)["skipped"] == 1
    assert pdic.read_bytes() == original
