#!/usr/bin/env python3






from __future__ import annotations

import argparse
import base64
import hashlib
import binascii
from collections import deque
import sys
if sys.platform != "win32":
    import fcntl
import http.client
import importlib.util
import json
import math
import os
from pathlib import Path
import queue
import random
import re
import runpy
import signal
import socket
import ssl
import stat
import struct
import sys
import threading
import time
from urllib.parse import unquote_to_bytes, urlsplit

if sys.platform == "win32":
    import importlib.util as _win_import
    _win_spec = _win_import.spec_from_file_location("eh_win_platform", Path(__file__).resolve().with_name("win_platform.py"))
    win = _win_import.module_from_spec(_win_spec); _win_spec.loader.exec_module(win)
else:
    win = None



_tls_spec = importlib.util.spec_from_file_location('eh_tls_channel', Path(__file__).resolve().with_name('tls_channel.py'))
_tls_module = importlib.util.module_from_spec(_tls_spec)
_tls_spec.loader.exec_module(_tls_module)
TLSChannel, ChannelError = _tls_module.TLSChannel, _tls_module.ChannelError
TransportStageTrace = _tls_module.TransportStageTrace
PROGRESS_PROFILE = _tls_module.PROGRESS_PROFILE
PROGRESS_HEARTBEAT_SECONDS = 45.0

PROTOCOL = "eh-connector/1"
MAX_FRAME = 2 * 1024 * 1024
MAX_HTTP_BODY = 1024 * 1024
MAX_CHUNK = 65536
MAX_STREAMS = 16
MAX_CLOSED_STREAMS = 256
MAX_HTTP_REQUESTS = 4
MAX_WORKERS = 48
MAX_OUTGOING_BYTES = 2 * MAX_FRAME
MAX_HTTP_SECONDS = 10.0
FRAME_SECONDS = 10.0


WRITE_SECONDS = 8.0
QUEUE_SECONDS = 10.0
SHUTDOWN_SECONDS = 6.0
_ID = re.compile(r"[0-9a-f]{32}\Z")
_DEVICE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_BROWSER_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class ConnectorError(Exception):
    pass


_SAFE_ERRORS = frozenset(['worker_shutdown_incomplete', 'transport_shutdown_incomplete', 'browser_connector_already_running', 'browser_discovery_failed', 'browser_discovery_mismatch', 'browser_endpoint_changed', 'browser_lock_changed', 'browser_not_running', 'browser_ownership_changed', 'browser_ownership_lost', 'browser_ownership_unverified', 'browser_profile_changed', 'browser_setup_failed', 'connector_connection_failed', 'connector_failed', 'connector_failure', 'connector_is_single_use', 'duplicate_http_id', 'duplicate_input_id', 'duplicate_stream_id', 'epoch_mismatch', 'file_too_large', 'frame_timeout', 'heartbeat_timeout', 'hub_closed_connection', 'hub_rejected_connection', 'invalid_browser_endpoint', 'invalid_browser_identity', 'invalid_browser_launch_args', 'invalid_ca_file', 'invalid_config', 'invalid_config_file', 'invalid_device', 'invalid_frame_json', 'invalid_frame_length', 'invalid_heartbeat_settings', 'invalid_message_id', 'invalid_outbound_frame', 'invalid_stream_data', 'invalid_tls_host', 'invalid_tls_port', 'invalid_token', 'invalid_welcome', 'local_http_body_too_large', 'local_http_timeout', 'local_stream_backpressure', 'outbound_backpressure', 'outbound_frame_too_large', 'stopped', 'stream_not_open', 'tls_certificate_rejected', 'transport_closed', 'transport_write_failed', 'truncated_frame', 'unknown_message_type', 'unsafe_browser_lock', 'unsafe_file', 'worker_capacity', 'worker_failure', 'worker_start_failed'])

_DIAGNOSTIC_CLASSES = frozenset({'TimeoutError', 'OSError', 'ConnectionResetError',
    'ConnectionAbortedError', 'BrokenPipeError', 'ConnectionRefusedError', 'EOFError',
    'SSLError', 'SSLCertVerificationError', 'SSLEOFError', 'SSLZeroReturnError',
    'ValueError', 'JSONDecodeError', 'UnicodeDecodeError', 'RecursionError',
    'ConnectorError', 'RuntimeError', 'BlockingIOError', 'InterruptedError',
    'SSLWantReadError', 'SSLWantWriteError'})
_SSL_REASONS = frozenset({'CERTIFICATE_VERIFY_FAILED', 'UNEXPECTED_EOF_WHILE_READING',
    'SSLV3_ALERT_BAD_RECORD_MAC', 'DECRYPTION_FAILED_OR_BAD_RECORD_MAC',
    'TLSV1_ALERT_UNKNOWN_CA', 'SSLV3_ALERT_CERTIFICATE_EXPIRED',
    'WRONG_VERSION_NUMBER', 'TLSV1_ALERT_PROTOCOL_VERSION', 'SHUTDOWN_WHILE_IN_INIT'})


def safe_diagnostic(reason, phase, exc=None, epoch=None, operation='none', thread_role='caller', occurred=None):
    
    name = type(exc).__name__ if exc is not None else None
    number = getattr(exc, 'errno', None)
    ssl_reason = getattr(exc, 'reason', None) if isinstance(exc, ssl.SSLError) else None
    return {'schema': 'eh-transport-error/1', 'reason': reason if reason in _SAFE_ERRORS else 'connector_failure',
            'phase': phase if phase in {'read', 'write', 'protocol', 'heartbeat', 'lifecycle',
                                      'registry', 'connect', 'tls', 'hello', 'ownership', 'worker'} else 'lifecycle',
            'at_unix': occurred.at_unix if isinstance(occurred, ChannelError) else time.time(),
            'monotonic_ns': occurred.monotonic_ns if isinstance(occurred, ChannelError) else time.monotonic_ns(),
            'owner_pid': os.getpid(),
            'operation': operation if operation in {'none','tls_handshake','recv_header','recv_body','send_frame','shutdown','close','dispatch','queue','select'} else 'none',
            'thread_role': thread_role if thread_role in {'tls_io','caller'} else 'caller',
            'epoch': epoch if isinstance(epoch, str) and re.fullmatch(r'[a-f0-9]{32}', epoch) else None,
            'exception_class': name if name in _DIAGNOSTIC_CLASSES else ('OtherError' if exc is not None else None),
            'errno': number if type(number) is int and 0 <= number <= 4095 else None,
            'ssl_reason': ssl_reason if isinstance(ssl_reason, str) and ssl_reason in _SSL_REASONS else ('OTHER_SSL_ERROR' if isinstance(exc, ssl.SSLError) else None),
            'transport': _tls_module.safe_transport_details(occurred.details) if isinstance(occurred, ChannelError) else {}}


def _json_object(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    def invalid_constant(_):
        raise ValueError("non-finite number")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value


def _owned_file(path, limit, *, mode=None):
    
    if win: return win.read_file(path, limit, allow_admin_owner=mode is None)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or (mode is not None and stat.S_IMODE(info.st_mode) != mode)):
            raise ConnectorError("unsafe_file")
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ConnectorError("file_too_large")
    return raw


def load_config(path):
    
    try:
        return validate_config(_json_object(_owned_file(
            Path(path).expanduser().absolute(), 32768, mode=0o600)))
    except ConnectorError:
        raise
    except (OSError, ValueError, TypeError, RecursionError):
        raise ConnectorError("invalid_config_file") from None


def validate_config(value):
    
    if not isinstance(value, dict) or set(value) - {
            "host", "port", "server_hostname", "ca_file", "device", "token"}:
        raise ConnectorError("invalid_config")
    result = dict(value)
    host = result.get("host")
    hostname = result.get("server_hostname", host)
    for name in (host, hostname):
        if (not isinstance(name, str) or not 1 <= len(name) <= 253
                or any(ord(c) <= 32 or ord(c) >= 127 for c in name)
                or any(c in name for c in "/\\?#@")):
            raise ConnectorError("invalid_tls_host")
    port = result.get("port")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ConnectorError("invalid_tls_port")
    if not isinstance(result.get("device"), str) or not _DEVICE.fullmatch(result["device"]):
        raise ConnectorError("invalid_device")
    token = result.get("token")
    if (not isinstance(token, str) or not 16 <= len(token) <= 512
            or any(ord(c) <= 32 or ord(c) >= 127 for c in token)):
        raise ConnectorError("invalid_token")
    ca_file = result.get("ca_file")
    if ca_file is not None:
        if not isinstance(ca_file, str) or not ca_file:
            raise ConnectorError("invalid_ca_file")
        result["ca_file"] = str(Path(ca_file).expanduser().absolute())
    result["server_hostname"] = hostname
    return result


def _close_socket(sock):
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass



LOCAL_INPUT_PROFILE = "local_input_v1"
LOCAL_INPUT_DIAGNOSTICS_PROFILE = "local_input_diagnostics_v1"
LOCAL_INPUT_MAX_TEXT_CHARS = 64
LOCAL_INPUT_MAX_TEXT_BYTES = 512
LOCAL_INPUT_MAX_CLEAR_CHARS = 128
LOCAL_INPUT_SECONDS = 20.0
LOCAL_INPUT_MAX_IDS = 4096
_LOCAL_INPUT_TARGET = re.compile(r"/devtools/page/[A-Za-z0-9_-]{1,128}\Z")
_LOCAL_INPUT_KEYS = {"Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8,
                     "Delete": 46, "ArrowDown": 40, "ArrowUp": 38,
                     "ArrowLeft": 37, "ArrowRight": 39, "End": 0, "Home": 0}
_LOCAL_INPUT_ERRORS = frozenset({"invalid_input", "target_unavailable", "not_editable",
    "clear_limit", "input_busy", "input_id_reused", "input_capacity", "input_stopped",
    "input_timeout", "input_cdp_error", "input_transport_error", "input_ownership_lost"})


def _local_input_operation(payload):
    operation = payload.get("operation") if isinstance(payload, dict) else None
    return operation if type(operation) is str and operation in {
        "press_key", "insert_text_slow", "clear_input_via_keys"} else "unknown"


def _local_input_diagnostic(operation, stage, error, status, dispatch_state,
                            side_effect, elapsed_ms):

    return {"schema": "eh-local-input/1", "scope": "primitive", "source": "client",
            "stage": stage, "operation": operation, "error": error,
            "receipt_status": status, "dispatch_state": dispatch_state,
            "side_effect": "possible" if side_effect else "none",
            "elapsed_ms": min(86400000, max(0, int(elapsed_ms)))}


def local_input_capabilities():
    return {"profile": LOCAL_INPUT_PROFILE,
            "operations": ["press_key", "insert_text_slow", "clear_input_via_keys"],
            "max_text_chars": LOCAL_INPUT_MAX_TEXT_CHARS,
            "max_text_bytes": LOCAL_INPUT_MAX_TEXT_BYTES,
            "max_clear_chars": LOCAL_INPUT_MAX_CLEAR_CHARS,
            "budget_seconds": LOCAL_INPUT_SECONDS}


def validate_local_input(value):
    
    if not isinstance(value, dict) or not isinstance(value.get("target"), str):
        raise ValueError("invalid_input")
    if not _LOCAL_INPUT_TARGET.fullmatch(value["target"]):
        raise ValueError("invalid_input")
    op = value.get("operation")
    required = {"target", "operation"}
    if op == "press_key":
        required.add("key")
        if not isinstance(value.get("key"), str) or value["key"] not in _LOCAL_INPUT_KEYS:
            raise ValueError("invalid_input")
    elif op == "insert_text_slow":
        required.add("text")
        text = value.get("text")
        if not isinstance(text, str) or len(text) > LOCAL_INPUT_MAX_TEXT_CHARS:
            raise ValueError("invalid_input")
        try:
            if len(text.encode("utf-8")) > LOCAL_INPUT_MAX_TEXT_BYTES:
                raise ValueError("invalid_input")
        except UnicodeError:
            raise ValueError("invalid_input") from None
    elif op != "clear_input_via_keys":
        raise ValueError("invalid_input")
    if set(value) != required:
        raise ValueError("invalid_input")
    return dict(value)



_LOCAL_FOCUS_JS = r"""(function(){var a=document.activeElement;if(!a)return {editable:false,value:''};
 var role=(a.getAttribute&&a.getAttribute('role')||'').toLowerCase();
 var g=(role==='gridcell'||role==='cell')&&a.closest&&a.closest('[role=grid],[role=treegrid]');
 var grid=(role==='gridcell'||role==='cell')&&a.getAttribute('aria-disabled')!=='true'&&a.getAttribute('aria-readonly')!=='true'&&
 (a.getAttribute('aria-readonly')==='false'||(g&&g.getAttribute('aria-readonly')==='false'));
 var edit=!a.disabled&&!a.readOnly&&(('value' in a&&/^(INPUT|TEXTAREA)$/.test(a.tagName))||a.isContentEditable||grid);
 return {editable:!!edit,value:'value' in a?String(a.value||''):(a.isContentEditable||grid)?String(a.innerText||a.textContent||''):''};})()"""
_LOCAL_SELECTION_JS = (
    "(function(){var e=document.activeElement;"
    "if(e&&e.setSelectionRange){try{e.setSelectionRange(0,String(e.value||'').length);}catch(x){}}"
    "else if(e&&(e.isContentEditable||/^(gridcell|cell)$/.test((e.getAttribute('role')||'').toLowerCase()))){"
    "try{var r=document.createRange();r.selectNodeContents(e);var s=getSelection();s.removeAllRanges();s.addRange(r);}catch(x){}}})()")


class LocalInputFailure(Exception):
    pass


class _LocalInputCDP:
    
    def __init__(self, port, target, guard):
        self.guard, self.sock, self.buffer, self.sequence = guard, None, b"", 0
        self.closed = threading.Event()
        try:
            guard()
            self.sock = socket.create_connection(("127.0.0.1", port), timeout=1)
            self.sock.settimeout(.2)
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            request = (f"GET {target} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                       f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                       "Sec-WebSocket-Version: 13\r\n\r\n").encode("ascii")
            guard()
            self.sock.sendall(request)
            header = b""
            while b"\r\n\r\n" not in header:
                if len(header) > 8192:
                    raise LocalInputFailure("input_transport_error")
                header += self._read_some(1024)
            head, self.buffer = header.split(b"\r\n\r\n", 1)
            lines = head.decode("ascii").split("\r\n")
            headers = {}
            for line in lines[1:]:
                name, value = line.split(":", 1)
                name = name.strip().lower()
                if name in headers:
                    raise LocalInputFailure("input_transport_error")
                headers[name] = value.strip()
            expected = base64.b64encode(hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
            if (lines[0].split()[:2] != ["HTTP/1.1", "101"]
                    or headers.get("sec-websocket-accept") != expected
                    or headers.get("upgrade", "").lower() != "websocket"
                    or "upgrade" not in [x.strip().lower() for x in headers.get("connection", "").split(",")]):
                raise LocalInputFailure("input_transport_error")
        except Exception:
            self.close()
            raise LocalInputFailure("input_transport_error") from None

    def _read_some(self, size):
        while True:
            self.guard()
            if self.closed.is_set():
                raise LocalInputFailure("input_stopped")
            try:
                value = self.sock.recv(size)
                if not value:
                    raise LocalInputFailure("input_transport_error")
                return value
            except socket.timeout:
                continue

    def _exact(self, size):
        while len(self.buffer) < size:
            self.buffer += self._read_some(min(65536, size - len(self.buffer)))
        result, self.buffer = self.buffer[:size], self.buffer[size:]
        return result

    def _send_frame(self, opcode, payload):
        self.guard()
        mask = os.urandom(4)
        size = len(payload)
        head = bytes([0x80 | opcode])
        head += bytes([0x80 | size]) if size < 126 else bytes([0x80 | 126]) + struct.pack("!H", size)
        masked = bytes(ch ^ mask[i % 4] for i, ch in enumerate(payload))
        self.sock.sendall(head + mask + masked)

    def _message(self):
        fragments, total, fragmented = [], 0, False
        for _ in range(256):
            h = self._exact(2)
            final, opcode, size = bool(h[0] & 0x80), h[0] & 15, h[1] & 127
            if h[0] & 0x70 or h[1] & 0x80:
                raise LocalInputFailure("input_transport_error")
            if size == 126:
                size = struct.unpack("!H", self._exact(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self._exact(8))[0]
            if size > MAX_HTTP_BODY or total + size > MAX_HTTP_BODY:
                raise LocalInputFailure("input_transport_error")
            if opcode in (8, 9, 10):
                if not final or size > 125:
                    raise LocalInputFailure("input_transport_error")
                payload = self._exact(size)
                if opcode == 8:
                    raise LocalInputFailure("input_transport_error")
                if opcode == 9:
                    self._send_frame(10, payload)
                continue
            if (opcode == 1 and fragmented) or opcode not in (0, 1) or (opcode == 0 and not fragmented):
                raise LocalInputFailure("input_transport_error")
            fragments.append(self._exact(size)); total += size
            if final:
                return _json_object(b"".join(fragments))
            fragmented = True
        raise LocalInputFailure("input_transport_error")

    def send(self, method, params):
        self.sequence += 1
        self._send_frame(1, json.dumps({"id": self.sequence, "method": method, "params": params},
                                     ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
        for _ in range(256):
            result = self._message()
            if result.get("id") == self.sequence and type(result.get("id")) is int:
                if "error" in result or not isinstance(result.get("result"), dict):
                    raise LocalInputFailure("input_cdp_error")
                if result["result"].get("exceptionDetails"):
                    raise LocalInputFailure("input_cdp_error")
                return result["result"]
        raise LocalInputFailure("input_transport_error")

    def close(self):
        self.closed.set()
        _close_socket(self.sock)


class LocalInputRunner:
    





    def __init__(self, port, stop, check_owned, *, websocket_factory=None):
        self.port, self.stop, self.check_owned = port, stop, check_owned
        self.websocket_factory = websocket_factory or _LocalInputCDP
        self.cdp, self.http, self.http_sock, self.side_effect = None, None, None, False
        self.deadline = 0.0
        self.stage, self.operation, self.dispatch_state = "validate", "unknown", "not_sent"

    def close(self):
        if self.cdp is not None:
            self.cdp.close()
        if self.http is not None:
            _close_socket(self.http_sock)
            self.http.close()

    def guard(self):
        if self.stop.is_set():
            raise LocalInputFailure("input_stopped")
        if time.monotonic() >= self.deadline:
            raise LocalInputFailure("input_timeout")

    def _owned(self):
        self.guard()
        try:
            self.check_owned()
        except Exception:
            raise LocalInputFailure("input_ownership_lost") from None
        self.guard()

    def _discover(self, target):
        self.guard()
        self.http = http.client.HTTPConnection("127.0.0.1", self.port, timeout=1)
        timer = None
        try:
            self.http.connect()
            self.http_sock = self.http.sock
            self.guard()
            timer = threading.Timer(max(.001, self.deadline-time.monotonic()), _close_socket,
                                    args=(self.http_sock,))
            timer.daemon = True
            timer.start()
            self.http.request("GET", "/json/list", headers={"Connection": "close"})
            response = self.http.getresponse()
            raw = response.read(MAX_HTTP_BODY + 1)
            self.guard()
            if response.status != 200 or len(raw) > MAX_HTTP_BODY:
                raise LocalInputFailure("target_unavailable")
            rows = json.loads(raw)
            if not isinstance(rows, list) or len(rows) > 4096:
                raise LocalInputFailure("target_unavailable")
            found = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                ws = row.get("webSocketDebuggerUrl")
                if not isinstance(ws, str):
                    continue
                parsed = urlsplit(ws)
                if parsed.path != target:
                    continue
                if (row.get("type") not in ("page", "iframe") or parsed.scheme != "ws"
                        or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
                        or parsed.port != self.port or parsed.username is not None or parsed.password is not None
                        or parsed.query or parsed.fragment):
                    raise LocalInputFailure("target_unavailable")
                found += 1
            if found != 1:
                raise LocalInputFailure("target_unavailable")
        finally:
            if timer is not None:
                timer.cancel(); timer.join()
            self.http.close(); self.http = None; self.http_sock = None

    def _send(self, method, params, *, side_effect=True):
        if side_effect:
            self.stage = "input_send"
        self.guard()
        if side_effect:
            self.side_effect = True
            self.dispatch_state = "maybe_sent"
        result = self.cdp.send(method, params)
        if side_effect:
            self.dispatch_state = "acknowledged"
        self.guard()
        return result

    def _sleep(self, low, high):
        self.stage = "input_pause"
        if self.stop.wait(random.uniform(low, high)):
            raise LocalInputFailure("input_stopped")
        self.guard()

    def _press(self, key):
        base = {"key": key, "code": key}
        if _LOCAL_INPUT_KEYS[key]:
            base["windowsVirtualKeyCode"] = _LOCAL_INPUT_KEYS[key]
        self._send("Input.dispatchKeyEvent", {"type": "keyDown", **base})
        self._sleep(.02, .06)
        self._send("Input.dispatchKeyEvent", {"type": "keyUp", **base})

    def _focus_value(self):
        result = self._send("Runtime.evaluate", {"expression": _LOCAL_FOCUS_JS,
                                                 "returnByValue": True}, side_effect=False)
        value = (result.get("result") or {}).get("value")
        if not isinstance(value, dict) or value.get("editable") is not True or not isinstance(value.get("value"), str):
            raise LocalInputFailure("not_editable")
        return value["value"]

    def run(self, payload):
        started = time.monotonic()
        self.cdp, self.http, self.http_sock, self.side_effect = None, None, None, False
        self.stage, self.operation, self.dispatch_state = "validate", _local_input_operation(payload), "not_sent"
        self.deadline = started + LOCAL_INPUT_SECONDS
        try:
            try:
                payload = validate_local_input(payload)
            except ValueError:
                raise LocalInputFailure("invalid_input") from None
            self.stage = "ownership_before"
            self._owned()
            self.stage = "target_discovery"
            self._discover(payload["target"])
            self.stage = "cdp_connect"
            self.cdp = self.websocket_factory(self.port, payload["target"], self.guard)
            operation = payload["operation"]
            if operation == "press_key":
                self._press(payload["key"])
            elif operation == "insert_text_slow":
                self.stage = "focus_check"
                self._focus_value()
                last = ""
                for ch in payload["text"]:
                    if 0x20 <= ord(ch) <= 0x7e:
                        up = ch.upper()
                        code = "Key" + up if up.isalpha() else ("Digit" + ch if ch.isdigit() else "")
                        base = {"key": ch, "windowsVirtualKeyCode": ord(up)}
                        if code:
                            base["code"] = code
                        self._send("Input.dispatchKeyEvent", {"type": "keyDown", **base})
                        self._send("Input.dispatchKeyEvent", {"type": "char", "text": ch, "key": ch})
                        self._send("Input.dispatchKeyEvent", {"type": "keyUp", **base})
                    else:
                        self._send("Input.insertText", {"text": ch})
                    last = ch
                    self._sleep(.06, .18)
                if last and not 0x20 <= ord(last) <= 0x7e:
                    self._send("Input.dispatchKeyEvent", {"type": "keyUp", "key": last})
                    self._sleep(.05, .12)
            else:
                self.stage = "focus_check"
                current = self._focus_value()
                if len(current) > LOCAL_INPUT_MAX_CLEAR_CHARS:
                    raise LocalInputFailure("clear_limit")
                if current:
                    self._press("End")
                    for _ in range(len(current) + 3):
                        self._press("Backspace")
                    self.stage = "clear_verify"
                    if self._focus_value():
                        self._send("Runtime.evaluate", {"expression": _LOCAL_SELECTION_JS})
                        self._press("Backspace")
            self.stage = "ownership_after"
            self._owned()
            return {"ok": True, "status": "completed"}
        except Exception as exc:
            code = str(exc) if type(exc) is LocalInputFailure else "input_transport_error"
            if code not in _LOCAL_INPUT_ERRORS:
                code = "input_transport_error"
            status = "uncertain" if self.side_effect else "rejected"
            return {"ok": False, "status": status, "error": code,
                    "diagnostic": _local_input_diagnostic(self.operation, self.stage, code, status,
                        self.dispatch_state, self.side_effect, (time.monotonic()-started)*1000)}
        finally:
            self.close()


class _TracedChunk:
    __slots__ = ("data", "stage_meta")

    def __init__(self, data, stage_meta):
        self.data, self.stage_meta = data, stage_meta


class _Stream:
    def __init__(self, stream_id):
        self.id = stream_id
        self.sock = None
        self.pending = queue.Queue(maxsize=16)
        self.read_trace_seq = self.write_trace_seq = 0
        self.closed = threading.Event()


class Connector:
    






    def __init__(self, config, browser_state, *, stage_trace=None):
        if stage_trace is not None and type(stage_trace) is not TransportStageTrace:
            raise ValueError("invalid transport stage trace")
        self._stage_trace = stage_trace
        self._received_stage_meta = None
        self.config = (validate_config(config) if isinstance(config, dict)
                       else load_config(config))
        self.browser_state = Path(browser_state).expanduser().absolute()
        self._browser = runpy.run_path(str(Path(__file__).resolve().with_name("browser.py")))
        self._state = None
        self._state_path = None
        self._cdp_port = None
        self._browser_instance = None
        self._browser_ws_path = None
        self._lock_fd = None
        self._channel = None
        self._epoch = None
        self._transport_profile = None
        self._input_profile = None
        self._input_diagnostics_profile = None
        self._input_lock = threading.Lock()
        self._input_seen = set()
        self._input_runner = None
        self._interval = 5.0
        self._timeout = 15.0
        self._last_received = time.monotonic()
        self._last_ping = time.monotonic()
        self._stop = threading.Event()
        self.connected = threading.Event()
        self._used = False
        self._signal_stop = False
        self.shutdown_complete = False
        self.close_reason = None
        self._failure = None
        self.first_error = None
        self._state_lock = threading.Lock()
        self._streams_lock = threading.Lock()
        self._streams = {}
        self._closed_streams = deque(maxlen=MAX_CLOSED_STREAMS)
        self._http_lock = threading.Lock()
        self._http = {}
        self._threads_lock = threading.Lock()
        self._threads = set()

    def _trace_stage(self, stage, stage_meta=None, **fields):
        if self._stage_trace is not None:
            self._stage_trace.record(stage, **dict(stage_meta or {}, **fields))

    @staticmethod
    def _chunk_stage_meta(stream, direction, sequence):
        return {"stream_token": hashlib.sha256(stream.id.encode("ascii")).hexdigest(),
                "direction": direction, "chunk_seq": sequence}

    def _spawn(self, fn, *args):
        def execute():
            try:
                fn(*args)
            except Exception as exc:
                self._fail("worker_failure", exc=exc, phase='worker')
            finally:
                with self._threads_lock:
                    self._threads.discard(threading.current_thread())

        thread = threading.Thread(target=execute, daemon=True)
        with self._threads_lock:
            if self._stop.is_set():
                return
            capacity = len(self._threads) >= MAX_WORKERS
            start_error = None
            if not capacity:
                self._threads.add(thread)


                try:
                    thread.start()
                except RuntimeError as exc:
                    self._threads.discard(thread)
                    start_error = exc
        if capacity:
            self._fail("worker_capacity")
        elif start_error is not None:
            self._fail("worker_start_failed", exc=start_error, phase='worker')

    def _join_workers(self, deadline):
        with self._threads_lock:
            threads = list(self._threads)
        for thread in threads:
            thread.join(timeout=max(0., deadline-time.monotonic()))
        return not any(thread.is_alive() for thread in threads)

    def _shutdown_incomplete(self, reason):


        with self._state_lock:
            if self.first_error is None:
                self.first_error = safe_diagnostic(reason, 'lifecycle')
            if self._failure is None:
                self._failure = reason
        raise ConnectorError(reason)

    def _check_owned(self):
        try:
            path, state = self._browser["read_state"](self.browser_state)
            if state.get("status") != "running":
                raise ConnectorError("browser_not_running")
            root_info = path.parent.lstat()
            profile = Path(state["profile"])
            info = profile.lstat()
            if win:
                win.private_dir(path.parent, create=False); win.private_dir(profile, create=False)
                if info.st_ino != state.get('profile_inode') or info.st_dev != state.get('profile_device'): raise ConnectorError('browser_profile_changed')
            else:
                if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.getuid()
                        or root_info.st_mode & 0o022
                        or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_mode & 0o022 or info.st_ino != state.get("profile_inode")
                        or info.st_dev != state.get("profile_device")):
                    raise ConnectorError("browser_profile_changed")
            identity = state.get("identity")
            args = state.get("launch_args")
            if (not isinstance(identity, dict) or identity.get("pid") != state.get("pid")
                    or not isinstance(args, list) or not args
                    or not all(isinstance(arg, str) for arg in args)
                    or not Path(args[0]).is_absolute()):
                raise ConnectorError("invalid_browser_identity")
            rules = self._browser["blocked_resolver_rules"]()
            expected = tuple(self._browser["launch_command"](
                args[0], profile, headless=headless, resolver_rules=rules)
                for headless in (False, True))
            if args not in expected:
                raise ConnectorError("invalid_browser_launch_args")
            if "--user-data-dir=" + str(profile) not in identity.get("command", ""):
                raise ConnectorError("invalid_browser_identity")
            endpoint = urlsplit(state.get("CDP_ENDPOINT", ""))
            if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1"
                    or endpoint.username is not None or endpoint.password is not None
                    or endpoint.path or endpoint.query or endpoint.fragment
                    or endpoint.port is None or not 1 <= endpoint.port <= 65535):
                raise ConnectorError("invalid_browser_endpoint")
            active = _owned_file(profile / "DevToolsActivePort", 4096).decode("utf-8").splitlines()
            if (len(active) < 2 or active[0] != str(endpoint.port)
                    or not active[1].startswith("/devtools/browser/")
                    or not _BROWSER_ID.fullmatch(active[1][len("/devtools/browser/"):])):
                raise ConnectorError("browser_endpoint_changed")
            if self._state is not None and (
                    state != self._state or path != self._state_path
                    or active[1] != self._browser_ws_path):
                raise ConnectorError("browser_ownership_changed")
            if self._lock_fd is not None:
                held = os.fstat(self._lock_fd)
                current = (path.parent / ".connector.lock").lstat()
                if (not stat.S_ISREG(current.st_mode) or current.st_ino != held.st_ino
                        or current.st_dev != held.st_dev):
                    raise ConnectorError("browser_lock_changed")
            if not self._browser["still_owned"](identity):
                raise ConnectorError("browser_not_running")
            if self._state is None:
                self._state = state
                self._state_path = path
                self._cdp_port = endpoint.port
                self._browser_ws_path = active[1]
        except ConnectorError:
            raise
        except Exception:
            raise ConnectorError("browser_ownership_unverified") from None

    def _acquire_browser(self):
        self._check_owned()
        path = self._state_path.parent / ".connector.lock"
        fd = None
        try:
            if win:
                try: fd = win.lock_file(path)
                except OSError: raise ConnectorError('browser_connector_already_running') from None
                info = os.fstat(fd)
            else:
                fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
                             | getattr(os, "O_CLOEXEC", 0), 0o600)
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                    raise ConnectorError("unsafe_browser_lock")
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ConnectorError("browser_connector_already_running") from None
            current = path.lstat()
            if current.st_ino != info.st_ino or current.st_dev != info.st_dev:
                raise ConnectorError("browser_lock_changed")
            self._lock_fd = fd
            fd = None
            self._check_owned()


            conn = http.client.HTTPConnection("127.0.0.1", self._cdp_port, timeout=3)
            timer = None
            try:
                conn.connect()
                timer = threading.Timer(MAX_HTTP_SECONDS, _close_socket, args=(conn.sock,))
                timer.daemon = True
                timer.start()
                conn.request("GET", "/json/version", headers={"Connection": "close"})
                response = conn.getresponse()
                body = response.read(MAX_HTTP_BODY + 1)
                if response.status != 200 or len(body) > MAX_HTTP_BODY:
                    raise ConnectorError("browser_discovery_failed")
                value = _json_object(body)
                ws = urlsplit(value.get("webSocketDebuggerUrl", ""))
                if (ws.scheme != "ws" or ws.hostname != "127.0.0.1"
                        or ws.port != self._cdp_port or ws.username is not None
                        or ws.password is not None or ws.query or ws.fragment
                        or ws.path != self._browser_ws_path):
                    raise ConnectorError("browser_discovery_mismatch")
                self._browser_instance = ws.path.rsplit("/", 1)[1]
            finally:
                if timer is not None:
                    timer.cancel()
                    timer.join()
                conn.close()
        except ConnectorError:
            raise
        except Exception:
            raise ConnectorError("browser_setup_failed") from None
        finally:
            if fd is not None:
                os.close(fd)

    def _fail(self, reason, *, exc=None, phase='lifecycle', operation='none', thread_role='caller', occurred=None):
        with self._state_lock:
            if self._failure is None and not self._stop.is_set():
                self._failure = reason if reason in _SAFE_ERRORS else 'connector_failure'
                self.first_error = safe_diagnostic(self._failure, phase, exc, self._epoch, operation, thread_role, occurred)
        self.stop()

    def stop(self):
        
        self._stop.set()
        self.connected.clear()
        with self._input_lock:
            runner = self._input_runner
        if runner is not None:
            runner.close()
        if self._channel is not None:
            self._channel.request_stop()
        with self._streams_lock:
            streams = list(self._streams.values())
            self._streams.clear()
        for item in streams:
            item.closed.set()
            _close_socket(item.sock)
        with self._http_lock:
            requests = list(self._http.values())
        for item in requests:
            _close_socket(item.get("sock"))
            conn = item.get("conn")
            if conn is not None:
                conn.close()

    @staticmethod
    def _encode(message):
        try:
            data = json.dumps(message, ensure_ascii=True, separators=(",", ":"),
                              allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, RecursionError):
            raise ConnectorError("invalid_outbound_frame") from None
        if not 0 < len(data) <= MAX_FRAME:
            raise ConnectorError("outbound_frame_too_large")
        return struct.pack("!I", len(data)) + data

    def _write(self, frame, *, wait=False, stage_meta=None):
        if self._stop.is_set():
            return
        if stage_meta is not None and self._stage_trace is not None:
            self._channel.send(frame, wait=wait, stage_meta=stage_meta)
        elif wait:
            self._channel.send(frame, wait=True)
        else:
            self._channel.send(frame)

    def _send(self, message, *, wait=False, stage_meta=None):
        if self._stop.is_set():
            return
        traced = self._stage_trace is not None and stage_meta is not None
        encoded_at = time.monotonic() if traced else None
        try:
            frame = self._encode(dict(message, epoch=self._epoch))
            if traced:
                self._trace_stage('app_frame_encoded', stage_meta, frame_bytes=len(frame),
                                  elapsed_ms=(time.monotonic()-encoded_at)*1000, status='complete')
                self._trace_stage('app_send_begin', stage_meta, frame_bytes=len(frame), status='begin')
            sent_at = time.monotonic() if traced else None
            self._write(frame, wait=wait, stage_meta=stage_meta) if traced else self._write(frame, wait=wait)
            if traced:
                self._trace_stage('app_send_done', stage_meta, frame_bytes=len(frame),
                                  elapsed_ms=(time.monotonic()-sent_at)*1000,
                                  status='stopped' if self._stop.is_set() else ('accepted' if wait else 'queued'))
        except ChannelError as exc:
            if traced:
                self._trace_stage('app_send_done', stage_meta, status='error')
            if not self._stop.is_set():
                if exc.code == 'backpressure':
                    self._fail('outbound_backpressure', phase='write', operation='queue')
                else:
                    self._channel_failure(exc)

    def _receive(self, *, initial=False):
        if self._signal_stop:
            self.stop()
        if self._stop.is_set():
            raise ConnectorError('stopped')
        if self._stage_trace is None:
            raw = self._channel.receive()
        else:
            meta = {}
            raw = self._channel.receive(stage_meta=meta)
            self._received_stage_meta = meta
            self._trace_stage('app_frame_received', meta, frame_bytes=len(raw), status='complete')
        try:
            value = _json_object(raw.decode('utf-8'))
        except (ValueError, TypeError, RecursionError):
            raise ConnectorError('invalid_frame_json') from None
        self._last_received = time.monotonic()
        return value

    def _channel_failure(self, exc):
        if exc.code == 'peer_closed' and self._epoch is not None:
            self.close_reason = 'peer_closed'
            self.stop()
            return
        op = exc.operation
        phase = ('tls' if op == 'tls_handshake' else 'write' if op in {'send_frame','queue'}
                 else 'read' if op in {'recv_header','recv_body'} else 'lifecycle')
        if isinstance(exc.cause, ssl.SSLCertVerificationError):
            reason = 'tls_certificate_rejected'
        elif exc.code in {'eof', 'peer_closed', 'truncated_frame'}:
            reason = 'truncated_frame' if exc.code == 'truncated_frame' else 'transport_closed'
        elif exc.code in {'frame_timeout', 'initial_timeout'}:
            reason = 'frame_timeout'
        elif exc.code == 'frame_length':
            reason = 'invalid_frame_length'
        elif exc.code == 'worker_start':
            reason, phase = 'worker_start_failed', 'worker'
        elif phase == 'write':
            reason = 'transport_write_failed'
        else:
            reason = 'connector_connection_failed'
        if not self._stop.is_set():
            self._fail(reason, exc=exc.cause, phase=phase, operation=op, thread_role='tls_io', occurred=exc)

    def _welcome(self, message):
        if message.get("type") == "error":
            raise ConnectorError("hub_rejected_connection")
        if (message.get("type") != "welcome" or not isinstance(message.get("epoch"), str)
                or not _ID.fullmatch(message["epoch"])):
            raise ConnectorError("invalid_welcome")
        interval = message.get("heartbeat_interval")
        timeout = message.get("heartbeat_timeout")
        if (type(interval) not in (int, float) or type(timeout) not in (int, float)
                or not math.isfinite(interval) or not math.isfinite(timeout)
                or not 0.25 <= interval <= 60 or not interval < timeout <= 180):
            raise ConnectorError("invalid_heartbeat_settings")


        profile = message.get("transport_profile")
        if "transport_profile" in message:
            if profile != PROGRESS_PROFILE or timeout != PROGRESS_HEARTBEAT_SECONDS or interval > 15 or timeout < 3 * interval:
                raise ConnectorError("invalid_welcome")
        input_profile = message.get("input_profile")
        if input_profile is not None and input_profile != LOCAL_INPUT_PROFILE:
            raise ConnectorError("invalid_welcome")
        diagnostics_profile = message.get("input_diagnostics_profile")
        if "input_diagnostics_profile" in message:
            if input_profile != LOCAL_INPUT_PROFILE or diagnostics_profile != LOCAL_INPUT_DIAGNOSTICS_PROFILE:
                raise ConnectorError("invalid_welcome")
        self._input_profile = input_profile
        self._input_diagnostics_profile = diagnostics_profile
        self._transport_profile = profile
        self._epoch = message["epoch"]
        self._interval, self._timeout = float(interval), float(timeout)
        self._last_ping = self._last_received

    def _watchdog(self):
        while not self._stop.wait(0.2):
            if self._signal_stop:
                self.stop()
                return
            now = time.monotonic()
            if now - self._last_received > self._timeout:
                self._fail("heartbeat_timeout", phase="heartbeat")
                return
            if now - self._last_ping >= self._interval:
                self._last_ping = now
                self._send({"type": "ping"})
            with self._http_lock:
                expired = [item for item in self._http.values()
                           if now - item["started"] > MAX_HTTP_SECONDS]
            if expired:

                self._fail("local_http_timeout")
                return

    def _ownership_watchdog(self):
        while not self._stop.wait(5):
            try:
                self._check_owned()
            except ConnectorError as error:
                self._fail(str(error) if str(error) in _SAFE_ERRORS else "browser_ownership_lost")
                return

    @staticmethod
    def _http_path(method, path):
        if (not isinstance(method, str) or not isinstance(path, str)
                or len(path) > 16384 or any(ord(c) < 32 or ord(c) >= 127 for c in path)):
            return False
        if method == "GET" and path in ("/json/list", "/json/version"):
            return True
        if method == "GET" and re.fullmatch(r"/json/(close|activate)/[A-Za-z0-9_-]{1,128}", path):
            return True
        if method not in ("GET", "PUT") or not path.startswith("/json/new?"):
            return False
        try:
            url = unquote_to_bytes(path[len("/json/new?"):]).decode("utf-8")
            if not url or any(ord(c) <= 32 or ord(c) == 127 for c in url) or "\\" in url:
                return False
            if url == "about:blank":
                return True
            parsed = urlsplit(url)
            return (parsed.scheme in ("http", "https") and parsed.hostname is not None
                    and parsed.username is None and parsed.password is None
                    and (parsed.port is None or 1 <= parsed.port <= 65535))
        except (ValueError, UnicodeError):
            return False

    def _http_start(self, message):
        request_id = message["id"]
        if not self._http_path(message.get("method"), message.get("path")):
            self._send({"type": "http_result", "id": request_id, "error": "local_http_failure"})
            return
        with self._http_lock:
            if request_id in self._http:
                duplicate, capacity = True, False
            else:
                duplicate, capacity = False, len(self._http) >= MAX_HTTP_REQUESTS
                if not capacity:
                    self._http[request_id] = {"started": time.monotonic(), "conn": None, "sock": None}
        if duplicate:
            self._fail("duplicate_http_id")
        elif capacity:
            self._send({"type": "http_result", "id": request_id, "error": "local_http_failure"})
        else:
            self._spawn(self._http_worker, request_id, message["method"], message["path"])

    def _http_worker(self, request_id, method, path):
        conn = None
        try:
            self._check_owned()
            if self._stop.is_set():
                return
            conn = http.client.HTTPConnection("127.0.0.1", self._cdp_port, timeout=3)
            with self._http_lock:
                self._http[request_id]["conn"] = conn
            conn.connect()
            with self._http_lock:
                self._http[request_id]["sock"] = conn.sock
            if self._stop.is_set():
                return
            conn.request(method, path, headers={"Connection": "close"})
            response = conn.getresponse()
            body = response.read(MAX_HTTP_BODY + 1)
            if len(body) > MAX_HTTP_BODY:
                raise ConnectorError("local_http_body_too_large")
            content_type = response.getheader("Content-Type", "application/octet-stream")
            if len(content_type) > 256 or any(ord(c) < 32 or ord(c) >= 127 for c in content_type):
                content_type = "application/octet-stream"
            self._send({"type": "http_result", "id": request_id, "status": response.status,
                        "content_type": content_type, "body_b64": base64.b64encode(body).decode("ascii")})
        except Exception:
            self._send({"type": "http_result", "id": request_id, "error": "local_http_failure"})
        finally:
            if conn is not None:
                conn.close()
            with self._http_lock:
                self._http.pop(request_id, None)

    def _stream_open(self, stream_id):
        with self._streams_lock:
            duplicate = stream_id in self._streams or stream_id in self._closed_streams
            capacity = len(self._streams) >= MAX_STREAMS
            if not duplicate and not capacity:
                stream = _Stream(stream_id)
                self._streams[stream_id] = stream
        if duplicate:
            self._fail("duplicate_stream_id")
        elif capacity:
            self._send({"type": "stream_closed", "id": stream_id, "error": "stream_capacity"})
        else:
            self._spawn(self._stream_connect, stream)

    def _stream_connect(self, stream):
        sock = None
        try:
            self._check_owned()
            if self._stop.is_set() or stream.closed.is_set():
                return
            sock = socket.create_connection(("127.0.0.1", self._cdp_port), timeout=3)
            sock.settimeout(1)
            with self._streams_lock:
                if self._stop.is_set() or stream.closed.is_set():
                    _close_socket(sock)
                    return
                stream.sock = sock
            self._send({"type": "stream_opened", "id": stream.id})
            self._spawn(self._stream_write, stream)
            while not self._stop.is_set() and not stream.closed.is_set():
                try:
                    read_at = time.monotonic() if self._stage_trace is not None else None
                    data = sock.recv(MAX_CHUNK)
                except socket.timeout:
                    continue
                if not data:
                    break
                meta = None
                if self._stage_trace is not None:
                    stream.read_trace_seq += 1
                    meta = self._chunk_stage_meta(stream, 'browser_to_core', stream.read_trace_seq)
                    self._trace_stage('app_chunk_read', meta, data_bytes=len(data),
                                      elapsed_ms=(time.monotonic()-read_at)*1000, status='complete')
                message = {"type": "stream_data", "id": stream.id,
                           "data_b64": base64.b64encode(data).decode("ascii")}
                self._send(message, wait=True, stage_meta=meta) if meta else self._send(message, wait=True)
        except Exception:
            self._stream_close(stream, notify=True, error="local_stream_failure")
        finally:
            self._stream_close(stream, notify=True)
            _close_socket(sock)

    def _stream_write(self, stream):
        while not self._stop.is_set() and not stream.closed.is_set():
            try:
                data = stream.pending.get(timeout=0.25)
            except queue.Empty:
                continue
            meta = data.stage_meta if type(data) is _TracedChunk else None
            data = data.data if type(data) is _TracedChunk else data
            write_at = time.monotonic() if meta is not None else None
            if meta is not None:
                self._trace_stage('app_write_begin', meta, data_bytes=len(data), status='begin')
            try:
                stream.sock.sendall(data)
                if meta is not None:
                    self._trace_stage('app_write_done', meta, data_bytes=len(data),
                                      elapsed_ms=(time.monotonic()-write_at)*1000, status='complete')
            except OSError:
                if meta is not None:
                    self._trace_stage('app_write_done', meta, data_bytes=len(data),
                                      elapsed_ms=(time.monotonic()-write_at)*1000, status='error')
                self._stream_close(stream, notify=True, error="local_stream_failure")
                return

    def _stream_close(self, stream, *, notify=False, error=None):
        with self._streams_lock:
            if stream.closed.is_set():
                return
            stream.closed.set()
            self._closed_streams.append(stream.id)
            if self._streams.get(stream.id) is stream:
                self._streams.pop(stream.id, None)
        _close_socket(stream.sock)
        if notify:
            frame = {"type": "stream_closed", "id": stream.id}
            if error:
                frame["error"] = error
            self._send(frame)

    def _input_start(self, message):
        if self._input_profile != LOCAL_INPUT_PROFILE:
            raise ConnectorError("unknown_message_type")
        request_id = message["id"]
        with self._input_lock:
            if request_id in self._input_seen:
                error = "input_id_reused"
            elif len(self._input_seen) >= LOCAL_INPUT_MAX_IDS:
                error = "input_capacity"
            else:
                self._input_seen.add(request_id)
                error = "input_busy" if self._input_runner is not None else None
            if error is None:
                runner = LocalInputRunner(self._cdp_port, self._stop, self._check_owned)
                self._input_runner = runner
        if error == "input_id_reused":


            self._fail("duplicate_input_id", phase="protocol")
            return
        if error:
            result = {"type": "input_result", "id": request_id,
                      "ok": False, "status": "rejected", "error": error}
            if self._input_diagnostics_profile == LOCAL_INPUT_DIAGNOSTICS_PROFILE:
                result["diagnostic"] = _local_input_diagnostic(_local_input_operation(message.get("input")),
                    "admission", error, "rejected", "not_sent", False, 0)
            self._send(result)
            return
        self._spawn(self._input_worker, request_id, message.get("input"), runner)

    def _input_worker(self, request_id, payload, runner):
        try:
            result = runner.run(payload)
            if self._input_diagnostics_profile != LOCAL_INPUT_DIAGNOSTICS_PROFILE:
                result = {key: value for key, value in result.items() if key != "diagnostic"}
            if not self._stop.is_set():
                self._send(dict(result, type="input_result", id=request_id))
        finally:
            with self._input_lock:
                if self._input_runner is runner:
                    self._input_runner = None

    def _dispatch(self, message):
        if message.get("epoch") != self._epoch:
            raise ConnectorError("epoch_mismatch")
        kind = message.get("type")
        if kind == "ping":
            self._send({"type": "pong"})
            return
        if kind == "pong":
            return
        if kind == "error":
            raise ConnectorError("hub_closed_connection")
        request_id = message.get("id")
        if not isinstance(request_id, str) or not _ID.fullmatch(request_id):
            raise ConnectorError("invalid_message_id")
        if kind == "input":
            self._input_start(message)
            return
        if kind == "http":
            self._http_start(message)
            return
        if kind == "stream_open":
            self._stream_open(request_id)
            return
        if kind not in ("stream_data", "stream_closed"):
            raise ConnectorError("unknown_message_type")
        with self._streams_lock:
            stream = self._streams.get(request_id)
        if kind == "stream_closed":
            if stream is not None:
                self._stream_close(stream)
            return
        encoded = message.get("data_b64")
        if not isinstance(encoded, str) or not 1 <= len(encoded) <= 4 * ((MAX_CHUNK + 2) // 3):
            raise ConnectorError("invalid_stream_data")
        decoded_at = time.monotonic() if self._stage_trace is not None else None
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ConnectorError("invalid_stream_data") from None
        if not 1 <= len(data) <= MAX_CHUNK:
            raise ConnectorError("invalid_stream_data")
        with self._streams_lock:
            stream = self._streams.get(request_id)
            if stream is None or stream.sock is None or stream.closed.is_set():




                if request_id in self._closed_streams:
                    return
                raise ConnectorError("stream_not_open")
        meta = None
        if self._stage_trace is not None:
            stream.write_trace_seq += 1
            meta = self._chunk_stage_meta(stream, 'core_to_browser', stream.write_trace_seq)
            meta.update(self._received_stage_meta or {})
            self._trace_stage('app_chunk_decoded', meta, data_bytes=len(data),
                              elapsed_ms=(time.monotonic()-decoded_at)*1000, status='complete')
            self._trace_stage('app_queue_begin', meta, data_bytes=len(data), status='begin')
        queued_at = time.monotonic() if meta is not None else None
        try:
            stream.pending.put_nowait(_TracedChunk(data, meta) if meta is not None else data)
            if meta is not None:
                self._trace_stage('app_queue_done', meta, data_bytes=len(data),
                                  elapsed_ms=(time.monotonic()-queued_at)*1000, status='queued')
        except queue.Full:
            if meta is not None:
                self._trace_stage('app_queue_done', meta, data_bytes=len(data), status='error')
            raise ConnectorError("local_stream_backpressure") from None

    def run(self):
        if self._used:
            raise ConnectorError("connector_is_single_use")
        self._used = True
        phase = 'ownership'
        try:
            if self._stop.is_set() or self._signal_stop:
                return {"status": "stopped"}
            self._acquire_browser()
            if self._stop.is_set() or self._signal_stop:
                return {"status": "stopped"}
            phase = 'tls'
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=self.config.get("ca_file"))
            context.minimum_version = ssl.TLSVersion.TLSv1_2


            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            phase = 'connect'
            raw = socket.create_connection((self.config["host"], self.config["port"]), timeout=5)
            self._channel = TLSChannel(raw, context, server_hostname=self.config['server_hostname'],
                max_frame=MAX_FRAME, max_bytes=MAX_OUTGOING_BYTES, frame_timeout=FRAME_SECONDS,
                write_timeout=WRITE_SECONDS, queue_timeout=QUEUE_SECONDS,
                **({"stage_trace": self._stage_trace} if self._stage_trace is not None else {})).start()
            if self._stop.is_set() or self._signal_stop:
                return {"status": "stopped"}
            phase = 'hello'
            self._write(self._encode({"type": "hello", "protocol": PROTOCOL,
                                      "device": self.config["device"], "token": self.config["token"],
                                      "browser_instance": self._browser_instance, "cdp_port": self._cdp_port,
                                      "transport_profile": PROGRESS_PROFILE,
                                      "input_profile": LOCAL_INPUT_PROFILE,
                                      "input_diagnostics_profile": LOCAL_INPUT_DIAGNOSTICS_PROFILE}))
            self._welcome(self._receive(initial=True))
            if self._transport_profile is None:
                self._channel.activate()
            else:
                self._channel.activate(profile=self._transport_profile)
            self.connected.set()
            self._spawn(self._watchdog)
            self._spawn(self._ownership_watchdog)
            while not self._stop.is_set():
                phase = 'read'
                message = self._receive()
                phase = 'protocol'
                self._dispatch(message)
        except ChannelError as exc:
            self._channel_failure(exc)
        except ConnectorError as exc:
            if not self._stop.is_set():
                self._fail(str(exc), exc=exc, phase=phase)
        except ssl.SSLCertVerificationError as exc:
            self._fail("tls_certificate_rejected", exc=exc, phase=phase)
        except Exception as exc:
            if not self._stop.is_set():
                self._fail("connector_connection_failed", exc=exc, phase=phase)
        finally:
            self.stop()
            deadline = time.monotonic() + SHUTDOWN_SECONDS
            if self._channel is not None and not self._channel.join(timeout=min(2., max(0., deadline-time.monotonic()))):


                self._shutdown_incomplete('transport_shutdown_incomplete')


            if not self._join_workers(deadline):
                self._shutdown_incomplete('worker_shutdown_incomplete')
            self.shutdown_complete = True
            if self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None
        if self._failure is not None:
            raise ConnectorError(self._failure)
        return dict(status='stopped', reason=self.close_reason) if self.close_reason else {'status':'stopped'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="current-owner mode-0600 connector JSON")
    parser.add_argument("--browser-state", required=True, help="owned browser ownership.json")
    args = parser.parse_args()
    connector = None
    try:
        connector = Connector(load_config(args.config), args.browser_state)


        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda _number, _frame: setattr(connector, "_signal_stop", True))
        result = connector.run()
        print(json.dumps(dict(result, owner_pid=os.getpid(), exit_code=0)))
        return 0
    except ConnectorError as exc:
        code = str(exc) if str(exc) in _SAFE_ERRORS else 'connector_failure'
        print(json.dumps({"status": "error", "error": code, "owner_pid": os.getpid(), "exit_code": 1,
                          "first_error": connector.first_error if connector is not None else None}), file=sys.stderr)
        return 1
    except Exception:
        print(json.dumps({"status": "error", "error": "connector_failed", "owner_pid": os.getpid(), "exit_code": 1,
                          "first_error": connector.first_error if connector is not None else None}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
