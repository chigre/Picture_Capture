from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/picture_capture/app.py"
NEXT_STAGE = ROOT / "tests/test_next_stage_regressions.py"
CORE = ROOT / "tests/test_core.py"


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


def replace_test_function(text: str, name: str, next_name: str, replacement: str) -> str:
    start = text.index(f"def {name}(")
    end = text.index(f"\ndef {next_name}(", start)
    return text[:start] + replacement.rstrip() + "\n\n" + text[end + 1:]


def patch_core_tests() -> None:
    text = CORE.read_text(encoding="utf-8")
    text = replace_test_function(
        text,
        "test_v296_existing_word_fill_runs_txt_parse_and_page_commits_in_background_batch",
        "test_v298_existing_word_source_selection_is_separate_and_refill_reuses_cache",
        '''def test_v296_existing_word_fill_runs_txt_parse_and_page_commits_in_background_batch():
    root = Path(__file__).resolve().parents[1]
    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    app_start = app_text.index("    def fill_existing_headwords(self) -> None:")
    app_end = app_text.index("    def import_legacy_words(self) -> bool:", app_start)
    app_block = app_text[app_start:app_end]
    assert "self._headword_controller_for_call().fill_existing_headwords()" in app_block

    controller_text = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "headword.py"
    ).read_text(encoding="utf-8")
    start = controller_text.index("    def fill_existing_headwords(self) -> None:")
    block = controller_text[start:]
    # v2.9.8 may reuse an already parsed source; a cache miss is still parsed
    # inside the batch worker call path rather than on Tk's event thread.
    ensure_pos = block.index("        def ensure_mapping(")
    worker_pos = block.index("        def worker(")
    assert block.index("read_text_detected(txt_path)", ensure_pos) < worker_pos
    assert block.index("mapping, present_pages = ensure_mapping()", worker_pos) > worker_pos
    assert "app._start_batch_task(" in block
    assert '\"填充词条\"' in block
    assert "item_label=lambda i: pages[i].name" in block
    assert "foreground_page_edit=False" in block
    assert "进度按页面更新，可暂停或停止" in block''',
    )
    text = replace_test_function(
        text,
        "test_v298_existing_word_source_selection_is_separate_and_refill_reuses_cache",
        "test_v298_action_row_exposes_select_then_fill_buttons",
        '''def test_v298_existing_word_source_selection_is_separate_and_refill_reuses_cache():
    root = Path(__file__).resolve().parents[1]
    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    select_start = app_text.index("    def select_existing_headwords_file(self) -> None:")
    fill_start = app_text.index("    def fill_existing_headwords(self) -> None:", select_start)
    import_start = app_text.index("    def import_legacy_words(self) -> bool:", fill_start)
    assert (
        "self._headword_controller_for_call().select_existing_headwords_file()"
        in app_text[select_start:fill_start]
    )
    assert (
        "self._headword_controller_for_call().fill_existing_headwords()"
        in app_text[fill_start:import_start]
    )

    controller_text = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "headword.py"
    ).read_text(encoding="utf-8")
    select_start = controller_text.index("    def select_existing_headwords_file(self) -> None:")
    fill_start = controller_text.index("    def fill_existing_headwords(self) -> None:", select_start)
    select_block = controller_text[select_start:fill_start]
    fill_block = controller_text[fill_start:]
    assert "filedialog.askopenfilename(" in select_block
    assert "filedialog.askopenfilename(" not in fill_block
    assert "app._word_fill_source_mapping" in fill_block
    assert '\"value\": app._word_fill_source_mapping' in fill_block
    assert "app._word_fill_source_mapping = mapping" in fill_block
    assert "请先点击[选择词条文件]" in fill_block''',
    )
    text = replace_test_function(
        text,
        "test_v2115_large_existing_word_fill_avoids_full_image_decode_and_bulk_tree_updates",
        "test_v2115_pdic_repair_and_restore_use_header_only_geometry",
        '''def test_v2115_large_existing_word_fill_avoids_full_image_decode_and_bulk_tree_updates():
    root = Path(__file__).parents[1]
    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app_text.index("    def fill_existing_headwords(self) -> None:")
    end = app_text.index("    def import_legacy_words(self) -> bool:", start)
    assert "self._headword_controller_for_call().fill_existing_headwords()" in app_text[start:end]

    controller_text = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "headword.py"
    ).read_text(encoding="utf-8")
    start = controller_text.index("    def fill_existing_headwords(self) -> None:")
    body = controller_text[start:]
    assert "settings_snapshot = replace(app.settings)" in body
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in body
    assert "derive_nominal_geometry(width, height, app.settings)" not in body
    assert "page_image = normalize_page_rgb(opened)" not in body
    assert "refresh_row=False" in body''',
    )
    CORE.write_text(text, encoding="utf-8")


def main() -> None:
    patch_app()
    patch_next_stage_test()
    patch_core_tests()


if __name__ == "__main__":
    main()
