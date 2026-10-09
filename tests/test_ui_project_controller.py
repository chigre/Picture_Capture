from __future__ import annotations

import ast
from pathlib import Path

import pytest

from picture_capture.ui.controllers.project import ProjectController
import picture_capture.ui.controllers.project as project_controller_module


ROOT = Path(__file__).resolve().parents[1]


class _App:
    def __init__(self) -> None:
        self.loads: list[tuple[Path, dict]] = []
        self.errors: list[tuple[str, Exception]] = []

    @staticmethod
    def _normalize_suffix(value: str) -> str:
        suffix = str(value or "").strip().lower()
        if suffix and not suffix.startswith("."):
            suffix = "." + suffix
        return suffix

    def _load_project(self, root: Path, **kwargs) -> None:
        self.loads.append((root, dict(kwargs)))

    def show_error(self, title: str, exc: Exception) -> None:
        self.errors.append((title, exc))


def test_new_project_suffix_requires_supported_page_images(monkeypatch) -> None:
    app = _App()
    controller = ProjectController(app)
    monkeypatch.setattr(project_controller_module, "project_page_images", lambda _root: [])

    with pytest.raises(ValueError, match="没有 tif/tiff/png/jpg/jpeg/bmp"):
        controller.choose_new_project_image_suffix(Path("/project"))


def test_new_project_suffix_accepts_single_detected_extension_without_prompt(monkeypatch) -> None:
    app = _App()
    controller = ProjectController(app)
    monkeypatch.setattr(
        project_controller_module,
        "project_page_images",
        lambda _root: [Path("0001.PNG"), Path("0002.png")],
    )
    monkeypatch.setattr(
        project_controller_module.simpledialog,
        "askstring",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected prompt")),
    )

    assert controller.choose_new_project_image_suffix(Path("/project")) == ".png"


def test_new_project_suffix_retries_invalid_choice_and_allows_cancel(monkeypatch) -> None:
    app = _App()
    controller = ProjectController(app)
    monkeypatch.setattr(
        project_controller_module,
        "project_page_images",
        lambda _root: [Path("0001.png"), Path("0002.png"), Path("0003.tif")],
    )
    responses = iter(["jpg", "TIF"])
    prompts: list[str] = []
    errors: list[tuple[str, str]] = []

    def askstring(_title, _message, *, initialvalue, parent):
        assert parent is app
        prompts.append(initialvalue)
        return next(responses)

    monkeypatch.setattr(project_controller_module.simpledialog, "askstring", askstring)
    monkeypatch.setattr(
        project_controller_module.messagebox,
        "showerror",
        lambda title, message, *, parent: errors.append((title, message)),
    )

    assert controller.choose_new_project_image_suffix(Path("/project")) == ".tif"
    assert prompts == [".png", ".jpg"]
    assert len(errors) == 1
    assert ".jpg" in errors[0][1]

    monkeypatch.setattr(project_controller_module.simpledialog, "askstring", lambda *a, **k: None)
    assert controller.choose_new_project_image_suffix(Path("/project")) is None


def test_open_project_cancel_and_declined_managed_project_do_not_load(monkeypatch) -> None:
    app = _App()
    controller = ProjectController(app)

    monkeypatch.setattr(project_controller_module.filedialog, "askdirectory", lambda **_kwargs: "")
    controller.open_project()
    assert app.loads == []

    monkeypatch.setattr(
        project_controller_module.filedialog,
        "askdirectory",
        lambda **_kwargs: "/managed",
    )
    monkeypatch.setattr(project_controller_module, "is_managed_project", lambda _root: True)
    monkeypatch.setattr(
        project_controller_module.messagebox,
        "askyesno",
        lambda *args, **kwargs: False,
    )
    controller.open_project()
    assert app.loads == []


def test_open_project_preserves_existing_and_new_project_loader_requests(monkeypatch) -> None:
    app = _App()
    controller = ProjectController(app)
    chosen = {"path": "/managed"}
    monkeypatch.setattr(
        project_controller_module.filedialog,
        "askdirectory",
        lambda **_kwargs: chosen["path"],
    )
    monkeypatch.setattr(
        project_controller_module.messagebox,
        "askyesno",
        lambda title, *args, **kwargs: title != "复用现有项目参数",
    )
    monkeypatch.setattr(
        project_controller_module,
        "is_managed_project",
        lambda root: root == Path("/managed"),
    )
    monkeypatch.setattr(
        project_controller_module,
        "has_legacy_project_data",
        lambda root: root == Path("/legacy"),
    )

    controller.open_project()
    assert app.loads[-1] == (
        Path("/managed"),
        {"requested_suffix": None, "launch_profile_setup": False},
    )

    chosen["path"] = "/legacy"
    controller.open_project()
    assert app.loads[-1] == (
        Path("/legacy"),
        {"requested_suffix": None, "launch_profile_setup": False},
    )

    chosen["path"] = "/new"
    monkeypatch.setattr(controller, "choose_new_project_image_suffix", lambda _root: ".png")
    controller.open_project()
    assert app.loads[-1] == (
        Path("/new"),
        {"requested_suffix": ".png", "launch_profile_setup": True},
    )


def test_new_project_accepts_existing_volume_as_parameter_source(monkeypatch) -> None:
    app = _App()
    controller = ProjectController(app)
    choices = iter(("/new", "/source-volume"))
    monkeypatch.setattr(
        project_controller_module.filedialog,
        "askdirectory",
        lambda **_kwargs: next(choices),
    )
    monkeypatch.setattr(
        project_controller_module, "is_managed_project", lambda root: False,
    )
    monkeypatch.setattr(
        project_controller_module, "has_legacy_project_data", lambda root: False,
    )
    monkeypatch.setattr(
        project_controller_module.messagebox, "askyesno",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        controller, "choose_new_project_image_suffix", lambda root: ".png",
    )
    controller.open_project()
    assert app.loads[-1] == (
        Path("/new"),
        {
            "requested_suffix": ".png",
            "launch_profile_setup": True,
            "parameter_template_root": Path("/source-volume"),
        },
    )


def test_open_project_new_project_suffix_cancel_and_errors_preserve_existing_behavior(monkeypatch) -> None:
    app = _App()
    controller = ProjectController(app)
    monkeypatch.setattr(
        project_controller_module.filedialog,
        "askdirectory",
        lambda **_kwargs: "/new",
    )
    monkeypatch.setattr(project_controller_module, "is_managed_project", lambda _root: False)
    monkeypatch.setattr(project_controller_module, "has_legacy_project_data", lambda _root: False)
    monkeypatch.setattr(controller, "choose_new_project_image_suffix", lambda _root: None)

    controller.open_project()
    assert app.loads == []
    assert app.errors == []

    problem = RuntimeError("boom")
    monkeypatch.setattr(
        controller,
        "choose_new_project_image_suffix",
        lambda _root: (_ for _ in ()).throw(problem),
    )
    controller.open_project()
    assert app.errors == [("无法打开项目", problem)]


def test_project_controller_has_no_reverse_dependency_on_app_module() -> None:
    path = ROOT / "src/picture_capture/ui/controllers/project.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_project_controller_wiring_keeps_picture_capture_app_compatibility_methods() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (ROOT / "src/picture_capture/ui/controllers/project.py").read_text(encoding="utf-8")

    imports = app[: app.index("class PictureCaptureApp")]
    assert "ProjectController" in imports
    assert "self.project_controller = ProjectController(self)" in app
    assert app.index("self.project_controller = ProjectController(self)") < app.index("self._build_ui()")
    assert "def _project_controller_for_call(" in app
    assert 'self.__dict__.get("project_controller")' in app

    expected = {
        "_choose_new_project_image_suffix": "choose_new_project_image_suffix",
        "open_project": "open_project",
    }
    for app_method, controller_method in expected.items():
        assert f"def {app_method}(" in app
        assert f"self._project_controller_for_call().{controller_method}" in app
        assert f"def {controller_method}(" in controller
