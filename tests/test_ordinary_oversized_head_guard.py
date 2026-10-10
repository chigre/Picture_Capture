"""Ordinary separator regression using the supplied 121218 geometry.

The scanned dictionary bitmap is not committed; geometry is synthesized from
measured oversized ideograph connected-component extents.  Thus this tests
the filtering logic, not the complete Page Understanding classifier.
"""
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.ordinary_oversized_head_guard import suppress_oversized_head_fragment_entries


SAMPLE_CANDIDATES = (
    (84, [659, 702, 735, 766, 824, 858, 893, 927, 986, 1029, 1050, 1086,
          1149, 1182, 1215, 1249, 1313, 1358, 1383, 1413, 1476, 1521, 1547,
          1584, 3275, 3525, 3571, 3596, 3633, 4017, 4344]),
    (1669, [169, 202, 239, 265, 332, 367, 398, 433, 828, 1235, 1394, 1425,
            1469, 1497, 1563, 1597, 1632, 1661, 2948, 2989, 3017, 3049]),
)
HEAD_COMPONENTS = (
    (150, [(665, 795), (836, 962), (992, 1120), (1156, 1268),
           (1318, 1450), (1480, 1611), (3287, 3419), (3532, 3663),
           (4027, 4157), (4347, 4481)]),
    (1736, [(169, 301), (339, 473), (831, 958), (1236, 1364),
            (1399, 1529), (1562, 1681)]),
)


def _geometry_sample():
    image = Image.new("L", (3240, 4600), 255)
    pen = ImageDraw.Draw(image)
    for x, extents in HEAD_COMPONENTS:
        for y0, y1 in extents:
            # A solid connected glyph component of comparable bounding
            # dimensions to the actual oversized Chinese characters.
            pen.rectangle((x, y0, x + 135, y1 - 1), fill=0)
    candidates = [
        SimpleNamespace(x=col_x, y=y)
        for col_x, positions in SAMPLE_CANDIDATES for y in positions
    ]
    return image, candidates


def test_sample_geometry_rejects_internal_large_head_lines():
    image, entries = _geometry_sample()
    try:
        filtered = suppress_oversized_head_fragment_entries(
            entries, image, [84, 1669], [1488, 1488], 35,
        )
    finally:
        image.close()
    kept = {(entry.x, entry.y) for entry in filtered}
    assert len(entries) == 53
    assert len(filtered) == 20
    assert (84, 659) in kept
    assert (84, 702) not in kept
    assert (1669, 332) in kept
    assert (1669, 367) not in kept
    assert (84, 3275) in kept
    # Lines outside confirmed tall heads are not erased by distance alone.
    assert (1669, 2948) in kept


def test_no_large_head_and_isolated_candidates_are_untouched():
    image = Image.new("L", (900, 900), 255)
    try:
        rows = [SimpleNamespace(x=50, y=y) for y in (100, 135, 180, 260)]
        assert suppress_oversized_head_fragment_entries(
            rows, image, [50], [700], 35
        ) == rows
    finally:
        image.close()
