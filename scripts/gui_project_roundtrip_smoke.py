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
                _assert(not app._batch_active, "unexpected active batch before GUI crop")
                app.split_whole_current()
                _assert(app._batch_active, "GUI crop callback did not launch batch")
                _pump_until(
                    app,
                    lambda: (
                        not app._batch_active
                        and not app._ui_worker_key_active("crop-width-normalization")
                        and "已导出" in app.status_var.get()
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
                    "PWWords/widths/plan; GUI CropController async parity; source image immutable",
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
