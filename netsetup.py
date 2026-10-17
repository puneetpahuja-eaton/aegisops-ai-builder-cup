"""Process-wide TLS setup so HTTPS works behind a corporate root CA.

Uses the OS trust store (which contains the corporate root CA) via `truststore`,
and drops any CA-bundle environment variable that points to a nonexistent file
(a common corporate misconfiguration that breaks `requests`). TLS verification is
kept on throughout — nothing here disables certificate checking.
"""
from __future__ import annotations

import os

_CONFIGURED = False
_CA_VARS = ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE")


def configure_tls() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    # Drop invalid CA-bundle paths so requests/urllib3 fall back to the OS store.
    for var in _CA_VARS:
        path = os.environ.get(var)
        if path and not os.path.exists(path):
            os.environ.pop(var, None)
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass
    _CONFIGURED = True
