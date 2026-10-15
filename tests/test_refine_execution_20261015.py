"""Execution-level proof that the refine command reaches the shared Y engine."""
from dataclasses import dataclass
from types import SimpleNamespace

from PIL import Image

from picture_capture import processing_core, paddle_headwords
from picture_capture.models import AppSettings


@dataclass
class Marker:
    word: str
    x: int
    y: int


class IdentityGeometry:
    column_widths = [90]
    top = 0
    transform = SimpleNamespace(canonical_image_for_analysis=lambda image: image)

    def source_to_canonical(self, x, y):
        return int(x), int(y)

    def canonical_to_source(self, x, y):
        return int(x), int(y)

    def x_at(self, column, y):
        return 10


def test_real_refine_loop_moves_existing_y_only_without_changing_words(monkeypatch):
    image = Image.new("RGB", (130, 150), "white")
    settings = AppSettings()
    settings.paddle_refine_separator_y = True
    geometry = IdentityGeometry()
    monkeypatch.setattr(processing_core, "_page_geometry_context",
                        lambda source, effective, page_index: (
                            source, effective, source, geometry,
                        ))
    monkeypatch.setattr(processing_core, "column_index", lambda *_args: 0)
    seen = []
    def fake_shared_y(gray, coarse_y, line_height, effective, **kwargs):
        seen.append((coarse_y, gray.shape, kwargs["lower_bound"]))
        return coarse_y + 3, {"refiner": "synthetic-white-gap"}
    # The public paddle facade proxies setattr into core. Avoid contaminating
    # subsequent tests and leave the original native function untouched.
    monkeypatch.setitem(paddle_headwords.__dict__, "refine_separator_y", fake_shared_y)
    old = [Marker("alpha", 12, 43), Marker("beta", 12, 85)]
    refined, stats = processing_core.refine_existing_entries(image, old, settings)
    assert [(r.word, r.x, r.y) for r in refined] == [
        ("alpha", 12, 46), ("beta", 12, 88),
    ]
    assert [(r.x, r.y) for r in old] == [(12, 43), (12, 85)]
    assert stats["total"] == stats["moved"] == 2
    assert [r[0] for r in seen] == [43, 85]
    image.close()
