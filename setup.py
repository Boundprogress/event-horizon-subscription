#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import socket
import ssl
import stat
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

if sys.platform == "win32":
    import importlib.util as _win_import
    _win_spec = _win_import.spec_from_file_location("eh_win_platform", Path(__file__).resolve().with_name("win_platform.py"))
    win = _win_import.module_from_spec(_win_spec); _win_spec.loader.exec_module(win)
else:
    win = None

HERE = Path(__file__).resolve().parent
MAX_CONFIG = 65536


class SetupError(Exception):
    pass


def sibling(name):
    spec = importlib.util.spec_from_file_location("eh_customer_" + name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise SetupError("duplicate_json_key")
        result[key] = value
    return result


def secure_json(path, *, limit=MAX_CONFIG):

    if win:
        try: return win.secure_json(path, limit)
        except Exception: raise SetupError("private_file_unreadable") from None
    fd = None
    try:
        fd = os.open(Path(path).expanduser(), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                     | getattr(os, "O_CLOEXEC", 0))
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise SetupError("private_file_required")
        with os.fdopen(fd, "rb") as handle:
            fd = None
            raw = handle.read(limit + 1)
        if len(raw) > limit:
            raise SetupError("private_file_too_large")
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(SetupError("invalid_json")))
        if not isinstance(value, dict):
            raise SetupError("json_object_required")
        return value
    except SetupError:
        raise
    except Exception:
        raise SetupError("private_file_unreadable") from None
    finally:
        if fd is not None:
            os.close(fd)


def api_config(value):
    try:
        if set(value) - {"endpoint", "token", "timeout"}:
            raise ValueError()
        endpoint, token = value["endpoint"], value["token"]
        timeout = value.get("timeout", 30)
        if (not isinstance(endpoint, str) or not isinstance(token, str) or not token
                or not 16 <= len(token) <= 512 or any(not 33 <= ord(c) <= 126 for c in token)
                or type(timeout) not in (int, float) or not math.isfinite(timeout)
                or not 0 < timeout <= 300):
            raise ValueError()
        parsed = urlsplit(endpoint)
        parsed.port
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or (parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"))):
            raise ValueError()
        return {"endpoint": endpoint.rstrip("/"), "token": token, "timeout": float(timeout)}
    except Exception:
        raise SetupError("invalid_api_config") from None


def trust_context(device):
    ca_file = device.get("ca_file")
    if ca_file is None:
        context = ssl.create_default_context()
    else:


        fd = win.fd_open(ca_file, private=False) if win else os.open(ca_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise SetupError("invalid_trust_file")
            data = handle.read(1_000_001)
        if len(data) > 1_000_000:
            raise SetupError("trust_file_too_large")
        context = ssl.create_default_context(cadata=data.decode("ascii"))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def load_configs(api_path, device_path):
    for path in (api_path, device_path):
        if Path(path).expanduser().resolve().is_relative_to(HERE):
            raise SetupError("keep_credentials_outside_customer_package")
    api = api_config(secure_json(api_path))
    try:
        device = sibling("connector").validate_config(secure_json(device_path, limit=32768))

        trust_context(device)
    except Exception:
        raise SetupError("invalid_device_config_or_trust_store") from None
    return api, device


def check(api_path, device_path, chrome=None):
    if sys.platform not in ("darwin", "linux", "win32"):
        raise SetupError("supported_posix_platform_required")
    load_configs(api_path, device_path)
    try:
        sibling("browser").find_chrome(chrome)
    except Exception:
        raise SetupError("chrome_not_found") from None
    return {"status": "checked", "mode": "offline", "api_config": "valid",
            "device_config": "valid", "chrome": "found", "network_tested": False,
            "browser_started": False, "device_authentication": "not_tested"}


def probe(api_path, device_path):
    api, device = load_configs(api_path, device_path)
    api["timeout"] = min(api["timeout"], 4)
    _, code = sibling("client").request(api, "GET", "/health")
    tls_ok = False
    try:
        context = trust_context(device)
        with socket.create_connection((device["host"], device["port"]), timeout=4) as raw:
            with context.wrap_socket(raw, server_hostname=device["server_hostname"]):
                tls_ok = True
    except Exception:
        pass
    return {"status": "checked" if code == 200 and tls_ok else "failed",
            "mode": "online", "api_http_status": code, "api_health_ok": code == 200,
            "connector_tls_verified": tls_ok, "device_authentication": "not_tested",
            "browser_started": False}


def online_probe(api_path, device_path, seconds=12):

    command = [sys.executable, "-I", "-S", "-B", str(Path(__file__).resolve()), "_probe",
               "--api-config", str(api_path), "--device-config", str(device_path)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=seconds, check=False)
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or result.returncode not in (0, 2):
            raise ValueError()

        expected = {"status", "mode", "api_http_status", "api_health_ok", "connector_tls_verified",
                    "device_authentication", "browser_started"}
        if (set(value) != expected or value.get("status") not in ("checked", "failed")
                or value.get("mode") != "online" or value.get("device_authentication") != "not_tested"
                or value.get("browser_started") is not False
                or type(value.get("api_health_ok")) is not bool
                or type(value.get("connector_tls_verified")) is not bool
                or (value.get("api_http_status") is not None
                    and (type(value["api_http_status"]) is not int or not 100 <= value["api_http_status"] <= 599))):
            raise ValueError()
        return value
    except subprocess.TimeoutExpired:
        return {"status": "failed", "mode": "online", "error": "diagnostic_deadline",
                "device_authentication": "not_tested", "browser_started": False}
    except Exception:
        return {"status": "failed", "mode": "online", "error": "diagnostic_failed",
                "device_authentication": "not_tested", "browser_started": False}


def redact(value, token):
    if isinstance(value, str):
        return value.replace(token, "[REDACTED]") if token else value
    if isinstance(value, dict):
        return {redact(str(key), token): redact(item, token) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, token) for item in value]
    return value


def ownership_stamp(path):
    if win: return win.stamp(path)
    info = Path(path).lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise SetupError("ownership_file_changed")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def assert_ownership(path, snapshot, stamp):


    if stamp is None or ownership_stamp(path) != stamp:
        raise SetupError("ownership_file_changed")
    current = secure_json(path)
    if current != snapshot or ownership_stamp(path) != stamp:
        raise SetupError("ownership_file_changed")
    profile = Path(snapshot["profile"])
    if profile != Path(path).parent / "profile":
        raise SetupError("profile_changed")
    if win:
        win.private_dir(profile, create=False); win.private_dir(Path(path).parent, create=False)
        info = profile.lstat()
        if (info.st_dev, info.st_ino) != (snapshot.get("profile_device"), snapshot.get("profile_inode")): raise SetupError("profile_changed")
        return
    info, directory = profile.lstat(), Path(path).parent.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077
            or (info.st_dev, info.st_ino) != (snapshot.get("profile_device"), snapshot.get("profile_inode"))
            or not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid() or directory.st_mode & 0o077):
        raise SetupError("profile_changed")


def process_table(deadline):
    if win: return win.process_table(deadline)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SetupError("process_observation_deadline")
    result = subprocess.run(
        ["/bin/ps", "-ww", "-A", "-o", "pid=", "-o", "ppid=", "-o", "lstart=", "-o", "stat=", "-o", "command="],
        capture_output=True, text=True, timeout=remaining, check=False, env=dict(os.environ, LC_ALL="C"))
    if result.returncode or time.monotonic() >= deadline:
        raise SetupError("process_observation_failed")
    rows = {}
    for line in result.stdout.splitlines():
        fields = line.split(None, 8)
        if len(fields) != 9 or not fields[0].isdigit() or not fields[1].isdigit() or int(fields[0]) in rows:
            raise SetupError("process_observation_invalid")
        pid = int(fields[0])
        rows[pid] = {"pid": pid, "parent_pid": int(fields[1]), "started": " ".join(fields[2:7]),
                     "stat": fields[7], "command": fields[8]}
    if os.getpid() not in rows:
        raise SetupError("process_observation_invalid")
    return rows


def owned_process_snapshot(path, snapshot, stamp, seconds=5):
    deadline = time.monotonic() + seconds
    assert_ownership(path, snapshot, stamp)
    rows = process_table(deadline)
    original = snapshot["identity"]
    current = rows.get(snapshot["pid"])
    if current is None or current["stat"].startswith("Z"):
        raise SetupError("browser_root_exited_before_stop")
    if any(current.get(key) != original.get(key) for key in ("pid", "parent_pid", "started", "command")):
        raise SetupError("browser_root_identity_changed")
    if "start_ticks" in original:


        fd = os.open(Path('/proc') / str(current['pid']) / 'stat', os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, 'r') as handle:
            raw = handle.read(4097)
        if len(raw) > 4096 or raw[raw.rfind(')') + 2:].split()[19] != original['start_ticks']:
            raise SetupError("browser_root_identity_changed")
    if "--user-data-dir=" + snapshot["profile"] not in current["command"]:
        raise SetupError("browser_root_identity_changed")
    children = {}
    for pid, row in rows.items():
        children.setdefault(row['parent_pid'], []).append(pid)
    owned, pending = {current['pid']}, [current['pid']]
    while pending:
        for pid in children.get(pending.pop(), []):
            if pid not in owned:
                owned.add(pid); pending.append(pid)
        if len(owned) > 256:
            raise SetupError("browser_tree_limit")
    assert_ownership(path, snapshot, stamp)
    if time.monotonic() >= deadline:
        raise SetupError("process_observation_deadline")
    return owned


def observe_stopped(path, snapshot, stamp, recorded, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        assert_ownership(path, snapshot, stamp)


        identity = snapshot["identity"]
        if not win and identity.get("parent_pid") == os.getpid() and identity.get("pid") == snapshot["pid"]:
            try:
                os.waitpid(snapshot["pid"], os.WNOHANG)
            except ChildProcessError:
                pass
        rows = process_table(deadline)
        absent = recorded.isdisjoint(rows)
        profile_absent = not any(snapshot["profile"] in row["command"] for row in rows.values())
        if absent and profile_absent:

            assert_ownership(path, snapshot, stamp)
            if time.monotonic() >= deadline:
                break
            return {"recorded_processes_absent": len(recorded), "profile_processes_absent": True,
                    "ownership_unchanged": True, "profile_identity_unchanged": True,
                    "extra_signals_sent": False}
        time.sleep(min(.1, max(0, deadline - time.monotonic())))
    raise SetupError("process_exit_not_proven")


def first_error_summary(first):

    safe_keys = {"schema", "reason", "phase", "at_unix", "monotonic_ns", "owner_pid",
                 "epoch", "exception_class", "errno", "ssl_reason"}
    result = {key: value for key, value in first.items() if key in safe_keys
              and (value is None or type(value) in (str, int, float, bool))}
    if isinstance(first.get('operation'), str) and first['operation'] in {'none', 'tls_handshake', 'recv_header', 'recv_body', 'send_frame',
                                 'shutdown', 'close', 'dispatch', 'queue', 'select'}:
        result['operation'] = first['operation']
    if isinstance(first.get('thread_role'), str) and first['thread_role'] in {'tls_io', 'caller'}:
        result['thread_role'] = first['thread_role']
    result['transport'] = sibling('tls_channel').safe_transport_details(first.get('transport'))
    return result


def cleanup_diagnostic(error):

    if str(error) in {"profile_in_use", "profile_in_use_or_unsafe_lock", "profile_identity_changed",
                      "profile_exit_not_verified", "browser_recovery_state_changed",
                      "browser_recovery_identity_unverified", "unsafe_profile_directory", "unsafe_profile_lock"}:
        return {"class": "BrowserError", "reason": str(error)}
    if isinstance(error, SetupError):
        allowed = {"ownership_file_changed", "profile_changed", "browser_root_exited_before_stop",
                   "browser_root_identity_changed", "browser_tree_limit", "process_observation_deadline",
                   "process_observation_failed", "process_observation_invalid", "process_exit_not_proven",
                   "browser_stop_unconfirmed", "browser_descendants_unverified"}
        return {"class": "SetupError", "reason": str(error) if str(error) in allowed else "ownership_check_failed"}
    if isinstance(error, subprocess.TimeoutExpired):
        return {"class": "TimeoutExpired", "reason": "process_observation_deadline"}
    if isinstance(error, OSError):
        return {"class": "OSError", "reason": "cleanup_io_failed"}

    reason = ("process_identity_changed" if str(error) == "process identity changed; refusing to signal this PID"
              else "launcher_cleanup_error")
    return {"class": "LauncherError", "reason": reason}


def run_owned(device, directory, *, chrome=None, headless=False, browser=None, factory=None, on_status=None, reuse_profile=False):

    browser = browser or sibling("browser")
    factory = factory or sibling("connector").Connector
    previous = {}
    connection = None
    snapshot = None
    stamp = None
    launched = False
    state_path = None
    profile_lease = None
    requested = [None]
    watcher = None
    watching_done = threading.Event()
    report = {"status": "stopped", "connector": "not_started", "browser_cleanup": "not_started"}

    def request_stop(number, _frame):
        requested[0] = number
        if connection is not None:
            connection._signal_stop = True

    signals = (signal.SIGINT, signal.SIGTERM) if win else (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    if win and os.environ.get("EH_STOP_STDIN") == "1":
        def stdin_stop():
            sys.stdin.buffer.readline(16)
            request_stop(signal.SIGTERM, None)
        threading.Thread(target=stdin_stop, daemon=True).start()
    try:
        for number in signals:
            previous[number] = signal.signal(number, request_stop)
        if reuse_profile:
            profile_lease = browser.profile_lease(directory)
            started = browser.start(directory, chrome=chrome, headless=headless, reuse_profile=True, lease=profile_lease)
        else:
            started = browser.start(directory, chrome=chrome, headless=headless)
        launched = True
        state_path, snapshot = browser.read_state(started["state_path"])
        stamp = ownership_stamp(state_path)
        assert_ownership(state_path, snapshot, stamp)
        report["browser_cleanup"] = "pending"
        if requested[0] is None:
            connection = factory(device, state_path)
            if requested[0] is not None:
                connection._signal_stop = True
            if on_status is not None:
                def observe_connection():
                    while not watching_done.wait(0.1):
                        if connection.connected.is_set():
                            on_status({"status": "connected", "mode": "foreground", "task_verified": False})
                            return
                watcher = threading.Thread(target=observe_connection, daemon=True)
                watcher.start()
            connection.run()
            report["connector"] = "stopped"
    except Exception as error:
        report.update(status="failed", error="startup_or_connector_failed")
        if (reuse_profile and isinstance(error, getattr(browser, 'BrowserError', ()))
                and str(error) in {'profile_in_use', 'profile_in_use_or_unsafe_lock',
                                   'profile_reuse_requires_review', 'profile_identity_changed',
                                   'profile_exit_not_verified', 'unsafe_profile_directory',
                                   'unsafe_profile_runtime_file', 'unsafe_profile_lock', 'invalid_profile_lease'}):
            report['first_error'] = {'schema': 'eh-browser-error/1', 'reason': str(error), 'phase': 'profile'}
        if connection is not None:
            report["connector"] = "failed"
            first = getattr(connection, "first_error", None)
            if isinstance(first, dict):
                report["first_error"] = first_error_summary(first)
        elif state_path is None:


            report["browser_cleanup"] = "unknown" if launched else "startup_not_confirmed"
    finally:
        for number in previous:
            signal.signal(number, signal.SIG_IGN)
        watching_done.set()
        if watcher is not None:
            watcher.join(timeout=1)
        try:
            if connection is not None:
                try:
                    connection.stop()
                except Exception:
                    report["status"] = "failed"
                    report.setdefault("cleanup_errors", []).append("connector_cleanup_failed")
            if snapshot is not None and connection is not None and not getattr(connection, 'shutdown_complete', True):


                report.update(status='failed', browser_cleanup='retained_connector_shutdown_incomplete')
                report.setdefault('cleanup_errors', []).append('connector_shutdown_incomplete')
            elif snapshot is not None:
                try:
                    try:
                        recorded = owned_process_snapshot(state_path, snapshot, stamp)
                    except SetupError as error:
                        if str(error) != "browser_root_exited_before_stop":
                            raise
                        if not win and snapshot.get("identity", {}).get("parent_pid") == os.getpid():
                            try:
                                os.waitpid(snapshot["pid"], os.WNOHANG)
                            except ChildProcessError:
                                pass
                        # The user or Chrome may already have closed the window.
                        # Reconcile only after connector shutdown, under all locks.
                        result = browser.reconcile_stopped(state_path, lease=profile_lease, expected=snapshot)
                        report["browser_stop_result"] = result
                        report["browser_cleanup"] = result["browser_cleanup"]
                        recorded = None
                    try:
                        result = browser.stop(state_path) if recorded is not None else result
                    except Exception as error:
                        report["browser_stop_diagnostic"] = cleanup_diagnostic(error)
                        report["browser_exit_observation"] = observe_stopped(state_path, snapshot, stamp, recorded)
                        report["browser_cleanup"] = "observed_after_cleanup_error"
                    else:
                        report["browser_stop_result"] = result
                        if result.get("status") != "stopped":
                            raise SetupError("browser_stop_unconfirmed")
                        if result.get("reason") == "parent_already_exited":
                            raise SetupError("browser_descendants_unverified")
                        report["browser_cleanup"] = "verified_snapshot_stopped"
                except Exception as error:
                    report.update(status="failed", browser_cleanup="unknown")
                    report["browser_cleanup_diagnostic"] = cleanup_diagnostic(error)
                    report.setdefault("cleanup_errors", []).append("browser_cleanup_unconfirmed")

                try:
                    if not win: os.waitpid(snapshot["pid"], os.WNOHANG)
                except (ChildProcessError, KeyError, OSError):
                    pass
        finally:
            try:
                if profile_lease is not None:
                    profile_lease.close()
            finally:
                for number, handler in previous.items():
                    signal.signal(number, handler)
    if requested[0] is not None:
        report["stop_signal"] = requested[0]
    report["profile_retained"] = True
    report["automatic_reconnect"] = False
    return redact(report, device.get("token", ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True, metavar="{check,diagnose,run}")
    for name in ("check", "diagnose", "run", "_probe"):
        entry = sub.add_parser(name) if name == "_probe" else sub.add_parser(name, help={
            "check": "offline configuration and Chrome check",
            "diagnose": "offline check; --online explicitly permits bounded network probes",
            "run": "start a dedicated Chrome and foreground connector"}[name])
        entry.add_argument("--api-config", required=True)
        entry.add_argument("--device-config", required=True)
        if name != "_probe":
            entry.add_argument("--chrome")
        if name == "diagnose":
            entry.add_argument("--online", action="store_true", help="explicitly allow HTTPS GET and connector TLS")
        if name == "run":
            entry.add_argument("--directory", required=True, help="dedicated browser directory; new unless --reuse-profile is set")
            entry.add_argument("--reuse-profile", action="store_true", help="reuse this managed profile only after verified shutdown")
            entry.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.operation == "_probe":
            result = probe(args.api_config, args.device_config)
        else:
            result = check(args.api_config, args.device_config, args.chrome)
            if args.operation == "diagnose" and args.online:
                result = online_probe(args.api_config, args.device_config)
            elif args.operation == "run":
                _, device = load_configs(args.api_config, args.device_config)
                print(json.dumps({"status": "starting", "mode": "foreground", "stop": "Ctrl-C"}), flush=True)
                result = run_owned(device, args.directory, chrome=args.chrome, headless=args.headless,
                                   reuse_profile=args.reuse_profile, on_status=lambda value: print(json.dumps(value), flush=True))
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if result["status"] in ("checked", "stopped") else 2
    except SetupError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), flush=True)
        return 2
    except Exception:
        print(json.dumps({"status": "failed", "error": "setup_failed"}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
