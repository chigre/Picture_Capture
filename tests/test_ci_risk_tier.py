"""Risk-tier CI policy unit tests. Production behavior edits must fail closed."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "ci_risk_tier", Path(__file__).resolve().parents[1] / "scripts" / "ci_risk_tier.py"
)
assert _SPEC is not None and _SPEC.loader is not None
module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(module)


def tier(changes, before="", after=""):
    return module.select_tier(changes, lambda _: before, lambda _: after)[0]


def test_docs_only():
    assert tier([("M", "docs/architecture/ROADMAP.md", "docs/architecture/ROADMAP.md")]) == "docs"
    assert tier([("M", "README.md", "README.md")]) == "docs"


def test_policy_docs_must_have_full_matrix():
    for p in ("docs/architecture/CHANGE_POLICY.md", "docs/architecture/CI_RISK_POLICY.md"):
        assert tier([("M", p, p)]) == "full"


def test_import_only_physical_rename_is_fast():
    a = "from .models import Entry\n\ndef value(x: Entry) -> int:\n    return x.y\n"
    b = "from ..models import Entry\n\ndef value(x: Entry) -> int:\n    return x.y\n"
    assert tier([("R", "src/picture_capture/symbol_evidence.py",
                  "src/picture_capture/layout/symbol_evidence.py")], a, b) == "fast"
    p = "src/picture_capture/layout/page_understanding.py"
    assert tier([("M", p, p)], a, b) == "fast"


def test_behavior_change_requires_full():
    p = "src/picture_capture/layout/page_understanding.py"
    a = "from .models import Entry\n\ndef result(x):\n    return x.y\n"
    b = "from .models import Entry\n\ndef result(x):\n    return x.y + 1\n"
    assert tier([("M", p, p)], a, b) == "full"


def test_critical_paths_full_even_on_import_only_change():
    for p in ("src/picture_capture/windows_gpu.py",
              "src/picture_capture/bootstrap/worker.py",
              "src/picture_capture/page_sections.py",
              "src/picture_capture/image_utils.py",
              "src/picture_capture/geometry/layout_transform.py",
              "src/picture_capture/marker_refinement_parallel.py"):
        assert tier([("M", p, p)], "import math\n", "import cmath\n") == "full"


def test_unknown_workflow_added_source_fail_closed():
    assert tier([("M", ".github/workflows/ci.yml", ".github/workflows/ci.yml")]) == "full"
    p = "src/picture_capture/new_business_logic.py"
    assert tier([("A", p, p)]) == "full"
    assert tier([]) == "full"


def test_guard_only_grows_for_fast_tier():
    p = "scripts/architecture_guard.py"
    assert tier([("M", p, p)], "def check():\n    return True\n",
                "def check():\n    # added guard\n    return True\n") == "fast"
    assert tier([("M", p, p)], "return False\n", "return True\n") == "full"


def test_matrix_sizes():
    fast = module.build_output("fast")
    full = module.build_output("full")
    assert fast["os313"].count('"os"') == 1
    assert fast["os310"].count('"os"') == 2
    assert full["os313"].count('"os"') == 3
    assert full["os310"].count('"os"') == 3
