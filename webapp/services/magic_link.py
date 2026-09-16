"""
Magic-link login emails for external sales reps.

External users sign in with email-only auth: they enter their address on
the login page, we generate a one-time URL-safe token, store it with a
15-minute expiry, and email them a link. Clicking the link consumes the
token and signs them in.

Email transport: Microsoft Graph (same path the Amazon weekly report
already uses). Falls back to a clear log entry if Graph isn't configured
so the calling route can show a helpful error.

Security notes
* Tokens are 32 random bytes (URL-safe base64 ~43 chars). Not guessable.
* One-time use: the consume call sets ``consumed_at`` so a leaked link
  in browser history can't be replayed.
* Expiry: 15 minutes is short enough that a stolen device shouldn't be
  able to use a stale link from someone's email.
* We don't reveal whether an email exists in our system: the login route
  returns the same "if your email is registered, you'll get a link"
  message either way (caller's responsibility, not this module).
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class MagicLinkError(RuntimeError):
    """Raised when the magic-link email could not be sent."""


def send_magic_link_email(to_email: str, link_url: str) -> None:
    """Email *to_email* a one-time login link pointing at *link_url*.

    Sends from the configured Graph mailbox (typically
    ``reports@achimonline.com``). Raises :class:`MagicLinkError` on failure
    so the caller can flash a "couldn't send" message to the user.
    """
    from config.settings import (
        get_client_id, get_client_secret, get_tenant_id,
        get_graph_email_from,
    )
    from core.email_report import _send_via_graph

    from_address = get_graph_email_from()
    if not from_address:
        raise MagicLinkError(
            "Graph email is not configured. Set EMAIL_FROM_ADDRESS in App Settings."
        )

    if not (get_tenant_id() and get_client_id() and get_client_secret()):
        raise MagicLinkError(
            "Graph credentials are not configured (GRAPH_TENANT_ID / GRAPH_CLIENT_ID / GRAPH_CLIENT_SECRET)."
        )

    subject = "Your Achim Sales Reports sign-in link"
    body_html = _build_html_body(link_url)

    try:
        _send_via_graph(
            from_address=from_address,
            to_list=[to_email],
            subject=subject,
            body=body_html,
            file_path=None,
            content_type="HTML",
        )
    except Exception as exc:
        log.exception("Magic-link email failed for %s", to_email)
        raise MagicLinkError(f"Failed to send sign-in email: {exc}") from exc


def _build_html_body(link_url: str) -> str:
    return f"""\
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif;
             color: #1f2937; line-height: 1.5; padding: 24px;">
  <h2 style="color: #111827; margin-top: 0;">Sign in to Achim Sales Reports</h2>
  <p>Click the button below to sign in. The link works once and expires in 15 minutes.</p>
  <p style="margin: 28px 0;">
    <a href="{link_url}"
       style="background: #2563eb; color: #ffffff; padding: 12px 24px;
              border-radius: 6px; text-decoration: none; font-weight: 600;
              display: inline-block;">
      Sign in
    </a>
  </p>
  <p style="color: #6b7280; font-size: 13px;">
    If the button doesn't work, copy and paste this URL into your browser:<br>
    <span style="word-break: break-all;">{link_url}</span>
  </p>
  <p style="color: #6b7280; font-size: 13px; margin-top: 32px;">
    If you didn't request this email, ignore it &mdash; no one can sign in without
    clicking the link in this message.
  </p>
</body>
</html>
"""
