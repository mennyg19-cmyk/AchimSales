"""Rule 8: no fake stubs. Backlog reports must never masquerade as built."""

from report_engine import registry
from report_engine.registry import ReportStatus


def test_every_report_has_explicit_status():
    for spec in registry.REGISTRY:
        assert spec.status in (ReportStatus.BUILT, ReportStatus.BACKLOG)


def test_built_and_backlog_are_disjoint_and_complete():
    built = set(registry.built_reports())
    backlog = set(registry.backlog_reports())
    assert built.isdisjoint(backlog)
    assert built | backlog == set(registry.REGISTRY)


def test_lookup_unknown_key_returns_none():
    assert registry.get("does_not_exist") is None
