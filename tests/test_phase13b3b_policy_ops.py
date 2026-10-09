"""Phase 13B3b: explicit Layout operations pass through policy and Profile anchoring."""
from dataclasses import replace
from types import SimpleNamespace

from PIL import Image

from picture_capture import dictionary_page_design as base
from picture_capture import dictionary_page_layout_policy as policy
from picture_capture import layout_profile_anchor as anchor
from picture_capture.models import AppSettings


def test_policy_registration_receives_explicit_ops_without_changing_defaults(monkeypatch):
    settings = AppSettings()
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_manual_x = True
    image = Image.new("RGB", (100, 80), "white")
    monkeypatch.setattr(policy, "detect_layout_parameters", lambda *_: SimpleNamespace())
    monkeypatch.setattr(base, "_analysis_page", lambda im, opts, idx: (im, im, None, opts))
    calls = []

    def register(_canonical, _settings, _estimate, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(value=37)

    monkeypatch.setattr(policy, "register_page_manual_x", register)
    raw = base.RAW_LAYOUT_OPS
    resolved, _, applied = policy.resolve_page_layout_policy(image, settings, ops=raw)
    assert calls == [{"ops": raw}]
    assert resolved.manual_x == 37
    assert applied["manual_x"] == 37
    policy.resolve_page_layout_policy(image, settings)
    assert calls[-1] == {}


def test_profile_anchor_forwards_only_explicit_ops(monkeypatch):
    # Preserve the existing installer composition and anchoring timing.
    original = policy.resolve_page_layout_policy
    seen = []

    def underlying(image, settings, *, page_index=0, **kwargs):
        seen.append((page_index, kwargs))
        return replace(settings), None, {}

    monkeypatch.setattr(policy, "resolve_page_layout_policy", underlying)
    monkeypatch.setattr(policy, "_profile_layout_anchor_installed", False, raising=False)
    anchor.install_profile_layout_anchor()
    wrapped = policy.resolve_page_layout_policy
    settings = AppSettings()
    wrapped(None, settings, page_index=4, ops=base.RAW_LAYOUT_OPS)
    wrapped(None, settings, page_index=5)
    assert seen == [(4, {"ops": base.RAW_LAYOUT_OPS}), (5, {})]
    monkeypatch.setattr(policy, "resolve_page_layout_policy", original)
