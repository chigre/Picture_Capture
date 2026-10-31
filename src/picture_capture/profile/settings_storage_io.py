"""Physical owner of crash-safe AppSettings JSON read/write semantics.

The public AppSettings class stays in models.py for serialized identity. Dependencies
are resolved by the original methods at call time so monkeypatches still work.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def write_settings_json(self: Any, path: Path, *, deps: dict[str, Any]) -> None:
    """Publish whole settings JSON atomically with same-directory rollback."""
    Path = deps["Path"]
    canonicalize_app_settings_payload = deps["canonicalize_app_settings_payload"]
    _normalize_display_opacity = deps["_normalize_display_opacity"]
    asdict = deps["asdict"]
    json = deps["json"]
    tempfile = deps["tempfile"]
    os = deps["os"]
    _APP_SETTINGS_SAVE_LOCK = deps["_APP_SETTINGS_SAVE_LOCK"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonicalize_app_settings_payload(asdict(self))
    for name in ("guide_opacity", "headword_marker_opacity", "illustration_fill_opacity"):
        payload[name] = _normalize_display_opacity(payload.get(name, 40.0))
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)

    # Publish only fully written settings: interrupted writes must not
    # truncate an existing project configuration. A unique same-directory
    # temporary file also prevents parallel saves sharing a fixed .tmp.
    with _APP_SETTINGS_SAVE_LOCK:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def read_settings_json(cls: type[Any], path: Path, *, deps: dict[str, Any]) -> Any:
    """Migrate legacy configuration and preserve persisted defaults."""
    json = deps["json"]
    _normalize_display_opacity = deps["_normalize_display_opacity"]
    migrate_app_settings_payload = deps["migrate_app_settings_payload"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Existing project configs created before the 100%-width default
    # retain the historical 60% when this field was absent.
    raw.setdefault("paddle_separator_roi_width_ratio", 60.0)
    for name in ("guide_opacity", "headword_marker_opacity", "illustration_fill_opacity"):
        raw[name] = _normalize_display_opacity(raw.get(name, 40.0))
    raw = migrate_app_settings_payload(raw, cls)

    known = cls.__dataclass_fields__
    return cls(**{key: value for key, value in raw.items() if key in known})
