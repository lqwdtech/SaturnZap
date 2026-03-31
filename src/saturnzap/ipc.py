"""IPC layer — Unix Domain Socket server, client, and protocol.

The daemon hosts an asyncio-based UDS server.  CLI commands and the MCP
server connect as thin clients, sending JSON requests and reading JSON
responses (one newline-delimited message per line).

Protocol
--------
Request:  ``{"method": "get_balance", "params": {}, "id": 1}\\n``
Response: ``{"result": {...}, "id": 1}\\n``
Error:    ``{"error": {"code": "...", "message": "..."}, "id": 1}\\n``
Stream:   ``{"stream": {"type": "heartbeat", ...}, "id": 1}\\n`` (repeating)
          ``{"result": {...}, "id": 1}\\n`` (final)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from saturnzap.config import data_dir

# Maximum message size (1 MB) — guards against malformed input.
MAX_MSG_BYTES = 1_048_576

SOCKET_NAME = "sz.sock"


def socket_path() -> Path:
    """Return the network-namespaced socket path."""
    return data_dir() / SOCKET_NAME


# ── Protocol helpers ─────────────────────────────────────────────


def _encode(obj: dict) -> bytes:
    """Serialize a dict to a newline-terminated JSON line."""
    return json.dumps(obj, separators=(",", ":")).encode() + b"\n"


def _decode(line: bytes) -> dict:
    """Deserialize a newline-terminated JSON line."""
    return json.loads(line)


# ── Server ───────────────────────────────────────────────────────


class IPCServer:
    """Asyncio-based Unix Domain Socket server.

    Parameters
    ----------
    path : Path
        Socket file path.
    dispatcher : dict[str, Callable]
        Maps method names to handler callables.  Handlers receive
        ``(**params)`` and return a JSON-serializable result.
    """

    def __init__(
        self,
        path: Path,
        dispatcher: dict[str, Callable[..., Any]],
    ) -> None:
        self._path = path
        self._dispatcher = dispatcher
        self._server: asyncio.AbstractServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        # Serialize node operations — LDK may not be fully thread-safe.
        self._lock = threading.Lock()

    # ── lifecycle ────────────────────────────────────────────

    def start_background(self) -> None:
        """Start the server in a background daemon thread."""
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ipc-server",
        )
        self._thread.start()

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        # Remove stale socket
        if self._path.exists():
            self._path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_connection, path=str(self._path),
        )
        # Restrict socket to owner only
        os.chmod(self._path, 0o600)

        async with self._server:
            with contextlib.suppress(asyncio.CancelledError):
                await self._server.serve_forever()

    def stop(self) -> None:
        """Stop the server and clean up the socket file."""
        if self._server and self._loop:
            self._loop.call_soon_threadsafe(self._server.close)
            # Give it a moment to shut down
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)
        if self._path.exists():
            self._path.unlink(missing_ok=True)

    # ── connection handler ───────────────────────────────────

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                if len(line) > MAX_MSG_BYTES:
                    writer.write(
                        _encode({"error": {"code": "MSG_TOO_LARGE",
                                           "message": "Request exceeds 1 MB"},
                                 "id": None}),
                    )
                    await writer.drain()
                    break

                try:
                    msg = _decode(line)
                except (json.JSONDecodeError, ValueError):
                    writer.write(
                        _encode({"error": {"code": "INVALID_JSON",
                                           "message": "Malformed request"},
                                 "id": None}),
                    )
                    await writer.drain()
                    continue

                req_id = msg.get("id")
                method = msg.get("method", "")
                params = msg.get("params", {})

                handler = self._dispatcher.get(method)
                if handler is None:
                    writer.write(
                        _encode({"error": {"code": "UNKNOWN_METHOD",
                                           "message": f"No such method: {method}"},
                                 "id": req_id}),
                    )
                    await writer.drain()
                    continue

                # Run handler in thread to avoid blocking the event loop
                # (LDK calls are synchronous).  Lock serializes access.
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, self._dispatch_locked, handler, params,
                    )
                    writer.write(_encode({"result": result, "id": req_id}))
                except SystemExit:
                    # output.error() raises SystemExit — catch and extract
                    writer.write(
                        _encode({"error": {"code": "COMMAND_ERROR",
                                           "message": "Command failed"},
                                 "id": req_id}),
                    )
                except Exception as exc:  # noqa: BLE001
                    writer.write(
                        _encode({"error": {"code": "INTERNAL_ERROR",
                                           "message": str(exc)},
                                 "id": req_id}),
                    )
                await writer.drain()
        finally:
            writer.close()

    def _dispatch_locked(self, handler: Callable, params: dict) -> Any:
        """Call handler under lock, capturing SystemExit from output.error()."""
        with self._lock:
            return handler(**params)


# ── Client ───────────────────────────────────────────────────────


class IPCError(Exception):
    """Raised when an IPC call returns an error response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class IPCConnectionError(Exception):
    """Raised when we can't connect to the daemon socket."""


def ipc_call(
    method: str,
    params: dict | None = None,
    *,
    timeout: float = 300.0,
) -> dict:
    """Send a JSON request to the daemon socket and return the result.

    Parameters
    ----------
    method : str
        The IPC method name (e.g. ``"get_balance"``).
    params : dict, optional
        Keyword arguments for the method.
    timeout : float
        Socket timeout in seconds (default 300 — generous for wait commands).

    Returns
    -------
    dict
        The ``result`` value from the daemon response.

    Raises
    ------
    IPCConnectionError
        If the daemon socket doesn't exist or refuses connections.
    IPCError
        If the daemon returns an error response.
    """
    sock_path = socket_path()
    if not sock_path.exists():
        raise IPCConnectionError("Daemon socket not found")

    request = {"method": method, "params": params or {}, "id": 1}

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(sock_path))
    except (ConnectionRefusedError, FileNotFoundError, OSError) as exc:
        sock.close()
        raise IPCConnectionError(f"Cannot connect to daemon: {exc}") from exc

    try:
        sock.sendall(_encode(request))

        # Read response lines until we get a result or error
        buf = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                raise IPCConnectionError("Daemon closed connection")
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                msg = _decode(line)
                if "result" in msg:
                    return msg["result"]
                if "error" in msg:
                    err = msg["error"]
                    raise IPCError(err.get("code", "UNKNOWN"), err.get("message", ""))
                # "stream" messages (heartbeats) — skip and keep reading
    finally:
        sock.close()


def daemon_is_running() -> bool:
    """Return True if the daemon socket exists and accepts connections."""
    sock_path = socket_path()
    if not sock_path.exists():
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        sock.connect(str(sock_path))
        sock.close()
        return True
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        # Stale socket — daemon crashed without cleanup
        with contextlib.suppress(OSError):
            sock_path.unlink(missing_ok=True)
        return False
    finally:
        sock.close()


# ── Dispatcher builder ───────────────────────────────────────────


def build_dispatcher() -> dict[str, Callable[..., Any]]:
    """Build the method → handler mapping for the IPC server.

    All handlers are imported lazily so the import graph stays clean.
    """
    from saturnzap import liquidity, node, payments

    return {
        # Node lifecycle
        "get_status": node.get_status,
        "get_balance": node.get_balance,
        "new_onchain_address": node.new_onchain_address,
        "send_onchain": node.send_onchain,
        # Peers
        "list_peers": node.list_peers,
        "connect_peer": node.connect_peer,
        "disconnect_peer": node.disconnect_peer,
        # Channels
        "list_channels": node.list_channels,
        "open_channel": node.open_channel,
        "close_channel": node.close_channel,
        "force_close_channel": node.force_close_channel,
        "wait_channel_ready": node.wait_channel_ready,
        # Payments
        "create_invoice": payments.create_invoice,
        "create_variable_invoice": payments.create_variable_invoice,
        "pay_invoice": payments.pay_invoice,
        "keysend": payments.keysend,
        "list_transactions": payments.list_transactions,
        "wait_for_payment": payments.wait_for_payment,
        # Liquidity
        "get_liquidity_status": liquidity.get_status,
        "request_inbound": liquidity.request_inbound,
        # L402
        "l402_fetch": lambda **kw: _l402_fetch_wrapper(**kw),
    }


def _l402_fetch_wrapper(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str | None = None,
    max_sats: int | None = None,
    timeout: float = 30.0,
) -> dict:
    """Wrapper that converts the L402 FetchResult dataclass to a dict."""
    from saturnzap import l402

    result = l402.fetch(
        url, method=method, headers=headers, body=body,
        max_sats=max_sats, timeout=timeout,
    )
    resp: dict = {
        "url": result.url,
        "http_status": result.http_status,
        "body": result.body,
        "duration_ms": result.duration_ms,
    }
    if result.payment_hash:
        resp["payment_hash"] = result.payment_hash
        resp["amount_sats"] = result.amount_sats
        resp["fee_sats"] = result.fee_sats
    return resp
