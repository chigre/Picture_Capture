from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_architecture_guard_accepts_pr161_baseline_without_new_debt() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "architecture_guard.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no debt added" in result.stdout


def test_architecture_guard_rejects_new_facade_compatibility_user() -> None:
    package = ROOT / "src" / "picture_capture"
    probe = package / "_phase9c_forbidden_facade.py"
    probe.write_text(
        "publish_core_namespace(globals(), _core)\n",
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "architecture_guard.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        probe.unlink(missing_ok=True)

    assert result.returncode == 1
    assert "new facade compatibility user: _phase9c_forbidden_facade.py" in result.stdout
