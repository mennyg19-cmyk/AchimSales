"""Graph picker error text — 401 vs 403 tells Menny what to grant in Entra."""

from web.delivery.graph_errors import graph_error_message


class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code


class _HttpError(Exception):
    def __init__(self, status_code):
        super().__init__(f"{status_code} Client Error")
        self.response = _Resp(status_code)


def test_graph_401_mentions_admin_consent_and_permissions():
    msg = graph_error_message(_HttpError(401), what="SharePoint")
    assert "401" in msg
    assert "Files.ReadWrite.All" in msg
    assert "Sites.ReadWrite.All" in msg
    assert "admin consent" in msg.lower()


def test_graph_403_mentions_forbidden_and_permissions():
    msg = graph_error_message(_HttpError(403), what="OneDrive")
    assert "403" in msg
    assert "Files.ReadWrite.All" in msg
