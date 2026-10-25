"""Synthetic managed-project Tk read/save/reopen smoke for Issue #562.

Runs real bootstrap, project-load worker, Tk event callbacks and managed PDIC/PPP
persistence in an isolated two-page temporary project. NEVER claims to validate
real dictionary scan pixels or a human's GUI/Profile/crop judgment.
"""
from __future__ import annotations

import faulthandler
import json
import hashlib
from pathlib import Path
import os
import sys
import tempfile
import threading
import time
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

from picture_capture import __version__
from picture_capture.io.formats import pdic_path, read_pdic, read_ppp, write_pdic, write_ppp
from picture_capture.models import AppSettings, Entry, PolygonRegion
from picture_capture.persistence.project_storage import (
    ensure_project_storage, ppp_read_path_for_image, ppp_write_path_for_image,
    profile_path, qt_root, settings_path,
)
from picture_capture.profile.dictionary import (
    load_dictionary_profile, write_project_profile,
)
from picture_capture.geometry.coordinate_space import SOURCE_COORDINATE_SPACE
from picture_capture.persistence.page_sections import (
    PAGE_SECTIONS_FORMAT, PageSection, read_page_sections,
)
from picture_capture.persistence.project_storage import page_sections_path_for_image
from picture_capture.proofreading.section import section_snapshot_for_source_point


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sample_project(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    page1, page2 = root / "synthetic-001.png", root / "synthetic-002.png"
    for path in (page1, page2):
        image = Image.new("RGB", (640, 460), "white")
        drawer = ImageDraw.Draw(image)
        for x in (70, 365):
            for y in (75, 180, 285):
                drawer.rectangle((x, y, x + 140, y + 12), fill=(25, 25, 25))
        image.save(path)
        image.close()
    ensure_project_storage(root, __version__)
    initial = AppSettings()
    # The synthetic page is only 640 px wide; the global 700-px default
    # would display as >100% in the real Tk percent-width control.
    # Keep the fixture's persisted geometry valid, without changing product
    # validation or silently weakening the user-action test.
    initial.column_width = 500
    initial.to_json(settings_path(root))
    _assert(
        write_pdic(
            pdic_path(page1),
            [Entry("synthetic-alpha", 80, 76), Entry("synthetic-beta", 85, 182)],
            640, ("synthetic-001", "@", "synthetic-002"),
        ),
        "fixture PDIC writer did not publish",
    )
    _assert(
        write_ppp(
            ppp_write_path_for_image(page1),
            [PolygonRegion("P_01|synthetic-001|xxx", [
                (400, 92), (500, 92), (500, 142), (400, 142),
            ])],
            page1.stem,
        ),
        "fixture PPP writer did not publish",
    )
    return page1, page2


def _pump_until(app, predicate, *, seconds: float, description: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        if predicate():
            return
        time.sleep(0.025)
    status = app.status_var.get() if getattr(app, "status_var", None) is not None else "missing"
    actual = getattr(app, "current_page", None)
    project = getattr(app, "project", None)
    raise RuntimeError(
        f"Tk integration timed out during {description}; "
        f"actual_page={actual!s}, project_root={getattr(project, 'root', None)!s}, "
        f"status={status!r}"
    )


def main() -> int:
    from picture_capture.bootstrap.application import build_application

    module = build_application()
    complete = threading.Event()

    def watchdog() -> None:
        if complete.wait(95):
            return
        print("[managed-project-smoke] hard timeout", flush=True)
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        os._exit(124)

    threading.Thread(target=watchdog, name="project-roundtrip-watchdog", daemon=True).start()

    with tempfile.TemporaryDirectory(prefix="pc-managed-roundtrip-") as temp:
        # macOS /var may resolve to /private/var; match the loader's .resolve().
        root = (Path(temp) / "synthetic-dictionary").resolve()
        first, second = _sample_project(root)
        original_hashes = {page.name: _source_hash(page) for page in (first, second)}
        app = module.PictureCaptureApp()
        try:
            app.withdraw()

            def unexpected_dialog(*args, **kwargs):
                raise AssertionError(f"unexpected modal during managed synthetic smoke: {args!r}")

            with patch.object(module.messagebox, "askyesno", side_effect=unexpected_dialog), patch.object(
                module.messagebox, "showerror", side_effect=unexpected_dialog,
            ):
                app._load_project(root)
                _pump_until(
                    app,
                    lambda: app.project is not None
                    and app.current_page == first
                    and app.image is not None,
                    seconds=32, description="initial managed project bootstrap",
                )
                _assert(app.current_index == 0, "project did not select first page")
                _assert(app.image.size == (640, 460), "source image dimensions changed")
                _assert(
                    {(e.word, e.x, e.y) for e in app.entries}
                    == {("synthetic-alpha", 80, 76), ("synthetic-beta", 85, 182)},
                    "initial GUI PDIC markers do not match saved source XY",
                )
                _assert(len(app.polygons) == 1, "initial GUI PPP polygon missing")

                # Round 64: exercise the ORIGINAL user-facing detection
                # actions and OCR-engine preflight on the live Tk workspace.
                # The detector backend is a dispatch spy, not a model run;
                # missing native OCR packages must never be fabricated here.
                engine_names = (
                    "paddle_use_paddleocr",
                    "paddle_compare_tesseract",
                    "paddle_enable_lens",
                )
                _assert(
                    all(name in app.quick_bool_vars for name in engine_names),
                    "Tk OCR engine switches missing from the main workspace",
                )
                previous_switches = {
                    name: bool(app.quick_bool_vars[name].get())
                    for name in engine_names
                }
                settings_fields = (*engine_names, "paddle_tesseract_rescue",
                                   "paddle_lens_mode", "detection_method")
                previous_settings = {
                    name: getattr(app.settings, name) for name in settings_fields
                }
                previous_lens_label = app.lens_mode_var.get()
                marker_hash = _source_hash(pdic_path(first))
                polygon_hash = _source_hash(ppp_read_path_for_image(first))
                original_entry_snapshot = [(e.word, e.x, e.y) for e in app.entries]
                original_polygon_snapshot = [
                    (p.label, tuple(p.points)) for p in app.polygons
                ]
                original_page_index = app.current_index
                original_page_path = app.current_page
                original_project_root = app.project.root
                try:
                    for name, enabled in (
                        ("paddle_use_paddleocr", False),
                        ("paddle_compare_tesseract", False),
                        ("paddle_enable_lens", True),
                    ):
                        app.quick_bool_vars[name].set(enabled)
                        setattr(app.settings, name, enabled)
                    app.settings.paddle_tesseract_rescue = False
                    app.settings.paddle_lens_mode = "off"
                    app.lens_mode_var.set("off")
                    blocked_dialogs = []

                    def capture_blocked_ocr(title, detail, **_kwargs):
                        blocked_dialogs.append((title, detail))

                    with patch.object(
                        app, "_detect_pages",
                        side_effect=AssertionError("invalid OCR action reached backend"),
                    ) as forbidden_dispatch, patch.object(
                        module.messagebox, "showerror",
                        side_effect=capture_blocked_ocr,
                    ):
                        app.run_ocr_draw_action()
                        app.run_combined_draw_action()
                        forbidden_dispatch.assert_not_called()
                    _assert(
                        len(blocked_dialogs) == 2
                        and all(title == "OCR 引擎配置无效"
                                for title, _text in blocked_dialogs),
                        "Lens-off-only selection did not block both OCR draw actions",
                    )
                    _assert(
                        app.settings.detection_method
                        == previous_settings["detection_method"],
                        "rejected OCR action mutated selected drawing mode",
                    )
                    _assert(
                        app.current_index == original_page_index
                        and app.current_page == original_page_path
                        and app.project.root == original_project_root,
                        "rejected OCR action changed the active project/page",
                    )
                    _assert(
                        [(e.word, e.x, e.y) for e in app.entries]
                        == original_entry_snapshot
                        and [(p.label, tuple(p.points)) for p in app.polygons]
                        == original_polygon_snapshot,
                        "rejected OCR action changed unsaved PDIC/PPP in memory",
                    )
                    _assert(
                        _source_hash(pdic_path(first)) == marker_hash
                        and _source_hash(ppp_read_path_for_image(first)) == polygon_hash,
                        "rejected OCR action rewrote saved PDIC/PPP",
                    )

                    # Ordinary drawing must stay usable with *all* OCR
                    # engines disabled. Only the heavy backend is intercepted;
                    # real Tk action/quick-settings/scope logic runs unchanged.
                    app.quick_bool_vars["paddle_enable_lens"].set(False)
                    app.settings.paddle_enable_lens = False
                    dispatched = []

                    def capture_normal_draw(indices, *, method, force_refresh):
                        dispatched.append((
                            list(indices), method, force_refresh,
                            bool(app.quick_bool_vars["paddle_use_paddleocr"].get()),
                            bool(app.settings.paddle_use_paddleocr),
                        ))

                    with patch.object(app, "_detect_pages",
                                      side_effect=capture_normal_draw):
                        app.run_normal_draw_action()
                    _assert(
                        dispatched == [([0], "left_edge", False, False, False)],
                        "ordinary GUI action failed OCR-free left_edge routing",
                    )
                    _assert(
                        _source_hash(pdic_path(first)) == marker_hash
                        and _source_hash(ppp_read_path_for_image(first)) == polygon_hash,
                        "ordinary action dispatch spy unexpectedly touched PDIC/PPP",
                    )
                finally:
                    for name, value in previous_settings.items():
                        setattr(app.settings, name, value)
                    for name, value in previous_switches.items():
                        app.quick_bool_vars[name].set(value)
                    app.lens_mode_var.set(previous_lens_label)
                    app.sync_quick_settings()
                    app.save_settings()


                for entry in app.entries:
                    if (entry.x, entry.y) == (80, 76):
                        entry.word = "synthetic-alpha-edited"
                app.save_pdic(silent=True, sync_editors=False)
                persisted = read_pdic(pdic_path(first))
                _assert(
                    {(e.word, e.x, e.y) for e in persisted}
                    == {("synthetic-alpha-edited", 80, 76), ("synthetic-beta", 85, 182)},
                    "GUI PDIC save changed marker identities or source coordinates",
                )

                added_points = [(410, 295), (515, 295), (515, 342), (410, 342)]
                app.polygons.append(PolygonRegion("", list(added_points)))
                _assert(app._save_normalized_ppp(), "GUI PPP save did not publish new polygon")
                disk_polygons = read_ppp(ppp_read_path_for_image(first))
                _assert(len(disk_polygons) == 2, "PPP save lost a polygon")
                _assert(
                    {tuple(r.points) for r in disk_polygons}
                    == {
                        ((400, 92), (500, 92), (500, 142), (400, 142)),
                        tuple(added_points),
                    },
                    "PPP save changed source polygon vertices",
                )

                app.settings.headword_custom_order = "ZYX"
                app.save_settings()
                _assert(
                    AppSettings.from_json(settings_path(root)).headword_custom_order == "ZYX",
                    "GUI settings did not persist through canonical settings path",
                )
                # Profile v3 is a separate project sidecar. Verify the real
                # schema writer/loader while the Tk project's settings are live.
                profile_file = profile_path(root)
                write_project_profile(profile_file, app.settings, force=True)
                saved_profile = json.loads(profile_file.read_text(encoding="utf-8"))
                _assert(
                    saved_profile.get("schema_version") == 3,
                    "Profile sidecar was not saved in v3",
                )
                _assert(
                    saved_profile["layout"]["columns"] == app.settings.columns,
                    "Profile columns no longer match effective settings",
                )
                loaded_profile = load_dictionary_profile(profile_file)
                _assert(
                    bool(loaded_profile.name),
                    "Profile file could not round-trip via canonical loader",
                )
                profile_sha = _source_hash(profile_file)

                app.load_page(1, skip_current_save=True)
                _assert(
                    app.current_page == second and not app.entries and not app.polygons,
                    "page navigation leaked prior page PDIC or PPP state",
                )
                app.load_page(0, skip_current_save=True)
                _assert(app.current_page == first, "could not navigate back to first page")
                _assert(
                    {(e.word, e.x, e.y) for e in app.entries}
                    == {("synthetic-alpha-edited", 80, 76), ("synthetic-beta", 85, 182)},
                    "reopened page did not reload saved PDIC source XY",
                )
                _assert(
                    {tuple(p.points) for p in app.polygons}
                    == {tuple(r.points) for r in disk_polygons},
                    "reopened page did not reload saved PPP source vertices",
                )
                # Round 63: operate the ORIGINAL Tk SECTION edit callback;
                # its persist action must write a source-coordinate v2 sidecar.
                # The two sections intentionally have a gap between markers.
                app.page_sections = [
                    PageSection(50, 215), PageSection(230, 425),
                ]
                app._set_section_editing(True)
                _assert(app._section_editing, "SECTION edit mode did not activate")
                app._drag_section_boundary = (1, "top")
                app._drag_page_section_boundary_to(95, 242)
                _assert(
                    app.page_sections == [
                        PageSection(50, 215), PageSection(242, 425),
                    ],
                    "Tk SECTION edge dragging lost source-space interval",
                )
                _assert(
                    app._finish_section_editing() is True and not app._section_editing,
                    "Tk SECTION edit completion did not commit/exit",
                )
                section_file = page_sections_path_for_image(first)
                _assert(section_file.is_file(), "SECTION v2 sidecar not written")
                section_data = json.loads(
                    section_file.read_text(encoding="utf-8"),
                )
                _assert(
                    section_data["format"] == PAGE_SECTIONS_FORMAT
                    and section_data["coordinate_space"] == SOURCE_COORDINATE_SPACE
                    and section_data["source_width"] == 640
                    and section_data["source_height"] == 460,
                    "SECTION sidecar lost v2 source-image metadata",
                )
                _assert(
                    section_data["sections"][1]["top_source_segment_xyxy"]
                    == [[0, 242], [639, 242]],
                    "SECTION dragging did not serialize original-image XY segment",
                )
                _assert(
                    read_page_sections(first)
                    == [PageSection(50, 215), PageSection(242, 425)],
                    "SECTION v2 writer/reader lost the edited interval",
                )
                first_section = section_snapshot_for_source_point(first, 85, 182)
                second_section = section_snapshot_for_source_point(first, 95, 300)
                _assert(
                    first_section is not None
                    and first_section[0] == "section:1"
                    and second_section is not None
                    and second_section[0] == "section:2"
                    and first_section[1] == second_section[1],
                    "SECTION-proofreading evidence lost section/fingerprint identity",
                )
                _assert(
                    section_snapshot_for_source_point(first, 95, 225) is None,
                    "SECTION gap was incorrectly assigned to a nearest section",
                )
                section_hash = _source_hash(section_file)
                pdic_before_section_navigation = _source_hash(pdic_path(first))
                ppp_before_section_navigation = _source_hash(
                    ppp_read_path_for_image(first),
                )
                app.load_page(1, skip_current_save=True)
                _assert(not app.page_sections, "SECTION leaked to the other page")
                app.load_page(0, skip_current_save=True)
                _assert(
                    app.page_sections == [PageSection(50, 215), PageSection(242, 425)]
                    and _source_hash(section_file) == section_hash,
                    "SECTION edit lost persistence across real Tk page navigation",
                )
                _assert(
                    _source_hash(pdic_path(first)) == pdic_before_section_navigation
                    and _source_hash(ppp_read_path_for_image(first))
                    == ppp_before_section_navigation,
                    "SECTION page roundtrip modified PDIC or PPP bytes",
                )

                # Exercise the REAL production crop planner and atomic
                # publisher on already-reloaded, original-coordinate PDIC
                # entries. No fabricated crop plan or pixel operation.
                from picture_capture.processing import split_whole_entries
                export_settings = AppSettings(
                    columns=1, layout_columns_policy="fixed",
                    column_width=500, start_y=55, bottom_y=420,
                )
                output_dir = qt_root(root) / "PWW"
                crop_records = split_whole_entries(
                    first, list(app.entries), export_settings, output_dir,
                    top_y=55, bottom_y=420,
                    integrate_illustrations=False,
                )
                _assert(
                    bool(crop_records),
                    "production crop planner generated no entry pieces",
                )
                any_ink = False
                for record in crop_records:
                    png = output_dir / record.filename
                    _assert(png.is_file(), f"crop PNG was not published: {png.name}")
                    with Image.open(png) as rendered:
                        _assert(rendered.format == "PNG", "crop is not PNG")
                        _assert(
                            rendered.size == (
                                record.box[2] - record.box[0],
                                record.box[3] - record.box[1],
                            ),
                            f"crop dimensions disagree with source box: {png.name}",
                        )
                        _assert(
                            rendered.width > 0 and rendered.height > 0,
                            "export published an empty crop",
                        )
                        # Production opaque crop is a *source-pixel* crop;
                        # pixel-for-pixel parity is stronger than dimensions.
                        with Image.open(first) as original_source:
                            expected = original_source.crop(record.box)
                        try:
                            difference = ImageChops.difference(
                                rendered.convert("RGB"), expected.convert("RGB"),
                            )
                            try:
                                _assert(
                                    difference.getbbox() is None,
                                    f"crop pixels differ from source region: {png.name}",
                                )
                            finally:
                                difference.close()
                        finally:
                            expected.close()
                        any_ink = any_ink or rendered.convert("L").getextrema()[0] < 100
                _assert(any_ink, "all produced crops lost the synthetic dark ink")
                names = (output_dir / f"{first.stem}.PWWords").read_text(encoding="utf-8")
                widths = json.loads(
                    (output_dir / f"{first.stem}.PWWWidths.json").read_text(
                        encoding="utf-8",
                    )
                )
                _assert(
                    len(names.splitlines()) == len(crop_records),
                    "PWWords lost crop rows during atomic publication",
                )
                _assert(
                    {row.filename for row in crop_records} == set(widths),
                    "crop width manifest disagrees with PNG list",
                )
                crop_plan = qt_root(root) / "CropPlan" / f"{first.stem}.json"
                _assert(crop_plan.is_file(), "source crop plan JSON missing")
                _assert(
                    not list(output_dir.glob("*.tmp")),
                    "crop transaction left orphan .tmp files",
                )
                _assert(
                    _source_hash(profile_file) == profile_sha,
                    "entry crop export unexpectedly rewrote Profile v3",
                )
                first_manifest = _source_hash(output_dir / f"{first.stem}.PWWords")
                first_widths = _source_hash(output_dir / f"{first.stem}.PWWWidths.json")
                first_crop_hashes = {
                    row.filename: _source_hash(output_dir / row.filename)
                    for row in crop_records
                }
                second_records = split_whole_entries(
                    first, list(app.entries), export_settings, output_dir,
                    top_y=55, bottom_y=420,
                    integrate_illustrations=False,
                )
                _assert(
                    [r.filename for r in second_records]
                    == [r.filename for r in crop_records],
                    "identical export changed crop naming/order",
                )
                _assert(
                    _source_hash(output_dir / f"{first.stem}.PWWords") == first_manifest
                    and _source_hash(output_dir / f"{first.stem}.PWWWidths.json") == first_widths
                    and {
                        row.filename: _source_hash(output_dir / row.filename)
                        for row in second_records
                    } == first_crop_hashes,
                    "identical export changed published PNG/manifest bytes",
                )
                _assert(
                    [(e.word, e.x, e.y) for e in read_pdic(pdic_path(first))]
                    == [(e.word, e.x, e.y) for e in app.entries],
                    "crop export rewrote PDIC labels or source positions",
                )

                # Round 62: repeat that export through the PUBLIC Tk callback,
                # not the direct processing API. Preserve the original settings
                # persistence while providing the same explicit crop defaults.
                from picture_capture.crop.settings import normalize_crop_settings_payload
                for name in (
                    "columns", "layout_columns_policy", "column_width",
                    "start_y", "bottom_y",
                ):
                    setattr(app.settings, name, getattr(export_settings, name))
                crop_config = normalize_crop_settings_payload(None, app.settings)
                crop_config.update({
                    "general_top_y": 55,
                    "general_bottom_y": 420,
                    "integrate_illustrations": False,
                    "entry_width_mode": "off",
                })
                crop_settings_file = qt_root(root) / "_CropSettings.json"
                crop_settings_file.parent.mkdir(parents=True, exist_ok=True)
                crop_settings_file.write_text(
                    json.dumps(crop_config, ensure_ascii=False), encoding="utf-8",
                )
                _assert(
                    app._load_crop_settings()["integrate_illustrations"] is False
                    and app._load_crop_settings()["entry_width_mode"] == "off",
                    "Tk crop settings did not read the saved project config",
                )
                # UI status text is shared with settings autosave: it can
                # legitimately become "参数已保存" after export completion.
                # Observe worker lifecycle and 100% progress instead; the
                # manifest/PNG hashes below verify actual published output.
                _assert(not app._batch_active, "unexpected active batch before GUI crop")
                app.split_whole_current()
                _assert(app._batch_active, "GUI crop callback did not launch batch")
                _pump_until(
                    app,
                    lambda: (
                        not app._batch_active
                        and not app._ui_worker_key_active("crop-width-normalization")
                        and app.batch_progress_var.get() == 100.0
                        and "失败" not in app.status_var.get()
                    ),
                    seconds=40,
                    description="GUI CropController asynchronous crop and width callback",
                )
                _assert(
                    app.batch_progress_var.get() == 100.0,
                    "GUI crop batch did not complete progress to 100%",
                )
                _assert(
                    _source_hash(output_dir / f"{first.stem}.PWWords") == first_manifest
                    and _source_hash(output_dir / f"{first.stem}.PWWWidths.json") == first_widths
                    and {
                        row.filename: _source_hash(output_dir / row.filename)
                        for row in crop_records
                    } == first_crop_hashes,
                    "GUI CropController export differs from direct production output",
                )
                _assert(
                    {tuple(p.points) for p in read_ppp(ppp_read_path_for_image(first))}
                    == {tuple(p.points) for p in disk_polygons},
                    "GUI crop altered PPP vertices",
                )
                _assert(
                    [(e.word, e.x, e.y) for e in read_pdic(pdic_path(first))]
                    == [(e.word, e.x, e.y) for e in app.entries],
                    "GUI crop altered source PDIC marker identities",
                )
                _assert(
                    _source_hash(profile_file) == profile_sha,
                    "GUI crop unexpectedly rewrote project Profile v3",
                )

                # A 0-SECTION edit must atomically remove the canonical sidecar
                # on a new nonmigrated project, without touching PDIC or PPP.
                pdic_before_section_clear = _source_hash(pdic_path(first))
                ppp_before_section_clear = _source_hash(
                    ppp_read_path_for_image(first),
                )
                app.page_sections = []
                app._set_section_editing(True)
                _assert(
                    app._finish_section_editing() is True,
                    "SECTION zero-count edit did not exit through Tk completion",
                )
                _assert(
                    not section_file.exists()
                    and not read_page_sections(first)
                    and section_snapshot_for_source_point(first, 85, 182) is None,
                    "SECTION=0 resurrected or left the canonical sidecar",
                )
                app.load_page(1, skip_current_save=True)
                app.load_page(0, skip_current_save=True)
                _assert(not app.page_sections, "SECTION=0 returned after page reload")
                _assert(
                    _source_hash(pdic_path(first)) == pdic_before_section_clear
                    and _source_hash(ppp_read_path_for_image(first))
                    == ppp_before_section_clear,
                    "SECTION=0 inadvertently touched PDIC or PPP",
                )

                # Second identical publication should not rewrite atomically or
                # alter the recorded bytes/timestamps of immutable source scans.
                _assert(
                    not app._save_normalized_ppp(),
                    "unchanged PPP save published a different document",
                )
                for path in (first, second):
                    _assert(
                        _source_hash(path) == original_hashes[path.name],
                        f"source scan was mutated: {path.name}",
                    )
                print(
                    "[managed-project-smoke] PASS: Tk project load; original XY; "
                    "PDIC edit/save/reopen; PPP geometry/save/reopen; settings; "
                    "two-page navigation; v3 Profile; production crop PNG pixel parity, " 
                    "PWWords/widths/plan; GUI CropController async parity; "
                    "SECTION edit/save/reopen/evidence; OCR guard and ordinary dispatch; "
                    "source image immutable",
                    flush=True,
                )
            return 0
        finally:
            try:
                app.destroy()
            finally:
                complete.set()


if __name__ == "__main__":
    raise SystemExit(main())
