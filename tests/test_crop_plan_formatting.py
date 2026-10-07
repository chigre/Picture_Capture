from __future__ import annotations

from types import SimpleNamespace

import picture_capture.processing as processing
from picture_capture import crop_plan_formatting as formatting


def test_phase7j_core_reexports_crop_plan_formatting_helpers() -> None:
    for name in (
        "entry_crop_piece_filename",
        "_normalized_crop_name",
        "polygon_display_name",
        "page_crop_plan_dict",
    ):
        assert getattr(processing._core, name) is getattr(formatting, name)


def test_crop_plan_formatting_keeps_name_contracts() -> None:
    piece = SimpleNamespace(output_index=3, suffix="_P1")
    region = SimpleNamespace(label="illustration|Plate A|linked")

    assert formatting.entry_crop_piece_filename("page", piece) == "page_WW_003_P1.png"
    assert formatting._normalized_crop_name("  Ｈｅａｄ  Word (P1) ") == "head word"
    assert formatting.polygon_display_name(region, 0) == "Plate A"
    assert formatting.polygon_display_name(SimpleNamespace(label=""), 2) == "P_03"


def test_crop_plan_dict_keeps_source_coordinate_schema() -> None:
    plan = SimpleNamespace(
        integrate_illustrations=True,
        entry_pieces=[
            SimpleNamespace(
                output_index=1,
                entry_ref_index=4,
                word="alpha",
                box=(1, 2, 30, 40),
                suffix="",
                source_mode="entry",
                merge_polygon_indices=(2, 5),
            )
        ],
        illustrations=[
            SimpleNamespace(
                polygon_index=2,
                name="Plate",
                associated_entry_index=4,
                associated_word="alpha",
                relation="linked",
                standalone=False,
                box=(5, 6, 20, 25),
            )
        ],
    )

    payload = formatting.page_crop_plan_dict(plan)

    assert payload["version"] == 3
    assert payload["coordinate_space"] == "source_image_pixels"
    assert payload["box_format"] == "source_xyxy"
    assert payload["entry_pieces"][0]["box"] == [1, 2, 30, 40]
    assert payload["illustrations"][0]["box"] == [5, 6, 20, 25]


def test_phase7j_public_assignment_still_mirrors_crop_plan_helper(monkeypatch) -> None:
    def fake_plan_dict(_plan):
        return {"fake": True}

    monkeypatch.setattr(processing, "page_crop_plan_dict", fake_plan_dict)

    assert processing._core.page_crop_plan_dict is fake_plan_dict
