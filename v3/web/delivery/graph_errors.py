"""Turn Graph / token HTTP failures into a setup message the picker can show."""

from __future__ import annotations

_FILES = "Files.ReadWrite.All"
_SITES = "Sites.ReadWrite.All"


def graph_error_message(exc: BaseException, *, what: str) -> str:
    """what = 'SharePoint' or 'OneDrive'. Keep the HTTP code; say what to grant."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 401:
        return (
            f"{what} returned 401 (unauthorized). The Graph app token was rejected. "
            "In Entra: App registration → API permissions → Application permissions "
            f"(not Delegated): {_FILES} for OneDrive, {_SITES} (or {_FILES}) for SharePoint. "
            "Click Grant admin consent. Check the client secret is not expired."
        )
    if status == 403:
        return (
            f"{what} returned 403 (forbidden). The token works but the app cannot "
            f"read that drive. Grant Application {_FILES} (OneDrive of any user) and "
            f"{_SITES} (SharePoint site), then Grant admin consent. "
            "Sites.Selected also works if this site is granted to the app."
        )
    return f"{what} failed: {exc}"
