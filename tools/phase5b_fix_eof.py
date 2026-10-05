from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tests" / "test_postproduction_single_line_runtime.py"
text = path.read_text(encoding="utf-8")
path.write_text(text.rstrip() + "\n", encoding="utf-8")
