#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


HERE = Path(__file__).resolve().parent


class LaunchError(Exception):
    pass


def default_directory():
    
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", "").strip()
        if not base or not Path(base).is_absolute():
            raise LaunchError("localappdata_required")
        return Path(base) / "EH Client Data"
    return Path.home() / ".local" / "share" / "eh-subscription-console"


def data_directory(value, *, here=None):
    




    package = Path(here if here is not None else HERE).resolve()
    candidate = Path(value).expanduser().absolute() if value is not None else default_directory().absolute()
    resolved = candidate.resolve()
    boundaries = {package}
    for start in (package, resolved):
        for parent in (start, *start.parents):
            marker = parent / ".git"
            if marker.exists() or marker.is_symlink():
                boundaries.add(parent)
    if any(resolved == root or root in resolved.parents for root in boundaries):
        raise LaunchError("private_data_must_be_outside_source")
    return candidate


def version(*, here=None):
    package = Path(here if here is not None else HERE).resolve()
    path = package / "VERSION"
    if not path.exists() and package.name == "client":
        parent = package.parent
        if (parent / ".git").exists() or (parent / "release_files.json").is_file():
            path = parent / "VERSION"
    try:
        if path.is_symlink() or not path.is_file():
            raise LaunchError("client_version_unavailable")
        with path.open("r", encoding="ascii") as stream:
            raw = stream.read(129)
        value = raw.strip()
        if len(raw) > 128 or not re.fullmatch(r"[0-9][A-Za-z0-9.+_-]{0,79}", value):
            raise LaunchError("client_version_unavailable")
        return value
    except (OSError, UnicodeError) as exc:
        raise LaunchError("client_version_unavailable") from exc


def parser():
    result = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    result.add_argument("--version", action="store_true", help="show the local client version")
    commands = result.add_subparsers(dest="command")
    start = commands.add_parser("start", help="start the local customer console", allow_abbrev=False)
    start.add_argument("--directory", help="private data directory outside the source checkout")
    start.add_argument("--endpoint", help="API endpoint; defaults to the existing console default")
    start.add_argument("--no-open", action="store_true", help="start without opening a browser tab")
    start.add_argument("--chrome", help="task Chrome executable")
    start.add_argument("--headless", action="store_true", help="run the owned task Chrome headless")
    connect = commands.add_parser("agent-connect", help="prepare instructions to paste into your local Agent", allow_abbrev=False)
    connect.add_argument("--directory", "--console-directory", dest="directory", help="existing private console directory")
    connect.add_argument("--host", choices=("generic", "codex"), default="generic")
    connect.add_argument("--json-only", action="store_true", help="print safe connection metadata instead of one sentence")
    return result


def main(argv=None):
    options = parser()
    args = options.parse_args(argv)
    try:
        if sys.version_info < (3, 10):
            raise LaunchError("python_3_10_or_newer_required")
        if args.version:
            if args.command:
                options.error("--version cannot be combined with a command")
            print(version())
            return 0
        if not args.command:
            options.print_help()
            return 0


        if sys.platform == "win32":
            default_directory()
        directory = str(data_directory(args.directory))
        if args.command == "start":
            script = HERE / "panel.py"
            forwarded = ["--directory", directory]
            for flag in ("endpoint", "chrome"):
                value = getattr(args, flag)
                if value is not None:
                    forwarded.extend(["--" + flag, value])
            for flag in ("no_open", "headless"):
                if getattr(args, flag):
                    forwarded.append("--" + flag.replace("_", "-"))
        else:
            script = HERE / "client.py"
            forwarded = ["agent-connect", "--console-directory", directory, "--host", args.host]
            if args.json_only:
                forwarded.append("--json-only")
        if not script.is_file() or script.is_symlink():
            raise LaunchError("client_source_incomplete")
        command = [sys.executable, "-I", "-S", "-B", str(script), *forwarded]
        if sys.platform == "win32":


            with subprocess.Popen(command) as child:
                while True:
                    try:
                        return child.wait()
                    except KeyboardInterrupt:
                        continue
        os.execv(sys.executable, command)
        return 0
    except LaunchError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    except (OSError, RuntimeError, ValueError):
        print(json.dumps({"error": "client_launch_failed"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
