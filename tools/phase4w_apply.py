from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/picture_capture/app.py"
NEXT_STAGE = ROOT / "tests/test_next_stage_regressions.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from .ui.controllers import (\n"
        "    CanvasController, CropController, DetectionController, ExportController,\n"
        "    IllustrationController, PageController, ProjectController, ReviewController,\n"
        "    SESSION_STATE_FILENAME, SessionController,\n"
        ")\n",
        "from .ui.controllers import (\n"
        "    CanvasController, CropController, DetectionController, ExportController,\n"
        "    HeadwordController, IllustrationController, PageController, ProjectController,\n"
        "    ReviewController, SESSION_STATE_FILENAME, SessionController,\n"
        ")\n",
        "controller import",
    )

    init_marker = "        self.export_controller = ExportController(self)\n"
    init_insert = (
        init_marker
        + "        self.headword_controller = HeadwordController(\n"
        + "            self,\n"
        + "            parse_words_of_pages_text=_parse_words_of_pages_text,\n"
        + "            fill_page_entries=_fill_page_entries,\n"
        + "        )\n"
    )
    text = replace_once(text, init_marker, init_insert, "headword controller init")

    start = text.index("    @staticmethod\n    def _word_fill_file_signature(")
    end = text.index("    def import_legacy_words(", start)
    replacement = '''    def _headword_controller_for_call(self) -> HeadwordController:
        controller = self.__dict__.get("headword_controller")
        if controller is None:
            controller = HeadwordController(
                self,
                parse_words_of_pages_text=_parse_words_of_pages_text,
                fill_page_entries=_fill_page_entries,
            )
            self.__dict__["headword_controller"] = controller
        return controller

    def select_existing_headwords_file(self) -> None:
        self._headword_controller_for_call().select_existing_headwords_file()

    def fill_existing_headwords(self) -> None:
        self._headword_controller_for_call().fill_existing_headwords()

'''
    text = text[:start] + replacement + text[end:]
    APP.write_text(text, encoding="utf-8")


def patch_next_stage_test() -> None:
    text = NEXT_STAGE.read_text(encoding="utf-8")
    start = text.index('    fill_start = text.index("    def fill_existing_headwords(", app_start)')
    end = text.index("    prefetch_start = review.index(", start)
    replacement = '''    fill_start = text.index("    def fill_existing_headwords(", app_start)
    fill_end = text.index("\\n    def import_legacy_words", fill_start)
    fill_wrapper = text[fill_start:fill_end]
    assert "self._headword_controller_for_call().fill_existing_headwords()" in fill_wrapper

    headword_text = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "headword.py"
    ).read_text(encoding="utf-8")
    controller_fill_start = headword_text.index("    def fill_existing_headwords(")
    controller_fill = headword_text[controller_fill_start:]
    ensure_start = controller_fill.index("        def ensure_mapping()")
    worker_start = controller_fill.index("        def worker(", ensure_start)
    ensure = controller_fill[ensure_start:worker_start]
    assert "app._word_fill_source_mapping =" not in ensure
    assert "settings_snapshot = replace(app.settings)" in controller_fill
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in controller_fill
    assert "app._start_batch_task(" in controller_fill
    done_start = controller_fill.index("        def done(", worker_start)
    assert "app._word_fill_source_mapping = mapping" in controller_fill[done_start:]

'''
    text = text[:start] + replacement + text[end:]
    NEXT_STAGE.write_text(text, encoding="utf-8")


def main() -> None:
    patch_app()
    patch_next_stage_test()


if __name__ == "__main__":
    main()
