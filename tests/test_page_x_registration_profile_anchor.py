from __future__ import annotations

from picture_capture.page_x_registration import _robust_page_delta


def test_sparse_first_column_cannot_drag_two_column_profile_origin() -> None:
    # Profile predicts starts 33 / 1302. A sparse first column reports +26 px,
    # while the second column reports only +6 px. There is no page-wide
    # translation consensus, so the Profile origin must remain unchanged.
    delta, method = _robust_page_delta(
        [(33, 59, 2), (1302, 1308, 22)],
        projection_deltas=[26, 6],
        semantics="正文缩进",
        max_shift=24,
        expected_columns=2,
        seed=49.0,
    )

    assert delta == 0
    assert method == "profile_anchor"


def test_two_columns_must_agree_before_profile_origin_moves() -> None:
    delta, method = _robust_page_delta(
        [(33, 40, 8), (1302, 1310, 18)],
        projection_deltas=[7, 8],
        semantics="正文缩进",
        max_shift=24,
        expected_columns=2,
        seed=49.0,
    )

    assert delta == 8
    assert method == "multi_column_semantic"


def test_single_column_profile_can_still_register_locally() -> None:
    delta, method = _robust_page_delta(
        [(33, 39, 12)],
        projection_deltas=[6],
        semantics="正文缩进",
        max_shift=24,
        expected_columns=1,
        seed=49.0,
    )

    assert delta == 6
    assert method == "multi_column_semantic"
