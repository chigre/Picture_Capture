"""Synthetic R4.2 prefetch owner regression: no real project or user data."""
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
import pytest
from picture_capture.ui import review_page_lifecycle as lifecycle

@pytest.mark.parametrize("changed", [None, "review_zoom", "view_scale", "canvas_width", "settings"])
def test_prefetch_consumer_rejects_changed_render_owner(changed):
    page = Path("/synthetic/project/page-02.png")
    state = {"review_zoom": 1.0, "view_scale": 1.0, "canvas_width": 800, "settings": "v1"}
    def key():
        return (state["settings"], state["review_zoom"], state["view_scale"], state["canvas_width"])
    original_key = key()
    signature = ((True, 101, 1000), (False, 0, 0), (False, 0, 0), (False, 0, 0))
    parent = SimpleNamespace(project=SimpleNamespace(root=Path("/synthetic/project"), images=[page]))
    review = SimpleNamespace(
        parent=parent,
        _prefetch_lock=Lock(),
        _prefetched_pages={0: {"project_root": str(parent.project.root), "signature": signature,
                               "review_key": original_key, "sentinel": "original"}},
        _page_prefetch_signature=lambda _: signature,
        _review_prefetch_key=key,
    )
    if changed is not None:
        state[changed] = {"review_zoom": 1.25, "view_scale": 1.5,
                          "canvas_width": 900, "settings": "v2"}[changed]
    result = lifecycle._take_prefetched_page(review, SimpleNamespace(), 0)
    if changed is None:
        assert result is not None and result["sentinel"] == "original"
    else:
        assert result is None, f"stale cached page accepted after {changed} changed"
