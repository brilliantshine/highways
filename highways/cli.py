"""Command-line interface for highways."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from . import config
from .search import search


def repo_root(path: str | None = None) -> str | None:
    try:
        return subprocess.check_output(["git", "--no-optional-locks", "-C", path or os.getcwd(), "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def scan_argv(root: str, path: str) -> list[str]:
    return [os.path.join(root, "create", "scan.sh"), path]


def _confirm(word: str) -> bool:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("highways: refusing to turn sending on without a terminal", file=sys.stderr)
        return False
    try:
        return input("Type %s to confirm: " % word) == word
    except EOFError:
        return False


def _repo_action(value: str, path: str | None) -> int:
    repo = repo_root(path)
    if not repo:
        print("highways: not inside a git repo", file=sys.stderr)
        return 1
    if value == "on" and not _confirm(os.path.basename(os.path.realpath(repo))):
        return 1
    config.set_repo(repo, value)
    return 0


def _text(value: dict) -> None:
    if value["status"] == "answers":
        for answer in value["answers"]:
            print("%s — %s — %.2f" % (answer["dir"], answer["router"], answer["own"]))
            for item in answer["files"]:
                print("  %s — %.2f" % (item["path"], item["p"]))
    print(value["note"])


def _delegate(name: str, argv: list[str]) -> int:
    if name == "sweep":
        from . import sweep as module
    elif name == "snapshot":
        from . import snapshot as module
    else:
        from . import evalset as module
    return module.main(argv)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # These own their option parsing; argparse's REMAINDER would reject a leading --option.
    if argv and argv[0] in {"sweep", "snapshot", "eval"}:
        return _delegate(argv[0], argv[1:])
    parser = argparse.ArgumentParser(prog="highways")
    commands = parser.add_subparsers(dest="command", required=True)
    p_search = commands.add_parser("search")
    p_search.add_argument("question")
    p_search.add_argument("--repo")
    p_search.add_argument("--json", action="store_true")
    p_scan = commands.add_parser("scan")
    p_scan.add_argument("path")
    for name in ("enable", "disable"):
        p = commands.add_parser(name)
        p.add_argument("path", nargs="?")
    p_default = commands.add_parser("default")
    p_default.add_argument("value", choices=("on", "off"))
    for name in ("sweep", "snapshot", "eval"):
        p = commands.add_parser(name)
        p.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == "search":
        repo = repo_root(args.repo)
        if not repo:
            print("highways: not inside a git repo", file=sys.stderr)
            return 1
        value = search(repo, args.question)
        if args.json:
            print(json.dumps(value))
        else:
            _text(value)
        return 0
    if args.command == "scan":
        root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        command = scan_argv(root, args.path)
        os.execv(command[0], command)
    if args.command in {"enable", "disable"}:
        return _repo_action("on" if args.command == "enable" else "off", args.path)
    if args.command == "default":
        if args.value == "on" and not _confirm("on"):
            return 1
        config.set_default(args.value)
        return 0
    if args.command == "snapshot":
        # Kept as an internal forwarding name for the eventual snapshot implementation.
        return _delegate("snapshot", args.argv)
    return _delegate(args.command, args.argv)
