#!/usr/bin/env python3








from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

if sys.platform == "win32":
    import importlib.util as _win_import
    _win_spec = _win_import.spec_from_file_location("eh_win_platform", Path(__file__).resolve().with_name("win_platform.py"))
    win = _win_import.module_from_spec(_win_spec); _win_spec.loader.exec_module(win)
else:
    win = None

SENSITIVE_FILE = Path(__file__).with_name("sensitive_domains.json")
_HOSTNAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251})")


def blocked_resolver_rules(path=None):









    path = SENSITIVE_FILE if path is None else Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    suffixes = data.get("suffixes") if isinstance(data, dict) else None
    if not isinstance(suffixes, list):
        return []
    rules = []
    for suffix in suffixes:
        if isinstance(suffix, str) and _HOSTNAME.fullmatch(suffix):
            rules.append("MAP *." + suffix + " ~NOTFOUND")
            rules.append("MAP " + suffix + " ~NOTFOUND")
    return rules


KIND = "eh-owned-local-browser-v1"


class BrowserError(Exception):
    pass


def write_state(path, value):
    if win: return win.atomic(path, (json.dumps(value)+"\n").encode())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                prefix=".browser-state-", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(handle.fileno(), 0o600)
            handle.write((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def process_identity(pid):

    if win: return win.process_identity(pid)
    if not isinstance(pid, int) or pid <= 1:
        raise BrowserError("invalid managed process id")
    result = subprocess.run(
        ["ps", "-ww", "-p", str(pid), "-o", "lstart=", "-o", "stat=", "-o", "ppid=", "-o", "command="],
        capture_output=True, text=True, timeout=5, check=False,
        env=dict(os.environ, LC_ALL="C"),
    )
    line = result.stdout.strip()
    if result.returncode == 1 and not line:
        return None
    if result.returncode != 0:
        raise BrowserError("cannot verify process identity")
    parts = line.split(None, 7)
    if len(parts) != 8:
        raise BrowserError("cannot parse process identity")
    if parts[5].startswith("Z"):
        return None
    identity = {"pid": pid, "started": " ".join(parts[:5]),
                "parent_pid": int(parts[6]), "command": parts[7]}
    proc_stat = Path("/proc") / str(pid) / "stat"
    if proc_stat.exists():


        try:
            raw = proc_stat.read_text()
            identity["start_ticks"] = raw[raw.rfind(")") + 2:].split()[19]
        except (OSError, IndexError):
            raise BrowserError("cannot verify kernel process identity") from None
    return identity


def descendant_ids(root_pid):
    if win: return win.descendant_ids(root_pid)
    result = subprocess.run(
        ["ps", "-A", "-o", "pid=", "-o", "ppid="],
        capture_output=True, text=True, timeout=5, check=False,
    )
    if result.returncode:
        raise BrowserError("cannot inventory owned browser descendants")
    children = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2:
            pid, parent = map(int, fields)
            children.setdefault(parent, []).append(pid)
    found, seen, pending = [], {root_pid}, [root_pid]
    while pending:
        parent = pending.pop()
        for pid in children.get(parent, []):
            if pid not in seen:
                found.append((pid, parent))
                seen.add(pid)
                pending.append(pid)
        if len(found) > 256:
            raise BrowserError("browser descendant count exceeds limit")
    return found


def still_owned(identity):
    current = process_identity(identity["pid"])
    if current is None:
        return False
    keys = ("pid", "started", "command", "start_ticks")
    if any(current.get(key) != identity.get(key) for key in keys):
        raise BrowserError("process identity changed; refusing to signal this PID")
    return True


def signal_owned(identity, sig):
    if not still_owned(identity):
        return False
    try:
        os.kill(identity["pid"], sig)
    except ProcessLookupError:
        return False
    return True


def stop_owned(identities):

    if win: return win.stop_owned(identities)
    active = [item for item in identities if still_owned(item)]
    if not active:
        return
    signal_owned(active[0], signal.SIGTERM)

    def remaining(items):
        pending = []
        for item in items:
            try:
                if still_owned(item):
                    pending.append(item)
            except BrowserError as error:
                if str(error) != "process identity changed; refusing to signal this PID":
                    raise




                pending.append(item)
        return pending

    for timeout, sig in ((4.0, signal.SIGTERM), (3.0, signal.SIGKILL), (2.0, None)):
        deadline = time.monotonic() + timeout
        while active and time.monotonic() < deadline:
            active = remaining(active)
            if active:
                time.sleep(0.1)
        if not active:
            return
        if sig is not None:
            for item in active:
                try:
                    signal_owned(item, sig)
                except BrowserError as error:
                    if str(error) != "process identity changed; refusing to signal this PID":
                        raise

    for item in active:
        still_owned(item)
    raise BrowserError("owned processes remain; profile retained for inspection")


def find_chrome(explicit=None):
    if explicit:
        candidate = Path(explicit).expanduser().absolute()
    else:
        candidates = [
            str(Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))/"Google/Chrome/Application/chrome.exe"),
            str(Path(os.environ.get("LOCALAPPDATA", "C:/Users/Default/AppData/Local"))/"Google/Chrome/Application/chrome.exe"),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            shutil.which("google-chrome"), shutil.which("google-chrome-stable"),
            shutil.which("chromium"), shutil.which("chromium-browser"),
        ]
        candidate = next((Path(item) for item in candidates if item and Path(item).is_file()), None)
    if candidate is None or not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise BrowserError("Chrome executable not found; pass --chrome explicitly")
    return candidate.resolve()


def launch_command(executable, profile, *, headless=False, resolver_rules=()):

    command = [
        str(executable), "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
        "--user-data-dir=" + str(profile), "--no-first-run", "--no-default-browser-check",
        "--disable-sync", "--disable-background-networking", "--disable-component-update",
        "--window-size=1440,1000",
    ]
    if resolver_rules:
        command.append("--host-resolver-rules=" + ",".join(resolver_rules))
    if headless:
        command.append("--headless=new")
    command.append("about:blank")
    return command


def _private_directory(path):
    path = Path(path)
    if win:
        try: win.private_dir(path, create=False)
        except (OSError, ValueError): raise BrowserError("unsafe_profile_directory") from None
    info = path.lstat()
    if (path.is_symlink() or not stat.S_ISDIR(info.st_mode)
            or (not win and (info.st_uid != os.getuid() or info.st_mode & 0o077))):
        raise BrowserError("unsafe_profile_directory")
    return info


class ProfileLease:
    def __init__(self, path, directory):
        self.path, self.directory, self.fd = path, directory, None
        try:
            if win:
                self.fd = win.lock_file(path)
            else:
                import fcntl
                self.fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
                                  | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0), 0o600)
                info = os.fstat(self.fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                    raise BrowserError("unsafe_profile_lock")
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.verify(directory)
        except (OSError, ValueError):
            self.close()
            raise BrowserError("profile_in_use_or_unsafe_lock") from None
        except BaseException:
            self.close()
            raise

    def verify(self, directory):
        if self.fd is None or self.directory != directory:
            raise BrowserError("invalid_profile_lease")
        held, current = os.fstat(self.fd), self.path.lstat()
        if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)):
            raise BrowserError("unsafe_profile_lock")

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _checked_path(path):
    raw = Path(path).expanduser().absolute()
    if win:
        try: win.path_check(raw)
        except (OSError, ValueError):
            raise BrowserError("unsafe_profile_directory") from None
    return raw


def profile_lease(directory):

    raw = _checked_path(directory)
    if raw.name in ("", ".", "..") or raw.is_symlink():
        raise BrowserError("unsafe_profile_directory")
    parent = raw.parent.resolve()
    _private_directory(parent)
    root = parent / raw.name
    return ProfileLease(parent / (raw.name + ".profile.lock"), root)


def _assert_profile_idle(profile):
    if win:
        rows = win.process_table(time.monotonic() + 5)
        commands = [row['command'] for row in rows.values()]
    else:
        result = subprocess.run(["ps", "-A", "-ww", "-o", "command="],
                                capture_output=True, text=True, timeout=5, check=False)
        if result.returncode:
            raise BrowserError("profile_exit_not_verified")
        commands = result.stdout.splitlines()
    if any(str(profile) in command for command in commands):
        raise BrowserError("profile_in_use")


def _validate_reuse(root, profile):
    try:
        _, previous = read_state(root / "ownership.json")
    except BrowserError:
        raise BrowserError("profile_reuse_requires_review") from None
    if previous.get("persistent_profile") is not True or previous.get("status") != "stopped":
        raise BrowserError("profile_reuse_requires_review")
    root_info, info = _private_directory(root), _private_directory(profile)
    if ((info.st_dev, info.st_ino) != (previous.get("profile_device"), previous.get("profile_inode"))
            or (root_info.st_dev, root_info.st_ino) !=
               (previous.get("directory_device"), previous.get("directory_inode"))):
        raise BrowserError("profile_identity_changed")
    identity = previous.get("identity")
    if not isinstance(identity, dict) or identity.get("pid") != previous.get("pid"):
        raise BrowserError("profile_reuse_requires_review")
    current = process_identity(identity["pid"])
    keys = ("pid", "started", "command", "start_ticks")
    if current is not None and all(current.get(k) == identity.get(k) for k in keys):
        raise BrowserError("profile_in_use")


    _assert_profile_idle(profile)


def _remove_old_file(path):
    try: info = path.lstat()
    except FileNotFoundError: return
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or (not win and info.st_uid != os.getuid())):
        raise BrowserError("unsafe_profile_runtime_file")
    if win:
        with os.fdopen(win.fd_open(path), "rb"): pass
    path.unlink()


def start(directory, chrome=None, headless=False, *, reuse_profile=False, lease=None):
    executable = find_chrome(chrome)
    raw = _checked_path(directory)
    if raw.name in ("", ".", "..") or raw.is_symlink():
        raise BrowserError("unsafe_profile_directory")
    root = raw.parent.resolve() / raw.name
    own_lease = None
    try:
        if reuse_profile:
            if lease is None:
                own_lease = lease = profile_lease(root)
            if not isinstance(lease, ProfileLease):
                raise BrowserError("invalid_profile_lease")
            lease.verify(root)
        elif lease is not None:
            raise BrowserError("invalid_profile_lease")
        created = False
        try:
            if win: win.private_dir(root, exclusive=True)
            else: root.mkdir(mode=0o700, parents=False, exist_ok=False)
            created = True
        except FileExistsError:
            if not reuse_profile:
                raise BrowserError("directory already exists; refusing to reuse or overwrite it") from None
        _private_directory(root)
        with ProfileLease(root / ".browser.lock", root):
            profile = root / "profile"
            if created:
                if win: win.private_dir(profile, exclusive=True)
                else: profile.mkdir(mode=0o700)
                return _launch(root, profile, executable, headless, reuse_profile)

            with ProfileLease(root / ".connector.lock", root):
                _validate_reuse(root, profile)
                _remove_old_file(profile / "DevToolsActivePort")
                _remove_old_file(root / "chrome.log")
                return _launch(root, profile, executable, headless, True)
    finally:
        if own_lease is not None:
            own_lease.close()


def _launch(root, profile, executable, headless, persistent):
    state_path = root / "ownership.json"
    state = {"kind": KIND, "status": "starting", "owner_uid": (win.owner_id() if win else os.getuid()),
             "directory": str(root), "profile": str(profile), "state_path": str(state_path),
             "profile_inode": profile.stat().st_ino, "profile_device": profile.stat().st_dev,
             "persistent_profile": persistent, "directory_inode": root.stat().st_ino,
             "directory_device": root.stat().st_dev}
    write_state(state_path, state)
    command = launch_command(executable, profile, headless=headless,
                             resolver_rules=blocked_resolver_rules())
    process = None
    try:
        log_fd = (win.fd_open(root / "chrome.log", write=True, exclusive=True) if win else os.open(root / "chrome.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        with os.fdopen(log_fd, "wb") as log:
            process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=not bool(win), close_fds=True,
            )
        state["pid"] = process.pid
        state["launch_args"] = command
        identity = process_identity(process.pid)
        if identity is None or "--user-data-dir=" + str(profile) not in identity["command"]:
            raise BrowserError("new browser identity could not be verified")
        state["identity"] = identity
        write_state(state_path, state)
        deadline = time.monotonic() + 15
        active_port = profile / "DevToolsActivePort"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise BrowserError("owned Chrome exited before opening its debug endpoint")
            if active_port.is_file() and not active_port.is_symlink():
                lines = active_port.read_text().splitlines()
                if lines and lines[0].isdigit() and 1 <= int(lines[0]) <= 65535:
                    endpoint = "http://127.0.0.1:" + lines[0]
                    if len(lines) < 2 or not re.fullmatch(r"/devtools/browser/[A-Za-z0-9_-]{1,128}", lines[1]):
                        raise BrowserError("invalid managed browser endpoint")
                    state.update(status="running", CDP_ENDPOINT=endpoint, browser_ws_path=lines[1])
                    write_state(state_path, state)
                    return {"status": "running", "pid": process.pid,
                            "CDP_ENDPOINT": endpoint, "state_path": str(state_path),
                            "profile": str(profile), "cloud_bridge_created": False}
            time.sleep(0.1)
        raise BrowserError("timed out waiting for owned Chrome endpoint")
    except Exception:
        state["status"] = "start_failed"
        if process is not None and process.poll() is None:


            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        write_state(state_path, state)
        raise


def read_state(path):
    path = Path(path).expanduser().absolute()
    if path.name != "ownership.json":
        raise BrowserError("state filename must be ownership.json")
    try:
        if win:
            raw = win.read_file(path, 65536)
        else:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                        or info.st_uid != (win.owner_id() if win else os.getuid())):
                    raise BrowserError("state must be a regular current-owner mode-0600 file")
                raw = handle.read(65_537)
        if len(raw) > 65_536:
            raise BrowserError("state exceeds size limit")
        state = json.loads(raw)
    except (OSError, ValueError, TypeError):
        raise BrowserError("cannot securely read browser ownership state") from None
    if not isinstance(state, dict) or state.get("kind") != KIND or state.get("owner_uid") != (win.owner_id() if win else os.getuid()):
        raise BrowserError("invalid browser ownership state")
    root = path.parent.resolve()
    if state.get("directory") != str(root) or state.get("state_path") != str(root / "ownership.json"):
        raise BrowserError("ownership state directory mismatch")
    if state.get("profile") != str(root / "profile"):
        raise BrowserError("ownership profile must be inside its dedicated directory")
    return root / "ownership.json", state


def _close_transport(port, target, guard):
    spec = importlib.util.spec_from_file_location("eh_browser_close_connector", Path(__file__).with_name("connector.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._LocalInputCDP(port, target, guard)


def _graceful_close(state_path, state):

    endpoint = urlsplit(state.get("CDP_ENDPOINT", ""))
    target = state.get("browser_ws_path", "")
    if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1"
            or endpoint.username is not None or endpoint.password is not None
            or endpoint.path or endpoint.query or endpoint.fragment
            or endpoint.port is None or not 1 <= endpoint.port <= 65535
            or not isinstance(target, str)
            or not re.fullmatch(r"/devtools/browser/[A-Za-z0-9_-]{1,128}", target)):
        raise BrowserError("invalid managed browser endpoint")
    profile = Path(state["profile"])
    deadline = time.monotonic() + 4

    def guard():
        if time.monotonic() >= deadline:
            raise BrowserError("browser_close_timeout")
        _, current = read_state(state_path)
        info = _private_directory(profile)
        if (current != state or (info.st_dev, info.st_ino) !=
                (state.get("profile_device"), state.get("profile_inode"))
                or not still_owned(state["identity"])):
            raise BrowserError("browser_close_ownership_changed")
        active = profile / "DevToolsActivePort"
        if win:
            raw = win.read_file(active, 4096)
        else:
            fd = os.open(active, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                    raise BrowserError("browser_close_endpoint_changed")
                raw = handle.read(4097)
        if len(raw) > 4096 or raw.decode("ascii").splitlines() != [str(endpoint.port), target]:
            raise BrowserError("browser_close_endpoint_changed")

    client = None
    attempted = False
    try:
        guard()
        client = _close_transport(endpoint.port, target, guard)
        attempted = True
        client.send("Browser.close", {})
    except Exception:


        pass
    finally:
        if client is not None:
            client.close()
    return attempted


def _wait_owned_exit(identities, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            active = []
            for item in identities:
                if time.monotonic() >= deadline:
                    return False
                if still_owned(item):
                    active.append(item)
        except BrowserError as error:
            if str(error) != "process identity changed; refusing to signal this PID":
                return False


            active = identities
        if not active:
            return True
        time.sleep(.1)
    return False


def stop(path):
    raw = _checked_path(path)
    if raw.parent.is_symlink():
        raise BrowserError("unsafe_profile_directory")
    root = raw.parent.resolve()
    _private_directory(root)
    with ProfileLease(root / ".browser.lock", root):
        return _stop(root / raw.name)


def _stop(path):
    state_path, state = read_state(path)
    if state.get("status") == "stopped":
        return {"status": "stopped", "state_path": str(state_path), "already_stopped": True}
    profile = Path(state["profile"])
    info = profile.lstat()
    if (not stat.S_ISDIR(info.st_mode) or profile.is_symlink()
            or info.st_ino != state.get("profile_inode")
            or info.st_dev != state.get("profile_device")):
        raise BrowserError("profile identity changed; refusing cleanup")
    identity = state.get("identity")
    if not isinstance(identity, dict) or identity.get("pid") != state.get("pid"):
        raise BrowserError("state has no verified process identity; inspect startup failure manually")
    args = state.get("launch_args")
    expected = "--user-data-dir=" + str(profile)
    if (not isinstance(args, list) or expected not in args
            or "--remote-debugging-address=127.0.0.1" not in args
            or "--remote-debugging-port=0" not in args or args[-1] != "about:blank"
            or expected not in identity.get("command", "")):
        raise BrowserError("stored process does not identify this dedicated Chrome profile")
    if not still_owned(identity):


        state.update(status="stopped", cleanup="profile_retained_parent_already_exited")
        write_state(state_path, state)
        return {"status": "stopped", "pid": state["pid"], "state_path": str(state_path),
                "profile_removed": False, "reason": "parent_already_exited"}
    identities = [identity]
    verified_pids = {identity["pid"]}
    for pid, parent in descendant_ids(identity["pid"]):
        child = process_identity(pid)
        if child is not None and child["parent_pid"] == parent and parent in verified_pids:
            identities.append(child)
            verified_pids.add(pid)

    if not still_owned(identity):
        raise BrowserError("browser exited during ownership inventory; retry stop to inspect")
    graceful = False
    if state.get("persistent_profile") is True:
        if _graceful_close(state_path, state):
            graceful = _wait_owned_exit(identities)
    stop_owned(identities)
    if win:
        rows=win.process_table(time.monotonic()+5)
        if any(item['pid'] in rows for item in identities) or any(str(profile) in row['command'] for row in rows.values()):
            raise BrowserError('owned processes remain; profile retained for inspection')
    state.update(status="stopped", cleanup="profile_retained", stopped_processes=len(identities),
                 graceful_shutdown=graceful)


    write_state(state_path, state)
    return {"status": "stopped", "pid": state["pid"], "state_path": str(state_path),
            "verified_processes_stopped": len(identities), "profile_removed": False,
            "graceful_shutdown": graceful,
            "profile": str(profile)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    start_parser = sub.add_parser("start")
    start_parser.add_argument("--directory", required=True)
    start_parser.add_argument("--chrome")
    start_parser.add_argument("--headless", action="store_true")
    start_parser.add_argument("--reuse-profile", action="store_true")
    stop_parser = sub.add_parser("stop")
    stop_parser.add_argument("--state", required=True)
    args = parser.parse_args(argv)
    try:
        result = (start(args.directory, args.chrome, args.headless, reuse_profile=args.reuse_profile) if args.operation == "start"
                  else stop(args.state))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        message = str(error) if isinstance(error, BrowserError) else type(error).__name__
        print(json.dumps({"status": "error", "error": message}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
