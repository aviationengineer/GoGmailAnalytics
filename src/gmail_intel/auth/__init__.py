"""Authentication transports.

Two transports implement the same GmailTransport interface:

- ConnectorTransport (default here): the runtime's connected Gmail account
  manages OAuth server-side; every call goes through ``hatch_gws_cli``.
  No tokens, secrets or client files ever touch this codebase.
- OAuthTransport: direct google-api-python-client OAuth 2.0 flow for
  deployments outside this runtime (read-only scope by default,
  token stored locally, never logged). Requires google-api-python-client.

Pick via ``gmail.transport`` in config.yaml.
"""
from __future__ import annotations

import abc
import json
import os
import subprocess


def _gws_cli() -> str:
    """Path to the workspace-connector CLI (overridable for other runtimes)."""
    return os.environ.get("GMAIL_INTEL_GWS_CLI", "/opt/hatch/bin/hatch_gws_cli")


class GmailTransport(abc.ABC):
    """Minimal Gmail read surface the framework needs."""

    @abc.abstractmethod
    def raw(self, *args: str, params: dict | None = None) -> dict:
        """Run one Gmail API-style call, return the parsed JSON response."""

    @abc.abstractmethod
    def profile_email(self) -> str:
        """The account's own email address."""


class ConnectorTransport(GmailTransport):
    """Transport over the runtime's connected Gmail connector (read-only)."""

    def __init__(self, account_id: str, cli: str | None = None):
        self.account_id = account_id
        self.cli = cli or _gws_cli()
        self._email: str | None = None

    def raw(self, *args: str, params: dict | None = None) -> dict:
        cmd = [self.cli, "gmail", *args, "--account", self.account_id]
        if params is not None:
            cmd += ["--params", json.dumps(params)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        out = proc.stdout + proc.stderr
        if "connector_rate_limited" in out or "rateLimitExceeded" in out:
            raise RateLimitedError(out[-500:])
        if proc.returncode != 0:
            raise TransportError(f"gmail call failed: {out[-1000:]}")
        start = proc.stdout.find("{")
        if start < 0:
            raise TransportError(f"no JSON in response: {proc.stdout[:300]}")
        return json.loads(proc.stdout[start:])

    def profile_email(self) -> str:
        if self._email is None:
            data = self.raw("users", "getProfile", params={"userId": "me"})
            self._email = str(data.get("emailAddress", "")).strip().lower()
        return self._email


class OAuthTransport(GmailTransport):
    """Direct OAuth 2.0 transport (read-only scope default).

    Not wired in this runtime; implement with google-api-python-client:
    local token storage, no secrets in code, read-only scope unless the
    user explicitly enables more in config.
    """

    READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

    def __init__(self, client_secrets_file: str, token_file: str):
        raise NotImplementedError(
            "OAuthTransport needs google-api-python-client and user OAuth "
            "consent; use ConnectorTransport in this runtime."
        )

    def raw(self, *args: str, params: dict | None = None) -> dict:  # pragma: no cover
        raise NotImplementedError

    def profile_email(self) -> str:  # pragma: no cover
        raise NotImplementedError


class TransportError(RuntimeError):
    pass


class RateLimitedError(TransportError):
    pass


def make_transport(kind: str, account_id: str = "", **kwargs) -> GmailTransport:
    if kind == "connector":
        return ConnectorTransport(account_id)
    if kind == "oauth":
        return OAuthTransport(kwargs.get("client_secrets_file", ""),
                              kwargs.get("token_file", ""))
    raise ValueError(f"unknown gmail.transport: {kind}")
