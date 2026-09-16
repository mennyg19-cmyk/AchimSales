"""
Mock layer for D365 OData, authentication, and email.

Provides a ``MockD365`` helper that patches all external I/O so tests
run fully offline.  Tests register per-entity DataFrames via
``mock.odata_responses[entity_name] = df`` before calling report code.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pandas as pd


@dataclass
class MockD365:
    """Holds state for the mock layer so tests can inspect captured calls."""

    odata_responses: dict[str, pd.DataFrame] = field(default_factory=dict)
    emails_sent: list[dict] = field(default_factory=list)

    def _resolve_odata(self, base_url, entity_name, token, **kwargs):
        return self.odata_responses.get(entity_name, pd.DataFrame()).copy()

    def _resolve_batched(self, base_url, entity_name, token,
                         filter_field, filter_values, **kwargs):
        df = self.odata_responses.get(entity_name, pd.DataFrame()).copy()
        if df.empty or filter_field not in df.columns:
            return df
        str_vals = {str(v).strip() for v in filter_values}
        return df[df[filter_field].astype(str).str.strip().isin(str_vals)].reset_index(drop=True)

    def _capture_email(self, file_path, subject, body, **kwargs):
        self.emails_sent.append({
            "file_path": file_path,
            "subject": subject,
            "body": body,
            **kwargs,
        })


class _FakeTokenManager:
    """Drop-in for ``D365TokenManager`` that returns a static string."""

    def __init__(self, *args, **kwargs):
        self._token = "fake-token"

    @property
    def token(self) -> str:
        return self._token

    def __str__(self) -> str:
        return self._token


@contextmanager
def mock_d365_env():
    """Context manager that patches all D365 externals.

    Yields a ``MockD365`` instance.  Tests populate
    ``mock.odata_responses`` before calling report code.
    """
    mock = MockD365()
    stack = ExitStack()

    try:
        stack.enter_context(patch("core.odata.fetch_odata_entity", side_effect=mock._resolve_odata))
        stack.enter_context(patch("core.odata.fetch_odata_batched", side_effect=mock._resolve_batched))

        stack.enter_context(patch("core.auth.D365TokenManager", _FakeTokenManager))
        stack.enter_context(patch("core.auth.get_d365_token", return_value="fake-token"))
        stack.enter_context(patch("core.auth.get_graph_token", return_value="fake-token"))

        stack.enter_context(patch("core.email_report.send_report_email", side_effect=mock._capture_email))

        stack.enter_context(patch("config.settings.get_d365_env_url", return_value="https://fake.operations.dynamics.com"))
        stack.enter_context(patch("config.settings.get_tenant_id", return_value="fake-tenant"))
        stack.enter_context(patch("config.settings.get_client_id", return_value="fake-client-id"))
        stack.enter_context(patch("config.settings.get_client_secret", return_value="fake-secret"))
        stack.enter_context(patch("config.settings.get_company_id", return_value=""))
        stack.enter_context(patch("config.settings.validate_d365_config"))

        stack.enter_context(patch("config.settings.get_email_recipients", return_value=[]))
        stack.enter_context(patch("config.settings.get_graph_email_from", return_value=""))
        stack.enter_context(patch("config.settings.get_smtp_user", return_value=""))
        stack.enter_context(patch("config.settings.get_smtp_password", return_value=""))

        yield mock
    finally:
        stack.close()
