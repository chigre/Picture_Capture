"""Fail-closed focused review close when its synchronous save trigger fails.

Synthetic E2 only. This tests the boundary before/at worker scheduling; it
does not infer whether an already-running writer committed and is not E3.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.ui.review_close_actions import close_review


@pytest.mark.parametrize("prior_close_intent", [False, True])
def test_focused_close_sync_flush_error_keeps_window_and_private_details_out(
    prior_close_intent, capsys,
):
    sentinel = "PRIVATE_TEST_LEMMA_C:/private/dictionary/page001.pdic"
    pending = {0: {(80, 76): {"current_word": "synthetic human correction"}}}
    statuses = []
    dialogs = []
    finishes = []

    def raise_on_sync_flush():
        raise OSError(sentinel)

    def showerror(title, body, **kwargs):
        dialogs.append((title, body, kwargs))

    review = SimpleNamespace(
        _filter_rows_active=True,
        _filter_close_after_save=prior_close_intent,
        _filter_save_running=False,
        _filter_pending_changes=pending,
        _flush_focused_changes_now=raise_on_sync_flush,
        _finish_close_review=lambda: finishes.append(True),
        parent=SimpleNamespace(status_var=SimpleNamespace(set=statuses.append)),
    )

    close_review(review, showerror=showerror)

    assert finishes == [], "uncertain save must not close the review"
    assert review._filter_close_after_save is False
    assert review._filter_pending_changes is pending
    assert pending[0][(80, 76)]["current_word"] == "synthetic human correction"
    assert len(statuses) == 1
    assert len(dialogs) == 1
    assert dialogs[0][2]["parent"] is review
    exposed = repr((statuses, dialogs, capsys.readouterr()))
    assert sentinel not in exposed
    assert "Traceback" not in exposed
    assert "保存" in statuses[0]
