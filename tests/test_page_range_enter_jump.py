"""The specified-page field and Jump button share one navigation action."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_specified_range_enter_invokes_existing_jump_action():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index('page_range_entry = ttk.Entry(')
    end = source.index("size_row = ttk.Frame(", start)
    snippet = source[start:end]
    assert "textvariable=self.page_range_spec_var" in snippet
    assert 'page_range_entry.bind("<Return>", lambda _event: self.jump_to_page_spec())' in snippet
    assert 'command=self.jump_to_page_spec' in source
    assert source.count("def jump_to_page_spec(") == 1
