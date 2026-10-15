"""Read-only visualization distinguishes proven OCR ancestry from unknown."""
from picture_capture.ui.ocr_detection_inspector import summary_and_rows, preview_markers


def test_diagnostics_only_show_persisted_explicit_statuses():
    summary, rows = summary_and_rows({
        "summary": {"ocr_candidates": 2, "final_markers": 2, "linked": 1,
                    "unmatched_final": 1, "post_ocr_removed": 1, "post_ocr_moved": 0},
        "candidate_decisions": [
            {"candidate_id": "a", "final_status": "retained", "final_word": "Word",
             "final_source_x": 10, "final_source_y": 20, "ocr_decision_reason": "accepted"},
            {"candidate_id": "b", "final_status": "removed_after_ocr", "final_word": None},
        ],
        "final_only": [{"word": "独立", "x": 30, "y": 40,
                        "reason": "final_without_unambiguous_ocr_match"}],
    })
    assert "确切对应 1" in summary
    assert rows[0][1:4] == ("OCR保留", "Word", "10, 20")
    assert rows[1][1] == "后处理删除"
    assert rows[2][0] == "非唯一OCR来源"
    assert rows[2][1] == "独立最终词条"


def test_plot_includes_only_proven_final_pdic_coordinates():
    report = {
        "candidate_decisions": [
            {"final_selected": True, "final_source_x": 8, "final_source_y": 22,
             "final_status": "retained"},
            {"final_selected": False, "source_x": 80, "source_y": 50,
             "final_status": "removed_after_ocr"},
            {"final_selected": True, "final_source_x": 14, "final_source_y": 43,
             "final_status": "moved_by_post_ocr"},
            {"final_selected": True, "final_source_x": None, "final_source_y": None,
             "final_status": "unknown"},
        ],
        "final_only": [{"x": 50, "y": 66, "word": "independent"}],
    }
    assert preview_markers(report) == [
        (8, 22, "retained"),
        (14, 43, "moved_by_post_ocr"),
        (50, 66, "unlinked"),
    ]
