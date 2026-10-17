"""Batch tasks permit browsing while protecting worker-owned page files."""
from pathlib import Path
from types import SimpleNamespace

from picture_capture.app import PictureCaptureApp
from picture_capture.ui.controllers.page import PageController


ROOT = Path(__file__).resolve().parents[1]


class _Status:
    def __init__(self):
        self.value = ""

    def set(self, message):
        self.value = message


class _PageList:
    def selection(self):
        return ("2",)

    def focus(self):
        return "2"


def test_lined_export_can_browse_other_pages_without_stopping_batch():
    app = SimpleNamespace(
        _batch_active=True, _batch_foreground_pages=False,
        _batch_allow_page_navigation=True, current_index=1,
        _pending_page_index=None, project=SimpleNamespace(images=[0, 1, 2]),
        page_list=_PageList(), status_var=_Status(),
    )
    controller = PageController(app)
    requests = []
    controller.request_page_load = lambda index, **kwargs: requests.append(index) or True

    controller.on_page_select(None)
    assert requests == [2]
    assert controller.change_page(-1)
    assert requests == [2, 0]
    assert "暂不允许切换页面" not in app.status_var.value


def test_worker_owned_pages_must_not_be_resaved_during_browsing():
    predicate = PictureCaptureApp._can_save_current_during_batch_navigation

    app = SimpleNamespace(
        _batch_active=True,
        _batch_foreground_pages=False,
        _batch_allow_pdic_edits=False,
    )
    assert predicate(app) is False

    app._batch_allow_pdic_edits = True  # PPP-only discovery supports PDIC edits.
    assert predicate(app) is True

    app._batch_foreground_pages = True
    app._foreground_batch_state = lambda _i: "processing"
    app.current_index = 2
    assert predicate(app) is False

    app._foreground_batch_state = lambda _i: "manual_locked"
    assert predicate(app) is True

    app._batch_active = False
    assert predicate(app) is True


def test_read_only_batch_blocks_manual_save_and_unsafe_entry_typing():
    status = _Status()
    app = SimpleNamespace(
        project=object(), current_page=Path("page.png"), image=object(),
        _batch_active=True, _batch_foreground_pages=False,
        _batch_allow_pdic_edits=False, status_var=status,
        _can_save_current_during_batch_navigation=lambda: False,
        polygon_draw_var=SimpleNamespace(get=lambda: False),
    )
    assert PictureCaptureApp._save_current_page_by_mode(app) is None
    assert "只读" in status.value
    assert PictureCaptureApp.save_pdic(app, silent=True) is None

    app._claim_page_for_manual_edit = lambda: False
    assert PictureCaptureApp._entry_keypress_batch_guard(
        app, SimpleNamespace(keysym="a")
    ) == "break"
    assert PictureCaptureApp._entry_keypress_batch_guard(
        app, SimpleNamespace(keysym="Left")
    ) is None


def test_core_page_commit_skips_stale_foreground_autosave_in_background_jobs():
    source = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    load = source.split("    def load_page(", 1)[1].split("    def change_page(", 1)[0]
    assert load.index("skip_current_save = True") < load.index(
        "save_review_before_page_change(self, index"
    )
    assert "if self._can_save_current_during_batch_navigation():" in load
    assert "skip_current_save=True" in source


def test_refinement_and_lined_exports_inherit_navigable_batch_runner_defaults():
    source = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    crop = (ROOT / "src/picture_capture/ui/controllers/crop.py").read_text(encoding="utf-8")
    assert "allow_page_navigation: bool = True" in source
    refine = source.split("    def refine_lines_selected_scope(", 1)[1].split(
        "    def ocr_ordinary_lines_text_selected_scope(", 1
    )[0]
    assert 'self._start_parallel_batch_task(\n            "精修画线",' in refine
    assert "foreground_page_edit=True" in refine
    assert '"单行切图",\n            indices,' in crop
