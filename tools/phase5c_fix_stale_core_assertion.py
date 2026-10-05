from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tests" / "test_core.py"
text = path.read_text(encoding="utf-8")
old = '    first_row = \'(("词条切图", self.split_entries_selected_scope), ("插图切图", self.split_illustrations_selected_scope))\'\n'
new = (
    '    first_row = (\n'
    '        \'(("单行切图", self.split_single_lines_selected_scope), \'\n'
    '        \'("词条切图", self.split_entries_selected_scope), \'\n'
    '        \'("插图切图", self.split_illustrations_selected_scope))\'\n'
    '    )\n'
)
if text.count(old) != 1:
    raise RuntimeError(f"expected one stale sidebar first-row assertion, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
