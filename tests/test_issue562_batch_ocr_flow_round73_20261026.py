"""Round 73: physical batch OCR UI flow, no lost editor or worker callbacks."""
from __future__ import annotations

from types import SimpleNamespace

from picture_capture.models import AppSettings
from picture_capture.ui.batch_ocr_flow import run_existing_pdic_batch


class Variable:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value


class FakeApp:
    def __init__(self, root):
        self.project = SimpleNamespace(
            root=root,
            images=[root / "first.png", root / "second.png"],
        )
        self.settings = AppSettings()
        self._batch_active = False
        self._batch_foreground_pages = False
        self.current_index = 0
        self.status_var = Variable()
        self.events = []
        self.batch = None

    def _guard_transformed_geometry(self, title):
        self.events.append(("geometry", title))
        return True

    def _sync_entry_editor_texts(self):
        self.events.append(("sync-editor",))

    def save_pdic(self, *, silent, sync_editors):
        self.events.append(("save-pdic", silent, sync_editors))

    def pages_tuple(self, index):
        return (str(index), "@", "@")

    def _start_batch_task(self, title, indices, worker, done, **kwargs):
        self.events.append(("schedule", title, list(indices), kwargs))
        self.batch = (worker, done)

    def load_page(self, index, *, skip_current_save):
        self.events.append(("load-page", index, skip_current_save))


def make_deps(app, *, consent=True, eligible=True):
    calls = []

    def askyesno(title, text, *, parent):
        calls.append(("prompt", title, parent))
        assert "已有 PDIC" in text
        return consent

    def process(page, index, root, settings, rules, pages, *, deps):
        calls.append(("page", page.name, index, pages, rules))
        assert page == app.project.images[index]
        assert root == app.project.root
        assert settings is not app.settings
        assert "ocr_entries" in deps and "write_pdic" in deps
        return 2

    live = {
        "read_pdic": lambda path: ["marker"] if eligible and path.stem == "first" else [],
        "pdic_path": lambda page: page.with_suffix(".PDIC"),
        "messagebox": SimpleNamespace(askyesno=askyesno),
        "load_replace_rules": lambda path: ("rules", path.name),
        "replace_rules_path": lambda root: root / "replace.json",
        "process_existing_pdic_page": process,
    }
    for key in (
        "Image", "normalize_page_rgb", "effective_page_settings",
        "page_template_analysis_image", "read_page_sections",
        "sort_entries_reading_order", "derive_geometry", "ocr_entries",
        "qt_root", "export_ocred", "write_pdic",
    ):
        live[key] = object()
    return (lambda: live), calls, live


def test_batch_selection_prompts_flushes_editor_and_schedules_first_pdic(tmp_path):
    app = FakeApp(tmp_path)
    deps, calls, live = make_deps(app)
    run_existing_pdic_batch(app, dependencies=deps)
    assert calls == [("prompt", "批量 OCR", app)]
    assert app.events[:3] == [
        ("geometry", "批量 OCR"),
        ("sync-editor",),
        ("save-pdic", True, False),
    ]
    item = app.events[3]
    assert item[0:3] == ("schedule", "批量 OCR", [0])
    assert item[3]["foreground_page_edit"] is True
    assert item[3]["allow_pdic_edits"] is True
    assert item[3]["item_label"](0) == "first.png"

    # Preserve original controller global-patching behavior: the worker must
    # resolve dependent operations at execution time, not at scheduling time.
    replacement_calls = []
    original = live["process_existing_pdic_page"]
    live["process_existing_pdic_page"] = (
        lambda *args, **kwargs: replacement_calls.append(args[0].name) or original(
            *args, **kwargs
        )
    )
    worker, done = app.batch
    assert worker(0, 1, 1) == 2
    assert replacement_calls == ["first.png"]
    assert calls[-1] == (
        "page", "first.png", 0, ("0", "@", "@"), ("rules", "replace.json"),
    )

    done(1, 1, False, [2], None)
    assert ("load-page", 0, True) in app.events
    assert app.status_var.value == "批量 OCR 完成：2 个词条"


def test_foreground_batch_stopping_does_not_reload_editable_page(tmp_path):
    app = FakeApp(tmp_path)
    app._batch_foreground_pages = True
    dependencies, _, _ = make_deps(app)
    run_existing_pdic_batch(app, dependencies=dependencies)
    _, done = app.batch
    done(1, 2, True, [2], None)
    assert not any(e[0] == "load-page" for e in app.events)
    assert app.status_var.value == "批量 OCR 已停止：完成 1/2 页，共 2 个词条"


def test_batch_completion_error_does_not_reload_or_change_status(tmp_path):
    app = FakeApp(tmp_path)
    dependencies, _, _ = make_deps(app)
    run_existing_pdic_batch(app, dependencies=dependencies)
    _, done = app.batch
    done(0, 1, False, [], RuntimeError("injected"))
    assert not any(e[0] == "load-page" for e in app.events)
    assert app.status_var.value == ""


def test_cancel_confirmation_keeps_editor_untouched(tmp_path):
    app = FakeApp(tmp_path)
    dependencies, calls, _ = make_deps(app, consent=False)
    run_existing_pdic_batch(app, dependencies=dependencies)
    assert calls == [("prompt", "批量 OCR", app)]
    assert app.events == [("geometry", "批量 OCR")]
    assert app.batch is None


def test_no_existing_pdic_does_not_prompt_or_schedule(tmp_path):
    app = FakeApp(tmp_path)
    dependencies, calls, _ = make_deps(app, eligible=False)
    run_existing_pdic_batch(app, dependencies=dependencies)
    assert calls == []
    assert app.batch is None
    assert app.status_var.value == "没有含 PDIC 词条的页面可执行批量 OCR"


def test_busy_batch_never_inspects_other_page_markers(tmp_path):
    app = FakeApp(tmp_path)
    app._batch_active = True
    dependencies, calls, _ = make_deps(app)
    run_existing_pdic_batch(app, dependencies=dependencies)
    assert calls == []
    assert app.events == []
    assert app.batch is None
