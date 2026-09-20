"""Local Tor SOCKS helper for crawlers.

Requires Docker container `tor` listening on 127.0.0.1:9050 with
IsolateSOCKSAuth (see crawler/tor/torrc). Each thread uses a distinct
SOCKS username so Tor builds a separate circuit — 429 rotates that
thread's username instead of SIGHUP (which is not NEWNYM and storms
under --aggressive).
"""

from __future__ import annotations

import socket
import threading
import time

import requests

from .base import logger

TOR_SOCKS_HOST = "127.0.0.1"
TOR_SOCKS_PORT = 9050
_ROTATE_GAP_S = 3.0


class TorProxyMixin:
    """Attach SOCKS5h to sessions; isolate + rotate circuits per thread."""

    def _check_tor(self) -> bool:
        try:
            with socket.create_connection((TOR_SOCKS_HOST, TOR_SOCKS_PORT), timeout=3):
                return True
        except OSError:
            return False

    def _socks_url(self) -> str:
        ident = threading.get_ident()
        gen = getattr(self._thread_local, "tor_circuit_gen", 0)
        return f"socks5h://w{ident}-{gen}:x@{TOR_SOCKS_HOST}:{TOR_SOCKS_PORT}"

    def _attach_tor(self, session: requests.Session) -> None:
        url = self._socks_url()
        session.proxies = {"http": url, "https": url}

    def _rotate_tor_circuit(self) -> None:
        """New SOCKS auth for this thread so Tor opens a fresh circuit."""
        if not getattr(self, "_tor_enabled", False):
            return
        last = getattr(self._thread_local, "tor_rotate_at", 0.0)
        wait = _ROTATE_GAP_S - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        gen = getattr(self._thread_local, "tor_circuit_gen", 0) + 1
        self._thread_local.tor_circuit_gen = gen
        self._thread_local.tor_rotate_at = time.monotonic()
        session = getattr(self._thread_local, "session", None) or self.session
        self._attach_tor(session)
        logger.info(f"Tor: new circuit gen={gen}")

    def _build_session(self) -> requests.Session:
        session = super()._build_session()
        self._tor_enabled = self._check_tor()
        if self._tor_enabled:
            self._attach_tor(session)
            if not getattr(self, "_tor_logged", False):
                logger.info(
                    "Tor SOCKS5 :9050 up — IsolateSOCKSAuth per thread/circuit"
                )
                self._tor_logged = True
        elif not getattr(self, "_tor_logged", False):
            logger.warning(
                "Tor SOCKS5 :9050 not reachable — crawling direct (429 risk)"
            )
            self._tor_logged = True
        return session

    def _on_rate_limited(self) -> None:
        super()._on_rate_limited()
        self._rotate_tor_circuit()
