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
