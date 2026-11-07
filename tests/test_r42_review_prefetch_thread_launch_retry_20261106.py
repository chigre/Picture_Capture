"""Synthetic R4.2 prefetch thread-launch failure/retry ownership regression.

No real scans, OCR, project files or background threads are created.
A start() exception is a possible runtime resource failure; optional
prefetch must not disrupt the ReviewWindow or pin an index as in-flight.
"""
from __future__ import annotations

from pathlib import Path
from threading import Lock
from types import SimpleNamespace

from picture_capture.ui import review_page_lifecycle as lifecycle


def _review(*, current_index=0, page_count=2):
    root = Path("/synthetic/prefetch-launch-retry")
    project = SimpleNamespace(
        root=root,
        images=[root / f"page-{i:02d}.png" for i in range(page_count)],
    )
    parent = SimpleNamespace(
        project=project,
        current_index=current_index,
        image=object(),
        settings=SimpleNamespace(tag="synthetic"),
        view_scale=1.0,
        canvas=SimpleNamespace(winfo_width=lambda: 800),
    )
    return SimpleNamespace(
        parent=parent,
        review_zoom=1.0,
        _prefetch_lock=Lock(),
        _prefetched_pages={},
        _prefetch_inflight=set(),
        _prefetch_closed=False,
        _review_prefetch_key=lambda: ("synthetic", 1.0, 1.0, 800),
        _page_prefetch_signature=lambda page: ("synthetic-signature", page.name),
    )


def _deps(factory):
    # Only launcher-bound dependencies are used: do not actually run a worker.
    unused = lambda *args, **kwargs: None
    return SimpleNamespace(
        replace=lambda settings: settings,
        Image=SimpleNamespace(),
        json=SimpleNamespace(),
        threading=SimpleNamespace(Thread=factory),
        Path=Path,
        ocr_cache_root=unused,
        ppp_read_path_for_image=lambda page: page.with_suffix(".ppp"),
        pdic_path=unused,
        read_pdic=unused,
        normalize_page_rgb=unused,
        effective_page_settings=unused,
        page_template_analysis_image=unused,
        derive_geometry=unused,
        read_page_sections=unused,
        sort_entries_reading_order=unused,
        read_ppp=unused,
        _review_crop_context=unused,
        _review_line_box=unused,
    )


def _thread_factory(events, *, fail_first=False):
    def make(*, target, name, daemon):
        assert callable(target)
        assert daemon is True
        class DeferredThread:
            def start(self):
                events.append(name)
                if fail_first and len(events) == 1:
                    raise RuntimeError("synthetic thread capacity exhausted")
                # A successful launch reserves the owner until the worker finishes.
        return DeferredThread()
    return make


def test_failed_prefetch_start_does_not_pin_index_and_next_attempt_retries():
    view = _review()
    launches = []
    deps = _deps(_thread_factory(launches, fail_first=True))

    # The first optional background start must be a safe no-op, not a Tk error.
    lifecycle._schedule_adjacent_preload(view, deps)
    assert launches == ["ReviewPrefetch-page-01"]
    assert view._prefetch_inflight == set()
    assert view._prefetched_pages == {}

    # A later ordinary scheduling request may legitimately retry this index.
    deps.threading = SimpleNamespace(Thread=_thread_factory(launches))
    lifecycle._schedule_adjacent_preload(view, deps)
    assert launches == ["ReviewPrefetch-page-01", "ReviewPrefetch-page-01"]
    assert view._prefetch_inflight == {1}


def test_failed_first_neighbor_does_not_block_independent_next_neighbor():
    view = _review(current_index=1, page_count=3)
    launches = []
    lifecycle._schedule_adjacent_preload(
        view, _deps(_thread_factory(launches, fail_first=True)),
    )
    assert launches == ["ReviewPrefetch-page-00", "ReviewPrefetch-page-02"]
    assert view._prefetch_inflight == {2}
    assert view._prefetched_pages == {}


def test_successful_prefetch_launch_keeps_single_flight_guard():
    view = _review()
    launches = []
    deps = _deps(_thread_factory(launches))
    lifecycle._schedule_adjacent_preload(view, deps)
    lifecycle._schedule_adjacent_preload(view, deps)
    assert launches == ["ReviewPrefetch-page-01"]
    assert view._prefetch_inflight == {1}
