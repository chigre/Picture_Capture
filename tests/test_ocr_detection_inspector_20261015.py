"""Read-only visualization distinguishes proven OCR ancestry from unknown."""
from picture_capture.ui.ocr_detection_inspector import summary_and_rows


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
