from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.formats import read_pdic, read_ppp, write_pdic, write_ppp, read_picdic_index_records
from picture_capture.app import (
    PictureCaptureApp, _candidate_choice_rows, _parse_words_of_pages_text, _fill_page_entries,
    _build_words_page_lookup, _resolve_words_page_token, _parse_merged_pdic_text, _write_pdic_atomic,
    _natural_text_key, _sorted_page_list_rows, project_language_from_ocr,
    transformed_geometry_pending,
)
from picture_capture.models import AppSettings, Entry, PolygonRegion, ProjectState
from picture_capture.processing import Geometry, ColumnPath, sort_entries_reading_order, sort_entries_column_y
from picture_capture.layout_detection import (
    _detect_persistent_vertical_rule,
    _projection_layout_estimate,
    detect_layout_parameters,
    infer_layout_from_boxes,
)
from picture_capture.layout_detection import LayoutEstimate, aggregate_layout_estimates
from picture_capture.layout_transform import LayoutTransform
from picture_capture.collation import available_profile_labels, collation_key, parse_custom_order
from picture_capture.dictionary_profile import (
    PROFILE_FORMAT_V2, PROFILE_FORMAT_V3, available_dictionary_profiles, dictionary_profile_labels,
    dictionary_profile_preset, load_dictionary_profile, profile_effective_settings, profile_layout_summary,
    write_project_profile,
)
from picture_capture.ocr_engines import _lens_payload_records, find_tesseract
from picture_capture.paddle_headwords import (
    OCRRecord,
    detect_paddle_headwords,
    extract_ocr_records,
    filter_headword_records,
    group_ocr_records,
    normalize_headword,
    parse_headword_text,
    parse_headword_filter_rules,
    recognize_paddle_text,
    refine_separator_y,
    _annotate_alphabetical_warnings,
    _diagnostic_text,
    _comparison_text,
    _pair_ocr_candidates,
    _arbitrate_pair,
    _agreement_summary,
    _issues_text,
    _pair_with_lens_candidates,
    _apply_pair_engine_position,
)
from picture_capture.processing import (
    clamp_box,
    derive_geometry, derive_nominal_geometry,
    detect_entries,
    import_ocred,
    export_ocred,
    line_box,
    process_ocr_text,
    split_single_lines,
    split_whole_entries,
    split_illustrations,
    illustration_crop_bounds,
    illustration_polygon_box,
    build_page_crop_plan,
    Geometry,
    ColumnPath,
    entry_crop_column_boxes,
    CropRecord,
    append_crop_log,
)


class FormatTests(unittest.TestCase):

    def test_layout_transform_points_boxes_images_and_markers_round_trip(self) -> None:
        source_size = (7, 5)
        image = Image.new("RGB", source_size, "white")
        image.putpixel((6, 1), (12, 34, 56))
        for kind in ("identity", "mirror_x", "rotate_ccw90", "rotate_cw90"):
            transform = LayoutTransform(kind)
            for point in ((0, 0), (6, 4), (3, 2), (6, 1)):
                canonical = transform.source_to_canonical_point(*point, source_size)
                self.assertEqual(transform.canonical_to_source_point(*canonical, source_size), point)
            box = (1, 1, 6, 4)
            self.assertEqual(
                transform.canonical_box_to_source(transform.source_box_to_canonical(box, source_size), source_size),
                box,
            )
            self.assertEqual(transform.canonical_image_for_analysis(image).size, transform.canonical_size(source_size))

        mirror = LayoutTransform("mirror_x")
        self.assertEqual(mirror.source_to_canonical_point(6, 1, source_size), (0, 1))
        ccw = LayoutTransform("rotate_ccw90")
        self.assertEqual(ccw.source_to_canonical_point(6, 1, source_size), (1, 0))
        marker = ccw.canonical_marker_to_source((1, 2), (4, 2), source_size)
        self.assertEqual(marker, ((4, 1), (4, 4)))
        self.assertEqual(ccw.source_segment_to_canonical(*marker, source_size), ((1, 2), (4, 2)))

    def test_layout_analysis_transform_does_not_mutate_source_pixels(self) -> None:
        source = Image.new("RGB", (4, 3), "white")
        source.putpixel((3, 0), (1, 2, 3))
        before = source.tobytes()
        canonical = LayoutTransform("mirror_x").canonical_image_for_analysis(source)
        self.assertEqual(canonical.getpixel((0, 0)), (1, 2, 3))
        self.assertEqual(source.tobytes(), before)

    def test_nonidentity_layout_detection_runs_in_canonical_space(self) -> None:
        image = Image.new("RGB", (400, 600), "white")
        draw = ImageDraw.Draw(image)
        for y in range(80, 540, 30):
            draw.rectangle((30, y, 175, y + 12), fill="black")
            draw.rectangle((225, y, 370, y + 12), fill="black")
        estimate = detect_layout_parameters(
            image,
            AppSettings(
                parameter_display_width=400,
                columns=2,
                layout_columns_policy="fixed",
                layout_transform="mirror_x",
            ),
        )
        self.assertEqual(estimate.columns, 2)
        self.assertEqual(estimate.canonical_transform, "mirror_x")

    def test_layout_aggregation_uses_mode_median_and_fixed_prior(self) -> None:
        rows = [
            LayoutEstimate(column, y, 400, 40, 20, 900, 20, 2, 10)
            for column, y in zip((2, 2, 2, 2, 1), (100, 101, 99, 102, 900))
        ]
        detected, confidence = aggregate_layout_estimates(rows)
        self.assertEqual(detected["columns"], 2)
        self.assertEqual(detected["start_y"], 95)
        self.assertEqual(confidence, "2栏: 4/5 pages")
        fixed, _ = aggregate_layout_estimates(rows, columns_policy="fixed", fixed_columns=3)
        self.assertEqual(fixed["columns"], 3)

    def test_v21111_picdic_index_uses_saved_percentages_and_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "0013.pdic"
            path.write_text(
                "abbassare#123#456#12.345#45.675#0013#0012#0014\n"
                "secondo#50#60#5#6.2##0012#0014\n",
                encoding="utf-8",
            )
            rows = read_picdic_index_records(path, fallback_page="0013")
            self.assertEqual(rows, [
                "abbassare\t12.35\t45.67\t0013",
                "secondo\t5.00\t6.20\t0013",
            ])

    def test_v21111_picdic_index_sanitizes_tabs_and_requires_percent_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.pdic"
            path.write_text("A\tB#1#2#3%#4%#page#@#@\n", encoding="utf-8")
            self.assertEqual(read_picdic_index_records(path), ["A B\t3.00\t4.00\tpage"])
            path.write_text("bad#1#2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "缺少 X/Y 比例"):
                read_picdic_index_records(path)

    def test_v297_parse_merged_pdic_groups_pages_without_cross_page_spill(self) -> None:
        text = (
            "甲#20#300#2#30#0001#@#0002\n"
            "乙#20#100#2#10#1#@#0002\n"
            "丙#25#200#2.5#20#0002#0001#0003\n"
            "外页#25#500#2.5#50#9999#@#@\n"
        )
        mapping, stats = _parse_merged_pdic_text(text, ["0001", "0002", "0003"])

        self.assertEqual([entry.word for entry in mapping["0001"]], ["甲", "乙"])
        self.assertEqual([entry.y for entry in mapping["0001"]], [300, 100])
        self.assertEqual([entry.word for entry in mapping["0002"]], ["丙"])
        self.assertEqual(mapping["0003"], [])
        self.assertEqual(stats, {"records": 4, "matched": 3, "unmatched": 1})

    def test_v297_parse_merged_pdic_rejects_malformed_rows(self) -> None:
        with self.assertRaisesRegex(ValueError, "文件为空"):
            _parse_merged_pdic_text("\n\n", ["0001"])
        with self.assertRaisesRegex(ValueError, "字段不足 8 个"):
            _parse_merged_pdic_text("bad#1#2\n", ["0001"])
        with self.assertRaisesRegex(ValueError, "坐标无效"):
            _parse_merged_pdic_text("词#x#2#0#0#0001#@#@\n", ["0001"])

    def test_v297_atomic_restore_overwrites_page_and_can_clear_to_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "0001.pdic"
            write_pdic(path, [Entry("旧", 10, 20)], 1000, ("0001", "@", "0002"))

            _write_pdic_atomic(
                path, [Entry("新", 30, 40)], 1000, ("0001", "@", "0002")
            )
            restored = read_pdic(path)
            self.assertEqual([(entry.word, entry.x, entry.y) for entry in restored], [("新", 30, 40)])
            self.assertFalse((Path(tmp) / ".0001.pdic.restore.tmp").exists())

            _write_pdic_atomic(path, [], 1000, ("0001", "@", "0002"))
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), "")
            self.assertEqual(read_pdic(path), [])

    def test_v283_page_range_accepts_hyphen_and_leading_zeroes(self) -> None:
        class FakeProject:
            images = [Path(f"{n:04d}.png") for n in range(1, 31)]

        app = PictureCaptureApp.__new__(PictureCaptureApp)
        app.project = FakeProject()

        self.assertEqual(app._parse_page_spec("0008-0020"), list(range(7, 20)))
        self.assertEqual(app._parse_page_spec("0008–0010,0015,0020~0022"), [7, 8, 9, 14, 19, 20, 21])

    def test_numeric_page_range_excludes_auxiliary_suffix_pages(self) -> None:
        class FakeProject:
            images = (
                [Path(f"0000_{n:02d}.png") for n in range(1, 13)]
                + [Path(f"{n:04d}.png") for n in range(1, 101)]
            )

        app = PictureCaptureApp.__new__(PictureCaptureApp)
        app.project = FakeProject()

        self.assertEqual(app._parse_page_spec("1-100"), list(range(12, 112)))
        self.assertEqual(app._parse_page_spec("1"), [12])

    def test_page_range_rejects_missing_page_before_work_starts(self) -> None:
        class FakeProject:
            images = [Path("0001.png"), Path("0002.png"), Path("0004.png")]

        app = PictureCaptureApp.__new__(PictureCaptureApp)
        app.project = FakeProject()

        with self.assertRaisesRegex(ValueError, "以下页码不存在：3"):
            app._parse_page_spec("1-4")


    def test_v276_projection_layout_fallback_detects_two_columns(self) -> None:
        image = Image.new("RGB", (1200, 1600), "white")
        draw = ImageDraw.Draw(image)
        for x in range(300, 900, 40):
            draw.rectangle((x, 60, x + 20, 78), fill="black")
        for y in range(180, 1500, 36):
            for left, right in ((80, 550), (650, 1120)):
                x = left
                while x < right - 20:
                    width = 25 + ((x + y) // 13) % 45
                    draw.rectangle((x, y, min(x + width, right), y + 14), fill="black")
                    x += width + 12
        settings = AppSettings()
        settings.parameter_display_width = 1200

        estimate = _projection_layout_estimate(image, settings)

        self.assertEqual(estimate.method, "projection_fallback")
        self.assertEqual(estimate.columns, 2)
        self.assertTrue(150 <= estimate.start_y <= 220)
        self.assertTrue(430 <= estimate.column_width <= 520)
        self.assertTrue(70 <= estimate.gutter <= 130)

    def test_fixed_projection_detects_divider_and_complete_gutter(self) -> None:
        image = Image.new("RGB", (1000, 1200), "white")
        draw = ImageDraw.Draw(image)
        for row, y in enumerate(range(100, 1100, 32)):
            for left, right in ((50, 430), (570, 950)):
                for x in range(left + row % 3 * 2, right, 35):
                    draw.rectangle((x, y, min(x + 20, right), y + 12), fill="black")
        draw.rectangle((497, 100, 502, 1099), fill="black")
        settings = AppSettings(
            geometry_coordinate_version=1,
            geometry_coordinate_space="legacy_display_pixels",
            parameter_display_width=1000,
            columns=2,
            layout_columns_policy="fixed",
            layout_column_separator_mode="present",
        )

        estimate = _projection_layout_estimate(image, settings)

        self.assertEqual(estimate.columns, 2)
        self.assertTrue(495 <= (estimate.separator_x or 0) <= 505)
        self.assertTrue(130 <= estimate.gutter <= 155)

    def test_v221_editor_sync_keeps_text_bound_after_middle_entry_removal(self) -> None:
        class FakeEditor:
            def __init__(self, text: str) -> None:
                self.text = text

            def get(self) -> str:
                return self.text

        first = Entry("alo", 20, 100)
        rejected = Entry("preparado", 20, 180)
        second = Entry("alocado", 20, 220)
        third = Entry("alocución", 20, 500)
        app = PictureCaptureApp.__new__(PictureCaptureApp)
        app.entries = [first, second, third]
        app.entry_editor_bindings = [
            (FakeEditor("alo"), first),
            (FakeEditor("preparado"), rejected),
            (FakeEditor("alocado"), second),
            (FakeEditor("alocución"), third),
        ]

        PictureCaptureApp._sync_entry_editor_texts(app)

        self.assertEqual([entry.word for entry in app.entries], ["alo", "alocado", "alocución"])


    def test_v27_review_save_bypasses_stale_main_editor_text(self) -> None:
        class FakeEditor:
            def get(self) -> str:
                return "stale-main-value"

        class FakeProject:
            def __init__(self, page: Path) -> None:
                self.images = [page]

        with tempfile.TemporaryDirectory() as raw:
            page = Path(raw) / "p001.png"
            Image.new("RGB", (200, 300), "white").save(page)
            entry = Entry("review-value", 20, 40)
            app = PictureCaptureApp.__new__(PictureCaptureApp)
            app.project = FakeProject(page)
            app.current_page = page
            app.current_index = 0
            app.image = Image.new("RGB", (200, 300), "white")
            app.entries = [entry]
            app.entry_editor_bindings = [(FakeEditor(), entry)]
            app._update_page_row = lambda _index: None

            PictureCaptureApp.save_pdic(app, silent=True, sync_editors=False)

            self.assertEqual(read_pdic(page.with_suffix(".pdic"))[0].word, "review-value")
            self.assertEqual(entry.word, "review-value")

    def test_v27_main_and_review_typography_are_independent_settings(self) -> None:
        settings = AppSettings(
            main_entry_font_family="Arial", main_entry_font_size=11,
            main_entry_font_bold=True, main_entry_font_italic=False,
            review_entry_font_family="Cambria", review_entry_font_size=19,
            review_entry_font_bold=False, review_entry_font_italic=True,
        )
        self.assertEqual(settings.main_entry_font_family, "Arial")
        self.assertEqual(settings.review_entry_font_family, "Cambria")
        self.assertTrue(settings.main_entry_font_bold)
        self.assertTrue(settings.review_entry_font_italic)

    def test_default_headword_ocr_uses_paddle_only(self) -> None:
        settings = AppSettings()
        self.assertEqual(settings.detection_method, "paddleocr")
        self.assertTrue(settings.paddle_use_paddleocr)
        self.assertFalse(settings.paddle_compare_tesseract)
        self.assertFalse(settings.paddle_enable_lens)
        self.assertEqual(settings.paddle_lens_mode, "off")

    def test_legacy_settings_import(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "_Mysettings.ini"
            fields = ["root", "page", "3", "44", "500", "60", "400", "31", "28", "4", "1.2", "6", "2", "4", "320", "88", "7", "6", "1"]
            path.write_text("@".join(fields), encoding="utf-8")
            settings = AppSettings.from_legacy(path)
            self.assertEqual(settings.columns, 3)
            self.assertEqual(settings.gutter, 44)
            self.assertEqual(settings.column_width, 500)
            self.assertEqual(settings.ocr_language, "spa")

    def test_v14_paddle_defaults_migrate_without_touching_custom_values(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "picture_capture_settings.json"
            legacy_regex = r"^\s*[•◆◇■□►▶*†‡§¶]?\s*([^\W\d_]+(?:[-'’][^\W\d_]+)*)"
            import json
            path.write_text(json.dumps({
                "paddle_headword_regex": legacy_regex,
                "paddle_band_width": 180,
                "paddle_min_candidate_score": 4.0,
            }, ensure_ascii=False), encoding="utf-8")
            settings = AppSettings.from_json(path)
            self.assertEqual(settings.paddle_band_width, 600)
            self.assertEqual(settings.paddle_min_candidate_score, 5.0)
            self.assertIn("·", settings.paddle_headword_regex)

            old_pos = (
                r"(?:s\.?\s*(?:m|f|com|n)\.?|adj\.?\s*(?:inv\.?)?|adv\.?|"
                r"[vy]\.(?:\s*prnl\.?)?|prep\.?|conj\.?|pron\.?|interj\.?|"
                r"art\.?|num\.?|loc\.?|superlat\.?(?:\s*irreg\.?)?)"
            )
            path.write_text(json.dumps({"paddle_pos_regex": old_pos}), encoding="utf-8")
            migrated_pos = AppSettings.from_json(path)
            self.assertIn("s\\.", migrated_pos.paddle_pos_regex)
            self.assertNotEqual(migrated_pos.paddle_pos_regex, old_pos)

            path.write_text(json.dumps({
                "paddle_headword_regex": r"^(\w+)",
                "paddle_band_width": 250,
                "paddle_min_candidate_score": 6.5,
            }), encoding="utf-8")
            custom = AppSettings.from_json(path)
            self.assertEqual(custom.paddle_band_width, 250)
            self.assertEqual(custom.paddle_min_candidate_score, 6.5)
            self.assertEqual(custom.paddle_headword_regex, r"^(\w+)")

    def test_v2112_pdic_round_trip_preserves_canonical_caller_order(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "p001.pdic"
            entries = [Entry("beta", 600, 70), Entry("alpha", 20, 100)]
            write_pdic(path, entries, 1000, ("p001", "@", "p002"))
            loaded = read_pdic(path)
            self.assertEqual([(e.word, e.x, e.y) for e in loaded], [("beta", 600, 70), ("alpha", 20, 100)])
            self.assertIn("#p001#@#p002", path.read_text(encoding="utf-8"))

    def test_v2112_manual_and_ocr_lines_merge_in_column_then_y_order(self) -> None:
        geometry = Geometry(
            column_starts=[20, 520],
            column_widths=[420, 420],
            top=0, bottom=1000,
            column_paths=[ColumnPath([(0, 20), (1000, 20)]), ColumnPath([(0, 520), (1000, 520)])],
        )
        entries = [
            Entry("ocr-late", 42, 300),
            Entry("manual-middle", 20, 200),
            Entry("ocr-early", 38, 100),
            Entry("right-column", 545, 50),
        ]
        ordered = sort_entries_reading_order(entries, geometry)
        self.assertEqual(
            [entry.word for entry in ordered],
            ["ocr-early", "manual-middle", "ocr-late", "right-column"],
        )

    def test_ppp_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "p001.PPP"
            regions = [PolygonRegion("figure", [(1, 2), (3, 4), (5, 6)])]
            write_ppp(path, regions, "p001")
            self.assertEqual(read_ppp(path), regions)

    def test_ocred_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "p001.OCRed"
            export_ocred(path, ["alpha", "bé"])
            self.assertEqual(import_ocred(path), ["alpha", "bé"])

    def test_v26_language_driven_collation_profiles(self) -> None:
        spa = available_profile_labels("spa")
        eng = available_profile_labels("eng")
        self.assertIn("西班牙语（现代）", spa)
        self.assertIn("西班牙语（传统：ch / ll 为整体字母）", spa)
        self.assertNotIn("英语（A–Z）", spa)
        self.assertIn("英语（A–Z）", eng)
        self.assertIn("自定义排序规则", spa)
        self.assertIn("自定义排序规则", eng)

    def test_v26_spanish_n_tilde_and_traditional_digraphs(self) -> None:
        self.assertEqual(
            sorted(["oso", "nube", "ñandú"], key=lambda w: collation_key(w, "auto", "spa")),
            ["nube", "ñandú", "oso"],
        )
        self.assertEqual(
            sorted(["dado", "chico", "cielo", "cabra"], key=lambda w: collation_key(w, "spa_traditional", "spa")),
            ["cabra", "cielo", "chico", "dado"],
        )

    def test_v26_custom_multichar_collation(self) -> None:
        order = "a b c ch d e f g h i j k l ll m n ñ o p q r s t u v w x y z"
        self.assertIn("ch", parse_custom_order(order))
        self.assertEqual(
            sorted(["dado", "chico", "cielo", "cabra"], key=lambda w: collation_key(w, "custom", "eng", order)),
            ["cabra", "cielo", "chico", "dado"],
        )


class ProcessingTests(unittest.TestCase):
    def make_page(self, path: Path) -> Image.Image:
        image = Image.new("RGB", (1200, 900), "white")
        draw = ImageDraw.Draw(image)
        for x in (30, 630):
            for y in (100, 260, 500):
                draw.rectangle((x, y, x + 18, y + 15), fill="black")
                draw.rectangle((x + 35, y, x + 180, y + 12), fill="black")
        image.save(path)
        return image

    def test_detection(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            image = self.make_page(Path(raw) / "p001.png")
            settings = AppSettings(
                columns=2, manual_x=30, column_width=550, gutter=50,
                start_y=40, detection_method="left_edge",
            )
            entries, geometry = detect_entries(image, settings)
            self.assertEqual(len(geometry.column_starts), 2)
            self.assertEqual(len(entries), 6)
            self.assertTrue(all(entry.word == "" for entry in entries))

    def test_geometry_parameters_use_displayed_image_pixels(self) -> None:
        image = Image.new("RGB", (2000, 1200), "white")
        settings = AppSettings(
            geometry_coordinate_version=1,
            geometry_coordinate_space="legacy_display_pixels",
            parameter_display_width=1000,
            columns=2,
            manual_x=50,
            column_width=400,
            gutter=50,
            start_y=25,
            character_height=20,
            row_padding=3,
            follow_column_deformation=False,
        )
        geometry = derive_geometry(image, settings)
        self.assertEqual(geometry.column_starts, [100, 1000])
        self.assertEqual(geometry.top, 50)
        box = line_box(Entry("word", 100, 200), geometry, image, settings)
        self.assertEqual(box[1], 194)
        self.assertEqual(box[3] - box[1], 52)

    def test_detection_converts_display_parameters_to_source_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            small = self.make_page(Path(raw) / "small.png")
            image = small.resize((2400, 1800), Image.Resampling.NEAREST)
            settings = AppSettings(
                geometry_coordinate_version=1,
                geometry_coordinate_space="legacy_display_pixels",
                parameter_display_width=1200,
                columns=2,
                manual_x=30,
                column_width=550,
                gutter=50,
                start_y=40,
                detection_method="left_edge",
                follow_column_deformation=False,
            )
            entries, geometry = detect_entries(image, settings)
            self.assertEqual(geometry.column_starts, [60, 1260])
            self.assertEqual(len(entries), 6)
            self.assertTrue(all(entry.y >= 190 for entry in entries))

    def test_deformed_column_tracking(self) -> None:
        image = Image.new("RGB", (800, 700), "white")
        draw = ImageDraw.Draw(image)
        draw.line((5, 0, 5, 699), fill="black", width=2)  # scan border, not a text edge
        for base_x in (30, 430):
            for y in range(80, 650, 45):
                x = base_x + round(0.08 * y)
                draw.rectangle((x, y, x + 110, y + 14), fill="black")
        settings = AppSettings(
            columns=2, manual_x=30, column_width=350, gutter=50,
            start_y=50, body_indent=24, character_height=20,
            detection_method="left_edge", follow_column_deformation=True,
            column_track_radius=90, column_track_block_height=100,
            column_track_max_step=20
        )
        geometry = derive_geometry(image, settings)
        self.assertAlmostEqual(geometry.x_at(0, 100), 38, delta=8)
        self.assertAlmostEqual(geometry.x_at(0, 600), 78, delta=8)
        tracked, _ = detect_entries(image, settings)
        settings.follow_column_deformation = False
        fixed, _ = detect_entries(image, settings)
        self.assertEqual(len(tracked), 26)
        self.assertLess(len(fixed), len(tracked))

    def test_paddle_result_parsing_and_headword_detection(self) -> None:
        class FakeResult:
            json = {
                "res": {
                    "rec_texts": ["caffè s.m.", "definition text", "◆ amore"],
                    "rec_scores": np.asarray([0.97, 0.94, 0.96]),
                    "rec_boxes": np.asarray([
                        [10, 28, 105, 50], [60, 63, 170, 76], [10, 123, 100, 145],
                    ]),
                }
            }

        class FakeEngine:
            def predict(self, _image, **_kwargs):
                return [FakeResult()]

        records = extract_ocr_records(FakeResult())
        self.assertEqual(records[0].text, "caffè s.m.")
        self.assertEqual(records[0].box, (10, 28, 105, 50))
        with tempfile.TemporaryDirectory() as raw:
            image = Image.new("RGB", (800, 700), "white")
            settings = AppSettings(
                columns=2, manual_x=30, column_width=350, gutter=50, start_y=0,
                follow_column_deformation=False, paddle_band_width=180,
            )
            geometry = derive_geometry(image, settings)
            cache_path = Path(raw) / "page.json"
            entries = detect_paddle_headwords(
                image, geometry, settings, cache_path=cache_path, engine=FakeEngine(),
            )
            self.assertEqual([entry.word for entry in entries], ["caffè", "amore", "caffè", "amore"])
            self.assertTrue(cache_path.exists())
            diagnostic_path = cache_path.with_name("page_ocr_diagnostics.txt")
            comparison_path = cache_path.with_name("page_ocr_comparison.txt")
            self.assertTrue(diagnostic_path.exists())
            self.assertTrue(comparison_path.exists())
            self.assertIn("caffè s.m.", diagnostic_path.read_text(encoding="utf-8"))
            self.assertEqual({len(line.split("\t")) for line in diagnostic_path.read_text(encoding="utf-8").splitlines()}, {12})
            self.assertEqual({len(line.split("\t")) for line in comparison_path.read_text(encoding="utf-8").splitlines()}, {27})
            import json
            report = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertIn("paddle_full_text", report["columns"][0])
            self.assertIn("paddle_merged_lines", report["columns"][0])
            cached = detect_paddle_headwords(
                image, geometry, settings, cache_path=cache_path,
                engine=object(),  # A valid cache must avoid calling the engine.
            )
            self.assertEqual(cached, entries)
            self.assertEqual(recognize_paddle_text(image, settings, FakeEngine()), "caffè s.m. definition text ◆ amore")


    def test_dictionary_headword_normalization_and_pos_cues(self) -> None:
        settings = AppSettings(ocr_language="spa")
        samples = {
            "a·ga·rrón (pl. agarrones) s.m. Acción de agarrar": "agarrón",
            "a.ga.rro.ta.mien.to s.m. Rigidez": "agarrotamiento",
            "a-ga-rrón (pl. agarrones) s.n. Acción": "agarrón",
            "a-ga.rro-ta-mien:to s.m. Rigidez": "agarrotamiento",
            "a · ga · za · par · se v.prnl. Esconderse": "agazaparse",
            "a·gen·te adj.inv./s.m. Que realiza": "agente",
            "anti-inflamatorio adj. Que combate": "anti-inflamatorio",
            "ag·nós·ti·co, ca adj. Relacionado": "agnóstico",
            "a·go·re·ro, ra adj./s. Que predice": "agorero",
            "a·gra·da·bi·lí·si·mo, ma superlat. irreg. de agradable": "agradabilísimo",
        }
        for text, expected in samples.items():
            parsed = parse_headword_text(text, settings)
            self.assertIsNotNone(parsed, text)
            assert parsed is not None
            self.assertEqual(parsed.normalized, expected)
            self.assertTrue(parsed.has_pos, text)
        self.assertEqual(normalize_headword("l’ami"), "l’ami")
        self.assertEqual(normalize_headword("á-gil"), "ágil")
        self.assertEqual(normalize_headword("anti-inflamatorio"), "anti-inflamatorio")
        self.assertEqual(normalize_headword("ex-presidente"), "ex-presidente")
        agent = parse_headword_text("agente Il adj.inv./s.m. Que realiza", settings)
        self.assertIsNotNone(agent)
        assert agent is not None
        self.assertTrue(agent.has_pos)
        body = parse_headword_text("des” es el agente. M s.com. 2 Persona", settings)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertFalse(body.has_pos)
        plural_only = parse_headword_text("aglomeración (pl. aglomeraciones) :", settings)
        self.assertIsNotNone(plural_only)
        assert plural_only is not None
        self.assertTrue(plural_only.has_inflection)
        bound = parse_headword_text("-a·go·gia, -a·go·gí·a Elemento compositivo que indica conducción", settings)
        self.assertIsNotNone(bound)
        assert bound is not None
        self.assertEqual(bound.normalized, "-agogia")
        self.assertTrue(bound.has_descriptor)

    def test_page54_bare_s_and_syllabified_gender_variants(self) -> None:
        settings = AppSettings(ocr_language="spa")
        samples = {
            "a·gra·de·ci·do, da adj. 1 Que tiende": "agradecido",
            "a·gre·ga·do, da s. 1 Funcionario": "agregado",
            "a·gre·si·vo, va adj. 1 Que actúa": "agresivo",
            "a·gre·sor, so·ra adj./s. Que comete": "agresor",
            "a·gri·cul·tor, to·ra s. Persona": "agricultor",
        }
        for text, expected in samples.items():
            parsed = parse_headword_text(text, settings)
            self.assertIsNotNone(parsed, text)
            assert parsed is not None
            self.assertEqual(parsed.normalized, expected)
            self.assertTrue(parsed.has_pos, text)

    def test_headword_digit_confusion_is_repaired_only_in_initial_lemma(self) -> None:
        settings = AppSettings(ocr_language="spa")
        parsed = parse_headword_text("a-g6-ni-co, ca adj. 2 Estado", settings)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.raw, "a-g6-ni-co")
        self.assertEqual(parsed.corrected_raw, "a-go-ni-co")
        self.assertEqual(parsed.normalized, "agonico")
        self.assertTrue(parsed.has_pos)
        self.assertIn("6->o", parsed.ocr_repairs[0])
        # Definition numbering must remain untouched.
        self.assertIn("2 Estado", parsed.parse_text)

    def test_active_right_fragment_absorption_recovers_pos(self) -> None:
        settings = AppSettings(
            ocr_language="spa", parameter_display_width=360, paddle_band_width=360,
            paddle_auto_header_rule=False, paddle_rec_score_threshold=0.20,
        )
        band = Image.new("RGB", (360, 120), "white")
        # Deliberately offset the POS box vertically so normal grouping leaves it
        # separate; the left-edge rescue should absorb it and recover the entry.
        records = [
            OCRRecord("a·gre·ga·do, da", 0.98, (8, 25, 155, 48)),
            OCRRecord("s. 1 Funcionario", 0.96, (165, 39, 320, 61)),
            OCRRecord("texto de otra línea", 0.99, (8, 75, 250, 96)),
        ]
        entries, _diagnostics = filter_headword_records(records, band, 0, 20, settings)
        self.assertIn("agregado", [entry.word for entry in entries])

    def test_paddle_merges_split_headword_and_pos_boxes(self) -> None:
        records = [
            OCRRecord("a·ga·rrón", 0.98, (10, 30, 95, 52)),
            OCRRecord("(pl. agarrones) s.m.", 0.96, (100, 31, 255, 52)),
            OCRRecord("Acción de agarrar", 0.95, (55, 65, 220, 84)),
        ]
        lines = group_ocr_records(records)
        self.assertEqual(len(lines), 2)
        self.assertIn("s.m.", lines[0].text)
        parsed = parse_headword_text(lines[0].text, AppSettings(ocr_language="spa"))
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.normalized, "agarrón")
        self.assertTrue(parsed.has_pos)

    def test_separator_y_refinement_uses_low_ink_valley(self) -> None:
        settings = AppSettings(
            paddle_refine_separator_y=True,
            paddle_separator_search_ratio=0.30,
            paddle_separator_band_radius=2,
            paddle_separator_column_margin=4,
        )
        # Simulate two tightly packed dictionary lines.  The preceding line has
        # descenders down to y=49; the next headword begins at y=58.  A coarse
        # OCR marker at y=50 would cross the descenders, while the safe
        # inter-line valley is roughly y=52..55 after the 5-row safety average.
        gray = np.full((100, 300), 255, dtype=np.uint8)
        gray[35:46, 20:280] = 35
        gray[46:50, 120:150] = 35  # g/q/y-like descender
        gray[58:76, 20:285] = 35
        refined, details = refine_separator_y(
            gray, coarse_y=50, line_height=24, settings=settings,
            reference_to_canonical_scale=1.0,
        )
        self.assertGreater(refined, 50)
        self.assertLess(refined, 58)
        self.assertEqual(details["refined_y"], refined)
        self.assertLess(details["minimum_ink_ratio"], details["coarse_ink_ratio"])

    def test_separator_y_refinement_can_be_disabled(self) -> None:
        settings = AppSettings(paddle_refine_separator_y=False)
        gray = np.full((60, 200), 255, dtype=np.uint8)
        refined, details = refine_separator_y(gray, 30, 20, settings)
        self.assertEqual(refined, 30)
        self.assertFalse(details["enabled"])


    def test_pos_cue_does_not_match_conjug_prefix_or_hyphenated_fragments(self) -> None:
        settings = AppSettings(ocr_language="spa")

        sa = parse_headword_text("sa. □ Conjug. → HABLAR (4).", settings)
        self.assertIsNotNone(sa)
        assert sa is not None
        self.assertFalse(sa.has_pos)
        self.assertTrue(sa.looks_like_continuation)

        blacion = parse_headword_text("blación. □ Conjug. → HABLAR (4).", settings)
        self.assertIsNotNone(blacion)
        assert blacion is not None
        self.assertFalse(blacion.has_pos)
        self.assertTrue(blacion.looks_like_continuation)

        genuine = parse_headword_text("agitación (pl. agitaciones) s.f. Movimiento", settings)
        self.assertIsNotNone(genuine)
        assert genuine is not None
        self.assertTrue(genuine.has_pos)
        self.assertFalse(genuine.looks_like_continuation)

    def test_false_continuation_fragments_are_rejected_as_headwords(self) -> None:
        settings = AppSettings(
            ocr_language="spa", parameter_display_width=320, paddle_band_width=320,
            paddle_min_candidate_score=5.0, paddle_auto_header_rule=False,
        )
        band = Image.new("RGB", (320, 180), "white")
        records = [
            OCRRecord("sa. □ Conjug. → HABLAR (4).", 0.99, (8, 20, 260, 42)),
            OCRRecord("a·gen·cia s.f. 1 Empresa", 0.99, (8, 55, 260, 79)),
            OCRRecord("blación. □ Conjug. → HABLAR (4).", 0.99, (8, 95, 305, 117)),
            OCRRecord("a·glo·me·ra·ción (pl. aglomeraciones) s.f. Reunión", 0.99, (8, 130, 315, 154)),
        ]
        entries, diagnostics = filter_headword_records(records, band, 0, 20, settings)
        self.assertEqual([entry.word for entry in entries], ["agencia", "aglomeración"])
        sa_diag = next(item for item in diagnostics[1:] if item.get("normalized_headword") == "sa")
        blacion_diag = next(item for item in diagnostics[1:] if item.get("normalized_headword") == "blación")
        self.assertFalse(sa_diag["accepted"])
        self.assertFalse(blacion_diag["accepted"])
        self.assertTrue(sa_diag["looks_like_continuation"])
        self.assertTrue(blacion_diag["looks_like_continuation"])

    def test_first_content_headword_uses_first_sustained_ink_y(self) -> None:
        settings = AppSettings(
            ocr_language="spa", parameter_display_width=300, paddle_band_width=300,
            row_padding=3, paddle_auto_header_rule=False, paddle_refine_separator_y=True,
            paddle_separator_search_ratio=0.30, paddle_separator_band_radius=2,
        )
        band = Image.new("RGB", (300, 150), "white")
        draw = ImageDraw.Draw(band)
        # OCR top is slightly early (36) while actual printed ink starts at 40.
        # The first-entry rule should move down to the first sustained ink row,
        # not into the blank top margin.
        draw.rectangle((15, 40, 280, 58), fill="black")
        records = [OCRRecord("a·ga·rrón (pl. agarrones) s.m.", 0.99, (10, 36, 270, 61))]
        entries, diagnostics = filter_headword_records(records, band, 0, 20, settings, separator_band=band)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].y, 40)
        candidate = next(item for item in diagnostics[1:] if item.get("accepted"))
        self.assertEqual(candidate["separator_refinement"]["reason"], "first_sustained_ink_onset")
        self.assertGreater(candidate["separator_refinement"]["shift"], 0)

    def test_page53_gender_variants_and_bound_morphemes_pass_structure_rules(self) -> None:
        settings = AppSettings(
            ocr_language="spa", parameter_display_width=600, paddle_band_width=600,
            paddle_auto_header_rule=False, paddle_min_candidate_score=5.0,
        )
        band = Image.new("RGB", (600, 360), "white")
        records = [
            OCRRecord("ag·nós·ti·co, ca adj. Del agnosticismo", 0.95, (8, 20, 470, 45)),
            OCRRecord("-a·go·gia, -a·go·gí·a Elemento compositivo que indica conducción", 0.94, (8, 80, 590, 106)),
            OCRRecord("-a·go·go, -a·go·ga Elemento compositivo que significa guía", 0.94, (8, 140, 585, 166)),
            OCRRecord("a·go·re·ro, ra adj./s. Que predice males", 0.96, (8, 200, 500, 226)),
            OCRRecord("a·gra·da·bi·lí·si·mo, ma superlat. irreg. de agradable", 0.96, (8, 260, 590, 286)),
        ]
        entries, diagnostics = filter_headword_records(records, band, 0, 20, settings, separator_band=band)
        words = [entry.word for entry in entries]
        self.assertEqual(words, ["agnóstico", "-agogia", "-agogo", "agorero", "agradabilísimo"])
        self.assertTrue(all(item.get("accepted") for item in diagnostics[1:]))

    def test_open_projection_valley_does_not_shift_separator(self) -> None:
        settings = AppSettings(
            paddle_refine_separator_y=True, paddle_separator_search_ratio=0.30,
            paddle_separator_band_radius=2, paddle_separator_column_margin=4,
        )
        gray = np.full((100, 260), 255, dtype=np.uint8)
        # Only the current line is present; the upper blank area reaches the
        # search boundary, so it is not a bounded inter-line valley.
        gray[45:66, 15:245] = 30
        refined, details = refine_separator_y(gray, coarse_y=40, line_height=24, settings=settings)
        self.assertEqual(refined, 40)
        self.assertEqual(details["reason"], "open_valley_at_search_edge_keep_coarse")

    def test_paddle_running_header_rule_is_ignored(self) -> None:
        settings = AppSettings(
            ocr_language="spa", parameter_display_width=300, paddle_band_width=300,
            paddle_header_search_height=80, paddle_header_rule_ink_ratio=0.5,
            paddle_header_rule_margin=4, paddle_min_candidate_score=5.0,
        )
        band = Image.new("RGB", (300, 260), "white")
        draw = ImageDraw.Draw(band)
        # Running header followed by a long horizontal separator.
        draw.rectangle((0, 48, 299, 50), fill="black")
        records = [
            OCRRecord("a·ga·rrón", 0.99, (10, 12, 100, 34)),
            OCRRecord("a·ga·rrón (pl. agarrones) s.m.", 0.99, (10, 70, 260, 94)),
            OCRRecord("a·ga·rro·tar v. Referido", 0.99, (10, 130, 245, 154)),
        ]
        entries, diagnostics = filter_headword_records(records, band, 0, 20, settings)
        self.assertEqual([entry.word for entry in entries], ["agarrón", "agarrotar"])
        meta = diagnostics[0]["meta"]
        self.assertGreater(meta["header_cutoff_band_y"], 50)
        header_candidate = next(item for item in diagnostics[1:] if item["source_y"] < 50)
        self.assertFalse(header_candidate["accepted"])
        self.assertFalse(header_candidate["features"]["below_header"])

    def test_text_rules(self) -> None:
        rules = [("N", "0", "o"), ("R", r"\s+", "")]
        self.assertEqual(process_ocr_text("  W0 RD  ", rules, True), "word")

    def test_external_headword_filter_rules_reject_accept_and_aliases(self) -> None:
        settings = AppSettings(
            paddle_rec_score_threshold=0.20,
            paddle_require_pos_or_symbol=True,
            paddle_min_candidate_score=5.0,
            paddle_refine_separator_y=False,
        )
        band = Image.new("RGB", (600, 180), "white")

        # A normal POS-bearing lemma is rejected by an explicit blacklist rule.
        reject_rules = parse_headword_filter_rules(
            "lemma_exact: agitación\naccept_lemma_exact: agitación\n", "test"
        )
        entries, diagnostics = filter_headword_records(
            [OCRRecord("a·gi·ta·ción s.f. Movimiento", 0.98, (5, 30, 330, 55))],
            band, 0, 10, settings, user_rules=reject_rules,
        )
        self.assertEqual(entries, [])
        candidate = next(item for item in diagnostics if "accepted" in item)
        self.assertTrue(candidate["user_rule"]["rejected"])
        self.assertFalse(candidate["accepted"])

        # A force-accept rule may rescue a parsed, left-aligned candidate that
        # intentionally lacks POS/inflection/descriptor evidence.
        accept_rules = parse_headword_filter_rules(
            "accept_line_contains: significado\n", "test"
        )
        entries, diagnostics = filter_headword_records(
            [OCRRecord("misterioso significado", 0.98, (5, 70, 260, 95))],
            band, 0, 10, settings, user_rules=accept_rules,
        )
        self.assertEqual([entry.word for entry in entries], ["misterioso"])
        candidate = next(item for item in diagnostics if "accepted" in item)
        self.assertTrue(candidate["user_rule"]["accepted"])
        self.assertTrue(candidate["features"]["forced_accept"])

    def test_external_headword_filter_rule_validation(self) -> None:
        rules = parse_headword_filter_rules(
            "# comment\nreject_lemma_regex: ^a.*\npos_exclude: Conjug.\n", "test"
        )
        self.assertEqual([rule.kind for rule in rules], ["reject_lemma_regex", "pos_exclude_exact"])
        with self.assertRaises(ValueError):
            parse_headword_filter_rules("unknown_rule: x", "test")
        with self.assertRaises(ValueError):
            parse_headword_filter_rules("reject_lemma_regex: [", "test")

    def test_external_filter_file_reuses_cached_ocr(self) -> None:
        class FakeResult:
            json = {
                "res": {
                    "rec_texts": ["a·gi·ta·ción s.f. Movimiento"],
                    "rec_scores": np.asarray([0.99]),
                    "rec_boxes": np.asarray([[5, 30, 300, 55]]),
                }
            }
        class FakeEngine:
            def predict(self, _image, **_kwargs):
                return [FakeResult()]

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            image = Image.new("RGB", (400, 180), "white")
            settings = AppSettings(
                columns=1, manual_x=0, column_width=350, gutter=0, start_y=0,
                follow_column_deformation=False, paddle_band_width=350,
                paddle_refine_separator_y=False,
            )
            geometry = derive_geometry(image, settings)
            cache_path = root / "QT" / "PaddleOCR" / "page.json"
            rules_path = root / "headword_filter_rules.txt"
            first = detect_paddle_headwords(
                image, geometry, settings, cache_path=cache_path, engine=FakeEngine(),
                filter_rules_path=rules_path,
            )
            self.assertEqual([entry.word for entry in first], ["agitación"])
            rules_path.write_text("reject_lemma_exact: agitación\n", encoding="utf-8")
            second = detect_paddle_headwords(
                image, geometry, settings, cache_path=cache_path, engine=object(),
                filter_rules_path=rules_path,
            )
            self.assertEqual(second, [])


    def test_v157_ocr_noise_descriptors_and_bound_morphemes(self) -> None:
        settings = AppSettings(ocr_language="spa")
        samples = {
            "a.gru-pa-mien+-to s.m. Reunión": "agrupamiento",
            "a-gro.-am-biental adj.inv. Que afecta": "agroambiental",
            "a-gro- Elemento compositivo que significa campo": "agro-",
            "-ai-co, -ai-ca Sufijo que indica pertenencia": "-aico",
            "-ai-na Sufijo que indica conjunto": "-aina",
            "Al Sigla de Amnistía Internacional": "Al",
            "agua Es.f. 1 Sustancia líquida": "agua",
            "a-guar li v. Referido a un líquido": "aguar",
            "a-gujeta Mls.f. Dolor muscular": "agujeta",
            "a-ho.g0 s.m. Dificultad para respirar": "ahogo",
        }
        for text, expected in samples.items():
            parsed = parse_headword_text(text, settings)
            self.assertIsNotNone(parsed, text)
            assert parsed is not None
            self.assertEqual(parsed.normalized, expected, text)
            self.assertTrue(parsed.has_pos or parsed.has_descriptor, text)
        agua = parse_headword_text("agua Es.f. 1 Sustancia", settings)
        assert agua is not None
        self.assertIn("ignored_pre_pos_noise:E", agua.ocr_repairs)
        ahogo = parse_headword_text("a-ho.g0 s.m. Dificultad", settings)
        assert ahogo is not None
        self.assertTrue(any("terminal" in item for item in ahogo.ocr_repairs))

    def test_marker_glyph_noise_is_not_accepted_as_short_lemma(self) -> None:
        settings = AppSettings(
            ocr_language="spa", paddle_auto_header_rule=False,
            parameter_display_width=300, paddle_band_width=300,
            paddle_refine_separator_y=False,
        )
        band = Image.new("RGB", (300, 100), "white")
        entries, diagnostics = filter_headword_records(
            [OCRRecord("Ml adj./s. 9 Referido a un sonido", 0.98, (5, 20, 280, 45))],
            band, 0, 10, settings, engine_name="tesseract",
        )
        self.assertEqual(entries, [])
        candidate = next(x for x in diagnostics if "accepted" in x)
        self.assertEqual(candidate["reject_reason"], "marker_glyph_ocr_noise")

    def test_alphabetical_warning_is_weak_annotation_only(self) -> None:
        def cand(lemma: str, y: int) -> dict:
            return {
                "accepted": True, "normalized_headword": lemma, "source_y": y,
                "features": {"at_left": True}, "reject_reason": "",
            }
        report = [{
            "column": 0,
            "candidates": [cand("agudo", 100), cand("Ml", 130), cand("agüera", 160)],
            "tesseract": {"candidates": []},
        }]
        warnings = _annotate_alphabetical_warnings(report)
        self.assertTrue(warnings)
        ml = report[0]["candidates"][1]
        self.assertIn("alphabetical_forward_outlier", ml["alphabetical_warning"])
        self.assertTrue(ml["accepted"])  # warning never changes acceptance

    def test_y_pairing_and_tsv_diagnostic_format(self) -> None:
        paddle = [{"meta": {}}, {
            "accepted": True, "source_y": 100, "box": [1, 2, 3, 4],
            "confidence": 0.93, "score": 8, "normalized_headword": "agua",
            "raw_headword": "a·gua", "corrected_headword": "a·gua",
            "pos_cue": "s.f.", "ocr_repairs": [], "text": "a·gua s.f.",
            "reject_reason": "", "features": {"at_left": True},
        }]
        tess = [{"meta": {}}, {
            "accepted": True, "source_y": 103, "box": [2, 2, 4, 4],
            "confidence": 0.88, "score": 8, "normalized_headword": "agua",
            "raw_headword": "a-gua", "corrected_headword": "a-gua",
            "pos_cue": "s.f.", "ocr_repairs": [], "text": "a-gua s.f.",
            "reject_reason": "", "features": {"at_left": True},
        }]
        pairs = _pair_ocr_candidates(paddle, tess, tolerance=6)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["delta_y"], 3)
        self.assertEqual(pairs[0]["lemma_compare"], "same")
        report = [{
            "column": 0,
            "ocr_records": [{"text": "a·gua", "confidence": 0.93, "box": [1, 2, 3, 4]}],
            "candidates": paddle,
            "tesseract": {
                "error": "",
                "records": [{"text": "a-gua", "confidence": 0.88, "box": [2, 2, 4, 4]}],
                "candidates": tess,
            },
            "ocr_y_comparison": pairs,
            "tesseract_rescued": [],
        }]
        text = _diagnostic_text(report)
        header = "column\tbox_band_xyxy\tconf\ttext\taccept/reject\tscore\tlemma\traw\tcorrected\tPOS\trepairs\treason"
        self.assertEqual(text.splitlines()[0], header)
        diag_counts = {len(line.split("\t")) for line in text.splitlines()}
        self.assertEqual(diag_counts, {12})
        self.assertIn("engine=PADDLE", text)
        self.assertIn("engine=TESSERACT", text)
        self.assertIn("\tagua\t", text)

        comparison = _comparison_text(report)
        comp_lines = comparison.splitlines()
        self.assertIn("lemma_compare", comp_lines[0])
        comp_counts = {len(line.split("\t")) for line in comp_lines}
        self.assertEqual(comp_counts, {27})
        self.assertIn("\tsame\tsame\tagree", comparison)

    def test_coordinate_pairing_uses_canonical_v_not_source_y(self) -> None:
        def cand(canonical_v, source_y, lemma):
            return {
                "canonical_v": canonical_v,
                "source_x": 20,
                "source_y": source_y,
                "accepted": True,
                "score": 8.0,
                "confidence": 0.95,
                "box": [5, canonical_v, 100, canonical_v + 20],
                "normalized_headword": lemma,
                "raw_headword": lemma,
                "corrected_headword": lemma,
                "pos_cue": "s.m.",
                "ocr_repairs": [],
                "text": lemma + " s.m.",
                "reject_reason": "",
                "features": {"at_left": True, "structural_cue": True},
                "parser_trace": [],
                "bug_types": [],
            }

        # Same reading-axis row but very different physical source Y. This is
        # normal after a 90-degree transform; source Y must not drive pairing.
        pairs = _pair_ocr_candidates(
            [cand(100, 420, "alpha")],
            [cand(104, 30, "alfa")],
            tolerance=10,
            min_similarity=0.55,
        )
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["paddle_lemma"], "alpha")
        self.assertEqual(pairs[0]["tesseract_lemma"], "alfa")

    def test_authoritative_engine_position_preserves_source_coordinates_after_rotation(self) -> None:
        source_size = (600, 900)
        transform = LayoutTransform("rotate_ccw90")
        geometry = Geometry(
            column_starts=[100],
            column_widths=[300],
            top=0,
            bottom=600,
            column_paths=[ColumnPath([(0, 100), (599, 100)])],
            transform=transform,
            source_size=source_size,
        )
        pair = {
            "paddle_y": 200,
            "paddle_coarse_y": 210,
            "paddle_anchor_y": 215,
            "paddle_source_x": 399,
            "paddle_source_y": 100,
        }
        item = {}
        _apply_pair_engine_position(item, pair, "paddle", 0, 100, geometry)
        expected = transform.canonical_to_source_point(100, 200, source_size)
        self.assertEqual((item["source_x"], item["source_y"]), expected)
        self.assertEqual(item["canonical_v"], 200)
        self.assertNotEqual(item["source_y"], item["canonical_v"])

    def test_v159_legacy_comma_swallowing_regex_is_hardened(self) -> None:
        # Some existing projects carried a legacy/custom regex that included
        # the grammatical comma in group(1). The parser must repair this without
        # overwriting the user's setting.
        settings = AppSettings(
            ocr_language="spa",
            paddle_headword_regex=r"^\s*([^\s]+)",
        )
        samples = {
            "a·gri·men.sor, so.ra s. Persona": "agrimensor",
            "a·grin·ga.do, dá adj. Amér.": "agringado",
            "a.gró-no·mo, ma adj./s. Referido": "agrónomo",
            "al·ba·ñil, ñila s. Persona": "albañil",
            "al·go·do·ne-ro, ra I adj. Del algodón": "algodonero",
            "-a.jo, -a·ja Sufijo que indica menor tamaño": "-ajo",
        }
        for text, expected in samples.items():
            parsed = parse_headword_text(text, settings)
            self.assertIsNotNone(parsed, text)
            assert parsed is not None
            self.assertEqual(parsed.normalized, expected, text)
            self.assertTrue(parsed.has_pos or parsed.has_descriptor, text)
            self.assertFalse(parsed.looks_like_continuation, text)

    def test_v159_pages55_70_extended_structural_forms(self) -> None:
        settings = AppSettings(ocr_language="spa")
        samples = {
            "a·gua·nie.ve (tb. agua nieve) (pl. aguanieve": ("aguanieve", "inflection"),
            "a·guan·tarv. 1 Sostener": ("aguantar", "pos"),
            "ai·re ar v. 1 Ventilar": ("airear", "pos"),
            "a.le.lu.ya s.amb. 1 En la liturgia": ("aleluya", "pos"),
            "al.go ■ pron.indef. 1 Designa una cosa": ("algo", "pos"),
            "al Contracción de la preposición a y del artículo": ("al", "descriptor"),
            "air mail || Correo aéreo": ("air mail", "descriptor"),
            "a.ji-llo ll al ~; referido a un alimento": ("ajillo", "descriptor"),
            "a.jo.a·rrie.ro ll (al) ~; referido": ("ajoarriero", "descriptor"),
            "a·las·ka ma·la·mu·te ll -perro Alaska": ("alaska malamute", "descriptor"),
        }
        for text, (expected, cue) in samples.items():
            parsed = parse_headword_text(text, settings)
            self.assertIsNotNone(parsed, text)
            assert parsed is not None
            self.assertEqual(parsed.normalized, expected, text)
            if cue == "pos":
                self.assertTrue(parsed.has_pos, text)
            elif cue == "inflection":
                self.assertTrue(parsed.has_inflection, text)
            else:
                self.assertTrue(parsed.has_descriptor, text)

    def test_v159_pronunciation_and_sense_continuations_are_rejected(self) -> None:
        settings = AppSettings(ocr_language="spa")
        for text in (
            "mail. Pron. [érmeil].",
            "conductor. Pron. [érbag].",
            "aislante. s.m. 2 Cuerpo que impide el paso",
            "hólica. adj./s. 2 (ser/estar) Que padece la enfermedad",
        ):
            parsed = parse_headword_text(text, settings)
            self.assertIsNotNone(parsed, text)
            assert parsed is not None
            self.assertTrue(parsed.looks_like_continuation, text)
        pron = parse_headword_text("al.go ■ pron.indef. 1 Designa", settings)
        assert pron is not None
        self.assertTrue(pron.has_pos)
        self.assertEqual(pron.pos_text.casefold(), "pron.indef.")

    def test_v159_wrapped_pos_on_next_printed_line_is_attached_logically(self) -> None:
        settings = AppSettings(
            ocr_language="spa", parameter_display_width=600, paddle_band_width=600,
            paddle_auto_header_rule=False, paddle_refine_separator_y=False,
            paddle_rec_score_threshold=0.20, paddle_left_tolerance=80,
        )
        band = Image.new("RGB", (600, 180), "white")
        records = [
            OCRRecord("a·gro-a·li-men-ta-ción (pl. agroalimentaciones)", 0.96, (8, 25, 580, 55)),
            OCRRecord("s.f. Producción o comercialización de productos", 0.99, (36, 58, 590, 87)),
        ]
        entries, diagnostics = filter_headword_records(records, band, 0, 10, settings)
        self.assertEqual([entry.word for entry in entries], ["agroalimentación"])
        candidate = next(item for item in diagnostics if item.get("accepted"))
        self.assertEqual(candidate["pos_cue"].casefold(), "s.f.")
        self.assertIn("s.f.", candidate["text"].casefold())


    def test_v2_structured_grammar_parser_exposes_variants_and_trace(self) -> None:
        settings = AppSettings(ocr_language="spa")
        parsed = parse_headword_text("a·gri·men·sor, so·ra s. Persona especializada", settings)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.normalized, "agrimensor")
        self.assertTrue(parsed.has_pos)
        self.assertEqual(parsed.pos_text.casefold(), "s.")
        self.assertEqual(tuple(x.replace("·", "") for x in parsed.variants), ("sora",))
        self.assertTrue(any(item.startswith("variant:") for item in parsed.parser_trace))
        self.assertTrue(any(item.startswith("pos:") for item in parsed.parser_trace))
        self.assertEqual(parsed.parser_stage, "definition")

    def test_v2_sequence_alignment_does_not_shift_after_missing_row(self) -> None:
        def cand(y, lemma, accepted=True):
            return {
                "source_y": y, "normalized_headword": lemma, "accepted": accepted,
                "score": 8.0, "confidence": 0.95, "box": [5, y, 100, y+20],
                "text": lemma, "raw_headword": lemma, "corrected_headword": lemma,
                "pos_cue": "s.m.", "features": {"at_left": True, "structural_cue": True},
                "ocr_repairs": [], "parser_trace": ["lemma:ok", "pos:s.m."], "bug_types": [],
            }
        p = [{"meta": {}}, cand(100, "alpha"), cand(200, "beta"), cand(300, "gamma")]
        t = [{"meta": {}}, cand(102, "alpha"), cand(302, "gamma")]
        pairs = _pair_ocr_candidates(p, t, 30)
        self.assertEqual([(x["paddle_lemma"], x["tesseract_lemma"]) for x in pairs], [
            ("alpha", "alpha"), ("beta", ""), ("gamma", "gamma")
        ])

    def test_v2_arbitration_and_quality_summary(self) -> None:
        pair = {
            "paddle_y": 100, "paddle_box": [0,0,10,10], "paddle_conf": .93,
            "paddle_accepted": True, "paddle_score": 8.0, "paddle_lemma": "agüero",
            "paddle_raw": "a·güe·ro", "paddle_corrected": "a·güe·ro", "paddle_pos": "s.m.",
            "paddle_repairs": [], "paddle_text": "a·güe·ro s.m.", "paddle_reject_reason": "",
            "paddle_features": {"structural_cue": True}, "paddle_parser_trace": [], "paddle_bug_types": [],
            "paddle_alphabetical_warning": "",
            "tesseract_y": 103, "tesseract_box": [0,0,10,10], "tesseract_conf": .88,
            "tesseract_accepted": True, "tesseract_score": 7.2, "tesseract_lemma": "agúero",
            "tesseract_raw": "a.gú.e.ro", "tesseract_corrected": "a.gú.e.ro", "tesseract_pos": "s.m.",
            "tesseract_repairs": [], "tesseract_text": "a.gú.e.ro s.m.", "tesseract_reject_reason": "",
            "tesseract_features": {"structural_cue": True}, "tesseract_parser_trace": [], "tesseract_bug_types": [],
            "tesseract_alphabetical_warning": "", "lemma_similarity": .83,
            "lemma_compare": "similar", "status_compare": "same", "reason": "lemma_variant",
            "alignment_method": "sequence_y_similar",
        }
        decision = _arbitrate_pair(pair, 0, 25, AppSettings())
        self.assertTrue(decision["selected"])
        self.assertEqual(decision["final_engine"], "paddle")
        self.assertIn("OCR_VARIANT", decision["issue_types"])
        q = _agreement_summary([decision])
        self.assertEqual(q["similar"], 1)
        self.assertGreater(q["agreement"], 0.5)

    def test_v2_issues_tsv_is_rectangular(self) -> None:
        row = {
            "candidate_id": "c1", "column": 0, "source_y": 100, "selected": True,
            "word": "alpha", "final_engine": "paddle", "confidence": .9, "score": 8,
            "issue_types": ["OCR_CONFLICT"], "decision_reason": "test",
            "paddle": {"lemma": "alpha", "text": "alpha s.m."},
            "tesseract": {"lemma": "alfa", "text": "alfa s.m."},
        }
        text = _issues_text([row])
        widths = {len(line.split("\t")) for line in text.splitlines()}
        self.assertEqual(widths, {16})

    def test_v21_dictionary_profile_distinguishes_pos_and_internal_structure(self) -> None:
        profile = load_dictionary_profile()
        self.assertIn("pron.", profile.pos_labels)
        self.assertIn("Pron.", profile.relation_labels)
        self.assertIn("■", profile.internal_leading_symbols)
        records = [
            OCRRecord("■ adj./s. 2 Uso figurado", 0.98, (2, 40, 210, 62)),
            OCRRecord("a·gua s.f. Sustancia", 0.98, (2, 90, 220, 114)),
            OCRRecord("air mail || Correo aéreo", 0.98, (2, 130, 260, 154)),
        ]
        band = Image.new("RGB", (500, 180), "white")
        entries, diagnostics = filter_headword_records(
            records, band, 0, 10, AppSettings(ocr_language="spa"), profile=profile,
        )
        self.assertEqual([entry.word for entry in entries], ["agua"])
        internal = next(row for row in diagnostics if row.get("text", "").startswith("■"))
        self.assertEqual(internal["reject_reason"], "internal_article_symbol")
        locution = next(row for row in diagnostics if row.get("text", "").startswith("air mail"))
        self.assertEqual(locution["reject_reason"], "internal_locution")

    def test_v21_lens_breaks_local_conflict(self) -> None:
        def cand(y, lemma, confidence=.92):
            return {
                "source_y": y, "normalized_headword": lemma, "accepted": True,
                "score": 8.0, "confidence": confidence, "box": [4, y, 120, y + 20],
                "text": lemma + " s.m.", "raw_headword": lemma, "corrected_headword": lemma,
                "pos_cue": "s.m.", "features": {"at_left": True, "structural_cue": True},
                "ocr_repairs": [], "parser_trace": ["lemma:ok", "pos:s.m."], "bug_types": [],
            }
        pairs = _pair_ocr_candidates([cand(100, "agüero")], [cand(102, "agúero")], 30)
        pairs = _pair_with_lens_candidates(pairs, [cand(101, "agüero", .82)], 30, .55)
        decision = _arbitrate_pair(pairs[0], 0, 20, AppSettings())
        self.assertEqual(decision["word"], "agüero")
        self.assertIn(decision["final_engine"], {"paddle", "lens"})
        self.assertEqual(decision["decision_reason"], "lens_breaks_local_conflict")

    def test_v21_lens_normalized_geometry_becomes_pixel_bbox(self) -> None:
        payload = {"detailed_blocks": [{"lines": [{
            "text": "a·gua s.f. Sustancia",
            "geometry": {"center_x": .30, "center_y": .20, "width": .40, "height": .10, "coordinate_type": "NORMALIZED"},
            "words": [],
        }]}]}
        rows, full_text = _lens_payload_records(payload, 1000, 2000, .82)
        self.assertEqual(rows[0][0], "a·gua s.f. Sustancia")
        self.assertEqual(rows[0][2], (100, 300, 500, 500))
        self.assertIn("a·gua", full_text)

    def test_v21_tesseract_explicit_path_is_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fake = Path(raw) / "tesseract.exe"
            fake.write_bytes(b"")
            self.assertEqual(Path(find_tesseract(str(fake)) or ""), fake.resolve())

    def test_clamp_and_splits(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            page = root / "p001.png"
            image = self.make_page(page)
            settings = AppSettings(columns=2, manual_x=30, column_width=550, gutter=50, start_y=40)
            entries = [Entry("a", 30, 100), Entry("b", 30, 260), Entry("c", 630, 100)]
            self.assertEqual(clamp_box((-5, -3, 1300, 950), image), (0, 0, 1200, 900))
            line_records = split_single_lines(page, entries, settings, root / "QT" / "PSW")
            whole_records = split_whole_entries(page, entries, settings, root / "QT" / "PWW")
            self.assertEqual(len(line_records), 3)
            self.assertGreaterEqual(len(whole_records), 3)
            self.assertTrue((root / "QT" / "PSW" / "p001.PSWords").exists())
            self.assertTrue((root / "QT" / "PWW" / "p001.PWWords").exists())
            for record in line_records + whole_records:
                self.assertTrue((root / "QT" / ("PSW" if "_SW_" in record.filename else "PWW") / record.filename).exists())



class DictionaryProfileV2Tests(unittest.TestCase):

    def test_v210_profile_names_describe_layout_types(self) -> None:
        labels = dictionary_profile_labels()
        self.assertEqual(set(labels.values()), {
            "latin_regular", "cjk_visual", "numbered_prefix", "marker_prefixed", "custom",
        })
        self.assertIn("常规边缘词头", labels)
        self.assertIn("视觉词头（大字/括号词头）", labels)
        self.assertIn("编号前缀词头", labels)
        self.assertIn("符号前缀词头", labels)
        self.assertNotIn("FarEast", " ".join(labels))
        self.assertEqual(len(labels), 5)

    def test_v210_profile_preview_examples_exist(self) -> None:
        import json
        from picture_capture.dictionary_profile import profile_library_path
        raw = json.loads(profile_library_path().read_text(encoding="utf-8"))
        self.assertEqual(set(raw["validated_examples"]), {
            "NewApproach", "LDER", "HZYLDZD", "XDHYCD", "TimesCED", "RUIGO", "XAHDCD", "shueisha",
        })

    def test_v210_profile_defaults_keep_supported_language_variant(self) -> None:
        ita = profile_effective_settings("latin_pos_classic", current_language="ita+chi_sim")
        self.assertEqual(ita["ocr_language"], "ita+chi_sim")
        self.assertEqual(ita["paddle_language"], "it")
        self.assertEqual(ita["columns"], 2)
        cjk = profile_effective_settings("cjk_marker_pinyin", current_language="eng")
        self.assertEqual(cjk["ocr_language"], "chi_sim")
        self.assertEqual(cjk["columns"], 3)

    def test_v210_portuguese_and_italian_share_layout_but_not_pos_grammar(self) -> None:
        pt = load_dictionary_profile(preset="latin_pos_classic", language="por")
        it = load_dictionary_profile(preset="latin_pos_classic", language="ita")
        self.assertEqual(pt.family, it.family)
        self.assertIn("v.t.", pt.pos_labels)
        self.assertIn("v.tr.", it.pos_labels)
        self.assertNotIn("v.tr.", pt.pos_labels)

    def test_v210_numbered_pos_profile_accepts_conjugation_index_before_pos(self) -> None:
        profile = load_dictionary_profile(preset="latin_numbered_pos", language="spa")
        parsed = parse_headword_text(
            "abalanzar 18,8 tr. arrojarse sobre alguien",
            AppSettings(ocr_language="spa", dictionary_profile_id="latin_numbered_pos"),
            profile=profile,
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.normalized, "abalanzar")
        self.assertEqual(parsed.pos_text.casefold(), "tr.")

    def test_v210_marker_pinyin_profile_parses_marker_led_chinese_head(self) -> None:
        profile = load_dictionary_profile(preset="cjk_marker_pinyin", language="chi_sim")
        parsed = parse_headword_text(
            "○阿爸 ābà padre",
            AppSettings(ocr_language="chi_sim", dictionary_profile_id="cjk_marker_pinyin"),
            profile=profile,
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.normalized, "阿爸")
        self.assertEqual(parsed.descriptor_text, "cjk_marker_pinyin")

    def test_v210_latin_profile_does_not_enable_cjk_parser_from_definition_language(self) -> None:
        profile = load_dictionary_profile(preset="latin_pos_classic", language="por+chi_sim")
        parsed = parse_headword_text(
            "【中文释义】",
            AppSettings(ocr_language="por+chi_sim", dictionary_profile_id="latin_pos_classic"),
            profile=profile,
        )
        self.assertIsNone(parsed)

    def test_profile_v3_project_records_sections_and_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "dictionary_profile.json"
            settings = AppSettings(
                dictionary_profile_id="latin_numbered_pos", ocr_language="spa",
                paddle_language="es", paddle_left_tolerance=19,
            )
            write_project_profile(path, settings, settings.dictionary_profile_id, force=True)
            import json
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["format"], PROFILE_FORMAT_V3)
            self.assertEqual(raw["schema_version"], 3)
            self.assertEqual(raw["preset"], "latin_regular")
            self.assertEqual(raw["layout"]["columns"], 2)
            self.assertEqual(raw["ocr"]["semantic_language"], "spa")
            self.assertEqual(raw["headword"]["parser_modes"], ["latin", "numbered_pos"])
            self.assertEqual(raw["overrides"]["settings"]["paddle_left_tolerance"], 19)
            resolved = load_dictionary_profile(path, language="spa")
            self.assertEqual(resolved.key, "latin_regular")

    def test_profile_v2_project_is_loaded_without_implicit_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "dictionary_profile.json"
            original = {
                "format": PROFILE_FORMAT_V2,
                "preset": "latin_numbered_pos",
                "language": "spa",
                "overrides": {"settings": {"paddle_left_tolerance": 19}, "grammar": {}},
            }
            import json
            payload = json.dumps(original, ensure_ascii=False, indent=2)
            path.write_text(payload, encoding="utf-8")
            resolved = load_dictionary_profile(path)
            self.assertEqual(resolved.key, "latin_numbered_pos")
            write_project_profile(path, AppSettings(dictionary_profile_id="latin_numbered_pos"))
            self.assertEqual(path.read_text(encoding="utf-8"), payload)

    def test_profile_v3_bundles_real_dictionary_layout_ground_truth(self) -> None:
        expected = {
            "newapproach_2col": (2, "absent", "identity", "horizontal-tb", "ltr"),
            "lder_single": (1, "absent", "identity", "horizontal-tb", "ltr"),
            "cjk_etymology_large_head_2col": (2, "present", "identity", "horizontal-tb", "ltr"),
            "cjk_bracket_large_head_2col": (2, "present", "identity", "horizontal-tb", "ltr"),
            "cjk_large_head_pinyin_2col": (2, "present", "identity", "horizontal-tb", "ltr"),
            "jpn_numbered_headword_2col": (2, "absent", "identity", "horizontal-tb", "ltr"),
            "arabic_rtl_bilingual_2col": (2, "present", "mirror_x", "horizontal-tb", "rtl"),
            "jpn_vertical_kana_bracket_3band": (3, "absent", "rotate_ccw90", "vertical-rl", "rtl"),
        }
        for key, values in expected.items():
            layout = dictionary_profile_preset(key).layout
            self.assertEqual(
                (layout["columns"], layout["column_separator"], layout["canonical_transform"],
                 layout["writing_mode"], layout["text_direction"]),
                values,
            )

    def test_profile_v3_resolves_layout_ocr_and_headword_settings(self) -> None:
        arabic = profile_effective_settings("arabic_rtl_bilingual_2col")
        self.assertEqual(arabic["layout_transform"], "mirror_x")
        self.assertEqual(arabic["layout_text_direction"], "rtl")
        self.assertEqual(arabic["layout_columns_policy"], "fixed")
        self.assertEqual(arabic["tesseract_language"], "ara")
        self.assertEqual(arabic["paddle_language"], "ar")
        vertical = profile_effective_settings("jpn_vertical_kana_bracket_3band")
        self.assertEqual(vertical["layout_transform"], "rotate_ccw90")
        self.assertEqual(vertical["tesseract_language"], "jpn_vert")
        self.assertEqual(vertical["paddle_tesseract_psm"], 5)
        self.assertTrue(vertical["paddle_use_textline_orientation"])
        ruigo = dictionary_profile_preset("jpn_numbered_headword_2col")
        self.assertEqual(ruigo.headword["prefix_regex"], r"^\s*\d{1,4}(?:\s*[.．]\s*|\s+)")
        self.assertTrue(ruigo.headword["prefix_required"])
        hzy = load_dictionary_profile(preset="cjk_etymology_large_head_2col")
        self.assertIn("【本义】", hzy.internal_leading_symbols)

    def test_profile_v3_ui_summaries_are_compact_and_directional(self) -> None:
        self.assertEqual(
            profile_layout_summary(dictionary_profile_preset("arabic_rtl_bilingual_2col")),
            "2栏 · RTL · 镜像 · 中央分隔线",
        )
        self.assertEqual(
            profile_layout_summary(dictionary_profile_preset("jpn_vertical_kana_bracket_3band")),
            "竖排 · CCW90 · 3 canonical columns",
        )

    def test_profile_v3_numbered_prefix_parser_is_structural_and_language_neutral(self) -> None:
        profile = load_dictionary_profile(preset="jpn_numbered_headword_2col")
        accepted = parse_headword_text("12 【野生動物】 説明", AppSettings(ocr_language="jpn"), profile=profile)
        rejected = parse_headword_text("【分類見出し】 説明", AppSettings(ocr_language="jpn"), profile=profile)
        self.assertIsNotNone(accepted)
        self.assertIsNone(rejected)

    def test_profile_v3_direction_and_language_are_derived_components(self) -> None:
        from picture_capture.dictionary_profile import language_effective_settings
        vertical = language_effective_settings("jpn", "vertical-rl")
        horizontal = language_effective_settings("jpn", "horizontal-tb")
        self.assertEqual(vertical["tesseract_language"], "jpn_vert")
        self.assertEqual(vertical["paddle_tesseract_psm"], 5)
        self.assertEqual(horizontal["tesseract_language"], "jpn")
        self.assertFalse(horizontal["paddle_use_textline_orientation"])
        self.assertFalse(transformed_geometry_pending(AppSettings(layout_transform="mirror_x")))
        self.assertFalse(transformed_geometry_pending(AppSettings(layout_transform="identity")))

    def test_v3_profile_file_does_not_override_authoritative_saved_settings(self) -> None:
        import json
        from picture_capture.project_storage import ensure_project_storage, profile_path, settings_path
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            Image.new("RGB", (20, 30), "white").save(root / "0001.png")
            ensure_project_storage(root, "test")
            AppSettings(columns=7, ocr_language="fra", layout_transform="identity").to_json(settings_path(root))
            profile_path(root).write_text(json.dumps({
                "format": PROFILE_FORMAT_V3, "preset": "latin_regular",
                "layout": {"columns": 2, "writing_mode": "vertical-rl", "text_direction": "rtl"},
                "ocr": {"semantic_language": "jpn", "tesseract_language": "jpn_vert"},
            }), encoding="utf-8")
            opened = ProjectState.open(root)
            self.assertEqual(opened.settings.columns, 7)
            self.assertEqual(opened.settings.ocr_language, "fra")
            self.assertEqual(opened.settings.layout_transform, "identity")

    def test_tesseract_uses_engine_specific_language_with_fallback(self) -> None:
        from types import SimpleNamespace
        import picture_capture.paddle_headwords as module
        commands = []
        def fake_run(command, **_kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=0, stdout=b"level\tleft\ttop\twidth\theight\tconf\ttext\n", stderr=b"")
        original = module.subprocess.run
        original_find = module._tesseract_executable
        module.subprocess.run = fake_run
        module._tesseract_executable = lambda _path: "tesseract"
        try:
            module.run_tesseract_band_records(Image.new("RGB", (10, 10)), AppSettings(tesseract_language="jpn_vert"))
            module.run_tesseract_band_records(Image.new("RGB", (10, 10)), AppSettings(ocr_language="ara", tesseract_language=""))
        finally:
            module.subprocess.run = original
            module._tesseract_executable = original_find
        self.assertEqual(commands[0][commands[0].index("-l") + 1], "jpn_vert")
        self.assertEqual(commands[1][commands[1].index("-l") + 1], "ara")

    def test_paddle_orientation_participates_in_cache_and_prediction(self) -> None:
        import sys
        from types import SimpleNamespace
        import picture_capture.paddle_headwords as module
        created = []
        class FakePaddle:
            def __init__(self, **kwargs):
                self.kwargs = kwargs; self.predictions = []; created.append(self)
            def predict(self, _image, **kwargs):
                self.predictions.append(kwargs); return []
        old = sys.modules.get("paddleocr")
        sys.modules["paddleocr"] = SimpleNamespace(PaddleOCR=FakePaddle)
        module.clear_paddle_engine_cache()
        try:
            off = AppSettings(paddle_use_textline_orientation=False)
            on = AppSettings(paddle_use_textline_orientation=True)
            first = module.get_paddle_engine(off)
            second = module.get_paddle_engine(on)
            self.assertIsNot(first, second)
            self.assertFalse(first.kwargs["use_textline_orientation"])
            self.assertTrue(second.kwargs["use_textline_orientation"])
            module.run_paddle_band(Image.new("RGB", (10, 10)), on, engine=second)
            self.assertTrue(second.predictions[-1]["use_textline_orientation"])
        finally:
            module.clear_paddle_engine_cache()
            if old is None: sys.modules.pop("paddleocr", None)
            else: sys.modules["paddleocr"] = old

    def test_old_profile_ids_are_aliases_not_visible_profiles(self) -> None:
        labels = set(dictionary_profile_labels().values())
        self.assertNotIn("arabic_rtl_bilingual_2col", labels)
        self.assertEqual(dictionary_profile_preset("arabic_rtl_bilingual_2col").family, "latin_regular")
        self.assertEqual(dictionary_profile_preset("edge_visual_regular").family, "latin_regular")
        self.assertEqual(dictionary_profile_preset("cjk_large_head_pinyin_2col").family, "cjk_visual")


if __name__ == "__main__":
    unittest.main()

def test_review_crop_settings_ignores_stale_main_zoom_reference():
    from PIL import Image
    from picture_capture.app import _review_crop_settings
    from picture_capture.models import AppSettings, Entry
    from picture_capture.processing import derive_geometry, line_box

    image = Image.new("RGB", (3000, 4000), "white")
    settings = AppSettings()
    settings.parameter_display_width = 450  # stale/small reference: would make crop too tall
    settings.character_height = 26
    settings.row_padding = 3
    local = _review_crop_settings(image, settings, 1000)
    assert local.parameter_display_width == 450
    geometry = derive_geometry(image, local)
    box = line_box(Entry(word="test", x=100, y=500), geometry, image, local)
    # Modern review crops use the persisted full-resolution canonical geometry
    # directly; stale historical display width cannot enlarge the crop.
    assert box[3] - box[1] == 32
    assert settings.parameter_display_width == 450


def test_load_page_resets_scroll_position_without_resetting_zoom():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def load_page(")
    end = text.index("    def change_page(", start)
    block = text[start:end]
    assert "self.canvas.xview_moveto(0.0)" in block
    assert "self.canvas.yview_moveto(0.0)" in block
    assert "self.view_scale" in block  # zoom remains managed independently


def test_v273_main_entry_membership_border_rule_is_wordslist_driven():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _style_entry_editor(")
    end = text.index("    def _paddle_cache_path", start)
    block = text[start:end]
    assert 'border = "#d32f2f"' in block
    assert 'thickness = 2' in block
    assert 'border = "#b0b0b0"' in block
    assert 'thickness = 1' in block
    assert '"#2e7d32"' not in block
    assert "alphabetical_warning" not in block


def test_v273_main_entry_border_updates_while_typing():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _draw_entry_overlay(")
    end = text.index("    def _remove_entry_overlay", start)
    block = text[start:end]
    assert '"<KeyRelease>"' in block
    assert 'self._style_entry_editor(w, e, w.get().strip())' in block

def test_v274_main_ocr_candidate_rows_include_each_engine_and_fused_result():
    candidate = {
        "word": "agüero", "final_engine": "paddle",
        "paddle": {"lemma": "agüero", "confidence": 0.97},
        "tesseract": {"lemma": "agúero", "confidence": 0.88},
        "lens": {"lemma": "agüero", "confidence": 0.82},
    }
    rows = _candidate_choice_rows(candidate)
    assert [(engine, label, word, is_final) for engine, label, word, _conf, is_final in rows] == [
        ("paddle", "PaddleOCR", "agüero", False),
        ("tesseract", "Tesseract", "agúero", False),
        ("lens", "Google Lens", "agüero", False),
        ("paddle", "融合结果", "agüero", True),
    ]
    assert rows[0][3] == 0.97
    assert rows[-1][3] is None


def test_v274_main_redraw_wires_compact_ocr_selector_next_to_entry():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _draw_entry_overlay(")
    end = text.index("    def _remove_entry_overlay", start)
    block = text[start:end]
    assert "candidate = self._candidate_for_entry(entry)" in block
    assert "self._create_main_ocr_menu(entry, editor, candidate)" in block
    assert "editor.winfo_reqwidth()" in block
    assert "window=ocr_menu" in block


def test_v275_main_ocr_button_has_fixed_compact_label():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _create_main_ocr_menu(")
    end = text.index("    def _paddle_cache_path", start)
    block = text[start:end]
    assert 'text="OCR ▾"' in block
    assert 'text=f"OCR:' not in block
    fill_start = text.index("    def _fill_main_entry_from_ocr(")
    fill_end = text.index("    def _create_main_ocr_menu(", fill_start)
    fill_block = text[fill_start:fill_end]
    assert "menu_button.configure(text=" not in fill_block


def test_v275_page_switch_saves_current_editing_mode_before_loading_new_page():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")

    load_start = text.index("    def load_page(")
    load_end = text.index("    def change_page(", load_start)
    load_block = text[load_start:load_end]
    assert "self._save_current_page_by_mode()" in load_block
    assert load_block.index("self._save_current_page_by_mode()") < load_block.index("self.current_index = index")

    change_start = load_end
    change_end = text.index("    def redraw(", change_start)
    change_block = text[change_start:change_end]
    assert "self._save_current_page_by_mode()" in change_block


def test_v2810_save_current_page_is_mode_specific():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _save_current_page_by_mode(")
    end = text.index("    def save_current_page(", start)
    block = text[start:end]
    assert "if self.polygon_draw_var.get():" in block
    assert "write_ppp(target, self.polygons, self.current_page.stem)" in block
    assert "self.save_pdic(silent=True, sync_editors=sync_editors)" in block
    assert "self.polygon_var.get()" not in block

def test_v280_chinese_bracketed_headwords_are_structural_candidates():
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import parse_headword_text
    settings = AppSettings()
    settings.ocr_language = "chi_tra"
    for text, expected in [
        ("【一刀】 一枚刀幣。", "一刀"),
        ("〔一寸〕長度單位。", "一寸"),
        ("[一人] 一個人。", "一人"),
        ("【一 部】 部首名稱。", "一部"),
    ]:
        parsed = parse_headword_text(text, settings)
        assert parsed is not None
        assert parsed.normalized == expected
        assert parsed.has_descriptor
        assert parsed.descriptor_text == "chinese_bracketed_headword"


def test_wizard_parser_controls_gate_human_selected_structures():
    from picture_capture.dictionary_profile import load_dictionary_profile
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import parse_headword_text

    latin = load_dictionary_profile(preset="latin_regular", language="eng")
    settings = AppSettings()
    settings.ocr_language = "eng"
    settings.profile_parser_controls_version = 1
    settings.profile_allow_ordinary_left_edge = False
    settings.profile_allow_numbered_prefix = False
    settings.profile_allow_marker_prefix = False
    settings.profile_cjk_allow_bracketed_headword = False
    settings.profile_cjk_allow_single_headword = False

    # Ordinary lemma parsing is completely closed when its checkbox is off.
    assert parse_headword_text("apple n. fruit", settings, profile=latin) is None
    settings.profile_allow_ordinary_left_edge = True
    parsed = parse_headword_text("apple n. fruit", settings, profile=latin)
    assert parsed is not None
    assert parsed.normalized.casefold() == "apple"

    # Numbered structure can be enabled independently from ordinary lemmas.
    settings.profile_allow_ordinary_left_edge = False
    settings.profile_allow_numbered_prefix = True
    numbered = parse_headword_text("1. apple n. fruit", settings, profile=latin)
    assert numbered is not None
    assert numbered.normalized.casefold() == "apple"


def test_wizard_parser_controls_gate_cjk_bracket_and_marker_structures():
    from picture_capture.dictionary_profile import load_dictionary_profile
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import parse_headword_text

    profile = load_dictionary_profile(preset="cjk_visual", language="chi_tra")
    settings = AppSettings()
    settings.ocr_language = "chi_tra"
    settings.profile_parser_controls_version = 1
    settings.profile_allow_ordinary_left_edge = False
    settings.profile_allow_numbered_prefix = False
    settings.profile_allow_marker_prefix = False
    settings.profile_cjk_allow_single_headword = False
    settings.profile_cjk_allow_bracketed_headword = True

    bracketed = parse_headword_text("【同室】共同居住。", settings, profile=profile)
    assert bracketed is not None
    assert bracketed.normalized == "同室"

    settings.profile_cjk_allow_bracketed_headword = False
    assert parse_headword_text("【同室】共同居住。", settings, profile=profile) is None

    # Fixed-marker parsing is a separate checkbox with stable marker semantics.
    settings.profile_allow_marker_prefix = True
    marker = parse_headword_text("○同義 同樣的意思。", settings, profile=profile)
    assert marker is not None
    assert marker.normalized == "同義"


def test_v280_cjk_bracket_body_option_requires_extra_visual_evidence():
    from PIL import Image
    from picture_capture.dictionary_profile import load_dictionary_profile
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import OCRRecord, filter_headword_records

    settings = AppSettings()
    settings.ocr_language = "chi_tra"
    settings.paddle_band_width = 200
    settings.paddle_band_width_ratio = 100
    settings.paddle_band_left_margin = 0
    settings.paddle_left_tolerance = 12
    settings.paddle_rec_score_threshold = 0.1
    settings.paddle_auto_header_rule = False
    settings.paddle_refine_separator_y = False
    settings.paddle_require_pos_or_symbol = False
    settings.paddle_require_visual_cue = False
    settings.character_height = 16
    settings.row_padding = 4
    profile = load_dictionary_profile(preset="cjk_visual", language="chi_tra")

    band = Image.new("RGB", (200, 120), "white")
    records = [OCRRecord("【測試】正文解釋", 0.99, (2, 20, 130, 40))]

    entries, diagnostics = filter_headword_records(
        records, band, 0, 0, settings, profile=profile,
    )
    assert [entry.word for entry in entries] == ["測試"]

    settings.profile_cjk_brackets_in_body = True
    entries, diagnostics = filter_headword_records(
        records, band, 0, 0, settings, profile=profile,
    )
    assert entries == []
    row = next(item for item in diagnostics if item.get("text"))
    assert row["reject_reason"] == "cjk_bracket_needs_visual_evidence"


def test_v280_chinese_bracket_parser_is_language_driven():
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import parse_headword_text
    settings = AppSettings()
    settings.ocr_language = "spa"
    assert parse_headword_text("【一刀】 一枚刀幣。", settings) is None


def test_v281_chinese_single_character_parser_is_visual_candidate():
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import parse_headword_text

    settings = AppSettings()
    settings.ocr_language = "chi_tra"

    parsed = parse_headword_text("系", settings)
    assert parsed is not None
    assert parsed.normalized == "系"
    assert parsed.descriptor_text == "chinese_single_character_visual"
    assert parsed.parser_stage == "chinese_single_character"

    variant = parse_headword_text("个 巾", settings)
    assert variant is not None
    assert variant.normalized == "个"
    assert variant.descriptor_text == "chinese_single_character_visual"
    assert variant.parser_stage == "chinese_single_character_with_variant"

    section = parse_headword_text("丨部", settings)
    assert section is not None
    assert section.descriptor_text != "chinese_single_character_visual"


def test_v281_chinese_single_character_requires_visual_prominence():
    from PIL import Image
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import OCRRecord, filter_headword_records

    settings = AppSettings()
    settings.ocr_language = "chi_tra"
    settings.paddle_band_width = 200
    settings.paddle_band_width_ratio = 100
    settings.paddle_band_left_margin = 0
    settings.paddle_left_tolerance = 12
    settings.paddle_rec_score_threshold = 0.1
    settings.paddle_auto_header_rule = False
    settings.paddle_refine_separator_y = False
    settings.character_height = 16
    settings.row_padding = 4

    band = Image.new("RGB", (200, 220), "white")
    records = [
        OCRRecord("正文說明", 0.99, (10, 10, 100, 30)),
        OCRRecord("另一正文", 0.99, (10, 45, 100, 65)),
        OCRRecord("系", 0.99, (24, 80, 70, 124)),
        OCRRecord("普通正文", 0.99, (10, 135, 100, 155)),
        OCRRecord("同", 0.99, (24, 170, 50, 190)),
    ]

    entries, diagnostics = filter_headword_records(records, band, 0, 0, settings)
    assert [entry.word for entry in entries] == ["系"]
    rows = {row.get("text"): row for row in diagnostics if row.get("text")}
    assert rows["系"]["features"]["cjk_single_prominent"] is True
    assert rows["系"]["features"]["cjk_single_accept"] is True
    assert rows["同"]["accepted"] is False
    assert rows["同"]["reject_reason"] == "cjk_single_not_visually_prominent"


def test_v281_candidate_band_is_capped_to_current_column_width():
    from PIL import Image
    from picture_capture.models import AppSettings
    from picture_capture.processing import ColumnPath, Geometry
    from picture_capture.paddle_headwords import unwrap_column_band

    image = Image.new("RGB", (900, 500), "white")
    geometry = Geometry(
        column_starts=[10, 310, 610],
        column_widths=[270, 270, 290],
        top=0,
        bottom=500,
        column_paths=[
            ColumnPath([(0, 10), (500, 10)]),
            ColumnPath([(0, 310), (500, 310)]),
            ColumnPath([(0, 610), (500, 610)]),
        ],
    )
    settings = AppSettings()
    settings.parameter_display_width = 900
    settings.paddle_band_width = 600
    settings.paddle_band_width_ratio = 100
    settings.paddle_band_left_margin = 12

    band, _top, left_margin = unwrap_column_band(image, geometry, 0, settings)
    assert left_margin == 8
    assert band.width == 278


def test_v281_cjk_visual_projection_recovers_oversized_single_character_row():
    import numpy as np
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import _cjk_visual_projection_runs

    settings = AppSettings()
    settings.character_height = 20
    gray = np.full((260, 220), 255, dtype=np.uint8)
    # Several ordinary body rows establish the local body-height reference.
    for y0 in (20, 60, 100, 190, 225):
        gray[y0:y0 + 20, 4:90] = 0
    # One oversized display glyph near the column left edge.
    gray[130:178, 8:70] = 0

    zone_width, runs = _cjk_visual_projection_runs(gray, 0, settings, 1.0)
    assert zone_width >= 90
    assert any(start <= 130 and end >= 178 for start, end in runs)


def test_v282_alignment_key_preserves_cjk_characters():
    from picture_capture.paddle_headwords import _alignment_key, _lemma_similarity

    assert _alignment_key("囚") == "囚"
    assert _alignment_key("【並肩】") == "並肩"
    assert _lemma_similarity("囚", "囚") == 1.0
    assert _lemma_similarity("囚", "因") < 1.0


def test_v282_selected_single_cjk_duplicates_are_merged():
    from picture_capture.paddle_headwords import _deduplicate_selected_cjk_review_candidates

    rows = [
        {
            "candidate_id": "a", "column": 0, "source_y": 100, "box": [8, 112, 66, 180],
            "selected": True, "word": "囚", "score": 7.2, "confidence": 0.93,
            "issue_types": [], "decision_reason": "ocr",
            "paddle": {"y": 100, "accepted": True}, "tesseract": {}, "lens": {},
        },
        {
            "candidate_id": "b", "column": 0, "source_y": 105, "box": [9, 113, 67, 180],
            "selected": True, "word": "囚", "score": 8.1, "confidence": 0.96,
            "issue_types": [], "decision_reason": "visual",
            "paddle": {}, "tesseract": {"y": 105, "accepted": True}, "lens": {},
        },
        # A genuinely different, later single-character headword must survive.
        {
            "candidate_id": "c", "column": 0, "source_y": 255, "box": [8, 267, 66, 335],
            "selected": True, "word": "丞", "score": 8.0, "confidence": 0.95,
            "issue_types": [], "decision_reason": "visual",
            "paddle": {"y": 255, "accepted": True}, "tesseract": {}, "lens": {},
        },
    ]
    merged = _deduplicate_selected_cjk_review_candidates(rows)
    selected = [row for row in rows if row.get("selected")]
    assert merged == 1
    assert [row["word"] for row in selected] == ["囚", "丞"]
    assert selected[0]["source_y"] == 105
    assert "NEAR_Y_DUPLICATE_MERGED" in selected[0]["issue_types"]


def test_v288_selected_bracketed_cjk_duplicates_are_merged():
    from picture_capture.paddle_headwords import _deduplicate_selected_cjk_review_candidates

    rows = [
        {
            "candidate_id": "a", "column": 1, "source_y": 220, "box": [10, 228, 126, 252],
            "selected": True, "word": "並肩", "score": 7.6, "confidence": 0.94,
            "line_dedup_tolerance": 8, "issue_types": [], "decision_reason": "paddle",
            "paddle": {"y": 220, "accepted": True}, "tesseract": {}, "lens": {},
        },
        {
            "candidate_id": "b", "column": 1, "source_y": 228, "box": [12, 229, 125, 253],
            "selected": True, "word": "並肩", "score": 7.2, "confidence": 0.91,
            "line_dedup_tolerance": 8, "issue_types": [], "decision_reason": "tesseract",
            "paddle": {}, "tesseract": {"y": 228, "accepted": True}, "lens": {},
        },
        {
            "candidate_id": "c", "column": 1, "source_y": 268, "box": [10, 276, 126, 300],
            "selected": True, "word": "並病", "score": 7.7, "confidence": 0.95,
            "issue_types": [], "decision_reason": "paddle",
            "paddle": {"y": 268, "accepted": True}, "tesseract": {}, "lens": {},
        },
    ]
    merged = _deduplicate_selected_cjk_review_candidates(rows)
    selected = [row for row in rows if row.get("selected")]
    assert merged == 1
    assert [row["word"] for row in selected] == ["並肩", "並病"]
    assert selected[0]["source_y"] == 228
    assert "NEAR_Y_DUPLICATE_MERGED" in selected[0]["issue_types"]


def test_v288_nearby_different_bracketed_cjk_entries_do_not_merge():
    from picture_capture.paddle_headwords import _deduplicate_selected_cjk_review_candidates

    rows = [
        {
            "candidate_id": "a", "column": 1, "source_y": 220, "box": [10, 228, 126, 252],
            "selected": True, "word": "並肩", "score": 7.6, "confidence": 0.94,
            "line_dedup_tolerance": 8, "issue_types": [], "decision_reason": "paddle",
            "paddle": {"y": 220, "accepted": True}, "tesseract": {}, "lens": {},
        },
        {
            "candidate_id": "b", "column": 1, "source_y": 236, "box": [10, 244, 126, 268],
            "selected": True, "word": "並病", "score": 7.2, "confidence": 0.91,
            "line_dedup_tolerance": 8, "issue_types": [], "decision_reason": "tesseract",
            "paddle": {}, "tesseract": {"y": 236, "accepted": True}, "lens": {},
        },
    ]
    merged = _deduplicate_selected_cjk_review_candidates(rows)
    selected = [row for row in rows if row.get("selected")]
    assert merged == 0
    assert [row["word"] for row in selected] == ["並肩", "並病"]


def test_v289_near_y_duplicate_merges_even_when_ocr_words_disagree():
    from picture_capture.paddle_headwords import _deduplicate_selected_cjk_review_candidates

    rows = [
        {
            "candidate_id": "p", "column": 0, "source_y": 500, "box": [8, 506, 120, 532],
            "selected": True, "word": "並肩", "score": 8.0, "confidence": 0.96,
            "line_dedup_tolerance": 7, "issue_types": [], "decision_reason": "paddle",
            "paddle": {"y": 500, "accepted": True}, "tesseract": {}, "lens": {},
        },
        {
            "candidate_id": "t", "column": 0, "source_y": 506, "box": [9, 507, 121, 533],
            "selected": True, "word": "並肓", "score": 7.1, "confidence": 0.88,
            "line_dedup_tolerance": 7, "issue_types": [], "decision_reason": "tesseract",
            "paddle": {}, "tesseract": {"y": 506, "accepted": True}, "lens": {},
        },
    ]
    merged = _deduplicate_selected_cjk_review_candidates(rows)
    selected = [row for row in rows if row.get("selected")]
    assert merged == 1
    assert len(selected) == 1
    assert selected[0]["source_y"] == 506


def test_v289_y_gap_beyond_one_fifth_line_is_not_merged_even_if_word_same():
    from picture_capture.paddle_headwords import _deduplicate_selected_cjk_review_candidates

    rows = [
        {
            "candidate_id": "a", "column": 0, "source_y": 500, "box": [8, 506, 120, 532],
            "selected": True, "word": "並肩", "score": 8.0, "confidence": 0.96,
            "line_dedup_tolerance": 7, "issue_types": [], "decision_reason": "paddle",
            "paddle": {"y": 500, "accepted": True}, "tesseract": {}, "lens": {},
        },
        {
            "candidate_id": "b", "column": 0, "source_y": 508, "box": [8, 514, 120, 540],
            "selected": True, "word": "並肩", "score": 7.8, "confidence": 0.94,
            "line_dedup_tolerance": 7, "issue_types": [], "decision_reason": "tesseract",
            "paddle": {}, "tesseract": {"y": 508, "accepted": True}, "lens": {},
        },
    ]
    merged = _deduplicate_selected_cjk_review_candidates(rows)
    assert merged == 0
    assert sum(1 for row in rows if row.get("selected")) == 2


def test_v2814_large_single_cjk_uses_wider_type_specific_dedup_tolerance():
    from picture_capture.paddle_headwords import _deduplicate_selected_cjk_review_candidates

    rows = [
        {
            "candidate_id": "ocr", "column": 0, "source_y": 500, "box": [8, 510, 72, 574],
            "selected": True, "word": "囚", "score": 8.1, "confidence": 0.96,
            "line_dedup_tolerance": 7, "line_height_reference": 30.0,
            "issue_types": [], "decision_reason": "paddle",
            "paddle": {"y": 500, "accepted": True, "lemma": "囚", "parser_trace": ["chinese_single_character"]},
            "tesseract": {}, "lens": {},
        },
        {
            "candidate_id": "visual", "column": 0, "source_y": 512, "box": [9, 512, 73, 575],
            "selected": True, "word": "因", "score": 7.6, "confidence": 0.90,
            "line_dedup_tolerance": 7, "line_height_reference": 30.0,
            "issue_types": [], "decision_reason": "visual",
            "paddle": {},
            "tesseract": {"y": 512, "accepted": True, "lemma": "因", "parser_trace": ["chinese_single_character_with_variant"]},
            "lens": {},
        },
    ]
    # 12 px is beyond the ordinary 7 px tolerance but inside 0.55 * 30 = 16.5.
    merged = _deduplicate_selected_cjk_review_candidates(rows)
    selected = [row for row in rows if row.get("selected")]
    assert merged == 1
    assert len(selected) == 1
    assert selected[0]["source_y"] == 512
    assert "SINGLE_CJK_DUPLICATE_MERGED" in selected[0]["issue_types"]


def test_v2814_ordinary_compound_does_not_get_single_cjk_wide_tolerance():
    from picture_capture.paddle_headwords import _deduplicate_selected_cjk_review_candidates

    rows = [
        {
            "candidate_id": "a", "column": 0, "source_y": 500, "box": [8, 506, 120, 532],
            "selected": True, "word": "並肩", "score": 8.0, "confidence": 0.96,
            "line_dedup_tolerance": 7, "line_height_reference": 30.0,
            "issue_types": [], "decision_reason": "paddle",
            "paddle": {"y": 500, "accepted": True, "lemma": "並肩"}, "tesseract": {}, "lens": {},
        },
        {
            "candidate_id": "b", "column": 0, "source_y": 512, "box": [9, 509, 121, 535],
            "selected": True, "word": "並肩", "score": 7.7, "confidence": 0.92,
            "line_dedup_tolerance": 7, "line_height_reference": 30.0,
            "issue_types": [], "decision_reason": "tesseract",
            "paddle": {}, "tesseract": {"y": 512, "accepted": True, "lemma": "並肩"}, "lens": {},
        },
    ]
    merged = _deduplicate_selected_cjk_review_candidates(rows)
    assert merged == 0
    assert sum(1 for row in rows if row.get("selected")) == 2


def test_v2814_distinct_single_cjk_rows_beyond_wide_tolerance_survive():
    from picture_capture.paddle_headwords import _deduplicate_selected_cjk_review_candidates

    rows = [
        {
            "candidate_id": "a", "column": 0, "source_y": 500, "box": [8, 510, 72, 574],
            "selected": True, "word": "囚", "score": 8.1, "confidence": 0.96,
            "line_dedup_tolerance": 7, "line_height_reference": 30.0,
            "issue_types": [], "decision_reason": "paddle",
            "paddle": {"y": 500, "accepted": True, "lemma": "囚"}, "tesseract": {}, "lens": {},
        },
        {
            "candidate_id": "b", "column": 0, "source_y": 522, "box": [8, 534, 72, 598],
            "selected": True, "word": "丞", "score": 8.0, "confidence": 0.95,
            "line_dedup_tolerance": 7, "line_height_reference": 30.0,
            "issue_types": [], "decision_reason": "paddle",
            "paddle": {"y": 522, "accepted": True, "lemma": "丞"}, "tesseract": {}, "lens": {},
        },
    ]
    merged = _deduplicate_selected_cjk_review_candidates(rows)
    assert merged == 0
    assert sum(1 for row in rows if row.get("selected")) == 2


def test_v282_visual_projection_does_not_duplicate_accepted_cjk_row():
    from picture_capture.paddle_headwords import _accepted_cjk_row_for_visual_run

    diagnostics = [{
        "accepted": True,
        "normalized_headword": "囚",
        "box": [10, 112, 70, 182],
        "features": {"cjk_single_visual": True},
    }]
    row = _accepted_cjk_row_for_visual_run(diagnostics, 120, 178, "囚")
    assert row is diagnostics[0]


def test_v282_ocr_and_visual_channels_emit_one_entry_for_same_large_cjk_glyph():
    import numpy as np
    from PIL import Image
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import OCRRecord, filter_headword_records

    settings = AppSettings()
    settings.ocr_language = "chi_tra"
    settings.paddle_band_width = 220
    settings.paddle_band_left_margin = 0
    settings.paddle_left_tolerance = 14
    settings.paddle_rec_score_threshold = 0.1
    settings.paddle_auto_header_rule = False
    settings.paddle_refine_separator_y = False
    settings.character_height = 20
    settings.row_padding = 4

    gray = np.full((280, 220), 255, dtype=np.uint8)
    for y0 in (20, 60, 100, 205, 240):
        gray[y0:y0 + 20, 4:92] = 0
    gray[135:185, 8:72] = 0
    band = Image.fromarray(gray, mode="L").convert("RGB")
    records = [
        OCRRecord("正文", 0.99, (4, 20, 92, 40)),
        OCRRecord("正文", 0.99, (4, 60, 92, 80)),
        OCRRecord("正文", 0.99, (4, 100, 92, 120)),
        OCRRecord("囚", 0.99, (8, 135, 72, 185)),
        OCRRecord("正文", 0.99, (4, 205, 92, 225)),
        OCRRecord("正文", 0.99, (4, 240, 92, 260)),
    ]
    entries, diagnostics = filter_headword_records(records, band, 0, 0, settings)
    assert [entry.word for entry in entries].count("囚") == 1
    accepted_cjk = [
        row for row in diagnostics
        if row.get("accepted") and row.get("normalized_headword") == "囚"
    ]
    assert len(accepted_cjk) == 1
    assert accepted_cjk[0]["features"].get("cjk_visual_projection_confirmed") is True



def test_v2815_open_chinese_bracket_headword_without_closer_is_parsed():
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import parse_headword_text

    settings = AppSettings()
    settings.ocr_language = "chi_tra"
    parsed = parse_headword_text("【這是一個很長而且本行沒有閉括號的詞頭", settings)
    assert parsed is not None
    assert parsed.normalized.startswith("這是一個很長")
    assert parsed.descriptor_text == "chinese_open_bracket_headword"
    assert parsed.has_descriptor is True
    assert "accepted_unclosed_chinese_headword_bracket" in parsed.ocr_repairs


def test_v2815_lone_open_chinese_bracket_is_a_headword_start_marker():
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import parse_headword_text

    settings = AppSettings()
    settings.ocr_language = "chi_tra"
    parsed = parse_headword_text("【", settings)
    assert parsed is not None
    assert parsed.normalized == "【"
    assert parsed.descriptor_text == "chinese_open_bracket_headword"


def test_v2815_complete_long_chinese_bracket_headword_over_16_chars_is_parsed():
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import parse_headword_text

    settings = AppSettings()
    settings.ocr_language = "chi_tra"
    word = "這是一個超過十六個中文字而仍然完整閉合的超長詞頭"
    parsed = parse_headword_text(f"【{word}】正文", settings)
    assert parsed is not None
    assert parsed.normalized == word
    assert parsed.descriptor_text == "chinese_bracketed_headword"


def test_v2815_lone_open_bracket_at_column_left_is_accepted_for_line_drawing():
    import numpy as np
    from PIL import Image
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import OCRRecord, filter_headword_records

    settings = AppSettings()
    settings.ocr_language = "chi_tra"
    settings.paddle_band_width = 220
    settings.paddle_band_left_margin = 0
    settings.paddle_left_tolerance = 16
    settings.paddle_rec_score_threshold = 0.1
    settings.paddle_auto_header_rule = False
    settings.paddle_refine_separator_y = False
    settings.character_height = 20
    settings.row_padding = 4

    gray = np.full((160, 220), 255, dtype=np.uint8)
    gray[40:62, 4:22] = 0
    gray[85:105, 4:140] = 0
    band = Image.fromarray(gray, mode="L").convert("RGB")
    records = [
        OCRRecord("【", 0.99, (4, 40, 22, 62)),
        OCRRecord("下一行是超長詞頭的其餘部分", 0.98, (4, 85, 140, 105)),
    ]
    entries, diagnostics = filter_headword_records(records, band, 0, 0, settings)
    assert any(entry.word == "【" for entry in entries)
    marker_rows = [row for row in diagnostics if row.get("normalized_headword") == "【"]
    assert marker_rows and marker_rows[0]["accepted"] is True
    assert marker_rows[0]["descriptor_cue"] == "chinese_open_bracket_headword"

def test_v287_crop_worker_count_is_conservative_and_configurable():
    from picture_capture.processing import resolve_crop_worker_count

    assert resolve_crop_worker_count(0, cpu_count=1) == 1
    assert resolve_crop_worker_count(0, cpu_count=4) == 2
    assert resolve_crop_worker_count(0, cpu_count=8) == 4
    assert resolve_crop_worker_count(0, cpu_count=32) == 4
    assert resolve_crop_worker_count(6, cpu_count=8) == 6
    assert resolve_crop_worker_count(99, cpu_count=32) == 8
    assert resolve_crop_worker_count(1, cpu_count=16) == 1


def test_v287_crop_workers_are_spawn_safe_top_level_functions(tmp_path):
    import pickle
    from picture_capture.processing import split_whole_entries_job, split_illustrations_job

    # ProcessPoolExecutor on Windows/spawn requires top-level pickleable callables.
    assert pickle.loads(pickle.dumps(split_whole_entries_job)).__name__ == "split_whole_entries_job"
    assert pickle.loads(pickle.dumps(split_illustrations_job)).__name__ == "split_illustrations_job"


def test_v2811_pending_page_claim_is_atomic_manual_lock():
    import threading
    from picture_capture.app import PictureCaptureApp

    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app._batch_active = True
    app._batch_foreground_pages = True
    app._batch_page_states = {3: "pending"}
    app._batch_state_lock = threading.Lock()
    app.current_index = 3
    app.status_var = type("V", (), {"set": lambda self, value: None})()
    app._update_page_row = lambda index: None
    assert app._claim_page_for_manual_edit(3) is True
    assert app._batch_page_states[3] == "manual_locked"


def test_v2811_processing_page_rejects_foreground_edit():
    import threading
    from picture_capture.app import PictureCaptureApp

    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app._batch_active = True
    app._batch_foreground_pages = True
    app._batch_page_states = {4: "processing"}
    app._batch_state_lock = threading.Lock()
    app.current_index = 4
    messages = []
    app.status_var = type("V", (), {"set": lambda self, value: messages.append(value)})()
    app._update_page_row = lambda index: None
    assert app._claim_page_for_manual_edit(4) is False
    assert app._batch_page_states[4] == "processing"
    assert any("正在后台处理" in msg for msg in messages)


def test_v2811_navigation_does_not_save_pending_or_processing_page():
    import threading
    from picture_capture.app import PictureCaptureApp

    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app._batch_active = True
    app._batch_foreground_pages = True
    app._batch_state_lock = threading.Lock()
    app.current_index = 1
    app._batch_page_states = {1: "pending"}
    assert app._can_save_current_during_batch_navigation() is False
    app._batch_page_states[1] = "processing"
    assert app._can_save_current_during_batch_navigation() is False
    app._batch_page_states[1] = "manual_locked"
    assert app._can_save_current_during_batch_navigation() is True
    app._batch_page_states[1] = "done"
    assert app._can_save_current_during_batch_navigation() is True


def test_v2812_adaptive_cjk_separator_uses_loose_vs_dense_spacing():
    import numpy as np
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import refine_separator_y_adaptive

    settings = AppSettings(
        paddle_refine_separator_y=True,
        paddle_separator_column_margin=0,
        row_padding=3,
    )

    def add_text_line(gray, y0, y1, shift=0):
        for x0, width in ((22 + shift, 24), (70 + shift, 17), (112 + shift, 28), (162 + shift, 20), (210 + shift, 30)):
            gray[y0:y1, x0:min(gray.shape[1] - 1, x0 + width)] = 0

    loose = np.full((120, 300), 255, dtype=np.uint8)
    add_text_line(loose, 20, 38)
    add_text_line(loose, 65, 85, 7)
    loose_y, loose_info = refine_separator_y_adaptive(
        loose, coarse_y=62, reference_line_height=20, settings=settings,
        content_top=65, preceding_gap_hint=27,
    )
    assert loose_info["adaptive_mode"] == "local_blank_trace"
    assert loose_y < loose_info["current_ink_onset"]
    # v2.8.13: bottom-biased placement stays just above the headword rather
    # than centring the separator in a generous blank band.
    assert 1 <= loose_info["current_ink_onset"] - loose_y <= 2

    dense = np.full((100, 300), 255, dtype=np.uint8)
    add_text_line(dense, 20, 49)
    add_text_line(dense, 50, 70, 7)
    dense_y, dense_info = refine_separator_y_adaptive(
        dense, coarse_y=47, reference_line_height=20, settings=settings,
        content_top=50, preceding_gap_hint=1,
    )
    assert dense_info["adaptive_mode"] == "dense_fallback"
    assert dense_y < 50


def test_v2813_adaptive_separator_bottom_bias_in_normal_gap():
    import numpy as np
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import refine_separator_y_adaptive

    settings = AppSettings(
        paddle_refine_separator_y=True,
        paddle_separator_column_margin=0,
        row_padding=3,
    )
    gray = np.full((100, 260), 255, dtype=np.uint8)
    gray[20:38, 20:220] = 0
    gray[44:64, 20:220] = 0
    y, info = refine_separator_y_adaptive(
        gray, coarse_y=42, reference_line_height=20, settings=settings,
        content_top=44, preceding_gap_hint=3,
    )
    assert info["adaptive_mode"] == "local_blank_trace"
    assert info["reason"] == "nearest_blank_band_above_headword"
    assert 1 <= info["current_ink_onset"] - y <= 2


def test_v2816_separator_box_top_inside_ink_reverses_upward_to_nearest_blank():
    import numpy as np
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import refine_separator_y_adaptive

    settings = AppSettings(paddle_refine_separator_y=True, paddle_separator_column_margin=0, row_padding=3)
    gray = np.full((100, 220), 255, dtype=np.uint8)
    gray[20:36, 20:190] = 0          # previous line
    gray[48:72, 20:190] = 0          # current headword; box top is inside ink
    y, info = refine_separator_y_adaptive(
        gray, coarse_y=47, reference_line_height=20, settings=settings,
        content_top=50, preceding_gap_hint=12,
    )
    assert info["adaptive_mode"] == "local_blank_trace"
    assert info["current_ink_onset"] == 50
    assert y == 46  # current glyph starts at 48; keep the full 2 px marker safely above it
    assert info["blank_run_end"] < info["current_ink_onset"]


def test_v2816_separator_box_top_in_blank_scans_down_then_hugs_real_ink():
    import numpy as np
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import refine_separator_y_adaptive

    settings = AppSettings(paddle_refine_separator_y=True, paddle_separator_column_margin=0, row_padding=3)
    gray = np.full((110, 220), 255, dtype=np.uint8)
    gray[18:34, 20:190] = 0
    gray[54:78, 20:190] = 0          # real current glyph starts below OCR box top
    y, info = refine_separator_y_adaptive(
        gray, coarse_y=48, reference_line_height=20, settings=settings,
        content_top=50, preceding_gap_hint=20,
    )
    assert info["adaptive_mode"] == "local_blank_trace"
    assert info["current_ink_onset"] >= 53
    assert info["current_ink_onset"] - y == 2


def test_v2812_manual_click_uses_column_interval_not_nearest_start():
    from picture_capture.processing import Geometry, ColumnPath, column_index_for_click

    geometry = Geometry(
        column_starts=[100, 400, 700],
        column_widths=[250, 250, 250],
        top=0, bottom=1000,
        column_paths=[
            ColumnPath([(0, 100)]), ColumnPath([(0, 400)]), ColumnPath([(0, 700)]),
        ],
    )
    # x=340 is near the end of column 1 and much closer to the *start* of
    # column 2 than to the start of column 1.  It must still stay in column 1.
    assert column_index_for_click(340, geometry) == 0
    assert column_index_for_click(620, geometry) == 1
    # In a true gutter, choose the nearest interval boundary.
    assert column_index_for_click(370, geometry) == 0
    assert column_index_for_click(385, geometry) == 1


def test_pdic_x_left_of_detected_start_stays_in_nearest_visual_column():
    from picture_capture.processing import Geometry, ColumnPath, column_index, sort_entries_reading_order

    geometry = Geometry(
        column_starts=[20, 607, 1194],
        column_widths=[530, 530, 530],
        top=0, bottom=1600,
        column_paths=[
            ColumnPath([(0, 20)]), ColumnPath([(0, 607)]), ColumnPath([(0, 1194)]),
        ],
    )
    # OCR/PDIC X can be a few pixels left of a percentile-estimated column
    # start. It is in the narrow gutter beside column 2, not in column 1.
    assert column_index(600, geometry) == 1
    assert column_index(1186, geometry) == 2

    entries = [Entry("第二栏", 600, 100), Entry("第一栏", 20, 900)]
    assert [entry.word for entry in sort_entries_reading_order(entries, geometry)] == ["第一栏", "第二栏"]


def test_v2817_separator_safety_is_configurable():
    import numpy as np
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import refine_separator_y_adaptive

    gray = np.full((140, 160), 255, dtype=np.uint8)
    # A headword begins at y=70; the rows above it are blank.
    gray[70:110, 12:120] = 0

    settings = AppSettings()
    settings.paddle_refine_separator_y = True
    settings.paddle_separator_column_margin = 0
    settings.row_padding = 0

    settings.paddle_separator_safety_px = 2
    y2, d2 = refine_separator_y_adaptive(
        gray, coarse_y=70, reference_line_height=20, settings=settings,
        reference_to_canonical_scale=1.0, lower_bound=0, content_top=70,
    )
    settings.paddle_separator_safety_px = 6
    y6, d6 = refine_separator_y_adaptive(
        gray, coarse_y=70, reference_line_height=20, settings=settings,
        reference_to_canonical_scale=1.0, lower_bound=0, content_top=70,
    )

    assert d2["configured_safety_pixels"] == 2
    assert d6["configured_safety_pixels"] == 6
    assert d2["safety_pixels"] == 2
    assert d6["safety_pixels"] == 6
    assert y6 <= y2 - 4


def test_v2817_separator_safety_scales_with_page_geometry():
    import numpy as np
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import refine_separator_y_adaptive

    gray = np.full((180, 180), 255, dtype=np.uint8)
    gray[90:140, 10:150] = 0
    settings = AppSettings()
    settings.paddle_refine_separator_y = True
    settings.paddle_separator_column_margin = 0
    settings.paddle_separator_safety_px = 3
    _, diag = refine_separator_y_adaptive(
        gray, coarse_y=90, reference_line_height=24, settings=settings,
        reference_to_canonical_scale=2.0, lower_bound=0, content_top=90,
    )
    assert diag["configured_safety_pixels"] == 3
    assert diag["safety_pixels"] == 6


def test_v2818_refinement_preserves_original_y_as_checkbox_fallback():
    from picture_capture.paddle_headwords import _expand_original_y_fallback_candidates

    rows = [{
        "candidate_id": "c1-y100", "column": 0, "source_x": 20,
        "source_y": 92, "refined_source_y": 92, "coarse_source_y": 104,
        "box": [8, 107, 88, 134], "original_box": [8, 107, 88, 134],
        "selected": True, "word": "信", "position_variant": "refined",
        "issue_types": [], "paddle": {"y": 92, "accepted": True},
        "tesseract": {}, "lens": {},
    }]
    created = _expand_original_y_fallback_candidates(rows)
    assert created == 1
    assert len(rows) == 2
    refined = next(row for row in rows if row["position_variant"] == "refined")
    original = next(row for row in rows if row["position_variant"] == "original")
    assert refined["source_y"] == 92
    assert original["source_y"] == 104
    assert original["selected"] is False
    assert original["original_box"] == [8, 107, 88, 134]
    assert original["position_group_id"] == refined["position_group_id"]
    assert original["candidate_id"].endswith("-rawy")


def test_v2818_position_variants_are_mutually_exclusive_after_overrides():
    from picture_capture.paddle_headwords import _enforce_position_variant_exclusivity

    rows = [
        {"candidate_id": "base", "position_group_id": "base", "position_variant": "refined", "selected": True},
        {"candidate_id": "base-rawy", "position_group_id": "base", "position_variant": "original", "selected": True, "manual_override": True},
    ]
    changed = _enforce_position_variant_exclusivity(rows)
    assert changed == 1
    assert rows[0]["selected"] is False
    assert rows[1]["selected"] is True


def test_v2818_clicking_original_y_checkbox_switches_entry_in_one_action():
    from picture_capture.app import PictureCaptureApp
    from picture_capture.models import AppSettings, Entry

    class FakeVar:
        def __init__(self, value=True): self.value = value
        def set(self, value): self.value = value

    class Status:
        def __init__(self): self.messages = []
        def set(self, value): self.messages.append(value)

    refined = {
        "candidate_id": "base", "position_group_id": "base", "position_variant": "refined",
        "column": 0, "source_x": 20, "source_y": 92, "selected": True, "word": "信",
        "confidence": 0.95, "final_engine": "paddle", "issue_types": [], "score": 8.0,
    }
    original = {
        "candidate_id": "base-rawy", "position_group_id": "base", "position_variant": "original",
        "column": 0, "source_x": 20, "source_y": 104, "selected": False, "word": "信",
        "confidence": 0.95, "final_engine": "paddle", "issue_types": [], "score": 8.0,
    }
    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.settings = AppSettings()
    app.entries = [Entry("信", 20, 92, candidate_id="base")]
    app.ocr_review_candidates = [refined, original]
    app.candidate_check_vars = {"base": FakeVar(True), "base-rawy": FakeVar(False)}
    app.entry_editor_bindings = []
    app.status_var = Status()
    app._claim_page_for_manual_edit = lambda: True
    app._write_manual_override = lambda *args, **kwargs: None
    app.save_pdic = lambda *args, **kwargs: None
    app.redraw = lambda: None

    PictureCaptureApp.set_candidate_selected(app, original, True)

    assert refined["selected"] is False
    assert original["selected"] is True
    assert len(app.entries) == 1
    assert app.entries[0].y == 104
    assert app.entries[0].candidate_id == "base-rawy"
    assert app.candidate_check_vars["base"].value is False
    assert any("原始 Y" in message for message in app.status_var.messages)


def test_v2819_fallback_prefers_image_anchor_over_ocr_coarse_y():
    from picture_capture.paddle_headwords import _expand_original_y_fallback_candidates

    rows = [{
        "candidate_id": "c1", "column": 0, "source_x": 20,
        "source_y": 90, "refined_source_y": 90, "coarse_source_y": 62,
        "anchor_source_y": 101,
        "box": [8, 60, 88, 130], "original_box": [8, 60, 88, 130],
        "selected": True, "word": "信", "position_variant": "refined",
        "issue_types": [], "paddle": {"y": 90, "accepted": True},
        "tesseract": {}, "lens": {},
    }]
    created = _expand_original_y_fallback_candidates(rows)
    assert created == 1
    fallback = next(row for row in rows if row.get("position_variant") == "original")
    assert fallback["source_y"] == 101
    assert fallback["coarse_source_y"] == 62
    assert fallback["anchor_source_y"] == 101
    assert fallback["fallback_kind"] == "image_anchor"


def test_v2819_adaptive_refine_can_relocate_box_top_from_previous_line():
    import numpy as np
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import refine_separator_y_adaptive

    settings = AppSettings()
    settings.paddle_refine_separator_y = True
    settings.paddle_separator_safety_px = 2
    settings.paddle_separator_column_margin = 0
    gray = np.full((120, 160), 255, dtype=np.uint8)
    # OCR box top accidentally begins inside the preceding body line.
    gray[24:31, 8:145] = 0
    # Real inter-line whitespace 31:39, then the actual headword begins at 39.
    gray[39:61, 8:70] = 0
    refined, meta = refine_separator_y_adaptive(
        gray, coarse_y=24, reference_line_height=24, settings=settings,
        reference_to_canonical_scale=1.0, lower_bound=0, content_top=24,
    )
    assert meta["relocated_from_prior_ink"] is True
    assert 38 <= meta["current_ink_onset"] <= 41
    assert meta["anchor_y"] == meta["current_ink_onset"] - 2
    assert refined <= meta["anchor_y"]


def test_v290_separator_roi_width_ratio_limits_analysis_to_column_left():
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import _separator_analysis_x_bounds

    settings = AppSettings()
    settings.paddle_separator_column_margin = 0
    settings.paddle_separator_roi_width_ratio = 40
    x0, x1 = _separator_analysis_x_bounds(1000, settings, 1.0)
    assert x0 == 0
    assert 390 <= x1 <= 410

    settings.paddle_separator_roi_width_ratio = 100
    x0_full, x1_full = _separator_analysis_x_bounds(1000, settings, 1.0)
    assert x0_full == 0
    assert x1_full == 1000


def test_v290_image_boundary_and_ocr_headword_are_mutually_matched():
    import numpy as np
    from PIL import Image
    from picture_capture.models import AppSettings
    from picture_capture.paddle_headwords import OCRRecord, filter_headword_records

    settings = AppSettings()
    settings.ocr_language = "chi_tra"
    settings.paddle_auto_header_rule = False
    settings.paddle_band_width = 220
    settings.parameter_display_width = 220
    settings.paddle_band_left_margin = 0
    settings.paddle_left_tolerance = 20
    settings.paddle_rec_score_threshold = 0.1
    settings.paddle_min_candidate_score = 1.0
    settings.paddle_separator_column_margin = 0
    settings.paddle_separator_roi_width_ratio = 55
    settings.paddle_separator_safety_px = 2
    settings.character_height = 20
    settings.row_padding = 2

    gray = np.full((180, 220), 255, dtype=np.uint8)
    # Two genuine bracketed headword rows. The right side contains definition
    # ink that should not contaminate the local left-side boundary detector.
    gray[20:40, 5:95] = 0
    gray[20:55, 145:215] = 0
    gray[75:95, 5:95] = 0
    gray[75:110, 145:215] = 0
    band = Image.fromarray(gray, mode="L").convert("RGB")
    records = [
        OCRRecord("【甲】", 0.99, (5, 20, 92, 40)),
        OCRRecord("【乙】", 0.99, (5, 75, 92, 95)),
    ]
    entries, diagnostics = filter_headword_records(
        records, band, 0, 0, settings, separator_band=band,
    )
    assert [e.word for e in entries] == ["甲", "乙"]
    second = next(row for row in diagnostics if row.get("normalized_headword") == "乙")
    assert second.get("image_boundary_match") is not None
    assert second["features"].get("image_boundary_supported") is True
    assert second["separator_refinement"].get("image_boundary_matched") is True
    assert second["separator_refinement"].get("reason") == "ocr_image_boundary_mutual_match"
    meta = diagnostics[0]["meta"]
    assert meta["image_separator_match_count"] >= 1
    assert meta["separator_roi_width_ratio"] == 55


def test_v291_training_export_keeps_images_labels_and_ocr_provenance(tmp_path):
    import json
    import zipfile
    from PIL import Image
    from picture_capture.formats import write_pdic, write_ppp
    from picture_capture.models import AppSettings, Entry, PolygonRegion
    from picture_capture.training_export import (
        copy_project_context, export_training_page, make_training_zip, write_training_manifest,
    )

    root = tmp_path / "dict"
    root.mkdir()
    page = root / "0001.png"
    Image.new("RGB", (600, 900), "white").save(page)
    settings = AppSettings(columns=2, manual_x=20, column_width=250, gutter=40, parameter_display_width=600)
    settings.to_json(root / "picture_capture_settings.json")
    (root / "wordslist.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    entries = [Entry(word="alpha", x=20, y=120), Entry(word="beta", x=310, y=300)]
    write_pdic(page.with_suffix(".pdic"), entries, 600, ("0001", "@", "@"))
    write_ppp(page.with_suffix(".ppp"), [PolygonRegion("fig", [(400, 500), (500, 500), (500, 650)])], "0001")

    ocr_dir = root / "QT" / "PaddleOCR"
    ocr_dir.mkdir(parents=True)
    cache = {
        "manual_override_count": 1,
        "page_quality": {"agreement": 0.95},
        "review_candidates": [
            {
                "candidate_id": "c1", "column": 0, "source_x": 20, "source_y": 121,
                "word": "alpha", "selected": True, "original_box": [20, 125, 100, 145],
                "coarse_source_y": 118, "anchor_source_y": 120, "refined_source_y": 121,
                "separator_refinement": {"method": "image_boundary"},
            },
            {
                "candidate_id": "c2", "column": 0, "source_x": 20, "source_y": 220,
                "word": "noise", "selected": False,
            },
        ],
    }
    (ocr_dir / "0001.json").write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    (ocr_dir / "0001_manual_selection.json").write_text(
        json.dumps({"version": 1, "overrides": {"c1": {"selected": True}}}, ensure_ascii=False),
        encoding="utf-8",
    )

    staging = tmp_path / "staging"
    record = export_training_page(page, root, settings, staging, 0)
    context = copy_project_context(root, staging)
    write_training_manifest(
        staging, project_name="dict", settings=settings, pages=[record],
        context_files=context, software_version="2.9.1",
    )
    zip_path = make_training_zip(staging, tmp_path / "training.zip")

    annotation = json.loads((staging / "annotations" / "0001.json").read_text(encoding="utf-8"))
    assert annotation["annotation_status"] == "human_verified_saved_pdic"
    assert [row["word"] for row in annotation["ground_truth_lines"]] == ["alpha", "beta"]
    assert annotation["ocr_trace"]["candidates"][0]["ground_truth_selected"] is True
    assert annotation["ocr_trace"]["candidates"][0]["anchor_source_y"] == 120
    assert annotation["ocr_trace"]["candidates"][1]["ground_truth_selected"] is False
    assert annotation["illustration_polygons"][0]["label"] == "fig"
    assert (staging / "images" / "0001.png").exists()
    assert (staging / "artifacts" / "0001.pdic").exists()
    assert (staging / "artifacts" / "0001.ppp").exists()
    assert (staging / "ocr" / "0001.json").exists()
    assert (staging / "ocr" / "0001_manual_selection.json").exists()

    manifest = json.loads((staging / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["page_count"] == 1
    assert manifest["ground_truth_line_count"] == 2
    assert "project_context/picture_capture_settings.json" in manifest["project_context_files"]

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "dataset_manifest.json" in names
    assert "images/0001.png" in names
    assert "annotations/0001.json" in names


def test_v292_shared_rgb_source_preserves_unwrapped_band_pixels_exactly():
    import numpy as np
    from PIL import Image
    from picture_capture.models import AppSettings
    from picture_capture.processing import ColumnPath, Geometry
    from picture_capture.paddle_headwords import unwrap_column_band

    rng = np.random.default_rng(20260916)
    pixels = rng.integers(0, 256, size=(180, 320, 3), dtype=np.uint8)
    image = Image.fromarray(pixels, "RGB")
    geometry = Geometry(
        column_starts=[31, 171],
        column_widths=[118, 120],
        top=7,
        bottom=173,
        column_paths=[
            ColumnPath([(7, 31), (90, 36), (173, 29)]),
            ColumnPath([(7, 171), (90, 168), (173, 174)]),
        ],
    )
    settings = AppSettings()
    settings.parameter_display_width = 320
    settings.paddle_band_width = 110
    settings.paddle_band_width_ratio = 83
    settings.paddle_band_left_margin = 9

    legacy_band, legacy_top, legacy_margin = unwrap_column_band(image, geometry, 0, settings)
    shared = np.asarray(image)
    shared_band, shared_top, shared_margin = unwrap_column_band(
        image, geometry, 0, settings, source_rgb=shared,
    )
    assert legacy_top == shared_top
    assert legacy_margin == shared_margin
    assert legacy_band.size == shared_band.size
    assert np.array_equal(np.asarray(legacy_band), np.asarray(shared_band))

    # Separator-width extraction must also remain pixel-identical.
    legacy_sep, _, _ = unwrap_column_band(image, geometry, 0, settings, source_width=127)
    shared_sep, _, _ = unwrap_column_band(
        image, geometry, 0, settings, source_width=127, source_rgb=shared,
    )
    assert np.array_equal(np.asarray(legacy_sep), np.asarray(shared_sep))


def test_v292_shared_rgb_source_cannot_be_reused_across_pages():
    import numpy as np
    import pytest
    from PIL import Image
    from picture_capture.models import AppSettings
    from picture_capture.processing import ColumnPath, Geometry
    from picture_capture.paddle_headwords import unwrap_column_band

    image = Image.new("RGB", (200, 160), "white")
    geometry = Geometry(
        column_starts=[10], column_widths=[170], top=0, bottom=160,
        column_paths=[ColumnPath([(0, 10), (160, 10)])],
    )
    settings = AppSettings()
    settings.parameter_display_width = 200
    wrong_page = np.zeros((159, 200, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="禁止跨页复用"):
        unwrap_column_band(image, geometry, 0, settings, source_rgb=wrong_page)


def test_v292_display_zoom_remains_display_only_and_main_image_is_rgb():
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    load_start = text.index("    def load_page(")
    load_end = text.index("    def change_page(", load_start)
    load_block = text[load_start:load_end]
    assert 'normalize_page_rgb(opened)' in load_block
    assert 'convert("RGBA")' not in load_block

    cache_start = text.index("    def _get_cached_display_photo(")
    cache_end = text.index("    def _draw_entry_overlay(", cache_start)
    cache_block = text[cache_start:cache_end]
    assert 'self.image.resize(size, Image.Resampling.LANCZOS)' in cache_block
    assert 'self.image.convert("RGB")' not in cache_block

    redraw_start = text.index("    def redraw(")
    redraw_end = text.index("    def _update_view_zoom_label(", redraw_start)
    redraw_block = text[redraw_start:redraw_end]
    assert 'self._get_cached_display_photo(size)' in redraw_block

    zoom_start = text.index("    def zoom(")
    zoom_end = text.index("    def canvas_mousewheel(", zoom_start)
    zoom_block = text[zoom_start:zoom_end]
    assert "parameter_display_width" not in zoom_block
    assert "self.settings" not in zoom_block


def test_v292_paddle_engine_cache_is_bounded_without_invalidating_local_refs():
    from picture_capture.paddle_headwords import _ENGINE_CACHE, clear_paddle_engine_cache

    _ENGINE_CACHE.clear()
    old_engine = object()
    keep_engine = object()
    old_key = ("es", "cpu", "PP-OCRv5")
    keep_key = ("chinese_cht", "cpu", "PP-OCRv5")
    _ENGINE_CACHE[old_key] = old_engine
    _ENGINE_CACHE[keep_key] = keep_engine
    clear_paddle_engine_cache(keep_key=keep_key)
    assert list(_ENGINE_CACHE) == [keep_key]
    assert _ENGINE_CACHE[keep_key] is keep_engine
    # Clearing the cache cannot invalidate a reference already held by an
    # in-flight OCR caller; it only removes the cache's strong reference.
    assert old_engine is not None
    _ENGINE_CACHE.clear()



def test_v293_rgba_transparency_is_composited_onto_white_before_ocr():
    from PIL import Image
    from picture_capture.image_utils import normalize_page_rgb

    image = Image.new("RGBA", (3, 1), (255, 0, 0, 0))
    image.putpixel((1, 0), (0, 0, 0, 255))
    image.putpixel((2, 0), (0, 0, 0, 128))

    normalized = normalize_page_rgb(image)

    assert normalized.mode == "RGB"
    assert normalized.getpixel((0, 0)) == (255, 255, 255)
    assert normalized.getpixel((1, 0)) == (0, 0, 0)
    # Pillow alpha compositing rounds half-black over white to 127.
    assert normalized.getpixel((2, 0)) in {(127, 127, 127), (128, 128, 128)}


def test_v293_palette_transparency_is_composited_onto_white():
    from PIL import Image
    from picture_capture.image_utils import normalize_page_rgb

    image = Image.new("P", (2, 1))
    image.putpalette([255, 0, 0, 0, 0, 0] + [0, 0, 0] * 254)
    image.info["transparency"] = 0
    image.putdata([0, 1])

    normalized = normalize_page_rgb(image)

    assert normalized.mode == "RGB"
    assert normalized.getpixel((0, 0)) == (255, 255, 255)
    assert normalized.getpixel((1, 0)) == (0, 0, 0)


def test_v293_opaque_rgb_pixels_are_bit_exact_after_normalization():
    import numpy as np
    from PIL import Image
    from picture_capture.image_utils import normalize_page_rgb

    rng = np.random.default_rng(293)
    pixels = rng.integers(0, 256, size=(19, 23, 3), dtype=np.uint8)
    image = Image.fromarray(pixels, "RGB")
    normalized = normalize_page_rgb(image)

    assert normalized.mode == "RGB"
    assert np.array_equal(np.asarray(normalized), pixels)
    assert normalized is not image


def test_v293_all_primary_page_loaders_use_alpha_safe_normalization():
    from pathlib import Path

    package = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app_text = (package / "app.py").read_text(encoding="utf-8")
    training_text = (package / "training_export.py").read_text(encoding="utf-8")
    layout_text = (package / "layout_detection.py").read_text(encoding="utf-8")
    paddle_text = (package / "paddle_headwords.py").read_text(encoding="utf-8")

    assert "self.image = normalize_page_rgb(opened)" in app_text
    assert "image = normalize_page_rgb(opened)" in app_text
    assert "image = normalize_page_rgb(opened)" in training_text
    assert "source = normalize_page_rgb(image)" in layout_text
    assert "oriented = normalize_page_rgb(image)" in paddle_text



def test_v294_candidate_checkbox_uses_local_overlay_update_and_deferred_save():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def set_candidate_selected(")
    end = text.index("    def apply_candidate_choice", start)
    block = text[start:end]
    assert "self._update_entry_overlays_local(" in block
    assert "self._schedule_deferred_page_save(sync_editors=False)" in block
    assert "self.redraw()" not in block
    assert "self.save_pdic(" not in block
    assert "defer=True" in block


def test_v294_background_photo_cache_key_includes_page_size_binary_and_appearance():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _get_cached_display_photo(")
    end = text.index("    def _draw_entry_overlay(", start)
    block = text[start:end]
    assert "key = (id(self.image), int(size[0]), int(size[1]), binary, self.appearance_mode)" in block
    assert "self._display_photo_cache_key != key" in block


def test_v294_deferred_save_snapshot_is_immutable_against_later_entry_mutation(tmp_path):
    class FakeProject:
        def __init__(self, page):
            self.images = [page]

    class FakeAfter:
        def __init__(self):
            self.jobs = {}
            self.n = 0
        def after(self, _delay, callback):
            self.n += 1
            token = f"j{self.n}"
            self.jobs[token] = callback
            return token
        def cancel(self, token):
            self.jobs.pop(token, None)

    page = tmp_path / "0001.png"
    Image.new("RGB", (200, 300), "white").save(page)
    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.project = FakeProject(page)
    app.current_page = page
    app.current_index = 0
    app.image = Image.new("RGB", (200, 300), "white")
    app.entries = [Entry("old", 20, 40)]
    app.entry_editor_bindings = []
    app._deferred_save_job = None
    app._deferred_save_page = None
    app._deferred_save_snapshot = None
    app._deferred_save_delay_ms = 300
    app._pending_manual_override_path = None
    app._pending_manual_override_payload = None
    app._update_page_row = lambda _index: None
    fake = FakeAfter()
    app.after = fake.after
    app.after_cancel = fake.cancel

    PictureCaptureApp._schedule_deferred_page_save(app)
    app.entries[0].word = "newer-in-memory"
    PictureCaptureApp._flush_deferred_page_save(app)

    saved = read_pdic(page.with_suffix(".pdic"))
    assert len(saved) == 1
    assert saved[0].word == "old"


def test_v294_explicit_save_cancels_debounce_and_writes_latest_live_state(tmp_path):
    class FakeProject:
        def __init__(self, page):
            self.images = [page]

    page = tmp_path / "0001.png"
    Image.new("RGB", (200, 300), "white").save(page)
    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.project = FakeProject(page)
    app.current_page = page
    app.current_index = 0
    app.image = Image.new("RGB", (200, 300), "white")
    app.entries = [Entry("latest", 20, 40)]
    app.entry_editor_bindings = []
    app._deferred_save_job = "queued"
    app._deferred_save_page = page
    app._deferred_save_snapshot = (page, [Entry("stale", 20, 40)], 200, ("0001", "@", "@"), 0)
    app._pending_manual_override_path = None
    app._pending_manual_override_payload = None
    cancelled = []
    app.after_cancel = lambda token: cancelled.append(token)
    app._update_page_row = lambda _index: None

    PictureCaptureApp.save_pdic(app, silent=True, sync_editors=False)
    saved = read_pdic(page.with_suffix(".pdic"))
    assert cancelled == ["queued"]
    assert saved[0].word == "latest"


def test_v294_batch_runner_force_flushes_pending_foreground_checkbox_edits_before_start():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _start_batch_task(")
    end = text.index("    def _start_parallel_batch_task(", start)
    block = text[start:end]
    assert "self._flush_deferred_page_save()" in block
    assert block.index("self._flush_deferred_page_save()") < block.index("self._batch_active = True")



def test_v294_display_geometry_cache_invalidates_when_layout_parameters_change():
    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.image = Image.new("RGB", (600, 900), "white")
    app.settings = AppSettings()
    key1 = PictureCaptureApp._display_geometry_key(app)
    app.settings.manual_x += 3
    key2 = PictureCaptureApp._display_geometry_key(app)
    assert key2 != key1
    app.settings.manual_x -= 3
    app.settings.column_track_radius += 2
    key3 = PictureCaptureApp._display_geometry_key(app)
    assert key3 != key1
    app.settings.column_track_radius -= 2
    app.settings.geometry_reference_width += 100
    key4 = PictureCaptureApp._display_geometry_key(app)
    assert key4 != key1
    app.settings.geometry_reference_width -= 100
    app.settings.profile_side_percent_a += 1.0
    key5 = PictureCaptureApp._display_geometry_key(app)
    assert key5 != key1



def test_v295_page_aware_words_import_keeps_each_page_isolated():
    text = "\n".join([
        "uno#10#20#1#2#0001#@#0002",
        "dos#10#40#1#4#0001#@#0002",
        "tres#10#20#1#2#0002#0001#0003",
        "cuatro#10#20#1#2#0003#0002#@",
        "cinco#10#40#1#4#0003#0002#@",
        "seis#10#60#1#6#0003#0002#@",
    ])
    mapping = _parse_words_of_pages_text(text, ["0001", "0002", "0003"])
    assert mapping["0001"] == ["uno", "dos"]
    assert mapping["0002"] == ["tres"]
    assert mapping["0003"] == ["cuatro", "cinco", "seis"]


def test_v295_page_fill_never_borrows_or_overflows_between_pages():
    entries = [Entry("old-a", 10, 20), Entry("old-b", 10, 40)]
    filled, lines, words = _fill_page_entries(entries, ["A", "B", "EXTRA"])
    assert (filled, lines, words) == (2, 2, 3)
    assert [e.word for e in entries] == ["A", "B"]

    entries2 = [Entry("old-a", 10, 20), Entry("keep-me", 10, 40)]
    filled, lines, words = _fill_page_entries(entries2, ["ONLY"])
    assert (filled, lines, words) == (1, 2, 1)
    assert [e.word for e in entries2] == ["ONLY", "keep-me"]


def test_v295_plain_unpaged_word_list_is_rejected_to_prevent_cross_page_spill():
    import pytest
    with pytest.raises(ValueError, match="没有可识别的页码边界"):
        _parse_words_of_pages_text("a\nb\nc\n", ["0001", "0002"])


def test_v295_words_import_supports_explicit_page_sections():
    mapping = _parse_words_of_pages_text(
        "[0001]\n甲\n乙\n\n页码: 0002\n丙\n",
        ["0001", "0002"],
    )
    assert mapping == {"0001": ["甲", "乙"], "0002": ["丙"]}


def test_v295_illustration_crop_bounds_clip_to_header_without_mutating_polygon(tmp_path):
    page = tmp_path / "0001.png"
    Image.new("RGB", (200, 300), "white").save(page)
    region = PolygonRegion("pic", [(20, 30), (120, 30), (120, 160), (20, 160)])
    original = list(region.points)
    settings = AppSettings(parameter_display_width=200)
    top, bottom, margin = illustration_crop_bounds(
        Image.new("RGB", (200, 300), "white"), settings, top_y=80, bottom_y=250, margin=5
    )
    assert (top, bottom, margin) == (80, 250, 5)
    box = illustration_polygon_box(
        Image.new("RGB", (200, 300), "white"), region, top=top, bottom=bottom, margin_px=margin
    )
    assert box == (15, 80, 126, 166)
    assert region.points == original

    out = tmp_path / "out"
    records = split_illustrations(
        page, [region], out, settings, top_y=80, bottom_y=250, margin=5
    )
    assert len(records) == 1
    assert records[0].box == box
    assert Image.open(out / records[0].filename).size == (111, 86)


def test_v295_right_click_is_next_page_outside_polygon_mode():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def canvas_right_click(")
    end = text.index("    def canvas_motion", start)
    block = text[start:end]
    assert "self.change_page(1)" in block
    assert "self.auto_detect_current(clicked_x=x)" not in block
    assert "if self.polygon_draw_var.get():" in block


def test_v295_illustration_crop_button_uses_shared_crop_settings_before_running_batch():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def split_illustrations_selected_scope(")
    end = text.index("    def _start_illustration_crop(", start)
    block = text[start:end]
    assert "self._start_illustration_crop(indices, self._load_crop_settings())" in block
    assert "_start_parallel_batch_task" not in block



def test_v296_large_words_page_resolution_uses_one_prebuilt_lookup():
    stems = ["0001", "scan_0002", "other_0002", "0003"]
    lookup = _build_words_page_lookup(stems)
    assert _resolve_words_page_token("1", stems, lookup) == "0001"
    assert _resolve_words_page_token("0003.png", stems, lookup) == "0003"
    # Preserve v2.9.5 ambiguity semantics: two suffix matches must not guess.
    assert _resolve_words_page_token("2", stems, lookup) is None

    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("def _parse_words_of_pages_text(")
    end = text.index("\n\ndef _fill_page_entries", start)
    block = text[start:end]
    assert "lookup = _build_words_page_lookup(page_stems)" in block
    assert "page_stems, lookup" in block


def test_v296_existing_word_fill_runs_txt_parse_and_page_commits_in_background_batch():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def fill_existing_headwords(self) -> None:")
    end = text.index("    def import_legacy_words(self) -> bool:", start)
    block = text[start:end]
    # v2.9.8 may reuse an already parsed source; a cache miss is still parsed
    # inside the batch worker call path rather than on Tk's event thread.
    ensure_pos = block.index("        def ensure_mapping(")
    worker_pos = block.index("        def worker(")
    assert block.index("read_text_detected(txt_path)", ensure_pos) < worker_pos
    assert block.index("mapping, present_pages = ensure_mapping()", worker_pos) > worker_pos
    assert "self._start_batch_task(" in block
    assert '"填充词条"' in block
    assert "item_label=lambda i: pages[i].name" in block
    assert "foreground_page_edit=False" in block
    assert "进度按页面更新，可暂停或停止" in block


def test_v298_existing_word_source_selection_is_separate_and_refill_reuses_cache():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    select_start = text.index("    def select_existing_headwords_file(self) -> None:")
    fill_start = text.index("    def fill_existing_headwords(self) -> None:", select_start)
    import_start = text.index("    def import_legacy_words(self) -> bool:", fill_start)
    select_block = text[select_start:fill_start]
    fill_block = text[fill_start:import_start]
    assert "filedialog.askopenfilename(" in select_block
    assert "filedialog.askopenfilename(" not in fill_block
    assert "self._word_fill_source_mapping" in fill_block
    assert '"value": self._word_fill_source_mapping' in fill_block
    assert "self._word_fill_source_mapping = mapping" in fill_block
    assert "请先点击[选择词条文件]" in fill_block


def test_v298_action_row_exposes_select_then_fill_buttons():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert '("备份PDIC", self.backup_pdic)' in text
    assert '("恢复PDIC", self.restore_from_pdic_backup)' in text


def test_v296_batch_queue_polling_yields_between_large_progress_bursts():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _poll_batch_queue(self) -> None:")
    end = text.index("    def _finish_batch_task(", start)
    block = text[start:end]
    assert "max_events_per_poll = 120" in block
    assert "processed_events >= max_events_per_poll" in block
    assert "delay = 8 if processed_events >= max_events_per_poll else 80" in block


def test_v296_page_aware_parser_scales_to_many_pages_without_cross_page_spill():
    page_stems = [f"{i:04d}" for i in range(1, 1001)]
    lines = []
    expected = {stem: [] for stem in page_stems}
    for i in range(12000):
        stem = page_stems[i % len(page_stems)]
        word = f"词{i}"
        lines.append(f"{stem}\t{word}")
        expected[stem].append(word)
    mapping = _parse_words_of_pages_text("\n".join(lines), page_stems)
    assert mapping["0001"] == expected["0001"]
    assert mapping["0500"] == expected["0500"]
    assert mapping["1000"] == expected["1000"]
    assert sum(len(words) for words in mapping.values()) == 12000


def test_v299_word_fill_mismatch_status_persists_across_reopen(tmp_path):
    class FakeProject:
        def __init__(self, root: Path):
            self.root = root
            self.images = [root / "0001.png", root / "0002.png"]

    project = FakeProject(tmp_path)
    for page in project.images:
        Image.new("RGB", (40, 60), "white").save(page)

    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.project = project
    app._word_fill_check_status = {}
    app._word_fill_mismatch_pages = set()
    PictureCaptureApp._record_word_fill_check(
        app, 0, 18, 19, source="_WordsOfPages.txt", persist=True, refresh_overlay=False
    )
    PictureCaptureApp._record_word_fill_check(
        app, 1, 20, 20, source="_WordsOfPages.txt", persist=True, refresh_overlay=False
    )

    status_path = tmp_path / "QT" / "_WordFillStatus.json"
    assert status_path.exists()

    reopened = PictureCaptureApp.__new__(PictureCaptureApp)
    reopened.project = project
    reopened._word_fill_check_status = {}
    reopened._word_fill_mismatch_pages = set()
    PictureCaptureApp._load_word_fill_status(reopened)

    assert reopened._word_fill_mismatch_pages == {0}
    assert reopened._word_fill_check_status["0001"]["word_count"] == 19
    assert reopened._word_fill_check_status["0001"]["source"] == "_WordsOfPages.txt"
    assert reopened._word_fill_check_status["0002"]["mismatch"] is False


def test_v2910_manual_line_count_change_marks_status_stale_and_persists(tmp_path):
    class FakeProject:
        def __init__(self, root: Path):
            self.root = root
            self.images = [root / "0001.png"]

    project = FakeProject(tmp_path)
    Image.new("RGB", (40, 60), "white").save(project.images[0])
    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.project = project
    app._word_fill_check_status = {}
    app._word_fill_mismatch_pages = set()

    PictureCaptureApp._record_word_fill_check(
        app, 0, 18, 19, source="words.txt", persist=True, refresh_overlay=False
    )
    assert app._word_fill_mismatch_pages == {0}
    assert PictureCaptureApp._word_fill_status_text(app, 0) == "少 1"

    PictureCaptureApp._refresh_word_fill_check_from_line_count(app, 0, 19, persist=True)
    assert app._word_fill_mismatch_pages == set()
    assert app._word_fill_check_status["0001"]["state"] == "stale"
    assert PictureCaptureApp._word_fill_status_text(app, 0) == "待重新核对"

    reopened = PictureCaptureApp.__new__(PictureCaptureApp)
    reopened.project = project
    reopened._word_fill_check_status = {}
    reopened._word_fill_mismatch_pages = set()
    PictureCaptureApp._load_word_fill_status(reopened)
    assert reopened._word_fill_mismatch_pages == set()
    assert reopened._word_fill_check_status["0001"]["state"] == "stale"
    assert PictureCaptureApp._word_fill_status_text(reopened, 0) == "待重新核对"


def test_v299_load_project_restores_word_fill_status_before_page_list_refresh():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _load_project(")
    end = text.index("    def on_page_select(", start)
    block = text[start:end]
    assert "self._load_word_fill_status()" in block
    assert block.index("self._load_word_fill_status()") < block.index("self.page_list.insert(")


def test_v2910_page_list_has_persistent_fill_status_column():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert 'columns = ("bookmark", "page", "lined", "fill_status", "illustrations")' in text
    assert 'self.page_list.heading("fill_status", text="填充状态", anchor="w")' in text
    for column in ("bookmark", "page", "lined", "fill_status", "illustrations"):
        assert f'self.page_list.column("{column}",' in text
        column_call = text[text.index(f'self.page_list.column("{column}",'):][:140]
        assert 'anchor="w"' in column_call
    assert 'bd=0, highlightthickness=0, anchor="w", padx=4, pady=0' in text
    assert 'self._word_fill_status_text(index)' in text


def test_v2910_fill_status_text_reports_match_and_signed_difference(tmp_path):
    class FakeProject:
        def __init__(self, root: Path):
            self.root = root
            self.images = [root / "0001.png", root / "0002.png", root / "0003.png"]

    project = FakeProject(tmp_path)
    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.project = project
    app._word_fill_check_status = {}
    app._word_fill_mismatch_pages = set()
    PictureCaptureApp._record_word_fill_check(app, 0, 20, 20, refresh_overlay=False)
    PictureCaptureApp._record_word_fill_check(app, 1, 18, 20, refresh_overlay=False)
    PictureCaptureApp._record_word_fill_check(app, 2, 22, 20, refresh_overlay=False)
    assert PictureCaptureApp._word_fill_status_text(app, 0) == "一致"
    assert PictureCaptureApp._word_fill_status_text(app, 1) == "少 2"
    assert PictureCaptureApp._word_fill_status_text(app, 2) == "多 2"


def test_v2910_parser_collects_present_pages_for_no_data_status():
    present = set()
    mapping = _parse_words_of_pages_text(
        "0001\t甲\n0001\t乙\n0003\t丙\n",
        ["0001", "0002", "0003"],
        present_pages=present,
    )
    assert mapping["0002"] == []
    assert present == {"0001", "0003"}


def test_v2910_no_data_status_is_distinct_from_zero_count_match(tmp_path):
    class FakeProject:
        def __init__(self, root: Path):
            self.root = root
            self.images = [root / "0001.png"]

    project = FakeProject(tmp_path)
    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.project = project
    app._word_fill_check_status = {}
    app._word_fill_mismatch_pages = set()
    PictureCaptureApp._record_word_fill_check(
        app, 0, 0, 0, has_data=False, refresh_overlay=False
    )
    assert PictureCaptureApp._word_fill_status_text(app, 0) == "无资料"
    assert app._word_fill_check_status["0001"]["state"] == "no_data"


def test_v2910_text_only_save_does_not_stale_count_status(tmp_path):
    class FakeProject:
        def __init__(self, root: Path):
            self.root = root
            self.images = [root / "0001.png"]

    project = FakeProject(tmp_path)
    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.project = project
    app._word_fill_check_status = {}
    app._word_fill_mismatch_pages = set()
    PictureCaptureApp._record_word_fill_check(app, 0, 20, 20, refresh_overlay=False)
    PictureCaptureApp._refresh_word_fill_check_from_line_count(app, 0, 20, persist=False)
    assert app._word_fill_check_status["0001"]["state"] == "match"
    assert PictureCaptureApp._word_fill_status_text(app, 0) == "一致"


class PageListSortTests(unittest.TestCase):
    def test_v2911_page_names_sort_naturally(self) -> None:
        values = ["page10.png", "page2.png", "page1.png"]
        self.assertEqual(
            sorted(values, key=_natural_text_key),
            ["page1.png", "page2.png", "page10.png"],
        )

    def test_v2911_sort_preserves_stable_page_iids(self) -> None:
        rows = [
            ("9", ("page10.png", "✓", "一致")),
            ("1", ("page2.png", "", "少 3")),
            ("0", ("page1.png", "✓", "多 2")),
        ]
        ordered = _sorted_page_list_rows(rows, "page", False)
        self.assertEqual([iid for iid, _ in ordered], ["0", "1", "9"])
        self.assertEqual([vals[0] for _, vals in ordered], ["page1.png", "page2.png", "page10.png"])

    def test_v2911_empty_cells_stay_last_in_both_directions(self) -> None:
        rows = [
            ("0", ("a.png", "", "一致")),
            ("1", ("b.png", "✓", "一致")),
            ("2", ("c.png", "处理中…", "一致")),
        ]
        asc = _sorted_page_list_rows(rows, "lined", False)
        desc = _sorted_page_list_rows(rows, "lined", True)
        self.assertEqual(asc[-1][0], "0")
        self.assertEqual(desc[-1][0], "0")


def test_v2912_fill_status_cell_semantic_colors():
    from picture_capture.app import _fill_status_cell_style
    assert _fill_status_cell_style("一致") == ("#d9ead3", "#245b2a")
    assert _fill_status_cell_style("少 2") == ("#f8d7da", "#6b1f25")
    assert _fill_status_cell_style("多 3") == ("#f8d7da", "#6b1f25")
    assert _fill_status_cell_style("待重新核对") == ("#fff3cd", "#6b5714")
    assert _fill_status_cell_style("无资料") == ("#e9ecef", "#495057")
    assert _fill_status_cell_style("未核对") is None


def test_v2912_fill_status_overlay_targets_third_cell_and_keeps_legacy_warning():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _refresh_lined_cell_overlays(")
    end = text.index("    def _word_fill_status_path(", start)
    block = text[start:end]
    assert 'bbox(iid, "fill_status")' in block
    assert 'self.page_list.set(iid, "fill_status")' in block
    assert '_fill_status_cell_style(status_text)' in block
    assert 'bbox(iid, "lined")' in block  # legacy mismatch warning retained, column may be hidden


def test_v2913_page_overlay_refresh_is_coalesced():
    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.page_list = object()
    app._page_overlay_refresh_job = None
    callbacks = []
    refreshes = []

    def fake_after_idle(callback):
        callbacks.append(callback)
        return "job-1"

    app.after_idle = fake_after_idle
    app._refresh_lined_cell_overlays = lambda: refreshes.append("paint")

    PictureCaptureApp._schedule_page_cell_overlay_refresh(app)
    PictureCaptureApp._schedule_page_cell_overlay_refresh(app)
    assert len(callbacks) == 1
    assert app._page_overlay_refresh_job == "job-1"

    callbacks[0]()
    assert refreshes == ["paint"]
    assert app._page_overlay_refresh_job is None


def test_v2913_overlay_repaint_only_walks_visible_rows():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _refresh_lined_cell_overlays(")
    end = text.index("    def _word_fill_status_path(", start)
    block = text[start:end]
    assert "visible_iids = self._visible_page_list_iids()" in block
    assert "for iid in visible_iids:" in block
    assert "range(len(self.project.images))" not in block


def test_v2914_background_resort_does_not_snap_viewport_to_selection():
    class FakeTree:
        def __init__(self):
            self.rows = {
                "0": ("page10.png", "", "少 2"),
                "1": ("page2.png", "", "一致"),
            }
            self.order = ["0", "1"]
            self.seen = []
        def get_children(self, _parent=""):
            return tuple(self.order)
        def item(self, iid, option=None, **kwargs):
            if kwargs.get("values") is not None:
                self.rows[iid] = tuple(kwargs["values"])
                return None
            if option == "values":
                return self.rows[iid]
            return {"values": self.rows[iid]}
        def move(self, iid, _parent, position):
            self.order.remove(iid)
            self.order.insert(position, iid)
        def exists(self, iid):
            return iid in self.rows
        def see(self, iid):
            self.seen.append(iid)

    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.page_list = FakeTree()
    app._page_list_sort_column = "page"
    app._page_list_sort_descending = False
    app.current_index = 0
    app._update_page_list_sort_headings = lambda: None
    app._schedule_page_cell_overlay_refresh = lambda: None

    PictureCaptureApp._apply_page_list_sort(app, ensure_current_visible=False)
    assert app.page_list.seen == []
    PictureCaptureApp._apply_page_list_sort(app, ensure_current_visible=True)
    assert app.page_list.seen == ["0"]


def test_v2914_programmatic_page_selection_replaces_stale_selection():
    class FakeTree:
        def __init__(self):
            self._selection = ["5", "8"]
            self._focus = "5"
            self.seen = []
        def exists(self, iid):
            return iid in {"5", "8", "9"}
        def selection(self):
            return tuple(self._selection)
        def selection_remove(self, *items):
            self._selection = [x for x in self._selection if x not in items]
        def selection_set(self, iid):
            self._selection.append(iid)
        def focus(self, iid=None):
            if iid is not None:
                self._focus = iid
            return self._focus
        def see(self, iid):
            self.seen.append(iid)

    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.page_list = FakeTree()
    PictureCaptureApp._set_page_list_selection(app, 9, ensure_visible=True)
    assert app.page_list.selection() == ("9",)
    assert app.page_list.focus() == "9"
    assert app.page_list.seen == ["9"]


def test_page_list_current_row_is_centered_after_programmatic_selection():
    class FakeTree:
        def __init__(self):
            self._selection = []
            self._focus = ""
            self.moves = []
            self.seen = []
            self.rows = tuple(str(i) for i in range(100))
        def exists(self, iid):
            return iid in self.rows
        def selection(self):
            return tuple(self._selection)
        def selection_remove(self, *items):
            self._selection = [x for x in self._selection if x not in items]
        def selection_set(self, iid):
            self._selection = [iid]
        def focus(self, iid=None):
            if iid is not None:
                self._focus = iid
            return self._focus
        def see(self, iid):
            self.seen.append(iid)
        def get_children(self, _parent=""):
            return self.rows
        def update_idletasks(self):
            return None
        def yview(self):
            return (0.20, 0.40)
        def yview_moveto(self, fraction):
            self.moves.append(fraction)

    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.page_list = FakeTree()
    app._schedule_page_cell_overlay_refresh = lambda: None
    PictureCaptureApp._set_page_list_selection(app, 50, ensure_visible=True)
    assert app.page_list.seen == ["50"]
    assert app.page_list.moves
    # Row 50 center is at 0.505; with a 20% viewport, the top should be ~0.405.
    assert abs(app.page_list.moves[-1] - 0.405) < 1e-9


def test_v2914_lined_metadata_update_does_not_resort_fill_status_sort():
    class Page:
        name = "page1.png"
    class Project:
        images = [Page()]
    class FakeTree:
        def __init__(self):
            self.values = ("page1.png", "", "少 2")
        def exists(self, iid):
            return iid == "0"
        def item(self, iid, option=None, **kwargs):
            if "values" in kwargs:
                self.values = tuple(kwargs["values"])
                return None
            if option == "values":
                return self.values
            return {"values": self.values}

    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.project = Project()
    app.page_list = FakeTree()
    app._page_list_sort_column = "fill_status"
    app._page_metadata = lambda _index: "✓"
    app._word_fill_status_text = lambda _index: "少 2"
    resorts = []
    app._schedule_page_list_resort = lambda: resorts.append("resort")
    app._schedule_page_cell_overlay_refresh = lambda: None
    PictureCaptureApp._update_page_row(app, 0)
    assert resorts == []


def test_v2914_fill_status_change_resorts_fill_status_sort():
    class Page:
        name = "page1.png"
    class Project:
        images = [Page()]
    class FakeTree:
        def __init__(self):
            self.values = ("page1.png", "✓", "少 2")
        def exists(self, iid):
            return iid == "0"
        def item(self, iid, option=None, **kwargs):
            if "values" in kwargs:
                self.values = tuple(kwargs["values"])
                return None
            if option == "values":
                return self.values
            return {"values": self.values}

    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.project = Project()
    app.page_list = FakeTree()
    app._page_list_sort_column = "fill_status"
    app._page_metadata = lambda _index: "✓"
    app._word_fill_status_text = lambda _index: "一致"
    resorts = []
    app._schedule_page_list_resort = lambda: resorts.append("resort")
    app._schedule_page_cell_overlay_refresh = lambda: None
    PictureCaptureApp._update_page_row(app, 0)
    assert resorts == ["resort"]


def test_v2101_auto_illustration_detection_writes_ppp_and_preserves_manual(tmp_path):
    from PIL import Image, ImageDraw
    from picture_capture.models import AppSettings, PolygonRegion
    from picture_capture.processing import detect_illustrations_to_ppp
    from picture_capture.formats import write_ppp, read_ppp

    page = tmp_path / "p001.png"
    image = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(image)
    for x0 in (40, 520):
        for y in range(80, 1320, 28):
            for j in range(8):
                x = x0 + j * 42
                draw.rectangle((x, y, x + 28, y + 7), fill="black")
    draw.rectangle((120, 450, 420, 800), fill="white")
    draw.rectangle((150, 490, 380, 760), outline="black", width=5)
    draw.ellipse((190, 530, 340, 700), outline="black", width=6)
    draw.line((150, 760, 380, 490), fill="black", width=5)
    image.save(page)

    manual = PolygonRegion("manual", [(700, 900), (800, 900), (800, 1000), (700, 1000)])
    write_ppp(page.with_suffix(".ppp"), [manual], page.stem)
    settings = AppSettings(
        columns=2, gutter=20, column_width=450, start_y=50, bottom_y=1350,
        parameter_display_width=1000,
    )
    first = detect_illustrations_to_ppp(page, settings)
    saved = read_ppp(page.with_suffix(".ppp"))
    assert first["manual"] == 1
    assert first["auto"] >= 1
    assert any(r.label == "manual" for r in saved)
    assert any("|AUTO_" in r.label for r in saved)

    # Rerun must replace AUTO polygons rather than append duplicates.
    second = detect_illustrations_to_ppp(page, settings)
    saved2 = read_ppp(page.with_suffix(".ppp"))
    assert second["manual"] == 1
    assert sum("|AUTO_" in r.label for r in saved2) == second["auto"]
    assert sum(r.label == "manual" for r in saved2) == 1


def test_v2101_illustration_detection_button_uses_selected_scope_and_auto_ppp():
    from pathlib import Path
    text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert '("插图识别", self.detect_illustrations_selected_scope)' in text
    start = text.index("    def detect_illustrations_selected_scope(")
    end = text.index("    def split_illustrations_selected_scope(", start)
    block = text[start:end]
    assert "selected_page_indices()" in block
    assert "人工绘制的 PPP 多边形会保留" in block
    assert "foreground_page_edit=True" in block


def test_v2102_wordslist_path_default_and_project_relative_load(tmp_path):
    from picture_capture.models import ProjectState, resolve_wordslist_path

    image = Image.new("RGB", (50, 50), "white")
    image.save(tmp_path / "0001.png")
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "mywords.txt").write_text("alpha\nbeta\n'comment\n\n", encoding="utf-8")
    settings = AppSettings(wordslist_path="refs/mywords.txt")
    settings.to_json(tmp_path / "picture_capture_settings.json")

    project = ProjectState.open(tmp_path)
    assert project.words == ["alpha", "beta"]
    assert resolve_wordslist_path(tmp_path, project.settings.wordslist_path) == refs / "mywords.txt"


def test_v2102_reload_wordslist_updates_project_membership_and_persists_relative_path(tmp_path):
    from types import SimpleNamespace
    from picture_capture.models import ProjectState

    image = Image.new("RGB", (50, 50), "white")
    image.save(tmp_path / "0001.png")
    selected = tmp_path / "lists" / "chosen.txt"
    selected.parent.mkdir()
    selected.write_text("uno\ndos\n", encoding="utf-8")
    project = ProjectState.open(tmp_path)

    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.project = project
    app.settings = project.settings
    app._project_words = set()
    app.current_page = None
    app.image = None
    path, count = PictureCaptureApp.reload_wordslist_reference(
        app, selected, persist=True, redraw=False
    )
    assert path == selected
    assert count == 2
    assert project.words == ["uno", "dos"]
    assert app._project_words == {"uno", "dos"}
    assert app.settings.wordslist_path == "lists/chosen.txt"
    from picture_capture.project_storage import settings_path
    reopened = AppSettings.from_json(settings_path(tmp_path))
    assert reopened.wordslist_path == "lists/chosen.txt"


def test_v2102_review_ui_uses_wordslist_selector_not_wordsofpages_import():
    text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'text="选择文件"' in review
    assert 'text="导入_WordsOfPages.txt"' not in review
    assert "def choose_wordslist_file" in review
    assert "refresh_wordslist_display" in review


def test_v2103_large_wordslist_reader_streams_and_keeps_entries(tmp_path):
    from picture_capture.models import read_noncomment_lines

    path = tmp_path / "wordslist.txt"
    path.write_text("alpha\n'comment\n\nbeta\nGamma\n", encoding="utf-8")
    assert read_noncomment_lines(path) == ["alpha", "beta", "Gamma"]


def test_v2103_wordslist_lookup_key_is_lightweight_unicode_fold():
    from picture_capture.app import ReviewWindow

    assert ReviewWindow._wordslist_lookup_key("  Á-b.or  ") == "abor"
    assert ReviewWindow._wordslist_lookup_key("ÉLÈVE") == "eleve"
    assert ReviewWindow._wordslist_lookup_key("中文") == "中文"


def test_v2103_review_wordslist_uses_virtual_window_and_cached_membership():
    text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert "self.word_window_radius = 250" in review
    assert 'text="前500"' in review and 'text="后500"' in review
    assert "def _show_wordslist_window" in review
    assert "右侧仅显示当前词附近" in review
    assert "words = self.parent._project_words if self.parent.project else set()" in review
    assert "set(self.parent.project.words if self.parent.project else [])" not in review


def test_v2110_crop_plan_links_ppp_by_headword_and_classifies_geometry():
    image = Image.new("RGB", (400, 600), "white")
    settings = AppSettings(
        parameter_display_width=400, columns=1, column_width=300, gutter=20,
        start_y=20, bottom_y=580, manual_x=20, follow_column_deformation=False,
    )
    entries = [Entry("alpha", 20, 100), Entry("beta", 20, 300)]
    polygons = [
        PolygonRegion("x|alpha|1|x|", [(60, 140), (160, 140), (160, 220), (60, 220)]),
        PolygonRegion("x|beta|1|x|", [(250, 250), (390, 250), (390, 350), (250, 350)]),
        PolygonRegion("x|alpha|1|x|", [(50, 420), (120, 420), (120, 470), (50, 470)]),
        PolygonRegion("x|orphan|1|x|", [(200, 430), (260, 430), (260, 480), (200, 480)]),
    ]
    plan = build_page_crop_plan(image, entries, polygons, settings, top_y=20, bottom_y=580)
    relations = [(p.associated_word, p.relation, p.standalone) for p in plan.illustrations]
    assert relations[0] == ("alpha", "contained", False)
    assert relations[1] == ("beta", "partial", False)
    assert relations[2] == ("alpha", "outside", True)
    assert relations[3] == ("", "unassociated", True)
    beta_pieces = [p for p in plan.entry_pieces if p.entry_ref_index == 1]
    assert any(p.merge_polygon_indices == (1,) for p in beta_pieces)


def test_v2110_illustration_split_skips_embedded_and_names_external_like_headword(tmp_path):
    page = tmp_path / "0001.png"
    Image.new("RGB", (400, 600), "white").save(page)
    settings = AppSettings(
        parameter_display_width=400, columns=1, column_width=300, gutter=20,
        start_y=20, bottom_y=580, manual_x=20, follow_column_deformation=False,
    )
    entries = [Entry("alpha", 20, 100), Entry("beta", 20, 300)]
    polygons = [
        PolygonRegion("x|alpha|1|x|", [(60, 140), (160, 140), (160, 220), (60, 220)]),
        PolygonRegion("x|alpha|1|x|", [(50, 420), (120, 420), (120, 470), (50, 470)]),
    ]
    result = split_illustrations(page, polygons, tmp_path / "pic", settings, top_y=20, bottom_y=580, entries=entries)
    assert len(result.records) == 1
    assert result.records[0].filename == "0001_WW_000(P1).png"
    assert result.events[0].relation == "contained"
    assert "跳过" in result.events[0].action
    assert result.events[1].relation == "outside"
    assert (tmp_path / "pic" / "0001_WW_000(P1).png").exists()


def test_v2110_entry_crop_whitens_standalone_ppp_but_preserves_linked_ppp(tmp_path):
    page = tmp_path / "0001.png"
    image = Image.new("RGB", (400, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((60, 140, 160, 220), fill="black")   # alpha-linked PPP
    draw.rectangle((200, 430, 260, 480), fill="black")  # standalone PPP in beta crop
    image.save(page)
    settings = AppSettings(
        parameter_display_width=400, columns=1, column_width=300, gutter=20,
        start_y=20, bottom_y=580, manual_x=20, follow_column_deformation=False,
    )
    entries = [Entry("alpha", 20, 100), Entry("beta", 20, 300)]
    polygons = [
        PolygonRegion("x|alpha|1|x|", [(60, 140), (160, 140), (160, 220), (60, 220)]),
        PolygonRegion("x|orphan|1|x|", [(200, 430), (260, 430), (260, 480), (200, 480)]),
    ]
    out = tmp_path / "pww"
    records = split_whole_entries(page, entries, settings, out, top_y=20, bottom_y=580, polygons=polygons)
    alpha = next(r for r in records if r.word == "alpha")
    beta = next(r for r in records if r.word == "beta")
    with Image.open(out / alpha.filename) as a:
        # The linked illustration remains visible in alpha's original-source crop.
        assert min(a.convert("L").getextrema()) == 0
    with Image.open(out / beta.filename) as b:
        # The standalone PPP is white-filled before ordinary beta cropping.
        assert b.convert("L").getextrema()[0] == 255


def test_v2110_page_list_heading_context_menu_has_optional_columns_and_permanent_page():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert "bind_context_menu(self.page_list, self._page_list_right_click)" in text
    assert 'menu.add_checkbutton(label="页面", variable=page_var, state="disabled")' in text
    assert 'label="画线"' in text and 'label="填充状态"' in text and 'label="插图"' in text




def test_v2116_page_list_has_illustration_count_column_and_sort():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert 'self.page_list.heading("illustrations", text="插图", anchor="w")' in text
    assert 'command=lambda: self._sort_page_list("illustrations")' in text
    assert 'page_list_show_illustrations' in text
    rows = [
        ("0", ("a.png", "✓", "一致", "12")),
        ("1", ("b.png", "✓", "一致", "2")),
        ("2", ("c.png", "✓", "一致", "")),
    ]
    asc = _sorted_page_list_rows(rows, "illustrations", False)
    desc = _sorted_page_list_rows(rows, "illustrations", True)
    assert [iid for iid, _ in asc] == ["1", "0", "2"]
    assert [iid for iid, _ in desc] == ["0", "1", "2"]


def test_v2116_page_illustration_count_uses_ppp_without_opening_page_pixels(tmp_path):
    page = tmp_path / "0001.png"
    page.write_bytes(b"not-an-image")
    write_ppp(
        page.with_suffix(".ppp"),
        [
            PolygonRegion("a", [(1, 1), (5, 1), (5, 5), (1, 5)]),
            PolygonRegion("b", [(10, 10), (15, 10), (15, 15), (10, 15)]),
        ],
        page.stem,
    )
    class FakeProject:
        images = [page]
    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.project = FakeProject()
    app.current_index = -1
    app.current_page = None
    app.polygons = []
    assert PictureCaptureApp._page_illustration_count_text(app, 0) == "2"

def test_v2110_main_crop_preview_replaces_old_width_only_checkbox():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert 'text="显示切图预览"' in text
    assert 'command=self._toggle_crop_preview' in text
    assert 'def _draw_crop_plan_preview' in text


def test_page_list_uses_display_mode_selector_for_existing_view_states():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert 'text="显示模式："' in text
    assert 'values=("原图+标注", "二值+标注", "仅原图", "仅二值", "切图预览")' in text
    assert 'display_mode_combo.bind("<<ComboboxSelected>>", self._apply_display_mode)' in text
    page_start = text.index('page_panel = self._section_frame(sidebar, "六、页面列表"')
    page_end = text.index("        list_frame = ttk.Frame(page_panel)", page_start)
    page_toolbar = text[page_start:page_end]
    assert 'text="页面范围："' not in page_toolbar
    assert page_toolbar.index('text="显示模式："') < page_toolbar.index('text="当前页"')
    assert 'display_mode_combo = ttk.Combobox(\n            range_row,' in page_toolbar
    assert 'display_mode_combo = ttk.Combobox(\n            size_row,' not in page_toolbar
    assert 'text="◧"' not in text
    assert '"原图+标注": (False, False, False)' in text
    assert '"二值+标注": (True, False, False)' in text
    assert '"仅原图": (False, True, False)' in text
    assert '"仅二值": (True, True, False)' in text
    assert '"切图预览": (False, False, True)' in text


def test_page_list_compact_labels_navigation_order_and_consistency_minimum():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert 'text="当前页"' in text
    assert 'text="当前至末页"' in text
    assert 'text="↔"' in text
    assert 'text="↕"' in text
    assert 'text="跳到"' not in text
    assert 'text="跳转"' in text
    assert text.index('text="↕"') < text.index('text="跳转"') < text.index('text="上一页"') < text.index('text="下一页"')
    page_start = text.index('page_panel = self._section_frame(sidebar, "六、页面列表"')
    page_end = text.index("        list_frame = ttk.Frame(page_panel)", page_start)
    page_toolbar = text[page_start:page_end]
    assert page_toolbar.count('style="PC.PageNav.TButton"') == 3
    assert 'style.configure("PC.PageNav.TButton", padding=(2, 2))' in text
    assert 'text="跳转", width=6' in page_toolbar
    assert 'text="上一页", width=6' in page_toolbar
    assert 'text="下一页", width=6' in page_toolbar
    assert page_toolbar.count('style="PC.PageNav.TButton"') == 3
    for tooltip in (
        "缩小显示",
        "放大显示",
        "适合宽度显示",
        "适合高度显示",
        "跳转到上一书签",
        "跳转到下一书签",
        "跳转到指定页面的第一个有效页面",
    ):
        assert f'self._attach_tooltip(' in page_toolbar
        assert f'"{tooltip}"' in page_toolbar
    assert 'text="页面大小："' not in text
    assert '("已有项目", self.open_recent_project, "project")' in text
    assert "self.after_idle(self._maximize_main_window)" in text
    assert "self.after_idle(self._ensure_sidebar_navigation_width)" in text
    assert '"lined": "画线"' in text
    assert 'if len(indices) < 2:' in text
    assert '至少需要选择 2 页' in text


def test_action_and_postproduction_rows_use_equal_width_grid_columns():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    actions_start = text.index('        actions = self._section_frame(parent, "四、画线与校对"')
    actions_end = text.index("        postproduction = self._section_frame(", actions_start)
    actions = text[actions_start:actions_end]
    assert 'row.columnconfigure(bi, weight=1, uniform=f"actions-row-{ri}")' in actions
    assert 'button.grid(' in actions
    assert 'button.pack(side="left", fill="x", expand=True' not in actions

    post_start = text.index("        postproduction = self._section_frame(", actions_end)
    post_end = text.index("        # Main-panel parameters are live:", post_start)
    post = text[post_start:post_end]
    assert 'row.columnconfigure(bi, weight=1, uniform=f"postproduction-row-{ri}")' in post
    assert ').grid(' in post
    assert '.pack(\n                    side="left", fill="x", expand=True' not in post


def test_main_quick_parameter_entries_are_left_aligned():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _build_quick_settings(")
    end = text.index("\n    @staticmethod\n    def _style_color_button", start)
    quick = text[start:end]
    assert 'justify="right" if cast in {int, float} else "left"' not in quick
    assert 'justify="left"' in quick
    # Every explicit quick-panel Entry should declare left alignment.
    assert quick.count("ttk.Entry(") == quick.count('justify="left"')


def test_entry_default_color_and_bookmarks_persist(tmp_path):
    settings = AppSettings(
        main_entry_default_color="#fef3c7",
        page_bookmarks=["0002", "0010"],
    )
    path = tmp_path / "settings.json"
    settings.to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.main_entry_default_color == "#fef3c7"
    assert reopened.page_bookmarks == ["0002", "0010"]


def test_layout_gutter_uses_persistent_pixel_whitespace_not_ragged_line_ends():
    height, width = 800, 1000
    ink = np.zeros((height, width), dtype=bool)
    boxes = []
    for row, y in enumerate(range(100, 700, 40)):
        end = 250 if row % 3 else 450
        ink[y:y + 12, 50:end] = True
        ink[y:y + 12, 500:820] = True
        boxes.extend([(50, y, min(end, 300), y + 12), (500, y, 760, y + 12)])
    estimate = infer_layout_from_boxes(boxes, (width, height), ink_mask=ink)
    assert estimate.columns == 2
    assert 390 <= estimate.column_width <= 410
    assert 45 <= estimate.gutter <= 55


def test_vertical_rule_gutter_includes_blank_space_on_both_sides():
    ink = np.zeros((600, 1000), dtype=bool)
    for y in range(50, 550, 30):
        ink[y:y + 12, 50:430] = True
        ink[y:y + 12, 570:950] = True
    ink[50:550, 497:503] = True

    divider = _detect_persistent_vertical_rule(ink, 50, 570, 50, 550, "auto")

    assert divider is not None
    assert divider.center == 500
    assert divider.gutter_start == 430
    assert divider.gutter_end == 570
    assert _detect_persistent_vertical_rule(ink, 50, 570, 50, 550, "absent") is None


def test_auto_vertical_rule_rejects_persistent_text_stroke_without_blank_sides():
    ink = np.zeros((600, 800), dtype=bool)
    for y in range(50, 550, 24):
        ink[y:y + 16, 40:760] = True
    ink[50:550, 397:403] = True

    assert _detect_persistent_vertical_rule(ink, 40, 440, 50, 550, "auto") is None


def test_fixed_column_prior_constrains_sparse_box_layout():
    boxes = [(60, y, 340, y + 18) for y in range(100, 700, 45)]
    estimate = infer_layout_from_boxes(
        boxes,
        (1000, 800),
        columns_policy="fixed",
        fixed_columns=2,
        column_separator_mode="absent",
    )

    assert estimate.columns == 2
    assert estimate.manual_x == 60
    assert estimate.column_width == 280
    assert estimate.gutter > 100


def test_bookmark_controls_and_project_switch_protect_project_settings():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert 'text="⨇"' in text and 'text="⨈"' in text
    assert 'columns = ("bookmark", "page", "lined", "fill_status", "illustrations")' in text
    assert '"●" if page.stem in self._bookmark_stems() else ""' in text
    load_start = text.index("    def _load_project(")
    load_end = text.index("    def on_page_select", load_start)
    load_block = text[load_start:load_end]
    assert "self.after_cancel(pending_quick_job)" in load_block
    assert "self._quick_trace_ready = False" in load_block
    assert "self._display_geometry_cache = None" in load_block

    processing = (source.parent / "processing.py").read_text(encoding="utf-8")
    normal_start = processing.index("def _detect_entries_left_edge")
    normal_end = processing.index("\ndef detect_entries", normal_start)
    normal_block = processing[normal_start:normal_end]
    assert "from .paddle_headwords import refine_separator_y" in normal_block
    assert "y_source, _refinement = refine_separator_y(" in normal_block


def test_crop_preview_uses_export_filename_and_centered_entry_typography():
    from picture_capture.processing import EntryCropPiecePlan, entry_crop_piece_filename

    piece = EntryCropPiecePlan(7, 2, "词条", (10, 20, 110, 80), "(P2)")
    assert entry_crop_piece_filename("0001", piece) == "0001_WW_007(P2).png"

    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _draw_crop_plan_preview")
    end = text.index("    def redraw", start)
    preview = text[start:end]
    assert "self.settings.main_entry_font_family" in preview
    assert "self.settings.main_entry_font_size" in preview
    assert 'label = f"{piece.word}\\n{filename}"' in preview
    assert 'anchor="n", justify="center"' in preview



def test_v2111_entry_crop_width_uses_gutter_midlines_not_raw_column_edge():
    image = Image.new("RGB", (1800, 1200), "white")
    settings = AppSettings(
        parameter_display_width=1800,
        columns=3,
        manual_x=30,
        column_width=540,
        gutter=60,
        start_y=40,
        follow_column_deformation=False,
    )
    boxes = entry_crop_column_boxes(image, settings, top_y=40, bottom_y=1100)
    assert len(boxes) == 3
    # Inter-column whitespace is split at its midpoint, so neighbouring crop
    # boxes meet rather than leaving the right edge visibly short.
    assert abs(boxes[0][2] - boxes[1][0]) <= 1
    assert abs(boxes[1][2] - boxes[2][0]) <= 1
    # The final column no longer inherits "all remaining page width" as its
    # nominal printed-column width.
    widths = [box[2] - box[0] for box in boxes]
    assert max(widths) - min(widths) < 60


def test_v2111_entry_crop_extra_horizontal_padding_is_applied():
    image = Image.new("RGB", (1200, 800), "white")
    settings = AppSettings(
        parameter_display_width=1200,
        columns=2,
        manual_x=30,
        column_width=540,
        gutter=60,
        start_y=30,
        follow_column_deformation=False,
    )
    base = entry_crop_column_boxes(image, settings, top_y=30, bottom_y=700)
    padded = entry_crop_column_boxes(image, settings, top_y=30, bottom_y=700, extra_left=8, extra_right=12)
    assert padded[0][0] == max(0, base[0][0] - 8)
    assert padded[0][2] == min(image.width, base[0][2] + 12)


def test_v2111_rectangular_ppp_supports_four_side_drag_geometry():
    region = PolygonRegion("rect", [(10, 20), (110, 20), (110, 80), (10, 80)])
    assert PictureCaptureApp._rectangle_bounds(region) == (10, 20, 110, 80)
    PictureCaptureApp._set_rectangle_side(region, "right", 140)
    assert PictureCaptureApp._rectangle_bounds(region) == (10, 20, 140, 80)
    PictureCaptureApp._set_rectangle_side(region, "top", 15)
    assert PictureCaptureApp._rectangle_bounds(region) == (10, 15, 140, 80)


def test_v2111_ui_restores_hide_overlay_and_removes_crop_dialog_preview():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert 'text="隐藏线框(插图除外)"' in text
    crop_class = text.split('class CropSettingsDialog', 1)[1].split('class PictureCaptureApp', 1)[0]
    assert 'preview_canvas' not in crop_class
    assert '主界面完整预览' not in crop_class
    assert '词条右侧额外留白' in crop_class
    assert 'text="×"' in text
    assert 'edge_handles' in text


def test_v2113_gui_paths_do_not_use_raw_xy_entry_sort():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert "sorted(self.entries, key=lambda item: (item.x, item.y))" not in app_text
    assert "sorted(self.parent.entries, key=lambda item: (item.x, item.y))" not in app_text


def test_v2113_repair_pdic_order_button_is_exposed():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert '("修复排序", self.repair_pdic_order_selected_scope)' in app_text


def test_v2113_canonical_reorder_preserves_word_coordinate_binding():
    geometry = Geometry(
        column_starts=[20, 520], column_widths=[420, 420], top=0, bottom=1000,
        column_paths=[ColumnPath([(0, 20), (1000, 20)]), ColumnPath([(0, 520), (1000, 520)])],
    )
    entries = [Entry("manual-late", 20, 300), Entry("ocr-early", 42, 100), Entry("right", 540, 80)]
    before = {(e.word, e.x, e.y) for e in entries}
    ordered = sort_entries_reading_order(entries, geometry)
    assert [(e.word, e.y) for e in ordered] == [("ocr-early", 100), ("manual-late", 300), ("right", 80)]
    assert {(e.word, e.x, e.y) for e in ordered} == before


def test_v2114_repair_sort_uses_column_then_y_and_never_x():
    geometry = Geometry(
        column_starts=[20, 520], column_widths=[420, 420], top=0, bottom=1000,
        column_paths=[ColumnPath([(0, 20), (1000, 20)]), ColumnPath([(0, 520), (1000, 520)])],
    )
    entries = [
        Entry("same-y-first", 80, 100),
        Entry("later", 20, 200),
        Entry("same-y-second", 25, 100),
        Entry("right", 560, 50),
    ]
    ordered = sort_entries_column_y(entries, geometry)
    assert [e.word for e in ordered] == [
        "same-y-first", "same-y-second", "later", "right"
    ]


def test_v2114_repair_pdic_button_calls_column_y_sort_only():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app_text.index("def repair_pdic_order_selected_scope")
    end = app_text.index("def backup_pdic", start)
    body = app_text[start:end]
    assert "sort_entries_column_y(entries" in body
    assert "栏号 → Y" in body
    assert "Y → X" not in body


def test_v2115_nominal_geometry_matches_full_geometry_column_intervals():
    settings = AppSettings()
    settings.columns = 2
    settings.manual_x = 28
    settings.gutter = 34
    settings.column_width = 620
    settings.parameter_display_width = 1400
    settings.start_y = 75
    image = Image.new("RGB", (2400, 3400), "white")
    full = derive_geometry(image, settings)
    nominal = derive_nominal_geometry(image.width, image.height, settings)
    assert nominal.column_starts == full.column_starts
    assert nominal.column_widths == full.column_widths
    assert nominal.top == full.top
    assert nominal.bottom == full.bottom


def test_v2115_large_existing_word_fill_avoids_full_image_decode_and_bulk_tree_updates():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app_text.index("    def fill_existing_headwords(self) -> None:")
    end = app_text.index("    def import_legacy_words(self) -> bool:", start)
    body = app_text[start:end]
    assert "settings_snapshot = replace(self.settings)" in body
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in body
    assert "derive_nominal_geometry(width, height, self.settings)" not in body
    assert "page_image = normalize_page_rgb(opened)" not in body
    assert "refresh_row=False" in body


def test_v2115_pdic_repair_and_restore_use_header_only_geometry():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    repair_start = app_text.index("    def repair_pdic_order_selected_scope")
    repair_end = app_text.index("    def backup_pdic", repair_start)
    repair = app_text[repair_start:repair_end]
    assert "derive_nominal_geometry(width, height, settings)" in repair
    assert "normalize_page_rgb(opened)" not in repair
    restore_start = app_text.index("    def restore_from_pdic_backup")
    restore_end = app_text.index("    def restore_from_merged_pdic", restore_start)
    restore = app_text[restore_start:restore_end]
    assert "settings_snapshot = replace(self.settings)" in restore
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in restore
    assert "derive_nominal_geometry(width, height, self.settings)" not in restore
    assert "normalize_page_rgb(opened)" not in restore


def test_v2117_ppp_label_prefers_outside_upper_right():
    x, y = PictureCaptureApp._external_polygon_label_position(
        100, 120, 300, 420, 140, 26, 1000, 1200
    )
    assert x > 300
    assert y == 120


def test_v2117_ppp_label_avoids_right_edge_without_covering_polygon():
    x, y = PictureCaptureApp._external_polygon_label_position(
        760, 140, 980, 500, 160, 28, 1000, 1200
    )
    assert x + 160 <= 1000
    assert y + 28 < 140
    assert abs((x + 160) - 980) < 1e-6


def test_v2118_crop_settings_exposes_integrate_illustrations_toggle():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    crop_class = text.split("class CropSettingsDialog", 1)[1].split("class PictureCaptureApp", 1)[0]
    assert 'text="是否综合插图计算切图信息"' in crop_class
    assert 'self.integrate_illustrations_var = tk.BooleanVar(value=True)' in crop_class
    assert '"integrate_illustrations": bool(self.integrate_illustrations_var.get())' in crop_class
    assert '"integrate_illustrations": True' in text


def test_v2118_crop_plan_can_ignore_ppp_for_entry_geometry_but_keep_relations():
    image = Image.new("RGB", (400, 600), "white")
    settings = AppSettings(
        parameter_display_width=400, columns=1, column_width=300, gutter=20,
        start_y=20, bottom_y=580, manual_x=20, follow_column_deformation=False,
    )
    entries = [Entry("alpha", 20, 100), Entry("beta", 20, 300)]
    polygons = [
        PolygonRegion("x|alpha|1|x|", [(60, 140), (160, 140), (160, 220), (60, 220)]),
        PolygonRegion("x|beta|1|x|", [(250, 250), (390, 250), (390, 350), (250, 350)]),
    ]
    plan = build_page_crop_plan(
        image, entries, polygons, settings, top_y=20, bottom_y=580,
        integrate_illustrations=False,
    )
    assert plan.integrate_illustrations is False
    assert [(p.associated_word, p.relation, p.standalone) for p in plan.illustrations] == [
        ("alpha", "contained", False),
        ("beta", "partial", True),
    ]
    assert all(p.source_mode == "cleaned" for p in plan.entry_pieces)
    assert all(not p.merge_polygon_indices for p in plan.entry_pieces)


def test_v2118_entry_crop_without_illustration_integration_keeps_ppp_pixels(tmp_path):
    page = tmp_path / "0001.png"
    image = Image.new("RGB", (400, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((60, 140, 160, 220), fill="black")
    draw.rectangle((200, 430, 260, 480), fill="black")
    image.save(page)
    settings = AppSettings(
        parameter_display_width=400, columns=1, column_width=300, gutter=20,
        start_y=20, bottom_y=580, manual_x=20, follow_column_deformation=False,
    )
    entries = [Entry("alpha", 20, 100), Entry("beta", 20, 300)]
    polygons = [
        PolygonRegion("x|alpha|1|x|", [(60, 140), (160, 140), (160, 220), (60, 220)]),
        PolygonRegion("x|orphan|1|x|", [(200, 430), (260, 430), (260, 480), (200, 480)]),
    ]
    out = tmp_path / "pww"
    records = split_whole_entries(
        page, entries, settings, out, top_y=20, bottom_y=580, polygons=polygons,
        integrate_illustrations=False,
    )
    alpha = next(r for r in records if r.word == "alpha")
    beta = next(r for r in records if r.word == "beta")
    with Image.open(out / alpha.filename) as a:
        assert a.convert("L").getextrema()[0] == 0
    with Image.open(out / beta.filename) as b:
        # With integration disabled even an unrelated PPP is not white-filled
        # from the headword crop; the entry crop is the untouched source rectangle.
        assert b.convert("L").getextrema()[0] == 0


def test_v2118_illustration_export_still_deduplicates_contained_ppp_when_integration_off(tmp_path):
    page = tmp_path / "0001.png"
    Image.new("RGB", (400, 600), "white").save(page)
    settings = AppSettings(
        parameter_display_width=400, columns=1, column_width=300, gutter=20,
        start_y=20, bottom_y=580, manual_x=20, follow_column_deformation=False,
    )
    entries = [Entry("alpha", 20, 100)]
    polygons = [PolygonRegion("x|alpha|1|x|", [(60, 140), (160, 140), (160, 220), (60, 220)])]
    result = split_illustrations(
        page, polygons, tmp_path / "pic", settings, top_y=20, bottom_y=580,
        entries=entries, integrate_illustrations=False,
    )
    assert result.records == []
    assert result.events[0].relation == "contained"
    assert "跳过" in result.events[0].action


def test_v2118_partial_ppp_exports_standalone_when_entry_integration_off(tmp_path):
    page = tmp_path / "0001.png"
    Image.new("RGB", (400, 600), "white").save(page)
    settings = AppSettings(
        parameter_display_width=400, columns=1, column_width=300, gutter=20,
        start_y=20, bottom_y=580, manual_x=20, follow_column_deformation=False,
    )
    entries = [Entry("beta", 20, 300)]
    polygons = [PolygonRegion("x|beta|1|x|", [(250, 250), (390, 250), (390, 350), (250, 350)])]
    result = split_illustrations(
        page, polygons, tmp_path / "pic", settings, top_y=20, bottom_y=580,
        entries=entries, integrate_illustrations=False,
    )
    assert len(result.records) == 1
    assert result.records[0].filename == "0001_WW_000(P1).png"
    assert result.events[0].relation == "partial"
    assert "未综合插图" in result.events[0].action


def test_v2119_crop_controls_live_only_in_crop_settings_dialog():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    settings_class = text.split("class SettingsDialog", 1)[1].split("class CropSettingsDialog", 1)[0]
    crop_class = text.split("class CropSettingsDialog", 1)[1].split("class PictureCaptureApp", 1)[0]
    # Crop-only controls must not remain duplicated in More Parameters.
    assert '("裁剪终点 Y", "bottom_y", int)' not in settings_class
    assert '"crop_parallel_workers"' not in settings_class
    assert '("使用裁剪终点 Y", "crop_to_bottom_y")' not in settings_class
    # The unified dialog owns all actual crop parameters.
    for token in (
        'self.general_top_var', 'self.general_bottom_var',
        'self.entry_left_padding_var', 'self.entry_right_padding_var',
        'self.integrate_illustrations_var', 'self.margin_var', 'self.workers_var',
        'self.special_top_var', 'self.special_bottom_var',
    ):
        assert token in crop_class
    assert '完整切图设置（词条切图 / 插图切图共用）' in crop_class


def test_crop_settings_v6_declares_reference_coordinate_space():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    crop_class = text.split("class CropSettingsDialog", 1)[1].split("class PictureCaptureApp", 1)[0]
    assert '"version": CROP_SETTINGS_VERSION' in crop_class
    assert '"coordinate_space": CANONICAL_REFERENCE_SPACE' in crop_class
    assert '"geometry_reference_width"' in crop_class
    assert '"general_top_v"' in crop_class
    assert '"general_bottom_v"' in crop_class
    assert '"entry_left_padding_u"' in crop_class
    assert '"entry_right_padding_u"' in crop_class
    assert "参考页规范像素" in crop_class
    # start_y remains persisted layout geometry; the Settings Center labels its
    # coordinate space explicitly instead of presenting it as an unqualified Y.
    settings_class = text.split("class SettingsDialog", 1)[1].split("class CropSettingsDialog", 1)[0]
    assert '"start_y": "正文起始 V（参考页规范坐标）"' in settings_class


def test_v21110_backup_pdic_is_background_and_streaming():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app_text.index("    def backup_pdic(self) -> None:")
    end = app_text.index("    def restore_from_pdic_backup", start)
    body = app_text[start:end]
    assert 'self._start_batch_task(' in body
    assert 'temp.open("w", encoding="utf-8", newline="\\n")' in body
    assert 'source.read_text(encoding="utf-8-sig").splitlines()' in body
    assert 'stream.write("\\n".join(page_lines))' in body
    assert 'os.replace(temp, target)' in body
    assert 'lines: list[str]' not in body
    assert '"\\n".join(lines)' not in body


def test_v21110_backup_pdic_does_not_touch_page_images():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app_text.index("    def backup_pdic(self) -> None:")
    end = app_text.index("    def restore_from_pdic_backup", start)
    body = app_text[start:end]
    assert "normalize_page_rgb" not in body
    assert "Image.open" not in body
    assert "derive_geometry" not in body


def test_v21110_backup_skips_unrelated_full_page_metadata_refresh():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app_text.index("    def backup_pdic(self) -> None:")
    end = app_text.index("    def restore_from_pdic_backup", start)
    body = app_text[start:end]
    assert "refresh_page_quality=False" in body
    finish_start = app_text.index("    def _finish_batch_task")
    finish_end = app_text.index("    def _hide_batch_bar_if_idle", finish_start)
    finish = app_text[finish_start:finish_end]
    assert 'getattr(self, "_batch_refresh_page_quality", True)' in finish


def test_v21111_illustration_button_is_renamed_to_edit_only():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert '("编辑插图", self.toggle_polygon_drawing)' in app_text
    assert '绘制/编辑插图' not in app_text
    assert 'text="结束编辑插图"' in app_text


def test_v21111_picdic_index_export_is_background_streaming_and_exact_format():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app_text.index("    def export_picdic_index(self) -> None:")
    end = app_text.index("    def backup_pdic", start)
    body = app_text[start:end]
    assert '("导出PicDic索引", self.export_picdic_index)' in app_text
    assert 'read_picdic_index_records(pdic_path(page), fallback_page=page.stem)' in body
    assert 'stream.write("\\n".join(records))' in body
    assert 'self._start_batch_task(' in body
    assert 'refresh_page_quality=False' in body
    assert 'Image.open' not in body
    assert 'derive_geometry' not in body
    assert 'PicDic_index_{stamp}.txt' in body
    assert 'WORD<TAB>xx.xx<TAB>yy.yy<TAB>page' in body


def test_project_details_language_follows_ocr_language():
    assert project_language_from_ocr("eng") == "en"
    assert project_language_from_ocr("spa+chi_sim") == "es"
    assert project_language_from_ocr("chi_tra") == "zh"
    assert project_language_from_ocr("pt") == "pt"
    assert project_language_from_ocr("unknown") == ""


def test_imported_text_encoding_detection_supports_unicode_and_legacy_chinese(tmp_path):
    from picture_capture.text_encoding import read_text_detected

    samples = {
        "utf8.txt": ("词条 café", "utf-8"),
        "utf16.txt": ("繁體詞條", "utf-16"),
        "gb.txt": ("简体词条", "gb18030"),
        "big5.txt": ("繁體詞條", "big5"),
    }
    for name, (value, encoding) in samples.items():
        path = tmp_path / name
        path.write_bytes(value.encode(encoding))
        decoded, detected = read_text_detected(path)
        assert decoded == value
        assert detected.startswith(encoding.split("-")[0]) or detected == encoding


def test_right_ratio_migrates_from_divisor_to_percent(tmp_path):
    import json

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"right_ratio": 2}), encoding="utf-8")
    restored = AppSettings.from_json(path)
    assert restored.right_ratio == 50
    assert restored.right_ratio_percent_version == 1


def test_page_lined_metadata_is_total_count(tmp_path):
    page = tmp_path / "0001.png"
    Image.new("RGB", (20, 20), "white").save(page)
    write_pdic(
        page.with_suffix(".pdic"), [Entry("a", 1, 2), Entry("b", 1, 4)],
        image_width=20, pages=("0001", "@", "@"),
    )
    app = object.__new__(PictureCaptureApp)
    app.project = type("Project", (), {"images": [page]})()
    app.current_index = -1
    app.current_page = None
    assert PictureCaptureApp._page_metadata(app, 0) == "2"


def test_project_details_are_persisted_in_project_settings(tmp_path):
    path = tmp_path / "settings.json"
    AppSettings(
        dictionary_full_name="示例词典",
        dictionary_abbreviation="示例",
        dictionary_isbn="978-0-00-000000-0",
        dictionary_index_language="es",
        dictionary_content_language="zh",
        columns=3,
        dictionary_body_page_range="1-1250",
    ).to_json(path)
    restored = AppSettings.from_json(path)
    assert restored.dictionary_full_name == "示例词典"
    assert restored.dictionary_abbreviation == "示例"
    assert restored.dictionary_isbn == "978-0-00-000000-0"
    assert restored.dictionary_index_language == "es"
    assert restored.dictionary_content_language == "zh"
    assert restored.columns == 3
    assert restored.dictionary_body_page_range == "1-1250"


def test_sidebar_has_collapsed_postproduction_section_and_project_details():
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert '"postproduction": False' in app_text
    assert 'parent, "五、后期词典制作", padding=5, section_key="postproduction"' in app_text
    assert 'self._section_frame(parent, "四、画线与校对"' in app_text
    assert 'self._section_frame(sidebar, "六、页面列表"' in app_text
    first_row = '(("切图设置", self.open_crop_settings), ("词条切图", self.split_entries_selected_scope), ("插图切图", self.split_illustrations_selected_scope))'
    second_row = '(("项目详情", self.open_project_details), ("导出PicDic索引", self.export_picdic_index), ("PicDic制作", self.build_picdic))'
    assert first_row in app_text
    assert second_row in app_text
    assert '(project_tab, "项目 / 批量")' in app_text
    assert '"项目资料"' in app_text
    assert 'self.open_settings(initial_tab="project")' in app_text


def test_auxiliary_overlay_defaults_and_label_style_controls():
    settings = AppSettings()
    assert settings.guide_color == "#ff0000"
    assert settings.headword_marker_color == "#ff0000"
    assert settings.guide_width == 4
    assert settings.marker_height == 2
    assert settings.illustration_outline_width == 1
    assert settings.illustration_label_border_width == 1
    assert settings.main_entry_width_chars == 18
    assert settings.main_entry_x_ratio == 0.66
    assert settings.main_entry_font_size == 32
    assert settings.illustration_label_font_size == 32
    assert settings.show_illustration_labels is False
    assert settings.batch_interval == 3.0
    app_text = (Path(__file__).parents[1] / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    for token in (
        '"illustration_outline_width"', '"illustration_label_border_width"',
        '"illustration_label_font_family"', '"illustration_label_font_size"',
        '"illustration_label_font_bold"', '"illustration_label_font_italic"',
    ):
        assert token in app_text
    assert 'self.quick_bool_vars["show_illustration_labels"]' in app_text
    assert 'show_shapes = bool(self.polygon_var.get() or self.polygon_draw_var.get())' in app_text
    assert 'show_labels = bool(self.settings.show_illustration_labels or self.polygon_draw_var.get())' in app_text


def test_v21112_picdic_index_has_no_percent_signs(tmp_path):
    pdic = tmp_path / "0001.pdic"
    pdic.write_text("一#10#20#0.85#19.07#0001###\n", encoding="utf-8")
    from picture_capture.formats import read_picdic_index_records
    assert read_picdic_index_records(pdic) == ["一\t0.85\t19.07\t0001"]


def test_review_crop_context_keeps_true_horizontal_columns():
    from PIL import Image
    from picture_capture.app import _review_crop_context
    from picture_capture.models import AppSettings, Entry
    from picture_capture.processing import derive_geometry, line_box

    image = Image.new("RGB", (3000, 4000), "white")
    settings = AppSettings(
        parameter_display_width=450,
        columns=3,
        manual_x=15,
        column_width=130,
        gutter=10,
        start_y=30,
        character_height=26,
        row_padding=3,
        follow_column_deformation=False,
    )
    review_settings, geometry = _review_crop_context(image, settings, 1000)
    true_geometry = derive_geometry(image, settings)
    assert geometry.column_starts == true_geometry.column_starts
    assert geometry.column_widths == true_geometry.column_widths
    assert review_settings.parameter_display_width == 450

    # If review_display_width were incorrectly reused for horizontal geometry,
    # later columns would shift progressively.  The review crop must stay close
    # to each real column start instead.
    boxes = [
        line_box(Entry(word=f"w{i}", x=x, y=600), geometry, image, review_settings)
        for i, x in enumerate(geometry.column_starts)
    ]
    crop_lefts = [box[0] for box in boxes]
    assert crop_lefts[1] - crop_lefts[0] > 800
    assert crop_lefts[2] - crop_lefts[1] > 800


def test_review_editor_font_size_is_independent_of_review_zoom():
    from picture_capture.app import _review_editor_font_size
    from picture_capture.models import AppSettings

    settings = AppSettings(review_entry_font_size=17, review_zoom_percent=40)
    assert _review_editor_font_size(settings) == 17
    settings.review_zoom_percent = 250
    assert _review_editor_font_size(settings) == 17


def test_v21114_review_font_migrates_legacy_zoom_scaled_large_size(tmp_path):
    import json
    from picture_capture.models import AppSettings

    path = tmp_path / "picture_capture_settings.json"
    path.write_text(json.dumps({"review_entry_font_size": 72, "review_zoom_percent": 26}), encoding="utf-8")
    settings = AppSettings.from_json(path)
    assert settings.review_entry_font_size == 19
    assert settings.review_font_semantics_version == 2


def test_v21114_review_font_keeps_normal_fixed_size_when_marker_missing(tmp_path):
    import json
    from picture_capture.models import AppSettings

    path = tmp_path / "picture_capture_settings.json"
    path.write_text(json.dumps({"review_entry_font_size": 18, "review_zoom_percent": 26}), encoding="utf-8")
    settings = AppSettings.from_json(path)
    assert settings.review_entry_font_size == 18
    assert settings.review_font_semantics_version == 2


def test_v21114_review_font_marker_prevents_repeat_migration(tmp_path):
    import json
    from picture_capture.models import AppSettings

    path = tmp_path / "picture_capture_settings.json"
    path.write_text(json.dumps({
        "review_entry_font_size": 72,
        "review_zoom_percent": 26,
        "review_font_semantics_version": 2,
    }), encoding="utf-8")
    settings = AppSettings.from_json(path)
    assert settings.review_entry_font_size == 72


def test_v21115_review_window_exposes_persisted_font_controls():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    body = text[start:text.index("class ", start + 20) if "class " in text[start + 20:] else len(text)]
    assert 'text="词条字体："' in body
    assert 'text="字号："' in body
    assert 'text="粗体"' in body
    assert 'text="斜体"' in body
    assert 'self.review_font_family_var' in body
    assert 'self.review_font_size_var' in body
    assert 'settings.review_entry_font_family = family' in body
    assert 'settings.review_entry_font_size = size' in body
    assert 'self.parent.save_settings()' in body


def test_v21115_review_font_apply_does_not_change_review_zoom():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("    def _apply_review_font_settings", text.index("class ReviewWindow"))
    end = text.index("    def change_review_zoom", start)
    body = text[start:end]
    assert "review_zoom_percent" not in body
    assert "self.review_zoom =" not in body


def test_v21116_review_digit_map_defaults_and_persists(tmp_path):
    from picture_capture.models import AppSettings

    settings = AppSettings()
    assert settings.review_digit_map == list("áéíóúãçñõü")
    settings.review_digit_map = ["à", "è", "ì", "ò", "ù", "ä", "ë", "ï", "ö", "ü"]
    path = tmp_path / "settings.json"
    settings.to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.review_digit_map == settings.review_digit_map


def test_v21116_review_ui_exposes_editable_digit_map_and_grouped_vowels():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'text="数字替换映射"' in review
    assert 'self.accent_panel_title = tk.StringVar(value="▸ 变音字符")' in review
    assert 'DIGIT_KEYS = "1234567890"' in review
    assert '("´", ("á", "é", "í", "ó", "ú"))' in review
    assert '("`", ("à", "è", "ì", "ò", "ù"))' in review
    assert '("^", ("â", "ê", "î", "ô", "û"))' in review
    assert '("¨", ("ä", "ë", "ï", "ö", "ü"))' in review
    assert '("¯", ("ā", "ē", "ī", "ō", "ū"))' in review
    assert "self.digit_map_vars" in review
    assert "settings.review_digit_map = values[:10]" in review


def test_v21116_digit_replacement_uses_editable_map_not_fixed_constant():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("    def on_key", text.index("class ReviewWindow"))
    end = text.index("    def _save_digit_map", start)
    body = text[start:end]
    assert "self.digit_map_vars[self.DIGIT_KEYS.index(char)].get()" in body
    assert "DIGIT_MAP" not in body


def test_v21117_review_layout_matches_compact_workflow():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'self._review_flat_button(row1, "保存", self.save, role="primary")' in review
    assert 'textvariable=self.autosave_label_var' in review
    assert 'text="数字替换映射"' in review
    assert 'text="排序规则"' in review
    assert 'text="词条排序规则"' not in review
    assert 'text="词条排序检查："' not in review
    assert 'text="当前页"' in review and 'text="所有页"' in review
    assert 'text="上\\n一\\n页"' in review and 'text="下\\n一\\n页"' in review
    assert 'text="词条切图显示大小："' in review
    assert 'right, "ocr", "OCR结果"' in review
    assert 'right, "reference", "参考词表"' in review
    assert 'text="选择文件"' in review
    assert 'text="从所选词开始填充至本页结束"' in review
    assert 'self.word_list.bind("<ButtonRelease-1>", self.use_selected_word)' in review
    assert 'self.digit_panel_title = tk.StringVar(value="▸ 数字替换映射")' in review
    assert 'self.accent_panel_title = tk.StringVar(value="▸ 变音字符")' in review


def test_review_toolbar_controls_are_grouped_by_function():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    build_start = review.index("    def _build(self) -> None:")
    build_end = review.index("    def _toggle_review_panel(", build_start)
    build = review[build_start:build_end]

    row1_start = build.index('row1 = ttk.Frame(controls')
    row1_end = build.index('ttk.Separator(controls, orient="horizontal")', row1_start)
    row1 = build[row1_start:row1_end]
    assert 'text="数字替换映射"' in row1
    assert row1.index('text="数字替换映射"') < row1.index('text="排序规则"')
    assert row1.index('text="排序规则"') < row1.index('text="当前页"')
    assert row1.index('text="当前页"') < row1.index('text="所有页"')
    assert row1.index('text="所有页"') < row1.index('text="排序检查"')
    assert 'row2 = ttk.Frame(controls' not in build
    assert 'text="文本左边距："' not in row1
    assert 'text="上下边距："' not in row1
    assert 'text="与OCR比较："' not in row1
    assert 'text="简体化词条"' not in row1
    assert 'text="重新简体化"' not in row1

    display_start = build.index('right, "display", "显示设置"')
    display_end = build.index('right, "ocr", "OCR结果"', display_start)
    display = build[display_start:display_end]
    assert display.index("zoom_row = ttk.Frame(") < display.index("padding_row = ttk.Frame(")
    assert display.index("padding_row = ttk.Frame(") < display.index("font_row = ttk.Frame(")
    assert 'text="文本左边距：", style="PCR.Black.TLabel"' in display
    assert 'text="上下边距：", style="PCR.Black.TLabel"' in display
    assert 'foreground="#000000" if self.parent.appearance_mode != "dark" else colors["text"]' in review

    ocr_start = build.index('right, "ocr", "OCR结果"')
    ocr_end = build.index('right, "network", "词条联网核验结果"', ocr_start)
    ocr = build[ocr_start:ocr_end]
    assert ocr.index("ocr_compare_row = ttk.Frame(") < ocr.index("ocr_row = ttk.Frame(")
    assert 'text="与OCR比较：", style="PCR.Body.TLabel"' in ocr
    assert 'text="简体化词条"' in ocr
    assert 'text="重新简体化"' in ocr
    assert ocr.index('text="简体化词条"') < ocr.index('text="重新简体化"')
    assert 'style="PCR.Body.TCheckbutton"' in ocr


def test_review_right_sections_are_collapsible_and_default_expanded():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'for key in ("display", "ocr", "network", "reference")' in review
    assert 'key: tk.BooleanVar(value=True)' in review
    for key, title in (
        ("display", "显示设置"),
        ("ocr", "OCR结果"),
        ("network", "词条联网核验结果"),
        ("reference", "参考词表"),
    ):
        assert f'right, "{key}", "{title}"' in review
    assert 'def _toggle_review_right_section(self, key: str) -> None:' in review
    assert 'title_var.set(("▾ " if expanded else "▸ ") + title)' in review
    assert "body.pack_forget()" in review


def test_review_modern_styles_are_scoped_and_preserve_dense_workflow():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]

    styles_start = review.index("    def _configure_review_styles(")
    styles_end = review.index("    def _review_flat_button(", styles_start)
    styles = review[styles_start:styles_end]
    assert "theme_use(" not in styles
    assert '"PCR.Surface.TFrame"' in styles
    assert '"PCR.Section.TLabelframe"' not in styles
    assert '"PCR.Compact.TButton"' in styles

    build_start = review.index("    def _build(self) -> None:")
    build_end = review.index("    def _toggle_review_panel(", build_start)
    build = review[build_start:build_end]
    assert 'panes.add(left, weight=3)' in build
    assert 'panes.add(right, weight=2)' in build
    assert 'text="上\\n一\\n页"' in build and 'text="下\\n一\\n页"' in build
    assert 'self._review_collapsible_section(' in build
    section_helper = review[
        review.index("    def _review_collapsible_section("):
        review.index("    def _build(self) -> None:")
    ]
    assert 'style="PCR.Header.TLabel"' in section_helper
    assert 'relief="sunken"' not in build
    assert 'relief="groove"' not in build

    render_start = review.index("    def render_rows(")
    render_end = review.index("    def _candidate_for_entry(", render_start)
    render = review[render_start:render_end]
    assert 'editor_bg = "#b3fddd" if entry.word in words else "#fce5e8"' in render
    assert 'relief="flat"' in render
    assert 'highlightthickness=1' in render
    assert 'text="[X]"' in render


def test_review_screenshot_polish_prevents_right_pane_clipping():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]

    section_start = review.index("    def _review_collapsible_section(")
    section_end = review.index("    def _build(self) -> None:", section_start)
    section = review[section_start:section_end]
    assert "ttk.LabelFrame(" not in section
    assert 'ttk.Separator(frame, orient="horizontal")' in section
    assert "body.pack_forget()" in section

    build_start = review.index("    def _build(self) -> None:")
    build_end = review.index("    def _toggle_review_panel(", build_start)
    build = review[build_start:build_end]
    assert "crop_height_row = ttk.Frame(" in build
    assert 'text="普通词条行切图高："' in build
    assert 'text="单字行高："' in build
    assert "ref_fill_row = ttk.Frame(" not in build
    assert 'ref_actions, text="从所选词开始填充至本页结束"' in build
    assert build.index('text="定位："') < build.index('ref_actions, text="从所选词开始填充至本页结束"')

    network_start = build.index("        network_actions = ttk.Frame(")
    network_end = build.index("        self.network_status_label", network_start)
    network = build[network_start:network_end]
    assert "width=15" not in network
    assert "width=14" not in network
    assert "width=8" not in network
    assert 'style="PCR.Tool.TButton"' in network


def test_v21117_review_title_contains_page_and_progress():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("    def _update_title", text.index("class ReviewWindow"))
    end = text.index("    def _close_review", start)
    body = text[start:end]
    assert '词条校对 — {page} — 当前: {current} 剩余: {remaining} 合计: {total}' in body


def test_v21117_reference_position_prefers_neighbor_anchors_over_current_word():
    from types import SimpleNamespace
    from picture_capture.app import ReviewWindow

    class V:
        def __init__(self, value): self.value = value
        def get(self): return self.value

    review = object.__new__(ReviewWindow)
    review.parent = SimpleNamespace(project=SimpleNamespace(words=[f"w{i}" for i in range(40)]), current_index=0)
    review.vars = [V("w10"), V("WRONG"), V("w12")]
    review.word_exact_indices = {f"w{i}": [i] for i in range(40)}
    review.sorted_word_keys = []
    review.sorted_word_indices = []
    review.word_window_indices = []
    review.word_highlight_index = None
    review._previous_reference_base_cache = None
    assert review._infer_reference_target(1, "w30") == 11


def test_v21117_reference_position_uses_previous_verified_neighbor_for_blank():
    from types import SimpleNamespace
    from picture_capture.app import ReviewWindow

    class V:
        def __init__(self, value): self.value = value
        def get(self): return self.value

    review = object.__new__(ReviewWindow)
    review.parent = SimpleNamespace(project=SimpleNamespace(words=[f"w{i}" for i in range(40)]), current_index=0)
    review.vars = [V("w20"), V(""), V("")]
    review.word_exact_indices = {f"w{i}": [i] for i in range(40)}
    review.sorted_word_keys = []
    review.sorted_word_indices = []
    review.word_window_indices = []
    review.word_highlight_index = None
    review._previous_reference_base_cache = None
    assert review._infer_reference_target(2, "") == 22


def test_v21117_review_autosave_reuses_main_autosave_variable_and_tick():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'variable=self.parent.autosave_var' in review
    assert 'self.parent.toggle_autosave()' in review
    tick_start = text.index("    def autosave_tick", text.index("class PictureCaptureApp"))
    tick_end = text.index("    def open_settings", tick_start)
    tick = text[tick_start:tick_end]
    assert 'review.autosave_commit()' in tick


def test_v21118_review_page_nav_buttons_use_darker_gray():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'review_nav_bg = "#d7d7d7"' in review
    assert 'review_nav_active_bg = "#c8c8c8"' in review
    assert 'bg=review_nav_bg, activebackground=review_nav_active_bg' in review


def test_v21118_review_page_change_resets_crop_text_scroll_to_top():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("    def _reset_rows_scroll_top", text.index("class ReviewWindow"))
    end = text.index("class OCRConflictReviewDialog", start)
    body = text[start:end]
    assert "self.canvas.yview_moveto(0.0)" in body
    assert "self.after_idle(reset_after_layout)" in body
    change_start = body.index("    def change_page")
    change = body[change_start:]
    assert "self._request_render_rows(focus_index=0, reset_scroll=True)" in change
    assert "self.render_rows(preloaded_crops=crops)" in change
    assert "self._reset_rows_scroll_top()" in change
    assert change.index("self.render_rows(preloaded_crops=crops)") < change.index("self._reset_rows_scroll_top()")


def test_v21119_review_text_similarity_normalizes_spacing_punctuation_and_case():
    from picture_capture.app import _review_text_similarity
    assert _review_text_similarity("Ab-c ", "Ａｂｃ") == 1.0
    assert _review_text_similarity("七味散", "七味散") == 1.0
    assert (_review_text_similarity("七味散", "七味敬") or 0) < 1.0
    assert _review_text_similarity("", "七味散") is None


def test_v21119_review_similarity_colors_have_semantic_bands():
    from picture_capture.app import _review_similarity_color
    assert _review_similarity_color(1.0) == "#b7e1cd"
    assert _review_similarity_color(0.90) == "#d9ead3"
    assert _review_similarity_color(0.70) == "#fff2cc"
    assert _review_similarity_color(0.50) == "#fce5cd"
    assert _review_similarity_color(0.10) == "#f4cccc"
    assert _review_similarity_color(None) == "#f2f2f2"


def test_v21119_review_left_padding_persists(tmp_path):
    from picture_capture.models import AppSettings
    settings = AppSettings()
    settings.review_entry_left_padding = 13
    path = tmp_path / "settings.json"
    settings.to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.review_entry_left_padding == 13


def test_v21119_review_ui_exposes_text_left_padding_and_live_ocr_similarity():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module
    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'text="文本左边距："' in review
    assert 'textvariable=self.review_left_padding_var' in review
    assert 'self._refresh_ocr_similarity_colors()' in review
    assert 'bg=bg, activebackground=bg' in review
    assert 'editor.pack_configure(padx=(padding, 0))' in review


def test_v21120_review_single_cjk_crop_expands_but_normal_word_does_not():
    from picture_capture.app import _review_line_box

    image = Image.new("RGB", (1000, 1400), "white")
    settings = AppSettings(
        parameter_display_width=1000, columns=1, column_width=600,
        character_height=40, row_padding=4, ocr_language="chi_tra",
    )
    geometry = Geometry([100], [600], 50, 1300, [ColumnPath([(50, 100), (1300, 100)])])

    single = Entry("字", 110, 100)
    normal = Entry("字典", 110, 100)
    single_box = _review_line_box(single, geometry, image, settings)
    normal_box = _review_line_box(normal, geometry, image, settings)

    assert normal_box[1] == normal.y - round(0.5 * settings.row_padding)
    assert single_box[3] > normal_box[3]
    assert single_box[0] == normal_box[0]
    assert single_box[2] == normal_box[2]
    assert single_box[3] - single_box[1] == 100 + 2 * settings.row_padding


def test_review_regular_crop_uses_half_spacing_top_and_full_spacing_height():
    from picture_capture.app import _effective_review_regular_crop_height, _review_line_box

    settings = AppSettings(
        parameter_display_width=600, columns=1, manual_x=20, column_width=500,
        character_height=32, row_padding=10, review_regular_crop_height=0,
    )
    assert _effective_review_regular_crop_height(settings) == 42
    image = Image.new("RGB", (600, 900), "white")
    geometry = derive_geometry(image, settings)
    box = _review_line_box(Entry("ordinary", 20, 100), geometry, image, settings)
    assert box[1] == 95
    assert box[3] - box[1] == 42
    settings.review_regular_crop_height = 51
    assert _effective_review_regular_crop_height(settings) == 51
    box = _review_line_box(Entry("ordinary", 20, 100), geometry, image, settings)
    assert box[3] - box[1] == 51


def test_sidebar_scroll_review_height_controls_and_normal_process_worker_are_wired():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert "self.sidebar_canvas = tk.Canvas(" in text
    assert 'orient="vertical", command=self.sidebar_canvas.yview' in text
    assert "def _sidebar_mousewheel(" in text
    assert "height=max(viewport_height, requested_height)" in text
    review_start = text.index("class ReviewWindow")
    review_end = text.index("class OCRConflictReviewDialog", review_start)
    review = text[review_start:review_end]
    assert 'text="行间空："' in review
    assert 'text="普通词条行切图高："' in review
    assert "self.review_regular_crop_height_var" in review
    detect_start = text.index("    def _detect_pages(")
    detect_end = text.index("    def clear_entries", detect_start)
    detect_block = text[detect_start:detect_end]
    assert 'ProcessPoolExecutor(max_workers=1' in detect_block
    assert 'if method == "left_edge" else None' in detect_block
    assert "detect_entries_job" in detect_block


def test_v21120_review_single_cjk_crop_no_longer_caps_at_next_marker():
    from picture_capture.app import _review_line_box

    image = Image.new("RGB", (1000, 1400), "white")
    settings = AppSettings(
        parameter_display_width=1000, columns=1, column_width=600,
        character_height=40, row_padding=4, ocr_language="chi_sim",
    )
    geometry = Geometry([100], [600], 50, 1300, [ColumnPath([(50, 100), (1300, 100)])])

    current = Entry("字", 110, 100)
    next_entry = Entry("下一", 110, 160)
    box = _review_line_box(current, geometry, image, settings, next_entry)

    # Explicit/fixed review height wins even when the next hand-drawn marker is
    # closer than that height; this prevents inconsistent marker Y from clipping.
    assert box[3] > next_entry.y
    assert box[3] - box[1] == 100 + 2 * settings.row_padding


def test_v21121_review_ocr_compare_setting_persists(tmp_path):
    from picture_capture.models import AppSettings
    settings = AppSettings()
    assert settings.review_ocr_compare_source == "fusion"
    settings.review_ocr_compare_source = "lens"
    path = tmp_path / "settings.json"
    settings.to_json(path)
    assert AppSettings.from_json(path).review_ocr_compare_source == "lens"


def test_v21121_review_ui_exposes_selectable_ocr_compare_after_check_and_arrow_navigation():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module
    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    check_pos = review.index('text="排序检查"')
    compare_pos = review.index('text="与OCR比较："')
    assert check_pos < compare_pos
    assert '"融合结果": "fusion"' in review
    assert '"PaddleOCR": "paddle"' in review
    assert '"Tesseract": "tesseract"' in review
    assert '"LENS": "lens"' in review
    assert 'editor.bind("<Up>"' in review
    assert 'editor.bind("<Down>"' in review
    assert 'self._scroll_editor_into_view(index)' in review


def test_v21121_review_ocr_compare_marks_only_real_mismatch_and_is_neutral_when_source_missing():
    from types import SimpleNamespace
    from picture_capture.app import ReviewWindow

    class Var:
        def __init__(self, value): self.value = value
        def get(self): return self.value
    class Frame:
        def __init__(self): self.values = {"bg": "#b3fddd", "highlightbackground": "#b3fddd"}
        def cget(self, key): return self.values[key]
        def configure(self, **kwargs): self.values.update(kwargs)

    review = object.__new__(ReviewWindow)
    review.review_ocr_compare_var = Var("PaddleOCR")
    review.vars = [Var("七味散"), Var("不同"), Var("无Lens") ]
    review.editor_frames = [Frame(), Frame(), Frame()]
    entries = [SimpleNamespace(candidate_id=str(i), x=i, y=i) for i in range(3)]
    candidates = [
        {"paddle": {"lemma": "七味散"}},
        {"paddle": {"lemma": "七味敬"}},
        {"lens": {"lemma": "无Lens"}},
    ]
    review.parent = SimpleNamespace(_ordered_entries_reading_order=lambda: entries)
    review._candidate_for_entry = lambda entry: candidates[int(entry.candidate_id)]
    review._refresh_editor_ocr_compare()
    assert review.editor_frames[0].values["highlightbackground"] == "#b3fddd"
    assert review.editor_frames[1].values["highlightbackground"] == "#d32f2f"
    assert review.editor_frames[2].values["highlightbackground"] == "#b3fddd"


def test_v21121_candidate_choice_rows_include_lens_when_present():
    from picture_capture.app import _candidate_choice_rows
    rows = _candidate_choice_rows({
        "paddle": {"lemma": "a", "confidence": 0.8},
        "tesseract": {"lemma": "b", "confidence": 0.7},
        "lens": {"lemma": "c", "confidence": 0.9},
        "word": "c",
        "final_engine": "lens",
    })
    assert any(engine == "lens" and word == "c" for engine, _label, word, _conf, _final in rows)


def test_v21122_review_vertical_padding_persists(tmp_path):
    from picture_capture.models import AppSettings
    settings = AppSettings()
    assert settings.review_entry_vertical_padding == 3
    settings.review_entry_vertical_padding = 7
    path = tmp_path / "settings.json"
    settings.to_json(path)
    assert AppSettings.from_json(path).review_entry_vertical_padding == 7


def test_v21122_review_ui_exposes_vertical_safety_padding_and_applies_ipady():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module
    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'self.review_vertical_padding_var = tk.StringVar(' in review
    assert 'self._review_vertical_padding_apply_job: str | None = None' in review
    assert 'text="上下边距："' in review
    assert 'textvariable=self.review_vertical_padding_var' in review
    assert 'ipady=max(0, int(self.parent.settings.review_entry_vertical_padding))' in review
    assert 'editor.pack_configure(ipady=padding)' in review


def test_v21122_hotfix2_chinese_single_cjk_height_defaults_to_2_5x_and_can_override():
    from picture_capture.app import _effective_review_single_cjk_line_height

    settings = AppSettings(character_height=32, ocr_language="chi_tra", review_single_cjk_line_height=0)
    assert _effective_review_single_cjk_line_height(settings) == 80
    settings.review_single_cjk_line_height = 73
    assert _effective_review_single_cjk_line_height(settings) == 73


def test_v21122_hotfix2_review_height_and_main_ocr_preferences_persist(tmp_path):
    settings = AppSettings(
        review_single_cjk_line_height=71,
        review_main_show_ocr_choices=True,
        review_main_show_ocr_background=True,
    )
    path = tmp_path / "settings.json"
    settings.to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.review_single_cjk_line_height == 71
    assert reopened.review_main_show_ocr_choices is True
    assert reopened.review_main_show_ocr_background is True


def test_v21122_hotfix2_review_ui_exposes_shared_and_single_height_plus_main_ocr_switches():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'text="单行高："' in review
    assert 'textvariable=self.review_line_height_var' in review
    assert 'text="单字行高："' in review
    assert 'textvariable=self.review_single_cjk_line_height_var' in review
    assert 'text="显示 OCR 内容选择"' not in review
    assert 'text="显示 OCR 底色"' not in review
    assert 'self.settings.review_main_show_ocr_choices = False' in text
    assert 'self.settings.review_main_show_ocr_background = False' in text
    assert 'self.parent.settings.character_height = line_height' in review
    assert 'self.parent.settings.review_single_cjk_line_height = line_height' in review


def test_v21122_hotfix2_main_canvas_ocr_aids_follow_their_switches():
    from picture_capture.app import PictureCaptureApp

    app = object.__new__(PictureCaptureApp)
    app.settings = AppSettings()
    app.review_window = None
    assert app._main_ocr_review_option_enabled("review_main_show_ocr_choices") is False
    assert app._main_ocr_review_option_enabled("review_main_show_ocr_background") is False
    app.settings.review_main_show_ocr_choices = True
    app.settings.review_main_show_ocr_background = True
    assert app._main_ocr_review_option_enabled("review_main_show_ocr_choices") is True
    assert app._main_ocr_review_option_enabled("review_main_show_ocr_background") is True


def test_main_ocr_visibility_controls_apply_immediately_and_candidate_boxes_are_source_agnostic():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    assert 'command=lambda n=name, v=var: self._apply_overlay_visibility_toggle(n, v)' in text
    assert '"paddle_show_candidate_checkboxes", candidate_var' in text
    start = text.index("            show_candidates = (")
    end = text.index("        show_shapes =", start)
    candidate_block = text[start:end]
    assert "if show_candidates:" in candidate_block
    assert 'self.settings.detection_method == "paddleocr"' not in candidate_block


def test_v21122_hotfix3_page_word_text_and_diff_classify_add_delete_modify():
    from picture_capture.app import _page_word_mapping_text, _compare_page_word_mappings

    pages = ["0001", "0002"]
    old = {"0001": ["甲", "乙", "丁"], "0002": ["A", "B"]}
    new = {"0001": ["甲", "乙改", "丙", "丁"], "0002": ["B"]}

    text = _page_word_mapping_text(pages, new)
    assert text == "0001\t甲\n0001\t乙改\n0001\t丙\n0001\t丁\n0002\tB\n"

    changes, counts = _compare_page_word_mappings(pages, old, new)
    assert counts == {"新增": 1, "删除": 1, "修改": 1, "old_rows": 5, "new_rows": 5}
    assert [(row["kind"], row["page"], row["old"], row["new"]) for row in changes] == [
        ("修改", "0001", "乙", "乙改"),
        ("新增", "0001", "", "丙"),
        ("删除", "0002", "A", ""),
    ]


def test_v21122_hotfix3_main_actions_put_compare_before_review():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    row = '(("清除画线", self.clear_entries), ("清除文本", self.clear_text), ("精修画线", self.refine_lines_selected_scope), ("新旧比较", self.compare_old_new_selected_scope), ("词条校对", self.open_review))'
    assert row in text
    assert "class OldNewComparisonWindow" in text
    assert 'notebook.add(diff_tab, text="差异")' in text
    assert 'self._add_text_tab(notebook, "当前 PDIC 合集"' in text
    assert 'self._add_text_tab(notebook, "旧 wordslist 片段"' in text


def test_v21122_hotfix3_compare_uses_selected_scope_and_page_aware_wordslist():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("    def compare_old_new_selected_scope(")
    end = text.index("\n    def open_review", start)
    block = text[start:end]
    assert "indices = self.selected_page_indices()" in block
    assert "_parse_words_of_pages_text" in block
    assert "read_pdic(pdic_path(page))" in block
    assert '"new_text": _page_word_mapping_text(selected_stems, new_mapping)' in block
    assert '"old_text": _page_word_mapping_text(selected_stems, old_mapping)' in block
    assert "_compare_page_word_mappings(selected_stems, old_mapping, new_mapping)" in block


def test_v21122_hotfix5_review_rows_expose_x_delete_and_grave_shortcut():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'text="[X]"' in review
    assert 'command=lambda i=index: self.delete_review_entry(i)' in review
    assert 'editor.bind("<KeyPress-grave>", lambda _e, i=index: self.delete_review_entry(i))' in review
    assert "def delete_review_entry(self, index: int) -> str:" in review
    assert "self.parent.save_pdic(silent=True, sync_editors=False)" in review
    assert "self.parent.redraw()" in review


def test_v21122_hotfix5_review_delete_commits_text_removes_shared_entry_and_deselects_candidate():
    from types import SimpleNamespace
    from picture_capture.app import ReviewWindow
    from picture_capture.models import Entry

    class Var:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value

    class Status:
        def __init__(self):
            self.value = ""
        def set(self, value):
            self.value = value

    first = Entry("甲", 10, 20, candidate_id="c1")
    second = Entry("乙", 10, 40)
    candidate = {"candidate_id": "c1", "word": "甲", "selected": True}
    calls = {"saved": [], "redraw": 0, "override": []}

    parent = SimpleNamespace()
    parent.entries = [first, second]
    parent.candidate_check_vars = {}
    parent.status_var = Status()
    parent._ordered_entries_reading_order = lambda: list(parent.entries)
    parent._claim_page_for_manual_edit = lambda: True
    parent.get_review_candidate = lambda cid: candidate if cid == "c1" else None
    parent._write_manual_override = lambda cand, **kw: calls["override"].append((cand, kw))
    parent._sort_entries_reading_order = lambda: None
    parent.clear_review_entry_highlight = lambda: None
    parent.save_pdic = lambda **kw: calls["saved"].append(kw)
    parent.redraw = lambda: calls.__setitem__("redraw", calls["redraw"] + 1)

    review = object.__new__(ReviewWindow)
    review.parent = parent
    review.vars = [Var("甲改"), Var("乙改")]
    review.editors = []
    review.active_index = 0
    review.render_rows = lambda: setattr(review, "editors", [])
    review._show_ocr_options = lambda _candidate: None
    review._update_title = lambda: None

    result = ReviewWindow.delete_review_entry(review, 0)

    assert result == "break"
    assert parent.entries == [second]
    # All visible proofreading text is committed by identity before deletion.
    assert second.word == "乙改"
    assert candidate["selected"] is False
    assert calls["override"] and calls["override"][0][1]["selected"] is False
    assert calls["saved"] == [{"silent": True, "sync_editors": False}]
    assert calls["redraw"] == 1
    assert "已删除词条" in parent.status_var.value



def test_v212_new_project_centralizes_program_data_under_picturecapture(tmp_path):
    from picture_capture.formats import pdic_path, write_pdic, write_ppp
    from picture_capture.models import Entry, PolygonRegion, ProjectState
    from picture_capture.project_storage import (
        is_managed_project, ppp_write_path_for_image, qt_root, settings_path, storage_root,
    )

    page = tmp_path / "0001.png"
    Image.new("RGB", (100, 120), "white").save(page)
    project = ProjectState.open(tmp_path)

    assert project.images == [page]
    assert is_managed_project(tmp_path)
    managed = storage_root(tmp_path)
    assert managed == tmp_path / "_PictureCapture"
    assert (managed / "project.json").is_file()
    assert qt_root(tmp_path) == managed / "QT"

    project.settings.to_json(settings_path(tmp_path))
    assert settings_path(tmp_path) == managed / "settings.json"
    assert not (tmp_path / "picture_capture_settings.json").exists()

    pdic = pdic_path(page)
    ppp = ppp_write_path_for_image(page)
    write_pdic(pdic, [Entry("alpha", 10, 20)], 100, ("0001", "@", "@"))
    write_ppp(ppp, [PolygonRegion("pic", [(1, 1), (5, 1), (5, 5), (1, 5)])], "0001")
    assert pdic == managed / "data" / "PDIC" / "0001.pdic"
    assert ppp == managed / "data" / "PPP" / "0001.ppp"
    assert pdic.is_file() and ppp.is_file()
    assert not page.with_suffix(".pdic").exists()
    assert not page.with_suffix(".ppp").exists()

    # The scan root stays user-owned: the image plus one managed software folder.
    assert {p.name for p in tmp_path.iterdir()} == {"0001.png", "_PictureCapture"}


def test_v212_legacy_project_open_remains_non_destructive_until_migration(tmp_path):
    from picture_capture.models import AppSettings, ProjectState
    from picture_capture.project_storage import is_managed_project

    Image.new("RGB", (80, 80), "white").save(tmp_path / "0001.png")
    AppSettings(columns=3).to_json(tmp_path / "picture_capture_settings.json")
    (tmp_path / "0001.pdic").write_text("word#1#2#1.25#2.5#0001#@#@\n", encoding="utf-8")

    project = ProjectState.open(tmp_path)
    assert project.settings.columns == 3
    assert not is_managed_project(tmp_path)
    assert not (tmp_path / "_PictureCapture").exists()
    assert (tmp_path / "0001.pdic").is_file()


def test_v212_migration_moves_program_owned_files_and_preserves_user_files(tmp_path):
    from picture_capture.formats import pdic_path, read_pdic
    from picture_capture.models import AppSettings, ProjectState
    from picture_capture.project_storage import (
        is_managed_project, migrate_legacy_project, ocr_cache_root, profile_path,
        qt_root, replace_rules_path, settings_path, storage_root,
    )

    page = tmp_path / "0001.png"
    Image.new("RGB", (100, 100), "white").save(page)
    (tmp_path / "wordslist.txt").write_text("alpha\n", encoding="utf-8")
    AppSettings(columns=4).to_json(tmp_path / "picture_capture_settings.json")
    (tmp_path / "dictionary_profile.json").write_text('{"format":"dictionary-profile-v2","preset":"latin_structured_symbols","language":"eng","overrides":{"settings":{},"grammar":{}}}', encoding="utf-8")
    (tmp_path / "_Replace.txt").write_text("a=b\n", encoding="utf-8")
    (tmp_path / "headword_filter_rules.txt").write_text("# rules\n", encoding="utf-8")
    (tmp_path / "0001.pdic").write_text("alpha#10#20#10#20#0001#@#@\n", encoding="utf-8")
    (tmp_path / "0001.ppp").write_text("1\tpic\t|1,1|5,1|5,5|1,5\n", encoding="utf-8")
    (tmp_path / "QT" / "PaddleOCR").mkdir(parents=True)
    (tmp_path / "QT" / "PaddleOCR" / "0001.json").write_text("{}", encoding="utf-8")
    (tmp_path / "PicDic_index_20260920_120000.txt").write_text("x\n", encoding="utf-8")

    report = migrate_legacy_project(tmp_path, "2.12.0")
    assert report.files_copied >= 7
    assert is_managed_project(tmp_path)
    managed = storage_root(tmp_path)
    assert settings_path(tmp_path) == managed / "settings.json"
    assert settings_path(tmp_path).is_file()
    assert profile_path(tmp_path).is_file()
    assert replace_rules_path(tmp_path).is_file()
    assert (ocr_cache_root(tmp_path) / "0001.json").is_file()
    assert (managed / "output" / "exports" / "PicDic_index_20260920_120000.txt").is_file()

    # User-owned source material stays in place.
    assert page.is_file()
    assert (tmp_path / "wordslist.txt").is_file()
    # Old software-owned locations are cleaned only after verified copy.
    assert not (tmp_path / "picture_capture_settings.json").exists()
    assert not (tmp_path / "0001.pdic").exists()
    assert not (tmp_path / "0001.ppp").exists()
    assert not (tmp_path / "QT").exists()

    project = ProjectState.open(tmp_path)
    assert project.settings.columns == 4
    assert [entry.word for entry in read_pdic(pdic_path(page))] == ["alpha"]
    assert qt_root(tmp_path) == managed / "QT"


def test_v212_empty_folder_is_not_polluted_when_opened_as_project(tmp_path):
    from picture_capture.models import ProjectState

    project = ProjectState.open(tmp_path)
    assert project.images == []
    assert not (tmp_path / "_PictureCapture").exists()


def test_ppocrv6_version_gate():
    from picture_capture.app import PictureCaptureApp
    assert PictureCaptureApp._version_at_least("3.7.0", (3, 7))
    assert PictureCaptureApp._version_at_least("3.7.1rc1", (3, 7))
    assert not PictureCaptureApp._version_at_least("3.6.9", (3, 7))
    assert not PictureCaptureApp._version_at_least(None, (3, 7))


def test_v2130_uv_paddle_cpu_extra_is_declared_in_one_place():
    project_root = Path(__file__).resolve().parents[1]
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'paddleocr = ["paddleocr>=3.7,<4", "paddlepaddle==3.3.0"]' in pyproject
    assert 'name = "paddle-cpu"' in pyproject
    assert 'paddlepaddle = { index = "paddle-cpu" }' in pyproject
    assert not (project_root / "requirements-paddleocr.txt").exists()


def test_v2122_cjk_auto_wordslist_uses_external_sorted_locator():
    from types import SimpleNamespace
    from picture_capture.app import ReviewWindow
    from picture_capture.models import AppSettings

    review = object.__new__(ReviewWindow)
    review.parent = SimpleNamespace(settings=AppSettings(ocr_language="chi_sim", wordslist_locator_mode="auto"))
    assert review._effective_wordslist_locator_mode() == "sorted"
    review.parent.settings.wordslist_locator_mode = "sequential"
    assert review._effective_wordslist_locator_mode() == "sequential"


def test_v2122_external_sorted_wordslist_does_not_assume_one_to_one_offsets(monkeypatch):
    from types import SimpleNamespace
    import picture_capture.app as app_module
    from picture_capture.app import ReviewWindow
    from picture_capture.models import AppSettings

    class V:
        def __init__(self, value): self.value = value
        def get(self): return self.value

    order = {"阿": "a", "八": "ba", "白": "bai", "班": "ban", "才": "cai"}
    monkeypatch.setattr(app_module, "reference_sort_key", lambda word: (order.get(word, word), word))
    words = ["阿", "八", "白", "才"]
    review = object.__new__(ReviewWindow)
    review.parent = SimpleNamespace(
        project=SimpleNamespace(words=words), current_index=0,
        settings=AppSettings(ocr_language="chi_sim", wordslist_locator_mode="sorted"),
    )
    review.vars = [V("八"), V("班"), V("才")]
    review.word_exact_indices = {word.casefold(): [i] for i, word in enumerate(words)}
    review.word_window_indices = []
    review.word_highlight_index = None
    review.word_sort_key_cache = {}
    review._previous_reference_base_cache = None
    assert review._infer_reference_target(1, "班") == 3


def test_v2122_free_network_lookup_sources_parse_exact_hits(monkeypatch):
    import picture_capture.network_lookup as lookup

    def fake_read_json(url, timeout):
        if "moedict.tw" in url:
            return {"title": "校對"}
        return {"query": {"pages": [{"pageid": 123, "title": "校對"}]}}

    monkeypatch.setattr(lookup, "_read_json", fake_read_json)
    result = lookup.lookup_word_free("校對")
    assert result.found is True
    assert {item.name for item in result.sources if item.found} == {"萌典", "维基词典"}


def test_v2122_review_ui_has_free_network_check_and_locator_mode():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert "词条联网核验结果" in review
    assert 'right, "network", "网络词汇核验（免费，无需 Token）"' not in review
    assert "外部索引（拼音/字母）" in review
    assert "同源连续词表" in review
    assert "def _schedule_network_lookup" in review
    assert "def _infer_sorted_reference_target" in review


def test_v2123_review_simplified_setting_persists(tmp_path):
    from picture_capture.models import AppSettings
    settings = AppSettings()
    assert settings.review_show_simplified is False
    settings.review_show_simplified = True
    path = tmp_path / "settings.json"
    settings.to_json(path)
    assert AppSettings.from_json(path).review_show_simplified is True


def test_v2123_review_ui_renames_sort_controls_and_adds_simplified_controls_after_ocr_compare():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'text="排序规则"' in review
    assert 'text="词条排序规则"' not in review
    assert 'text="词条排序检查："' not in review
    assert 'text="排序检查"' in review
    compare_pos = review.index('text="与OCR比较："')
    simplify_pos = review.index('text="简体化词条"')
    regenerate_pos = review.index('text="重新简体化"')
    assert compare_pos < simplify_pos < regenerate_pos
    assert 'variable=self.review_show_simplified_var' in review
    assert 'command=self._toggle_review_simplified' in review
    assert 'command=self.regenerate_simplified_current_page' in review


def test_v2123_review_simplified_rows_use_equal_columns_and_expand_original_when_hidden():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("    def render_rows", text.index("class ReviewWindow"))
    end = text.index("    def _candidate_for_entry", start)
    body = text[start:end]
    assert 'simplified_var = tk.StringVar(' in body
    assert 'columnconfigure(1, weight=1, uniform=f"review_pair_{index}")' in body
    assert 'columnconfigure(2, weight=1, uniform=f"review_pair_{index}")' in body
    assert 'simplified_editor.grid_remove()' in body
    assert 'editor_frame.grid(row=index * 2 + 1, column=0, sticky="ew"' in body


def test_v2123_simplified_display_uses_check_mark_when_unchanged(monkeypatch):
    import picture_capture.chinese_simplify as mod

    class FakeConverter:
        def convert(self, text):
            return {"校對": "校对", "校对": "校对"}.get(text, text)

    monkeypatch.setattr(mod, "_get_converter", lambda: FakeConverter())
    assert mod.simplified_display("校對") == "校对"
    assert mod.simplified_display("校对") == "√"
    assert mod.simplified_display("opencc") == "√"


def test_v2124_simplified_sidecar_roundtrip(tmp_path):
    from picture_capture.simplified_review import read_records, write_records

    path = tmp_path / "0001.json"
    records = {
        "10,20": {"x": 10, "y": 20, "source_word": "詞條", "text": "词条", "manual": True},
        "10,40": {"x": 10, "y": 40, "source_word": "电脑", "text": "电脑", "manual": False},
    }
    write_records(path, "0001", records)
    loaded = read_records(path)
    assert loaded["10,20"]["text"] == "词条"
    assert loaded["10,20"]["manual"] is True
    assert loaded["10,40"]["text"] == "电脑"


def test_v2124_managed_storage_has_simplified_sidecar_root(tmp_path):
    from picture_capture.project_storage import ensure_project_storage, simplified_review_path_for_image

    page = tmp_path / "0001.png"
    page.write_bytes(b"x")
    ensure_project_storage(tmp_path, "2.12.4")
    path = simplified_review_path_for_image(page)
    assert path == tmp_path / "_PictureCapture" / "data" / "Simplified" / "0001.json"
    assert path.parent.is_dir()


def test_v2124_review_simplified_is_editable_saved_and_has_network_button():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'state="readonly"' not in review[review.index('simplified_editor = tk.Entry'):review.index('simplified_editor.grid', review.index('simplified_editor = tk.Entry'))]
    assert 'text="网查"' in review
    assert 'command=lambda i=index: self.lookup_simplified_online(i)' in review
    assert 'def _persist_simplified_page' in review
    assert 'write_simplified_records(' in review
    assert 'def on_simplified_key' in review


def test_v2124_simplified_manual_edit_is_not_overwritten_by_original_refresh():
    from types import SimpleNamespace
    from picture_capture.app import ReviewWindow

    class Var:
        def __init__(self, value): self.value = value
        def get(self): return self.value
        def set(self, value): self.value = value

    review = object.__new__(ReviewWindow)
    review.vars = [Var("詞條改")]
    review.simplified_vars = [Var("人工简化")]
    review.simplified_actual_values = ["人工简化"]
    review.simplified_manual_flags = [True]
    review._rendered_page_stem = ""
    review.parent = SimpleNamespace(_ordered_entries_reading_order=lambda: [])
    ReviewWindow._refresh_simplified_for_index(review, 0)
    assert review.simplified_vars[0].get() == "人工简化"


def test_v2125_main_delete_path_removes_aligned_simplified_record():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("    def _delete_aligned_simplified_entry")
    end = text.index("    def auto_detect_current", start)
    body = text[start:end]
    assert "simplified_entry_key(entry.x, entry.y)" in body
    assert "read_simplified_records(path)" in body
    assert "write_simplified_records(path, stem, records)" in body
    assert "self._delete_aligned_simplified_entry(entry)" in body
    assert "review.render_rows()" in body


def test_v2125_automatic_simplified_value_is_materialized_for_persistence():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("    def render_rows(self, preloaded_crops")
    end = text.index("    def _candidate_for_entry", start)
    body = text[start:end]
    assert "materialized_record = {" in body
    assert '"text": "" if simplified_actual is None else str(simplified_actual)' in body
    assert "if saved_simplified is None:" in body
    assert "self._simplified_dirty_pages.add(current_stem)" in body


def test_v2125_delete_aligned_simplified_entry_functionally_removes_sidecar(tmp_path):
    from types import SimpleNamespace
    from picture_capture.app import PictureCaptureApp
    from picture_capture.project_storage import simplified_review_path_for_image
    from picture_capture.simplified_review import read_records, write_records

    page = tmp_path / "0001.png"
    page.write_bytes(b"x")
    path = simplified_review_path_for_image(page)
    write_records(path, "0001", {
        "10,20": {"x": 10, "y": 20, "source_word": "詞條", "text": "词条", "manual": False},
        "10,40": {"x": 10, "y": 40, "source_word": "校對", "text": "校对", "manual": True},
    })
    app = object.__new__(PictureCaptureApp)
    app.current_page = page
    app.review_window = None
    PictureCaptureApp._delete_aligned_simplified_entry(app, SimpleNamespace(x=10, y=20))
    records = read_records(path)
    assert "10,20" not in records
    assert records["10,40"]["text"] == "校对"


def test_v2130_uses_official_opencc_dependency_only_under_uv():
    from pathlib import Path
    import inspect
    import picture_capture

    project_root = Path(inspect.getsourcefile(picture_capture)).resolve().parents[2]
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    lock = (project_root / "uv.lock").read_text(encoding="utf-8")
    assert '"opencc>=1.4.2,<2"' in pyproject
    assert "opencc-python-reimplemented" not in pyproject
    assert 'name = "opencc"' in lock
    assert not (project_root / "requirements.txt").exists()


def test_v2126_opencc_converter_uses_official_t2s_json(monkeypatch):
    import sys
    from types import SimpleNamespace
    import picture_capture.chinese_simplify as mod

    seen = []

    class FakeConverter:
        def convert(self, text):
            return text

    def make_converter(config):
        seen.append(config)
        return FakeConverter()

    monkeypatch.setitem(sys.modules, "opencc", SimpleNamespace(OpenCC=make_converter))
    monkeypatch.setattr(mod, "_converter", None)
    monkeypatch.setattr(mod, "_converter_error", None)
    converter = mod._get_converter()
    assert converter is not None
    assert seen == ["t2s.json"]


def test_v2133_redraw_parameter_scale_is_bound_after_coordinate_refactor():
    import picture_capture.app as app_module
    import picture_capture.processing as processing_module
    from picture_capture.models import AppSettings

    image = Image.new("RGB", (1200, 1600), "white")
    settings = AppSettings(
        geometry_coordinate_version=2,
        geometry_coordinate_space="canonical_reference_page_pixels",
        geometry_reference_width=1200,
    )
    assert app_module.parameter_scale is processing_module.parameter_scale
    assert app_module.parameter_scale(image, settings) == 1.0


def test_v2133_windows_launcher_is_runtime_only_and_never_installs():
    from pathlib import Path
    import inspect
    import picture_capture

    project_root = Path(inspect.getsourcefile(picture_capture)).resolve().parents[2]
    bat = (project_root / "run_windows.bat").read_text(encoding="utf-8")
    folded = bat.casefold()
    assert '".venv\\Scripts\\python.exe" "run.py"' in bat
    assert "install_ocr_windows.bat" in bat
    assert 'pushd "%~dp0"' in bat
    assert "popd" in bat
    for suspicious in (
        "uv ", "pip ", "powershell", "curl ", "wget ", "certutil", "bitsadmin",
        "invoke-webrequest", "http://", "https://", "pythonw.exe", "start ",
        "set /p", "create_no_window", ".picture_capture_ocr_extra",
    ):
        assert suspicious not in folded
    assert (project_root / ".python-version").read_text(encoding="utf-8").strip() == "3.13"
    assert not (project_root / "requirements.txt").exists()


def test_environment_center_reports_opencc_and_actionable_components():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module
    import picture_capture.environment_center as center_module

    app_text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    center_text = Path(inspect.getsourcefile(center_module)).read_text(encoding="utf-8")
    assert "EnvironmentCenterWindow" in app_text
    assert "show_environment_center" in app_text
    assert '"环境中心"' in app_text
    assert 'self.app._distribution_version("opencc")' in center_text
    assert 'self.app._distribution_version("opencc-python-reimplemented")' in center_text
    assert "简化配置：t2s.json（词组优先）" in center_text
    for label in ("PaddleOCR / PaddlePaddle", "Google Lens", "Tesseract", "OpenCC", "CC-CEDICT", "网络词典"):
        assert label in center_text


def test_v2128_cc_cedict_local_install_and_lookup(tmp_path, monkeypatch):
    import zipfile
    import picture_capture.cc_cedict as cedict

    monkeypatch.setattr(cedict, "user_data_root", lambda: tmp_path / "local" / "PictureCapture")
    monkeypatch.setattr(cedict, "legacy_user_data_roots", lambda: ())
    cedict.clear_cache()
    source = tmp_path / "cedict.zip"
    lines = ["# synthetic test"]
    # Installer intentionally rejects tiny/non-dictionary files, so provide a
    # compact but valid synthetic database above the safety threshold.
    for i in range(1001):
        lines.append(f"測試{i} 测试{i} [ce4 shi4] /test/")
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("cedict_ts.u8", "\n".join(lines) + "\n")

    state = cedict.install_from_file(source)
    assert state.installed is True
    assert state.entry_count == 1001
    assert cedict.lookup("測試8").found is True
    assert cedict.lookup("测试8").found is True
    assert cedict.lookup("不存在词").found is False
    assert state.path.parent == tmp_path / "local" / "PictureCapture" / "dictionaries" / "cc-cedict"


def test_review_network_status_uses_single_line_result_block():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'value="网络词汇核验：等待选择词条"' in review
    assert '"✓ 有词典收录：" + "、".join(found_names)' in review
    assert '"○ 各可用词典均未检出精确词条（不代表该词不存在）"' in review
    assert '"⚠ 部分词典未安装或网络来源暂不可用；可继续网络搜索。"' in review
    assert '"⚠ 网络词汇核验暂时失败；可点“网络搜索”手工确认。"' in review

    label_start = review.index("        self.network_status_label = tk.Label(")
    label_end = review.index("        self._refresh_cc_cedict_button_idle()", label_start)
    network_label = review[label_start:label_end]
    assert "height=2" not in network_label
    assert "wraplength=" not in network_label

    assert "self.wordslist_label_var" not in review
    assert 'self.word_window_var = tk.StringVar(value="词表（wordslist.txt） | 显示 0-0 / 0")' in review
    assert 'f"词表（{path.name}） | 显示 {start + 1}-{end} / {len(words)}"' in review
    assert "右侧仅显示当前词附近" not in review


def test_v2128_review_network_toolbar_has_compact_source_badges():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'text="自动检查"' in review
    assert 'text="立即"' in review
    assert 'value="CC-CEDICT(?)"' in review
    assert 'value="萌(?)"' in review
    assert 'value="Wiki(?)"' in review
    assert 'text="网络搜索"' in review
    assert "network_actions_more = ttk.Frame(network_box" in review
    assert "network_actions_more, textvariable=self.moedict_lookup_var" in review
    assert "network_actions_more, textvariable=self.wiktionary_lookup_var" in review
    assert 'network_actions_more, text="网络搜索"' in review
    assert "def manage_cc_cedict" in review
    assert "install_cc_cedict_from_file(source)" in review


def test_v2129_review_window_has_independent_simplified_font_controls():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    body = text[start:text.index("class ", start + 20) if "class " in text[start + 20:] else len(text)]
    assert 'text="词条字体："' in body
    assert 'text="简体字体："' in body
    assert 'self.review_simplified_font_family_var' in body
    assert 'self.review_simplified_font_size_var' in body
    assert 'self.review_simplified_font_bold_var' in body
    assert 'self.review_simplified_font_italic_var' in body
    assert 'settings.review_simplified_font_family = family' in body
    assert 'settings.review_simplified_font_size = size' in body


def test_v2129_existing_project_inherits_headword_font_for_simplified(tmp_path):
    import json
    from picture_capture.models import AppSettings

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "review_entry_font_family": "Microsoft YaHei",
        "review_entry_font_size": 23,
        "review_entry_font_bold": True,
        "review_entry_font_italic": True,
        "review_font_semantics_version": 2,
    }), encoding="utf-8")
    settings = AppSettings.from_json(path)
    assert settings.review_simplified_font_family == "Microsoft YaHei"
    assert settings.review_simplified_font_size == 23
    assert settings.review_simplified_font_bold is True
    assert settings.review_simplified_font_italic is True


def test_v2129_simplified_font_persists_independently(tmp_path):
    from picture_capture.models import AppSettings

    settings = AppSettings(
        review_entry_font_family="Cambria",
        review_entry_font_size=18,
        review_simplified_font_family="Microsoft YaHei",
        review_simplified_font_size=21,
        review_simplified_font_bold=True,
        review_simplified_font_italic=False,
    )
    path = tmp_path / "settings.json"
    settings.to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.review_entry_font_family == "Cambria"
    assert reopened.review_entry_font_size == 18
    assert reopened.review_simplified_font_family == "Microsoft YaHei"
    assert reopened.review_simplified_font_size == 21
    assert reopened.review_simplified_font_bold is True
    assert reopened.review_simplified_font_italic is False


def test_v2129_ocr_results_are_compact_single_row():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'right, "ocr", "OCR结果"' in review
    assert 'slots = (("P", "paddle"), ("T", "tesseract"), ("L", "lens"), ("融", "fusion"))' in review
    assert 'grid(row=0, column=slot_index' in review
    assert 'text="当前OCR结果"' not in review


def test_v21210_cc_cedict_exposes_traditional_to_simplified_candidates(tmp_path, monkeypatch):
    import picture_capture.cc_cedict as cedict

    monkeypatch.setattr(cedict, "user_data_root", lambda: tmp_path / "local" / "PictureCapture")
    monkeypatch.setattr(cedict, "legacy_user_data_roots", lambda: ())
    root = cedict.data_root()
    root.mkdir(parents=True, exist_ok=True)
    cedict.data_path().write_text(
        "# synthetic mapping test\n"
        "詞彙 词汇 [ci2 hui4] /vocabulary/\n"
        "異體 异体 [yi4 ti3] /variant/\n"
        "異體 异體 [yi4 ti3] /alternate synthetic mapping/\n",
        encoding="utf-8",
    )
    cedict.clear_cache()

    mapped = cedict.simplified_candidates("詞彙")
    assert mapped.found is True
    assert mapped.matched_as == "traditional"
    assert mapped.candidates == ("词汇",)

    already_simplified = cedict.simplified_candidates("词汇")
    assert already_simplified.found is True
    assert already_simplified.matched_as == "simplified"
    assert already_simplified.candidates == ("词汇",)

    multiple = cedict.simplified_candidates("異體")
    assert set(multiple.candidates) == {"异体", "异體"}

    missing = cedict.simplified_candidates("不存在词")
    assert missing.found is False
    assert missing.candidates == tuple()


def test_v21210_review_toolbar_has_cc_simplified_comparison():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert 'value="CC简(?)"' in review
    assert 'textvariable=self.cc_simplified_compare_var' in review
    assert 'command=self.show_cc_simplified_comparison' in review
    assert 'def _cc_simplified_comparison_details' in review
    assert 'cc_cedict_simplified_candidates(original)' in review
    assert 'opencc_value = simplify_text(original)' in review


def test_v21210_cc_simplified_comparison_detects_match_and_mismatch(monkeypatch):
    from types import SimpleNamespace
    import picture_capture.app as app_module

    class Var:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value

    review = app_module.ReviewWindow.__new__(app_module.ReviewWindow)
    review.active_index = 0
    review.vars = [Var("詞彙")]
    review.simplified_vars = [Var("词汇")]
    review.simplified_actual_values = ["词汇"]
    review.simplified_manual_flags = [False]

    monkeypatch.setattr(app_module, "simplify_text", lambda _word: "词汇")
    monkeypatch.setattr(
        app_module,
        "cc_cedict_simplified_candidates",
        lambda _word: SimpleNamespace(
            found=True, candidates=("词汇",), matched_as="traditional", detail="test"
        ),
    )
    info = app_module.ReviewWindow._cc_simplified_comparison_details(review, 0)
    assert info["state"] == "match"
    assert info["opencc"] == "词汇"
    assert info["candidates"] == ("词汇",)

    monkeypatch.setattr(
        app_module,
        "cc_cedict_simplified_candidates",
        lambda _word: SimpleNamespace(
            found=True, candidates=("词彙",), matched_as="traditional", detail="test"
        ),
    )
    info = app_module.ReviewWindow._cc_simplified_comparison_details(review, 0)
    assert info["state"] == "mismatch"



def test_v21211_saved_automatic_simplified_record_is_not_regenerated_on_reopen_source_contract():
    """A persisted manual=False value is still authoritative on page reopen."""
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("            saved_simplified = simplified_records.get(simplified_key)")
    end = text.index("            simplified_var = tk.StringVar(", start)
    body = text[start:end]
    assert "auto_refresh = saved_simplified is None" in body
    assert "if saved_simplified is not None:" in body
    assert "simplified_actual = saved_text" in body
    assert "self._auto_simplified_value(entry.word)" in body


def test_v21211_persisted_automatic_simplified_is_frozen_against_original_refresh(monkeypatch):
    """Editing the original must not overwrite an already persisted auto value."""
    from types import SimpleNamespace
    import picture_capture.app as app_module

    class Var:
        def __init__(self, value): self.value = value
        def get(self): return self.value
        def set(self, value): self.value = value

    review = object.__new__(app_module.ReviewWindow)
    review.vars = [Var("新原詞")]
    review.simplified_vars = [Var("已保存简体")]
    review.simplified_actual_values = ["已保存简体"]
    review.simplified_manual_flags = [False]
    review.simplified_auto_refresh_flags = [False]
    review.active_index = -1
    review._rendered_page_stem = "0001"
    review.parent = SimpleNamespace(_ordered_entries_reading_order=lambda: [])

    called = {"n": 0}
    def fake_auto(*args, **kwargs):
        called["n"] += 1
        return "不应覆盖"
    review._auto_simplified_value = fake_auto

    app_module.ReviewWindow._refresh_simplified_for_index(review, 0)
    assert review.simplified_vars[0].get() == "已保存简体"
    assert review.simplified_actual_values[0] == "已保存简体"
    assert called["n"] == 0


def test_v21211_new_unsaved_simplified_can_still_follow_original_during_session():
    """Never-saved rows keep the useful live OpenCC behavior before first reopen."""
    from types import SimpleNamespace
    import picture_capture.app as app_module

    class Var:
        def __init__(self, value): self.value = value
        def get(self): return self.value
        def set(self, value): self.value = value

    entry = SimpleNamespace(x=10, y=20)
    review = object.__new__(app_module.ReviewWindow)
    review.vars = [Var("校對")]
    review.simplified_vars = [Var("旧")]
    review.simplified_actual_values = ["旧"]
    review.simplified_manual_flags = [False]
    review.simplified_auto_refresh_flags = [True]
    review.active_index = -1
    review._rendered_page_stem = "0001"
    review._simplified_dirty_pages = set()
    review.parent = SimpleNamespace(_ordered_entries_reading_order=lambda: [entry])
    review._auto_simplified_value = lambda original, fallback=None: "校对"
    records = {}
    review._simplified_page_records = lambda stem: records

    app_module.ReviewWindow._refresh_simplified_for_index(review, 0)
    assert review.simplified_vars[0].get() == "校对"
    assert review.simplified_actual_values[0] == "校对"
    assert records["10,20"]["text"] == "校对"
    assert "0001" in review._simplified_dirty_pages


def test_v2140_regenerate_simplified_current_page_overwrites_saved_and_manual_results(monkeypatch):
    from types import SimpleNamespace
    import picture_capture.app as app_module

    class Var:
        def __init__(self, value): self.value = value
        def get(self): return self.value
        def set(self, value): self.value = value

    entries = [SimpleNamespace(x=10, y=20), SimpleNamespace(x=30, y=40)]
    records = {
        "10,20": {"x": 10, "y": 20, "source_word": "舊詞", "text": "人工旧值", "manual": True},
        "30,40": {"x": 30, "y": 40, "source_word": "測試", "text": "旧测试", "manual": False},
    }
    persisted = []
    statuses = []
    review = object.__new__(app_module.ReviewWindow)
    review.vars = [Var("舊詞"), Var("測試")]
    review.simplified_vars = [Var("人工旧值"), Var("旧测试")]
    review.simplified_actual_values = ["人工旧值", "旧测试"]
    review.simplified_manual_flags = [True, False]
    review.simplified_auto_refresh_flags = [False, False]
    review._simplified_dirty_pages = set()
    review._rendered_page_stem = "0001"
    review.active_index = 0
    review._bound_row_entries = lambda: entries
    review._simplified_page_records = lambda stem: records
    review._persist_simplified_page = lambda stem: persisted.append(stem)
    review._refresh_cc_simplified_comparison = lambda index: None
    review.parent = SimpleNamespace(
        current_page=SimpleNamespace(stem="0001", name="0001.png"),
        _claim_page_for_manual_edit=lambda: True,
        status_var=SimpleNamespace(set=lambda value: statuses.append(value)),
    )
    monkeypatch.setattr(
        app_module, "simplify_text",
        lambda text: {"舊詞": "旧词", "測試": "测试"}[text],
    )

    app_module.ReviewWindow.regenerate_simplified_current_page(review)

    assert [var.get() for var in review.simplified_vars] == ["旧词", "测试"]
    assert review.simplified_actual_values == ["旧词", "测试"]
    assert review.simplified_manual_flags == [False, False]
    assert review.simplified_auto_refresh_flags == [False, False]
    assert records["10,20"]["text"] == "旧词"
    assert records["10,20"]["manual"] is False
    assert records["30,40"]["text"] == "测试"
    assert persisted == ["0001"]
    assert statuses and "覆盖 2 条简体结果" in statuses[-1]


def test_v2140_review_window_defaults_to_sixty_percent_width_and_seventy_percent_height():
    from picture_capture.app import _review_window_dimensions

    assert _review_window_dimensions(1920, 1080) == (1152, 756)
    assert _review_window_dimensions(1366, 768) == (820, 538)


def test_v2140_review_left_pane_fits_complete_toolbar_and_right_gets_remaining_width():
    from pathlib import Path
    import inspect
    import picture_capture.app as app_module

    text = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    start = text.index("class ReviewWindow")
    end = text.index("class OCRConflictReviewDialog", start)
    review = text[start:end]
    assert "self.review_panes = panes" in review
    assert "self.review_control_row = row1" in review
    assert "self.after_idle(self._fit_review_left_pane_to_toolbar)" in review
    fit_start = review.index("    def _fit_review_left_pane_to_toolbar")
    fit_end = review.index("    def _build(self) -> None:", fit_start)
    fit = review[fit_start:fit_end]
    assert "row.winfo_reqwidth()" in fit
    assert "panes.sashpos(0, min(required, available))" in fit
    assert "panes.add(left, weight=0)" in review
    assert "panes.add(right, weight=1)" in review


def test_v21212_layout_behavior_fresh_defaults_are_both_off():
    from picture_capture.models import AppSettings

    settings = AppSettings()
    assert settings.manual_columns is False
    assert settings.follow_column_deformation is False
    assert settings.layout_behavior_defaults_version == 1


def test_v21212_layout_behavior_old_project_migrates_once_then_preserves_choice(tmp_path):
    import json
    from picture_capture.models import AppSettings

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "manual_columns": True,
        "follow_column_deformation": True,
    }), encoding="utf-8")
    migrated = AppSettings.from_json(path)
    assert migrated.manual_columns is False
    assert migrated.follow_column_deformation is False
    assert migrated.layout_behavior_defaults_version == 1

    migrated.manual_columns = True
    migrated.follow_column_deformation = True
    migrated.to_json(path)
    reloaded = AppSettings.from_json(path)
    assert reloaded.manual_columns is True
    assert reloaded.follow_column_deformation is True


def test_v21212_review_highlight_uses_rgba_alpha_not_stipple():
    import inspect
    import picture_capture.app as app_module

    body = inspect.getsource(app_module.PictureCaptureApp._draw_review_entry_highlight)
    assert 'Image.new(' in body
    assert '"RGBA"' in body
    assert '(255, 238, 128, 92)' in body
    assert 'create_image(' in body
    assert 'stipple=' not in body


def test_review_highlight_uses_the_same_geometry_as_review_crop():
    import inspect
    import picture_capture.app as app_module

    body = inspect.getsource(app_module.PictureCaptureApp._draw_review_entry_highlight)
    assert "review_settings = _review_crop_settings(" in body
    assert "left, top, right, bottom = _review_line_box(" in body
    assert "line_box(entry, geometry, self.image, self.settings)" not in body


def test_v2132_declares_cpu_and_gpu_ocr_profiles():
    import tomllib
    from pathlib import Path

    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    assert set(("ocr-cpu", "ocr-gpu-cu118", "ocr-gpu-cu126", "ocr-gpu-cu129")) <= set(extras)
    assert "paddlepaddle==3.3.0" in extras["ocr-cpu"]
    for name in ("ocr-gpu-cu118", "ocr-gpu-cu126", "ocr-gpu-cu129"):
        assert "paddleocr>=3.7,<4" in extras[name]
        assert "chrome-lens-py>=3.4,<4" in extras[name]
        assert "paddlepaddle-gpu==3.3.0" in extras[name]
    assert not any("nvidia-cudnn" in item for item in extras["ocr-gpu-cu118"])
    assert "nvidia-cudnn-cu12==9.5.1.17; sys_platform == 'win32'" in extras["ocr-gpu-cu126"]
    assert "nvidia-cudnn-cu12==9.9.0.52; sys_platform == 'win32'" in extras["ocr-gpu-cu129"]


def test_windows_ocr_installer_uses_thin_batch_and_locked_uv_profiles():
    import importlib.util
    import tomllib
    from pathlib import Path

    batch = Path("install_ocr_windows.bat").read_text(encoding="utf-8")
    assert '"scripts\\windows_ocr_setup.py"' in batch
    for suspicious in (
        "uv pip", "uninstall", "--index", "paddlepaddle-gpu",
        "packages/stable/cu", "nvidia-smi", "set /p",
        "powershell", "curl ", "wget ", "certutil", "bitsadmin",
        "invoke-webrequest", "http://", "https://", "pythonw.exe", "start ",
    ):
        assert suspicious not in batch.casefold()

    spec = importlib.util.spec_from_file_location(
        "_picture_capture_windows_ocr_setup", Path("scripts/windows_ocr_setup.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.PROFILES["2"]["extra"] == "ocr-gpu-cu118"
    assert module.PROFILES["3"]["extra"] == "ocr-gpu-cu126"
    assert module.PROFILES["4"]["extra"] == "ocr-gpu-cu129"
    assert module.sync_command(module.PROFILES["3"]) == [
        "uv", "sync", "--locked", "--no-dev", "--extra", "ocr-gpu-cu126",
    ]
    assert module.MARKER.name == ".picture_capture_ocr_extra"

    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    for name in ("ocr-gpu-cu118", "ocr-gpu-cu126", "ocr-gpu-cu129"):
        assert "paddlepaddle-gpu==3.3.0" in extras[name]
    sources = data["tool"]["uv"]["sources"]["paddlepaddle-gpu"]
    assert {item["extra"] for item in sources} == {
        "ocr-gpu-cu118", "ocr-gpu-cu126", "ocr-gpu-cu129",
    }

    runtime_source = Path("src/picture_capture/windows_gpu_runtime.py").read_text(encoding="utf-8")
    paddle_source = Path("src/picture_capture/paddle_headwords.py").read_text(encoding="utf-8")
    layout_source = Path("src/picture_capture/layout_detection.py").read_text(encoding="utf-8")
    verify_source = Path("scripts/verify_ocr_environment.py").read_text(encoding="utf-8")
    assert "add_dll_directory" in runtime_source
    assert 'glob("*/bin")' in runtime_source
    assert "configure_windows_nvidia_dlls()" in paddle_source
    assert "configure_windows_nvidia_dlls()" in layout_source
    assert "Paddle GPU/cuDNN smoke test: OK" in verify_source
    assert "paddle.nn.functional.conv2d" in verify_source


def test_windows_batch_launcher_is_visible_foreground_and_minimal():
    from pathlib import Path

    batch = Path("run_windows.bat").read_text(encoding="utf-8").casefold()
    run_py = Path("run.py").read_text(encoding="utf-8")

    assert '".venv\\scripts\\python.exe" "run.py"' in batch
    assert 'pushd "%~dp0"' in batch
    assert "popd" in batch
    for suspicious in (
        "uv ", "pip ", "powershell", "curl ", "wget ", "certutil", "bitsadmin",
        "invoke-webrequest", "http://", "https://", "pythonw.exe", "start ",
        "create_no_window", "subprocess", "fc /b", "set /p",
        ".picture_capture_ocr_extra",
    ):
        assert suspicious not in batch
    assert "subprocess" not in run_py
    assert "Popen" not in run_py
    assert "CREATE_NO_WINDOW" not in run_py
    assert "PC_NO_CONSOLE" not in run_py
    assert not Path("Picture_Capture.pyw").exists()
    assert not Path("Picture_Capture.vbs").exists()

    release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "sha256sum" in release
    assert "SHA256SUMS.txt" in release


def test_rtl_geometry_orders_source_right_column_first_and_keeps_source_crop_pixels():
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((300, 80, 360, 100), fill=(220, 20, 20))
    settings = AppSettings(
        parameter_display_width=400,
        columns=2,
        manual_x=30,
        column_width=150,
        gutter=40,
        character_height=24,
        layout_transform="mirror_x",
        layout_text_direction="rtl",
    )
    geometry = derive_geometry(image, settings)
    right = Entry("right", 350, 80)
    left = Entry("left", 50, 80)

    assert sort_entries_reading_order([left, right], geometry) == [right, left]
    right_box = line_box(right, geometry, image, settings)
    assert right_box[0] < 350 <= right_box[2]
    assert right_box[1] <= 80 < right_box[3]
    # The formal OCR path crops from the original source page. Its red source
    # pixels therefore remain red rather than becoming a mirrored derivative.
    crop = image.crop(right_box)
    assert any(
        crop.getpixel((x, y))[0] > 180 and crop.getpixel((x, y))[1] < 80
        for y in range(crop.height)
        for x in range(crop.width)
    )


def test_rtl_ordinary_drawing_detects_source_physical_right_edge():
    canonical = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(canonical)
    for y in (70, 120, 170, 220):
        draw.rectangle((30, y, 55, y + 12), fill="black")
    source = canonical.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    settings = AppSettings(
        parameter_display_width=400,
        columns=1,
        manual_x=30,
        column_width=330,
        start_y=40,
        body_indent=35,
        character_height=18,
        layout_transform="mirror_x",
        detection_method="left_edge",
        paddle_refine_separator_y=False,
    )

    entries, _geometry = detect_entries(source, settings)

    assert len(entries) == 4
    assert all(entry.x > 300 for entry in entries)


def test_vertical_geometry_maps_markers_boxes_and_whole_crops_back_to_source():
    from picture_capture.processing import entry_crop_column_boxes

    image = Image.new("RGB", (300, 500), "white")
    settings = AppSettings(
        parameter_display_width=500,
        columns=3,
        manual_x=20,
        column_width=130,
        gutter=25,
        character_height=30,
        layout_transform="rotate_ccw90",
        layout_writing_mode="vertical-rl",
    )
    geometry = derive_geometry(image, settings)
    source_point = geometry.canonical_to_source(geometry.column_starts[0], 70)
    entry = Entry("縦", *source_point)
    box = line_box(entry, geometry, image, settings)
    marker = geometry.transform.canonical_marker_to_source(
        (geometry.column_starts[0], 70),
        (geometry.column_starts[0] + geometry.column_widths[0], 70),
        image.size,
    )

    assert marker[0][0] == marker[1][0]
    assert box[2] - box[0] < box[3] - box[1]
    column_boxes = entry_crop_column_boxes(image, settings)
    assert len(column_boxes) == 3
    assert all(0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height for x0, y0, x1, y1 in column_boxes)


def test_transformed_ocr_band_uses_original_source_orientation_and_box_adapter():
    from picture_capture.paddle_headwords import _records_to_canonical_band, unwrap_column_band
    from picture_capture.paddle_headwords import OCRRecord

    image = Image.new("RGB", (120, 200), "white")
    image.putpixel((110, 80), (1, 2, 3))
    settings = AppSettings(
        parameter_display_width=120,
        columns=1,
        manual_x=5,
        column_width=100,
        layout_transform="mirror_x",
    )
    geometry = derive_geometry(image, settings)
    band, _top, _margin = unwrap_column_band(image, geometry, 0, settings)
    canonical = geometry.transform.canonical_image_for_analysis(band)
    records = _records_to_canonical_band([OCRRecord("abc", 1.0, (80, 5, 100, 20))], band.size, "mirror_x")

    source_pixel_x = next(x for x in range(band.width) if band.getpixel((x, 25)) == (1, 2, 3))
    assert canonical.getpixel((band.width - 1 - source_pixel_x, 25)) == (1, 2, 3)
    assert records[0].box[0] < records[0].box[2] <= band.width


def test_coordinate_contract_legacy_migration_preserves_runtime_geometry():
    from copy import deepcopy
    from PIL import Image
    from picture_capture.coordinate_space import (
        CANONICAL_REFERENCE_SPACE,
        migrate_legacy_geometry_settings,
    )
    from picture_capture.models import AppSettings
    from picture_capture.processing import derive_geometry

    image = Image.new("RGB", (2000, 1200), "white")
    legacy = AppSettings(
        geometry_coordinate_version=1,
        geometry_coordinate_space="legacy_display_pixels",
        parameter_display_width=1000,
        columns=2,
        manual_x=50,
        column_width=400,
        gutter=50,
        start_y=25,
        bottom_y=0,
        character_height=20,
        row_padding=3,
        follow_column_deformation=False,
    )
    before = derive_geometry(image, legacy)
    migrated = deepcopy(legacy)
    assert migrate_legacy_geometry_settings(migrated, image.size) is True
    assert migrated.geometry_coordinate_version == 2
    assert migrated.geometry_coordinate_space == CANONICAL_REFERENCE_SPACE
    assert migrated.geometry_reference_width == 2000
    assert migrated.manual_x == 100
    assert migrated.column_width == 800
    assert migrated.gutter == 100
    assert migrated.start_y == 50
    assert migrated.bottom_y == 0  # sentinel remains a sentinel
    after = derive_geometry(image, migrated)
    assert after.column_starts == before.column_starts
    assert after.column_widths == before.column_widths
    assert after.top == before.top
    assert after.bottom == before.bottom
    # The reference width also preserves the old width-normalized behavior on a
    # differently sized scan without reintroducing GUI display coordinates.
    larger = Image.new("RGB", (3000, 1800), "white")
    legacy_large = derive_geometry(larger, legacy)
    migrated_large = derive_geometry(larger, migrated)
    assert migrated_large.column_starts == legacy_large.column_starts
    assert migrated_large.column_widths == legacy_large.column_widths
    assert migrated_large.top == legacy_large.top
    assert migrate_legacy_geometry_settings(migrated, image.size) is False


def test_coordinate_contract_source_canonical_points_round_trip_for_all_transforms():
    from picture_capture.layout_transform import LayoutTransform

    source_size = (1234, 1642)
    points = [(0, 0), (1, 1), (617, 821), (1233, 1641), (77, 1500)]
    for kind in ("identity", "mirror_x", "rotate_ccw90", "rotate_cw90"):
        transform = LayoutTransform(kind)
        for point in points:
            canonical = transform.source_to_canonical_point(*point, source_size)
            restored = transform.canonical_to_source_point(*canonical, source_size)
            assert restored == point


def test_coordinate_contract_profile_percent_resolves_to_source_pixels_across_reference_width():
    from picture_capture.models import AppSettings
    from picture_capture.profile_semantics import effective_page_settings
    from picture_capture.processing import derive_nominal_geometry

    settings = AppSettings(
        geometry_reference_width=1400,
        profile_header_mode="present",
        profile_header_percent=3.0,
        profile_footer_mode="present",
        profile_footer_percent=4.0,
        columns=1,
        manual_x=20,
        column_width=800,
    )
    effective = effective_page_settings(settings, (1000, 1642), 0)

    # Persisted layout bounds remain reference-page values, not source Y.
    assert effective.start_y != 49
    assert effective.bottom_y != 1576

    # Runtime geometry and the public quick panel must resolve the physical
    # Profile percentages against the current original image.
    geometry = derive_nominal_geometry(1000, 1642, effective)
    assert geometry.top == 49
    assert geometry.bottom == 1576

    app = PictureCaptureApp.__new__(PictureCaptureApp)
    app.image = Image.new("RGB", (1000, 1642), "white")
    app.settings = settings
    assert PictureCaptureApp._quick_geometry_value(app, "start_y") == 49
    assert PictureCaptureApp._quick_geometry_value(app, "bottom_y") == 1576





def test_coordinate_contract_crop_plan_uses_same_profile_boundaries_as_main_geometry():
    from picture_capture.processing import build_page_crop_plan
    from picture_capture.models import AppSettings

    image = Image.new("RGB", (1000, 1642), "white")
    settings = AppSettings(
        geometry_reference_width=1400,
        columns=1,
        manual_x=70,
        column_width=1120,
        start_y=130,
        bottom_y=2000,
        crop_to_bottom_y=True,
        follow_column_deformation=False,
        profile_header_mode="present",
        profile_header_percent=3.0,
        profile_footer_mode="present",
        profile_footer_percent=4.0,
    )
    plan = build_page_crop_plan(
        image, [], [], settings, profile_page_index=0,
    )
    assert len(plan.entry_pieces) == 1
    box = plan.entry_pieces[0].box
    assert box[1] == 49
    assert box[3] == 1576


def test_coordinate_contract_training_export_separates_source_and_canonical(tmp_path):
    import json
    from PIL import Image
    from picture_capture.formats import write_pdic, write_ppp
    from picture_capture.models import AppSettings, Entry, PolygonRegion
    from picture_capture.training_export import export_training_page
    from picture_capture.coordinate_space import (
        SOURCE_COORDINATE_SPACE, CANONICAL_COORDINATE_SPACE,
    )

    root = tmp_path / "dict"
    root.mkdir()
    page = root / "0001.png"
    Image.new("RGB", (600, 900), "white").save(page)
    settings = AppSettings(
        columns=2,
        manual_x=20,
        column_width=250,
        gutter=40,
        start_y=30,
        bottom_y=850,
        crop_to_bottom_y=True,
        profile_header_mode="present",
        profile_header_percent=3.0,
        profile_footer_mode="present",
        profile_footer_percent=4.0,
    )
    write_pdic(page.with_suffix(".pdic"), [Entry("alpha", 20, 120)], 600, ("0001", "@", "@"))
    write_ppp(
        page.with_suffix(".ppp"),
        [PolygonRegion("fig", [(400, 500), (500, 500), (500, 650)])],
        "0001",
    )
    staging = tmp_path / "staging"
    export_training_page(page, root, settings, staging, 0)
    annotation = json.loads(
        (staging / "annotations" / "0001.json").read_text(encoding="utf-8")
    )

    assert annotation["format"] == "picture-capture-training-v2"
    assert annotation["coordinate_contract"]["annotations"] == SOURCE_COORDINATE_SPACE
    assert annotation["coordinate_contract"]["layout_geometry_runtime"] == CANONICAL_COORDINATE_SPACE
    assert annotation["ground_truth_lines"][0]["x"] == 20
    assert annotation["ground_truth_lines"][0]["y"] == 120
    assert annotation["page_template"]["coordinate_space"] == SOURCE_COORDINATE_SPACE
    assert annotation["page_template"]["header_boundary_y"] == 27
    assert annotation["page_template"]["footer_boundary_y"] == 864
    layout = annotation["layout"]
    assert layout["coordinate_space"] == CANONICAL_COORDINATE_SPACE
    # The exported runtime layout must use the same Profile-resolved boundaries
    # as detection/display, not the raw persisted start_y/bottom_y values.
    assert layout["top_v"] == 27
    assert layout["bottom_v"] == 864
    assert "column_starts_u" in layout and "column_paths_vu" in layout
    assert "header_y" not in layout
    assert "derived_top" not in layout


def test_new_project_initializes_explicit_reference_without_changing_1400_default_meaning(tmp_path):
    from picture_capture.coordinate_space import stored_geometry_to_canonical
    from picture_capture.models import AppSettings, ProjectState

    # A bare settings object remains page-local for library/test callers.
    assert AppSettings().geometry_reference_width == 0

    # A real project establishes an explicit reference only after a source page
    # is known. Historical untouched defaults still retain their old 1400px
    # physical meaning: 700 at 1400 becomes 1500 on a 3000px reference page.
    Image.new("RGB", (3000, 1800), "white").save(tmp_path / "0001.png")
    project = ProjectState.open(tmp_path)
    modern = project.settings
    assert modern.geometry_reference_width == 3000
    assert modern.column_width == 1500
    assert stored_geometry_to_canonical(modern.column_width, 3000, modern) == 1500

    legacy = AppSettings(
        geometry_coordinate_version=1,
        geometry_coordinate_space="legacy_display_pixels",
        geometry_reference_width=0,
        parameter_display_width=0,
    )
    assert stored_geometry_to_canonical(legacy.column_width, 3000, legacy) == 1500


def test_coordinate_contract_parameter_display_width_is_legacy_only_in_core_runtime():
    from pathlib import Path

    package = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    allowed = {
        "app.py",             # legacy project/crop-settings adapters + viewer compatibility
        "coordinate_space.py", # single migration/conversion authority
        "models.py",          # persisted legacy field + one-time project migration
        "processing.py",      # compatibility scale for unmigrated old settings
    }
    offenders = []
    for source in package.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        if "parameter_display_width" in text and source.name not in allowed:
            offenders.append(source.name)
    assert offenders == []

    coordinate_text = (package / "coordinate_space.py").read_text(encoding="utf-8")
    models_text = (package / "models.py").read_text(encoding="utf-8")
    assert "parameter_display_width" in coordinate_text
    assert "parameter_display_width" in models_text
    assert "parameter_display_width" not in (
        package / "paddle_headwords.py"
    ).read_text(encoding="utf-8")
    assert "parameter_display_width" not in (
        package / "profile_semantics.py"
    ).read_text(encoding="utf-8")
    assert "parameter_display_width" not in (
        package / "training_export.py"
    ).read_text(encoding="utf-8")


def test_crop_log_declares_source_image_coordinate_space(tmp_path):
    (tmp_path / "QT").mkdir()
    append_crop_log(
        tmp_path,
        [CropRecord("0001.png", 1, "alpha", "0001_SW_001.png", (10, 20, 110, 70))],
    )
    log = (tmp_path / "QT" / "_file_log.txt").read_text(encoding="utf-8")
    rows = log.splitlines()
    assert rows[0].startswith("# coordinate_space=source_image_pixels")
    assert "source_x,source_y,width,height" in rows[0]
    assert rows[1] == "0001.png\t0001_SW_001.png\t10\t20\t100\t50"


def test_crop_settings_v5_migrates_to_reference_page_pixels():
    from picture_capture.app import _normalize_crop_settings_payload
    from picture_capture.coordinate_space import CANONICAL_REFERENCE_SPACE
    from picture_capture.models import AppSettings

    settings = AppSettings(
        geometry_coordinate_version=2,
        geometry_coordinate_space=CANONICAL_REFERENCE_SPACE,
        geometry_reference_width=2000,
        parameter_display_width=1000,
        start_y=100,
        bottom_y=1800,
        crop_to_bottom_y=True,
    )
    legacy = {
        "version": 5,
        "general_top_y": 50,
        "general_bottom_y": 900,
        "entry_left_padding": 12,
        "entry_right_padding": 18,
        "polygon_margin": 8,
        "special_pages": {
            "0010": {"top_y": 60, "bottom_y": 880},
        },
    }
    migrated = _normalize_crop_settings_payload(legacy, settings)
    assert migrated["version"] == 6
    assert migrated["coordinate_space"] == CANONICAL_REFERENCE_SPACE
    assert migrated["geometry_reference_width"] == 2000
    assert migrated["general_top_v"] == 100
    assert migrated["general_bottom_v"] == 1800
    assert migrated["entry_left_padding_u"] == 24
    assert migrated["entry_right_padding_u"] == 36
    assert migrated["polygon_margin"] == 16
    assert migrated["special_pages"]["0010"] == {"top_v": 120, "bottom_v": 1760}


def test_crop_settings_v6_rescales_when_reference_page_changes():
    from picture_capture.app import _normalize_crop_settings_payload
    from picture_capture.coordinate_space import CANONICAL_REFERENCE_SPACE
    from picture_capture.models import AppSettings

    settings = AppSettings(
        geometry_reference_width=3000,
        geometry_coordinate_space=CANONICAL_REFERENCE_SPACE,
    )
    saved = {
        "version": 6,
        "coordinate_space": CANONICAL_REFERENCE_SPACE,
        "geometry_reference_width": 2000,
        "general_top_v": 100,
        "general_bottom_v": 1800,
        "entry_left_padding_u": 20,
        "entry_right_padding_u": 30,
        "polygon_margin": 10,
        "special_pages": {"p": {"top_v": 120, "bottom_v": 1750}},
    }
    normalized = _normalize_crop_settings_payload(saved, settings)
    assert normalized["geometry_reference_width"] == 3000
    assert normalized["general_top_v"] == 150
    assert normalized["general_bottom_v"] == 2700
    assert normalized["entry_left_padding_u"] == 30
    assert normalized["entry_right_padding_u"] == 45
    assert normalized["polygon_margin"] == 15
    assert normalized["special_pages"]["p"] == {"top_v": 180, "bottom_v": 2625}


def test_crop_bounds_scale_reference_values_to_current_page():
    from PIL import Image
    from picture_capture.coordinate_space import CANONICAL_REFERENCE_SPACE
    from picture_capture.models import AppSettings
    from picture_capture.processing import entry_crop_bounds, illustration_crop_bounds

    settings = AppSettings(
        geometry_coordinate_space=CANONICAL_REFERENCE_SPACE,
        geometry_reference_width=2000,
        columns=1,
        manual_x=100,
        column_width=1600,
        start_y=100,
        bottom_y=1800,
        crop_to_bottom_y=True,
    )
    image = Image.new("RGB", (3000, 2700), "white")
    top, bottom = entry_crop_bounds(image, settings, top_y=100, bottom_y=1800)
    assert (top, bottom) == (150, 2700)
    ill_top, ill_bottom, margin = illustration_crop_bounds(
        image, settings, top_y=100, bottom_y=1600, margin=20,
    )
    assert (ill_top, ill_bottom, margin) == (150, 2400, 30)


def test_page_crop_plan_declares_source_coordinate_space():
    from picture_capture.coordinate_space import SOURCE_COORDINATE_SPACE
    from picture_capture.processing import PageCropPlan, page_crop_plan_dict

    payload = page_crop_plan_dict(PageCropPlan([], [], True))
    assert payload["version"] == 3
    assert payload["coordinate_space"] == SOURCE_COORDINATE_SPACE
    assert payload["box_format"] == "source_xyxy"
