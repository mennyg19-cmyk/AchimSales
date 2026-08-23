"""The one place that decides who someone is and what they may do."""

# === What's in this file ===
# Central authorization: every route resolves identity and permission here, not
# with ad-hoc checks scattered around. Right now it resolves a person's role
# from their email (developers/admins are privileged; everyone else is a regular
# user). Report-level and salesman-scope rules get added here in the report
# phase, so there stays exactly one place that answers "who, what, scope".
#
# resolve_role() -- map an email to a role using the configured developer list
# build_principal() -- make the immutable Principal for a freshly signed-in user

from __future__ import annotations

from ..config import Config
from ..data.connection import normalize_email
from .principal import ROLE_DEVELOPER, ROLE_USER, Principal


def resolve_role(config: Config, email: str) -> str:
    if normalize_email(email) in config.developer_emails:
        return ROLE_DEVELOPER
    return ROLE_USER


def build_principal(config: Config, email: str, name: str) -> Principal:
    email = normalize_email(email)
    return Principal(email=email, name=name or email, role=resolve_role(config, email))
