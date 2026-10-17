"""Settings dialog must show the actual bad value and allow a safe escape.

These tests run without Tk GUI display; the real Windows close button,
window X, and Escape all route to lifecycle.close_validated.
"""
from types import SimpleNamespace

import pytest

from picture_capture.models import AppSettings
from picture_capture.ui.settings import lifecycle


class Var:
    def __init__(self, raw):
        self.raw = raw

    def get(self):
        return self.raw

    def set(self, value):
        self.raw = value


@pytest.mark.parametrize(
    "raw", ["0.01", "0.25", "0.3", " 0.30 ", "0，25", "0,25", "0．25", "0。25"],
)
def test_separator_fraction_valid_including_endpoints(raw):
    var = Var(raw)
    lifecycle.validate_separator_gap_controls({
        "separator_y_ink_safe_max_fraction": var,
    })
    settings = AppSettings()
    settings.separator_y_ink_safe_max_fraction = float(var.get())
    assert 0.01 <= settings.separator_y_ink_safe_max_fraction <= 0.30


@pytest.mark.parametrize("raw", ["0.009", "0.31", "0.45", "NaN", "Infinity"])
def test_separator_fraction_invalid_diagnostic_identifies_actual_input(raw):
    with pytest.raises(ValueError) as excinfo:
        lifecycle.validate_separator_gap_controls({
            "separator_y_ink_safe_max_fraction": Var(raw),
        })
    error = str(excinfo.value)
    assert "separator_y_ink_safe_max_fraction" in error
    assert repr(raw) in error


class Dialog:
    def __init__(self, *, ok=False):
        self.parent = SimpleNamespace(settings=AppSettings())
        self._autosave_job = "pending"
        self._last_settings_error = (
            "separator_y_ink_safe_max_fraction 当前输入 '0.45'，必须在 0.01–0.3 之间。"
        )
        self.ok = ok
        self.cancelled = []
        self.destroyed = False
        self.status = []
        self._settings_save_status_var = SimpleNamespace(set=self.status.append)

    def after_cancel(self, job):
        self.cancelled.append(job)

    def save(self, *, close, show_errors):
        # Simulate the historical partial-setting mutation before failure.
        self.parent.settings.columns = 7
        if close and self.ok:
            self.destroy()
        return self.ok

    def destroy(self):
        self.destroyed = True


@pytest.mark.parametrize("discard", [True, False])
def test_invalid_close_is_not_a_trap_and_avoids_partial_mutation(
    monkeypatch, discard,
):
    dialog = Dialog()
    prompts = []

    def askyesno(title, message, **kwargs):
        prompts.append((title, message, kwargs))
        return discard

    monkeypatch.setattr(lifecycle.messagebox, "askyesno", askyesno)
    lifecycle.close_validated(dialog)

    assert dialog.cancelled == ["pending"]
    assert dialog._autosave_job is None
    assert dialog.parent.settings.columns == AppSettings().columns
    assert dialog.destroyed is discard
    assert len(prompts) == 1
    assert "0.45" in prompts[0][1]
    assert "放弃未保存的输入" in prompts[0][1]
    assert prompts[0][2]["default"] == "no"


def test_failed_autosave_rolls_back_partial_in_memory_values():
    dialog = Dialog()
    lifecycle.run_autosave(dialog)
    assert dialog.parent.settings.columns == AppSettings().columns
    assert "暂未保存" in dialog.status[-1]


def test_valid_close_never_prompts_for_discard(monkeypatch):
    dialog = Dialog(ok=True)

    def must_not_prompt(*args, **kwargs):
        raise AssertionError("Valid settings must close without discard prompt")

    monkeypatch.setattr(lifecycle.messagebox, "askyesno", must_not_prompt)
    lifecycle.close_validated(dialog)
    assert dialog.destroyed
    assert dialog.parent.settings.columns == 7
