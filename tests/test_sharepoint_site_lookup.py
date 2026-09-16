# === What's in this file ===
# Regression test for the June 2026 CEO Daily Reports outage.
#
# The SP_SITE_URL app setting pointed at a SharePoint site that doesn't exist.
# Graph returned 404 on the site lookup, and that error got swallowed and
# reported as "file not found" for every report -- which sent us hunting for
# missing files that were actually there.
#
# raises_clear_error_when_sp_site_url_points_to_missing_site -- makes sure a
# 404 on the site lookup raises a message that names SP_SITE_URL as the culprit.

import pytest


class FakeResponse:
    status_code = 404

    def raise_for_status(self):
        raise AssertionError("should have raised before raise_for_status")

    def json(self):
        return {}


def test_raises_clear_error_when_sp_site_url_points_to_missing_site(monkeypatch):
    import webapp.services.sharepoint as sp

    monkeypatch.setattr(sp, "_cached_drive_id", None)
    monkeypatch.setattr(sp, "_get_token", lambda: "fake-token")
    monkeypatch.setenv("SP_SITE_URL", "https://example.sharepoint.com/sites/DoesNotExist")
    monkeypatch.setattr(sp.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(RuntimeError, match="SP_SITE_URL"):
        sp._resolve_drive_id()