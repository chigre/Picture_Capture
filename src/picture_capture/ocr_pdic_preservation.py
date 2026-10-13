"""Content-addressed pre-overwrite PDIC safety snapshots for OCR drawing.

An OCR rerun must not destroy the *only* copy of a user's earlier edits.
Snapshots are immutable, project-local and deduplicated by full file SHA-256.
Do not snapshot large images, intermediate OCR tensors or repeatedly back up
the same unchanged PDIC bytes.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

from .project_storage import data_root


def preserve_prior_pdic(project_root: Path, page: Path, pdic: Path) -> Path | None:
    """Preserve raw PDIC bytes before an OCR/combined overwrite.

    A failed snapshot raises an OSError so the caller must not overwrite the
    only existing PDIC copy. A missing original needs no snapshot. Files are
    content-addressed; unchanged reruns cannot multiply the backup count.
    """
    original = Path(pdic)
    try:
        source = original.read_bytes()
    except FileNotFoundError:
        return None
    digest = hashlib.sha256(source).hexdigest()
    # Preserve raw payload (including encoding/line endings and PDIC metadata)
    # for lossless recovery, not a read_pdic/write_pdic normalization.
    location = data_root(project_root) / "OCRPrewritePDIC" / Path(page).stem
    target = location / f"{digest}.pdic"
    if target.exists():
        if target.read_bytes() != source:
            raise OSError("Existing PDIC safety snapshot checksum collision")
        return target
    location.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=location, prefix=".backup-", suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(source)
            handle.flush()
            os.fsync(handle.fileno())
        # Even an interrupted export leaves the previous PDIC intact; only
        # after this durable backup is prepared may OCR replace its original.
        os.replace(temporary, target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
