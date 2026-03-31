"""Tests for the IPC layer — protocol, server, client, routing."""

from __future__ import annotations

import json
import socket
import threading
import time
from unittest.mock import MagicMock, patch

import pytest  # noqa: I001

# ── Protocol helpers ─────────────────────────────────────────────


def test_encode_produces_newline_terminated_json():
    from saturnzap.ipc import _encode

    result = _encode({"method": "get_status", "id": 1})
    assert result.endswith(b"\n")
    assert json.loads(result) == {"method": "get_status", "id": 1}


def test_decode_parses_json_line():
    from saturnzap.ipc import _decode

    data = b'{"result": {"pubkey": "02abc"}, "id": 1}'
    assert _decode(data) == {"result": {"pubkey": "02abc"}, "id": 1}


def test_encode_decode_roundtrip():
    from saturnzap.ipc import _decode, _encode

    original = {"method": "get_balance", "params": {"foo": 42}, "id": 7}
    encoded = _encode(original)
    decoded = _decode(encoded)
    assert decoded == original


def test_encode_uses_compact_separators():
    from saturnzap.ipc import _encode

    result = _encode({"a": 1, "b": 2})
    # Compact separators: no spaces after : or ,
    text = result.rstrip(b"\n").decode()
    assert " " not in text


# ── Socket path ──────────────────────────────────────────────────


def test_socket_path_uses_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from saturnzap.ipc import socket_path

    sp = socket_path()
    assert sp.name == "sz.sock"
    assert "saturnzap" in str(sp)


# ── daemon_is_running ────────────────────────────────────────────


def test_daemon_not_running_no_socket(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from saturnzap.ipc import daemon_is_running

    assert daemon_is_running() is False


def test_daemon_not_running_stale_socket(tmp_path, monkeypatch):
    """A stale socket (no listener) should be cleaned up."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from saturnzap.ipc import daemon_is_running, socket_path

    # Create parent dirs and a fake socket file
    sp = socket_path()
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.touch()
    assert sp.exists()

    assert daemon_is_running() is False
    # Stale socket should be removed
    assert not sp.exists()


def test_daemon_is_running_with_live_socket(tmp_path, monkeypatch):
    """A live socket that accepts connections → True."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from saturnzap.ipc import daemon_is_running, socket_path

    sp = socket_path()
    sp.parent.mkdir(parents=True, exist_ok=True)

    # Create a real listening socket
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sp))
    srv.listen(1)
    try:
        assert daemon_is_running() is True
    finally:
        srv.close()
        sp.unlink(missing_ok=True)


# ── IPCServer + ipc_call integration ────────────────────────────


@pytest.fixture()
def ipc_server_and_path(tmp_path, monkeypatch):
    """Start a real IPC server with mock handlers, yield (server, path)."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from saturnzap.ipc import IPCServer, socket_path

    sp = socket_path()
    sp.parent.mkdir(parents=True, exist_ok=True)

    dispatcher = {
        "echo": lambda **kw: kw,
        "add": lambda a, b: {"sum": a + b},
        "greet": lambda name="world": {"msg": f"hello {name}"},
        "fail": _raiser,
        "exit": _exit_raiser,
        "slow": lambda: _slow_handler(),
    }

    server = IPCServer(sp, dispatcher)
    server.start_background()
    # Wait for socket to appear
    for _ in range(50):
        if sp.exists():
            break
        time.sleep(0.05)
    yield server, sp
    server.stop()


def _raiser(**kw):
    msg = "test error"
    raise ValueError(msg)


def _exit_raiser(**kw):
    raise SystemExit(1)


def _slow_handler():
    time.sleep(0.2)
    return {"done": True}


def test_ipc_call_echo(ipc_server_and_path):
    from saturnzap.ipc import ipc_call

    result = ipc_call("echo", {"key": "value"})
    assert result == {"key": "value"}


def test_ipc_call_add(ipc_server_and_path):
    from saturnzap.ipc import ipc_call

    result = ipc_call("add", {"a": 3, "b": 5})
    assert result == {"sum": 8}


def test_ipc_call_default_params(ipc_server_and_path):
    from saturnzap.ipc import ipc_call

    result = ipc_call("greet")
    assert result == {"msg": "hello world"}


def test_ipc_call_with_params(ipc_server_and_path):
    from saturnzap.ipc import ipc_call

    result = ipc_call("greet", {"name": "agent"})
    assert result == {"msg": "hello agent"}


def test_ipc_call_unknown_method(ipc_server_and_path):
    from saturnzap.ipc import IPCError, ipc_call

    with pytest.raises(IPCError, match="No such method"):
        ipc_call("nonexistent")


def test_ipc_call_handler_error(ipc_server_and_path):
    from saturnzap.ipc import IPCError, ipc_call

    with pytest.raises(IPCError) as exc_info:
        ipc_call("fail")
    assert exc_info.value.code == "INTERNAL_ERROR"


def test_ipc_call_system_exit(ipc_server_and_path):
    from saturnzap.ipc import IPCError, ipc_call

    with pytest.raises(IPCError) as exc_info:
        ipc_call("exit")
    assert exc_info.value.code == "COMMAND_ERROR"


def test_ipc_call_no_socket(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from saturnzap.ipc import IPCConnectionError, ipc_call

    with pytest.raises(IPCConnectionError, match="socket not found"):
        ipc_call("get_status")


def test_ipc_server_sets_socket_permissions(ipc_server_and_path):
    import os
    import stat

    _, sp = ipc_server_and_path
    mode = os.stat(sp).st_mode
    # Should be owner rw only (0o600)
    assert stat.S_IMODE(mode) == 0o600


def test_ipc_concurrent_calls(ipc_server_and_path):
    """Multiple clients can call the server and get correct results."""
    from saturnzap.ipc import ipc_call

    results = []
    errors = []

    def call_add(a, b):
        try:
            results.append(ipc_call("add", {"a": a, "b": b}))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=call_add, args=(i, i * 10)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors
    assert len(results) == 5
    sums = sorted(r["sum"] for r in results)
    assert sums == [0, 11, 22, 33, 44]


def test_ipc_server_rejects_oversized_message(ipc_server_and_path):
    """Messages > MAX_MSG_BYTES should be rejected."""
    _, sp = ipc_server_and_path
    from saturnzap.ipc import MAX_MSG_BYTES

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect(str(sp))
    try:
        # Send a line larger than MAX_MSG_BYTES.
        # asyncio.StreamReader has a default limit (2**16).
        # readline() raises ValueError for lines over the limit,
        # which closes the connection. We test that the server
        # doesn't crash and the connection is handled gracefully.
        big_line = b"x" * (MAX_MSG_BYTES + 100) + b"\n"
        try:
            sock.sendall(big_line)
        except BrokenPipeError:
            return  # Server rejected — acceptable

        # Try to read a response — may get error or connection close
        data = b""
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
        except (ConnectionResetError, OSError):
            return  # Connection reset — server rejected

        if data:
            resp = json.loads(data.split(b"\n")[0])
            assert resp["error"]["code"] == "MSG_TOO_LARGE"
        # If no data, connection was closed — also acceptable
    finally:
        sock.close()


def test_ipc_server_rejects_invalid_json(ipc_server_and_path):
    _, sp = ipc_server_and_path

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect(str(sp))
    try:
        sock.sendall(b"not valid json\n")
        data = b""
        while b"\n" not in data:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
        resp = json.loads(data.split(b"\n")[0])
        assert resp["error"]["code"] == "INVALID_JSON"
    finally:
        sock.close()


# ── IPC routing in node.py ───────────────────────────────────────


def test_use_ipc_false_when_no_daemon(tmp_path, monkeypatch):
    """_use_ipc() returns False when no daemon socket exists."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = None
    node_mod._ipc_mode = False
    assert node_mod._use_ipc() is False


def test_use_ipc_false_when_node_running(tmp_path, monkeypatch):
    """_use_ipc() returns False when a local node is cached."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = MagicMock()
    node_mod._ipc_mode = False
    try:
        assert node_mod._use_ipc() is False
    finally:
        node_mod._node = None


def test_use_ipc_true_when_daemon_running(tmp_path, monkeypatch):
    """_use_ipc() auto-detects a daemon and sets _ipc_mode."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = None
    node_mod._ipc_mode = False

    with patch("saturnzap.ipc.daemon_is_running", return_value=True):
        assert node_mod._use_ipc() is True
    assert node_mod._ipc_mode is True
    node_mod._ipc_mode = False


def test_get_status_routes_via_ipc(tmp_path, monkeypatch):
    """get_status() calls ipc_call when in IPC mode."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = None
    node_mod._ipc_mode = True
    try:
        with patch("saturnzap.ipc.ipc_call", return_value={"pubkey": "02abc"}) as mock:
            result = node_mod.get_status()
        assert result == {"pubkey": "02abc"}
        mock.assert_called_once_with("get_status", None)
    finally:
        node_mod._ipc_mode = False


def test_get_balance_routes_via_ipc(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = None
    node_mod._ipc_mode = True
    try:
        mock_ret = {"onchain_sats": 1000}
        with patch("saturnzap.ipc.ipc_call", return_value=mock_ret) as mock:
            result = node_mod.get_balance()
        assert result == mock_ret
        mock.assert_called_once_with("get_balance", None)
    finally:
        node_mod._ipc_mode = False


def test_connect_peer_routes_via_ipc(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = None
    node_mod._ipc_mode = True
    try:
        with patch("saturnzap.ipc.ipc_call", return_value=None) as mock:
            node_mod.connect_peer("02abc", "127.0.0.1:9735")
        mock.assert_called_once_with(
            "connect_peer",
            {"node_id": "02abc", "address": "127.0.0.1:9735",
             "persist": True},
        )
    finally:
        node_mod._ipc_mode = False


def test_list_channels_routes_via_ipc(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = None
    node_mod._ipc_mode = True
    try:
        with patch("saturnzap.ipc.ipc_call", return_value=[]) as mock:
            result = node_mod.list_channels()
        assert result == []
        mock.assert_called_once_with("list_channels", None)
    finally:
        node_mod._ipc_mode = False


def test_stop_noop_in_ipc_mode(tmp_path, monkeypatch):
    """stop() should be a no-op when in IPC mode."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = None
    node_mod._ipc_mode = True
    try:
        # Should not raise or try to stop anything
        node_mod.stop()
    finally:
        node_mod._ipc_mode = False


# ── IPC routing in payments.py ───────────────────────────────────


def test_create_invoice_routes_via_ipc(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = None
    node_mod._ipc_mode = True
    try:
        invoice_ret = {"invoice": "lnbc..."}
        with patch("saturnzap.ipc.ipc_call", return_value=invoice_ret) as mock:
            from saturnzap import payments

            result = payments.create_invoice(1000, "test")
        assert result == invoice_ret
        mock.assert_called_once_with(
            "create_invoice",
            {"amount_sats": 1000, "memo": "test",
             "expiry_secs": 3600},
        )
    finally:
        node_mod._ipc_mode = False


def test_pay_invoice_routes_via_ipc(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = None
    node_mod._ipc_mode = True
    try:
        pay_ret = {"payment_id": "abc"}
        with patch("saturnzap.ipc.ipc_call", return_value=pay_ret) as mock:
            from saturnzap import payments

            result = payments.pay_invoice("lnbc1...")
        assert result == {"payment_id": "abc"}
        mock.assert_called_once_with("pay_invoice",
                                     {"invoice_str": "lnbc1...", "max_sats": None})
    finally:
        node_mod._ipc_mode = False


def test_list_transactions_routes_via_ipc(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = None
    node_mod._ipc_mode = True
    try:
        with patch("saturnzap.ipc.ipc_call", return_value=[]) as mock:
            from saturnzap import payments

            result = payments.list_transactions()
        assert result == []
        mock.assert_called_once_with("list_transactions", {"limit": 20})
    finally:
        node_mod._ipc_mode = False


# ── IPC routing in liquidity.py ──────────────────────────────────


def test_get_liquidity_status_routes_via_ipc(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    import saturnzap.node as node_mod

    node_mod._node = None
    node_mod._ipc_mode = True
    try:
        with patch("saturnzap.ipc.ipc_call", return_value={"channels": []}) as mock:
            from saturnzap import liquidity

            result = liquidity.get_status()
        assert result == {"channels": []}
        mock.assert_called_once_with("get_liquidity_status")
    finally:
        node_mod._ipc_mode = False


# ── build_dispatcher ─────────────────────────────────────────────


def test_build_dispatcher_returns_all_methods():
    from saturnzap.ipc import build_dispatcher

    d = build_dispatcher()
    expected = {
        "get_status", "get_balance", "new_onchain_address", "send_onchain",
        "list_peers", "connect_peer", "disconnect_peer",
        "list_channels", "open_channel", "close_channel",
        "force_close_channel", "wait_channel_ready",
        "create_invoice", "create_variable_invoice", "pay_invoice",
        "keysend", "list_transactions", "wait_for_payment",
        "get_liquidity_status", "request_inbound",
        "l402_fetch",
    }
    assert set(d.keys()) == expected
    for name, handler in d.items():
        assert callable(handler), f"{name} is not callable"


# ── IPCError / IPCConnectionError ────────────────────────────────


def test_ipc_error_stores_code():
    from saturnzap.ipc import IPCError

    err = IPCError("INSUFFICIENT_FUNDS", "Not enough sats")
    assert err.code == "INSUFFICIENT_FUNDS"
    assert str(err) == "Not enough sats"


def test_ipc_connection_error():
    from saturnzap.ipc import IPCConnectionError

    err = IPCConnectionError("socket not found")
    assert "socket not found" in str(err)
