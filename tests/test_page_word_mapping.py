from __future__ import annotations

from types import SimpleNamespace

from picture_capture import app, page_word_mapping as mapping


def test_phase7d_app_reexports_page_word_mapping_helpers() -> None:
    for name in (
        "_parse_words_of_pages_text",
        "_fill_page_entries",
        "_page_word_mapping_text",
        "_compare_page_word_sequences",
        "_compare_page_word_mappings",
    ):
        assert getattr(app, name) is getattr(mapping, name)


def test_page_word_mapping_parser_preserves_page_boundaries() -> None:
    present: set[str] = set()
    parsed = mapping._parse_words_of_pages_text(
        "0001\talpha\n0001\tbeta\n0002\tgamma\n",
        ["0001", "0002"],
        present_pages=present,
    )

    assert parsed == {"0001": ["alpha", "beta"], "0002": ["gamma"]}
    assert present == {"0001", "0002"}


def test_page_word_mapping_fill_never_borrows_from_next_page() -> None:
    entries = [SimpleNamespace(word=""), SimpleNamespace(word="")]
    result = mapping._fill_page_entries(entries, ["one"])

    assert result == (1, 2, 1)
    assert [entry.word for entry in entries] == ["one", ""]


def test_page_word_mapping_compare_reports_page_local_changes() -> None:
    changes, counts = mapping._compare_page_word_mappings(
        ["0001", "0002"],
        {"0001": ["a", "b"], "0002": ["c"]},
        {"0001": ["a", "x", "b"], "0002": ["d"]},
    )

    assert counts == {
        "新增": 1,
        "删除": 0,
        "修改": 1,
        "old_rows": 3,
        "new_rows": 4,
    }
    assert [item["page"] for item in changes] == ["0001", "0002"]
    assert {item["kind"] for item in changes} == {"新增", "修改"}
