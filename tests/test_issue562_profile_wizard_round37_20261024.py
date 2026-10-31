"""Round 37: Project Profile representative samples and async layout owner contracts."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from picture_capture.profile import (
    setup, wizard_sample_thumbnails, wizard_sample_analysis,
)

ROOT = Path(__file__).resolve().parents[1] / "src/picture_capture/profile"


def test_representative_methods_keep_legacy_signatures_and_physically_delegate():
    source = (ROOT / "setup.py").read_text(encoding="utf-8")
    cls = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == "ProjectProfileWizard")
    groups = (
        ("_sample_groups", "sample_groups", "_wizard_sample_thumbnails"),
        ("_show_sample_loading_state", "show_sample_loading_state", "_wizard_sample_thumbnails"),
        ("_start_sample_thumbnail_load", "start_sample_thumbnail_load", "_wizard_sample_thumbnails"),
        ("_poll_sample_thumbnail_load", "poll_sample_thumbnail_load", "_wizard_sample_thumbnails"),
        ("_render_sample_thumbnail_slot", "render_sample_thumbnail_slot", "_wizard_sample_thumbnails"),
        ("_finish_sample_thumbnail_load", "finish_sample_thumbnail_load", "_wizard_sample_thumbnails"),
        ("_start_sample_thumbnail_slot_load", "start_sample_thumbnail_slot_load", "_wizard_sample_thumbnails"),
        ("_poll_sample_thumbnail_slot_load", "poll_sample_thumbnail_slot_load", "_wizard_sample_thumbnails"),
        ("_choose_sample_page", "choose_sample_page", "_wizard_sample_thumbnails"),
        ("analyze_representative_pages", "analyze_representative_pages", "_wizard_sample_analysis"),
        ("_poll_analysis_queue", "poll_analysis_queue", "_wizard_sample_analysis"),
        ("_finish_analysis", "finish_analysis", "_wizard_sample_analysis"),
        ("apply_analysis_suggestion", "apply_analysis_suggestion", "_wizard_sample_analysis"),
    )
    for legacy, moved, module in groups:
        node = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == legacy)
        block = ast.get_source_segment(source, node)
        assert module + "." + moved + "(" in block
        assert len(block.splitlines()) < 35
        assert legacy in dir(setup.ProjectProfileWizard)
    assert "slot" in inspect.signature(setup.ProjectProfileWizard._choose_sample_page).parameters
    assert "auto_apply" in inspect.signature(setup.ProjectProfileWizard.analyze_representative_pages).parameters
    assert "image" in inspect.signature(setup.ProjectProfileWizard._render_sample_thumbnail_slot).parameters
    for file in ("wizard_sample_thumbnails.py", "wizard_sample_analysis.py"):
        content = (ROOT / file).read_text(encoding="utf-8")
        assert "from .setup import" not in content


def test_legacy_methods_forward_live_dependencies_and_original_args(monkeypatch):
    calls = []
    monkeypatch.setattr(wizard_sample_thumbnails, "choose_sample_page", lambda obj, slot, *, deps: calls.append(("choose", obj, slot, deps)))
    monkeypatch.setattr(wizard_sample_thumbnails, "start_sample_thumbnail_slot_load", lambda obj, slot, *, deps: calls.append(("slot", obj, slot, deps)))
    monkeypatch.setattr(wizard_sample_thumbnails, "render_sample_thumbnail_slot", lambda obj, slot, index, name, image, error, *, deps: calls.append(("render", obj, slot, index, name, image, error, deps)))
    monkeypatch.setattr(wizard_sample_analysis, "analyze_representative_pages", lambda obj, auto_apply, *, deps: calls.append(("analyze", obj, auto_apply, deps)))
    monkeypatch.setattr(wizard_sample_analysis, "finish_analysis", lambda obj, estimates, errors, *, deps: calls.append(("finish", obj, estimates, errors, deps)))
    obj = setup.ProjectProfileWizard.__new__(setup.ProjectProfileWizard)
    obj._choose_sample_page(2)
    obj._start_sample_thumbnail_slot_load(3)
    obj._render_sample_thumbnail_slot(1, 7, "page", None, "fail")
    obj.analyze_representative_pages(auto_apply=True)
    obj._finish_analysis([object()], ["fail"])
    assert [x[0] for x in calls] == ["choose", "slot", "render", "analyze", "finish"]
    assert calls[0][1:3] == (obj, 2) and calls[0][3]["messagebox"] is setup.messagebox
    assert calls[1][1:3] == (obj, 3) and calls[1][3]["normalize_page_rgb"] is setup.normalize_page_rgb
    assert calls[2][1:6] == (obj, 1, 7, "page", None)
    assert calls[2][7]["themed_display_image"] is setup.themed_display_image
    assert calls[3][1:3] == (obj, True) and calls[3][3]["detect_layout_parameters"] is setup.detect_layout_parameters
    assert calls[4][1] is obj and calls[4][4]["aggregate_layout_estimates"] is setup.aggregate_layout_estimates


def test_background_workers_snapshots_cancel_and_stale_generation_guards():
    th = (ROOT / "wizard_sample_thumbnails.py").read_text(encoding="utf-8")
    an = (ROOT / "wizard_sample_analysis.py").read_text(encoding="utf-8")
    whole = th[th.index("def start_sample_thumbnail_load("):th.index("def poll_sample_thumbnail_load(")]
    slot = th[th.index("def start_sample_thumbnail_slot_load("):th.index("def poll_sample_thumbnail_slot_load(")]
    picker = th[th.index("def choose_sample_page("):]
    whole_worker = whole[whole.index("    def worker()"):whole.index("    threading.Thread", whole.index("    def worker()"))]
    slot_worker = slot[slot.index("    def worker()"):slot.index("    threading.Thread", slot.index("    def worker()"))]
    assert "paths = [self.project.images[index] for index in indices]" in whole
    assert "self.project" not in whole_worker and "self.project" not in slot_worker
    assert "normalize_page_rgb(opened)" in whole_worker
    assert "result_queue.put((generation, results))" in whole_worker
    assert "self._thumbnail_load_generation" in th
    assert "self._thumbnail_slot_generation.get(slot) != generation" in th
    assert "self._start_sample_thumbnail_slot_load(slot)" in picker
    assert "self._start_sample_thumbnail_load()" not in picker
    assert "preview_uses_slot = self.template_preview_slot == slot" in picker
    assert "self.notebook.index(self.notebook.select()) == 1" in picker
    analysis = an[an.index("def analyze_representative_pages("):an.index("def poll_analysis_queue(")]
    worker = analysis[analysis.index("    def worker()"):analysis.index("    threading.Thread", analysis.index("    def worker()"))]
    assert "self.project" not in worker and "self._analysis_queue" not in worker
    assert "effective_page_settings(settings, image.size, index)" in worker
    assert "page_template_analysis_image(image, page_settings, index)" in worker
    assert "result_queue.put((estimates, errors))" in worker
    assert "self._closing" in whole and "self._closing" in slot and "self._closing" in analysis
    assert "self._analysis_revision_started != self._profile_revision" in an
    assert "成功样本不足，未自动应用" in an


def test_single_slot_worker_and_thumbnail_result_ownership_keep_tk_only_on_ui():
    th = (ROOT / "wizard_sample_thumbnails.py").read_text(encoding="utf-8")
    slot = th[th.index("def start_sample_thumbnail_slot_load("):th.index("def poll_sample_thumbnail_slot_load(")]
    worker = slot[slot.index("    def worker()"):slot.index("    threading.Thread", slot.index("    def worker()"))]
    render = th[th.index("def render_sample_thumbnail_slot("):th.index("def finish_sample_thumbnail_load(")]
    assert "ImageTk.PhotoImage" not in worker
    assert "themed_display_image(" in render
    assert "ImageTk.PhotoImage(" in render
    assert "self._render_sample_thumbnail_slot(slot, index, name, image, error)" in th
    assert "command=lambda s=slot: self._choose_sample_page(s)" in render
