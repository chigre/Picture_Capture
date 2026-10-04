from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui.controllers import session as session_controller


ROOT = Path(__file__).resolve().parents[1]


class _Var:
    def __init__(self, value="") -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


def test_session_controller_has_no_reverse_app_dependency() -> None:
    source = Path(session_controller.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_session_controller_persists_current_session_state(tmp_path: Path) -> None:
    path = tmp_path / "session_state.json"
    app = SimpleNamespace(
        _session_path=path,
        _last_session={},
        project=SimpleNamespace(root=tmp_path / "project"),
        current_page=tmp_path / "project" / "page001.png",
        current_index=7,
        settings=SimpleNamespace(image_suffix=".png"),
        page_range_var=_Var("specified"),
        page_range_spec_var=_Var("10-20"),
        view_scale=1.25,
        appearance_preference="dark",
        section_expanded={"pages": True, "normal": False},
    )

    controller = session_controller.SessionController(app)
    controller.save_state()

    assert path.exists()
    saved = controller.read_state()
    assert saved["last_project"] == str(tmp_path / "project")
    assert saved["last_page"] == "page001.png"
    assert saved["last_page_index"] == 7
    assert saved["page_range"] == "specified"
    assert saved["page_range_spec"] == "10-20"
    assert saved["view_zoom_percent"] == 125
    assert saved["appearance_mode"] == "dark"
    assert saved["section_expanded"] == {"pages": True, "normal": False}


def test_session_restore_delegates_project_loading_with_saved_targets(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    calls = []
    status = _Var()
    page_range = _Var("current")
    page_range_spec = _Var("")

    def load_project(project_root, **kwargs) -> None:
        calls.append((project_root, kwargs))

    app = SimpleNamespace(
        _last_session={
            "last_project": str(root),
            "last_page": "page010.png",
            "last_page_index": 9,
            "image_suffix": ".png",
            "page_range": "specified",
            "page_range_spec": "10-25",
            "view_zoom_percent": 140,
        },
        status_var=status,
        page_range_var=page_range,
        page_range_spec_var=page_range_spec,
        _load_project=load_project,
    )

    session_controller.SessionController(app).restore_last_session()

    assert page_range.value == "specified"
    assert page_range_spec.value == "10-25"
    assert calls == [
        (
            root,
            {
                "requested_suffix": ".png",
                "target_page": "page010.png",
                "target_index": 9,
                "target_view_scale": 1.4,
            },
        )
    ]
    assert status.value == f"正在后台恢复上次项目：{root}"


def test_app_keeps_session_compatibility_wrappers() -> None:
    app = (ROOT / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app.index("class PictureCaptureApp")
    body = app[start:]

    assert "def _default_session_state_path(" in body
    assert "def _read_session_state(" in body
    assert "def _save_session_state(" in body
    assert "def restore_last_session(" in body
