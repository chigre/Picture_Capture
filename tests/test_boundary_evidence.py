"""Boundary provenance is a non-destructive side channel, not a new PDIC."""
from types import SimpleNamespace

from picture_capture.geometry.boundary_evidence import (
    proposed_layout_boundaries, serialize_proposals,
)


class Identity:
    def canonical_to_source_point(self, x, y, _source_size):
        return x, y


def understanding():
    lines = [
        SimpleNamespace(y0=5, y1=21, role="entry", first_x=0, has_small_prefix=True),
        SimpleNamespace(y0=26, y1=43, role="body", first_x=14, has_small_prefix=False),
        SimpleNamespace(y0=51, y1=67, role="entry", first_x=92, has_small_prefix=False),
    ]
    layout = SimpleNamespace(
        columns=[SimpleNamespace(index=0, left=20, right=230, lines=lines)],
        body_top=100, source_size=(500, 700), ordinary_line_height=20,
        transform=Identity(),
    )
    return SimpleNamespace(layout=layout)


def test_evidence_records_uncertainty_without_changing_line_roles():
    data = understanding()
    before = [line.role for line in data.layout.columns[0].lines]
    proposals = proposed_layout_boundaries(data)
    assert [proposal.canonical_v for proposal in proposals] == [105, 151]
    assert len(proposals) == 2
    assert all(p.decision == "keep_legacy" for p in proposals)
    assert "small_leading_symbol" in proposals[0].positives
    assert "first_visible_row_may_continue_previous_page" in proposals[0].caveats
    assert "unusually_deep_start_check_caption_or_example" in proposals[1].caveats
    assert before == [line.role for line in data.layout.columns[0].lines]
    assert serialize_proposals(proposals) == serialize_proposals(
        proposed_layout_boundaries(data)
    )


def test_no_entry_proposals_on_a_dense_continuation_only_column():
    data = understanding()
    for row in data.layout.columns[0].lines:
        row.role = "body"
    assert proposed_layout_boundaries(data) == ()


def test_source_provenance_is_available_from_page_understanding_diagnostics():
    import picture_capture.page_understanding as page_module
    from pathlib import Path

    source = Path(page_module.__file__).read_text(encoding="utf-8")
    assert '"boundary_proposals": list(understanding.boundary_proposals)' in source
    from picture_capture import layout_core_understanding
    other = Path(layout_core_understanding.__file__).read_text(encoding="utf-8")
    assert "result.boundary_proposals = serialize_proposals(" in other
