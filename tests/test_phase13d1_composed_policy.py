"""Phase 13D1: composed policy is anchored without legacy mutable wrappers."""
from dataclasses import replace

from PIL import Image

from picture_capture import dictionary_page_layout_policy as policy
from picture_capture import layout_composition
from picture_capture.models import AppSettings


def _settings():
    settings = AppSettings()
    settings.columns = 1
    settings.start_y = 5
    settings.manual_x = 12
    settings.column_width = 300
    settings.character_height = 14
    settings.ordinary_auto_layout = False
    return settings


def test_explicit_composition_bypasses_installed_policy_wrappers(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("composed service should not use the mutable policy name")

    monkeypatch.setattr(policy, "resolve_page_layout_policy", forbidden)
    monkeypatch.setattr(policy, "infer_dictionary_page_layout", forbidden)
    image = Image.new("RGB", (360, 140), "white")
    layout, page_settings, applied = layout_composition.infer_composed_physical_page_layout(
        image, _settings()
    )
    assert layout.columns
    assert page_settings.manual_x == 12
    assert applied == {}


def test_explicit_composition_applies_profile_anchor_exactly_once(monkeypatch):
    settings = _settings()
    settings.column_width = 1204
    observed_width = 1182
    calls = []

    def unanchored(image, profile, *, page_index=0, ops=None):
        calls.append((page_index, ops))
        resolved = replace(profile)
        resolved.column_width = observed_width
        return resolved, None, {"column_width": observed_width}

    monkeypatch.setattr(policy, "_RAW_RESOLVE_PAGE_LAYOUT_POLICY", unanchored)
    result, resolved, applied = layout_composition.infer_composed_physical_page_layout(
        Image.new("RGB", (1350, 120), "white"),
        settings,
        page_index=2,
    )
    assert len(calls) == 1
    assert calls[0][0] == 2
    assert calls[0][1] is not None
    assert resolved.column_width == 1200
    assert applied["column_width"] == 1200
    assert result.columns[0].right - result.columns[0].left == 1200


def test_raw_policy_alias_stays_unanchored_after_public_wrapper_rebinding(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(policy, "resolve_page_layout_policy",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("mutated public policy was called")))
    resolved, estimate, applied = policy._RAW_RESOLVE_PAGE_LAYOUT_POLICY(
        Image.new("RGB", (360, 140)), settings
    )
    assert resolved.manual_x == settings.manual_x
    assert estimate is None
    assert applied == {}
