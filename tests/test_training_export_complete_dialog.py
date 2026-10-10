"""Completion-dialog action regression checks."""
from pathlib import Path
from types import SimpleNamespace

import picture_capture.training_export_complete_dialog as dialog_module


def test_training_export_completion_opens_zip_parent(monkeypatch, tmp_path):
    calls = []
    class Widget:
        def __init__(self, parent=None, **kwargs):
            self.parent = parent
            self.kwargs = kwargs
        def title(self, text): calls.append(("title", text))
        def transient(self, parent): pass
        def resizable(self, *args): pass
        def protocol(self, *args): pass
        def destroy(self): calls.append(("destroy",))
        def pack(self, **kwargs): pass
        def grab_set(self): pass
        def wait_window(self): pass
    class Button(Widget):
        def __init__(self, parent=None, **kwargs):
            super().__init__(parent, **kwargs)
            if kwargs.get("text") == "打开文件夹":
                kwargs["command"]()
    monkeypatch.setattr(dialog_module.tk, "Toplevel", Widget)
    monkeypatch.setattr(dialog_module.ttk, "Frame", Widget)
    monkeypatch.setattr(dialog_module.ttk, "Label", Widget)
    monkeypatch.setattr(dialog_module.ttk, "Button", Button)
    monkeypatch.setattr(
        dialog_module, "open_project_folder_with_error",
        lambda directory, parent: calls.append(("open", directory, parent)),
    )
    parent = SimpleNamespace()
    output = tmp_path / "TrainingExports" / "dataset.zip"
    dialog_module.show_training_export_complete(parent, 3, output)
    assert ("title", "导出训练标记包完成") in calls
    opened = [row for row in calls if row[0] == "open"]
    assert len(opened) == 1
    assert opened[0][1] == output.parent
    assert isinstance(opened[0][2], Widget)
