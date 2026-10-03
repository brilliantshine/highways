"""Find routers that may need upkeep after a change."""
from __future__ import annotations

import argparse
import json
import os
import subprocess

from .routers import Router, discover
from .snapshot import SESSION, repo_root, state_dir, status_paths


def git(repo: str, *args: str) -> bytes:
    return subprocess.check_output(["git", "--no-optional-locks", "-C", repo, *args], stderr=subprocess.DEVNULL)


def _names(raw: bytes, *, name_status: bool = False) -> set[str]:
    fields = raw.split(b"\0")
    result: set[str] = set()
    if name_status:
        index = 0
        while index < len(fields):
            status = fields[index]
            index += 1
            if not status or index >= len(fields):
                continue
            result.add(fields[index].decode("utf-8", "surrogateescape"))
            index += 1
            if status[:1] in b"RC" and index < len(fields):
                result.add(fields[index].decode("utf-8", "surrogateescape"))
                index += 1
    else:
        result.update(item.decode("utf-8", "surrogateescape") for item in fields if item)
    return result


def _read_snapshot(session: str | None, repo: str) -> dict | None:
    if not session or not SESSION.fullmatch(session):
        return None
    try:
        with open(os.path.join(state_dir(), "sessions", session + ".json"), encoding="utf-8") as handle:
            value = json.load(handle)
        if (not isinstance(value, dict) or value.get("repo") != os.path.realpath(repo) or
                not isinstance(value.get("paths"), dict) or
                (value.get("head") is not None and not isinstance(value.get("head"), str))):
            return None
        return value
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _changed_from_snapshot(repo: str, snapshot: dict) -> set[str]:
    changed: set[str] = set()
    try:
        revision = "HEAD" if snapshot["head"] is None else "%s..HEAD" % snapshot["head"]
        raw = git(repo, "log", "--no-renames", "--diff-merges=first-parent", "--name-only", "-z", "--format=", revision)
        changed.update(_names(raw))
    except subprocess.CalledProcessError:
        pass  # An unborn repository with no subsequent commit still has dirty checks.
    now = status_paths(repo)
    before = snapshot["paths"]
    for path, value in now.items():
        if before.get(path) != value:
            changed.add(path)
    changed.update(path for path in before if path not in now)
    return changed


def changed_paths(repo: str, base: str | None, session: str | None) -> set[str]:
    snapshot = _read_snapshot(session, repo)
    if snapshot is not None:
        return _changed_from_snapshot(repo, snapshot)
    if base is not None:
        changed = _names(git(repo, "diff", "--no-renames", "--name-status", "-z", base), name_status=True)
        for field in git(repo, "status", "--porcelain=v1", "-z", "-uall").split(b"\0"):
            if field.startswith(b"?? "):
                changed.add(field[3:].decode("utf-8", "surrogateescape"))
        return changed
    return set(status_paths(repo))


def _ancestor(directory: str, parent: str) -> bool:
    return parent == "." or directory == parent or directory.startswith(parent + "/")


def _router_name(router: Router) -> str:
    return router.paths[0]


def map_paths(repo: str, paths: set[str]) -> list[dict]:
    routers = discover(repo)
    router_files = {path for router in routers for path in router.paths}
    selected: dict[str, set[str]] = {}
    by_dir = {router.dir: router for router in routers}
    for path in sorted(paths):
        if path in router_files:
            continue
        directory = os.path.dirname(path).replace(os.sep, "/") or "."
        ancestors = [router for router in routers if _ancestor(directory, router.dir)]
        if not ancestors:
            continue
        nearest = max(ancestors, key=lambda item: 0 if item.dir == "." else item.dir.count("/") + 1)
        selected.setdefault(nearest.dir, set()).add(path)
        for router in ancestors:
            relative = path if router.dir == "." else os.path.relpath(path, router.dir).replace(os.sep, "/")
            if relative in router.text or ("`%s`" % os.path.basename(path)) in router.text:
                selected.setdefault(router.dir, set()).add(path)
    return [{"router": _router_name(by_dir[directory]), "dir": directory, "paths": sorted(selected[directory])}
            for directory in sorted(selected, key=lambda item: _router_name(by_dir[item]))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="highways sweep")
    parser.add_argument("--base")
    parser.add_argument("--session")
    parser.add_argument("--repo")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    repo = repo_root(args.repo or os.getcwd())
    if not repo:
        return 1
    try:
        rows = map_paths(repo, changed_paths(repo, args.base, args.session))
    except (OSError, subprocess.CalledProcessError):
        return 1
    if args.json:
        print(json.dumps({"routers": rows}, ensure_ascii=False, separators=(",", ":")))
    else:
        for row in rows:
            print(row["router"])
            for path in row["paths"]:
                print("  " + path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
