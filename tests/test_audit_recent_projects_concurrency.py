"""Audit: registry writes by parallel app instances must use distinct temp files."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading

from picture_capture import recent_projects


def test_simultaneous_recent_project_writes_have_private_temps(monkeypatch, tmp_path):
    target = tmp_path / "recent_projects.json"
    replacement_barrier = threading.Barrier(2)
    real_replace = os.replace
    sources = []
    lock = threading.Lock()

    def synchronized_replace(source, destination):
        with lock:
            sources.append(Path(source))
        replacement_barrier.wait(timeout=10)
        real_replace(source, destination)

    monkeypatch.setattr(recent_projects.os, "replace", synchronized_replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            pool.submit(recent_projects.save_recent_projects,
                        [{"path": f"project-{index}"}], target)
            for index in range(2)
        ]
        for future in results:
            future.result(timeout=15)

    assert len({str(path) for path in sources}) == 2
    assert json.loads(target.read_text(encoding="utf-8")) in (
        [{"path": "project-0"}], [{"path": "project-1"}],
    )
    assert list(tmp_path.glob("*.tmp")) == []
