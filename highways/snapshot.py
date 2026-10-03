"""Store an outside-the-repository baseline for one hook session."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile


SESSION = re.compile(r"^[A-Za-z0-9._-]+$")


def state_dir() -> str:
    return os.environ.get("HIGHWAYS_STATE", os.path.expanduser("~/.cache/highways"))


def git(repo: str, *args: str) -> bytes:
    return subprocess.check_output(["git", "--no-optional-locks", "-C", repo, *args], stderr=subprocess.DEVNULL)


def repo_root(path: str) -> str | None:
    try:
        return git(path, "rev-parse", "--show-toplevel").decode("utf-8", "surrogateescape").strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def status_paths(repo: str) -> dict[str, str]:
    """Return porcelain paths and their current content state."""
    raw = git(repo, "status", "--porcelain=v1", "-z", "-uall")
    fields = raw.split(b"\0")
    result: dict[str, str] = {}
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if not field or len(field) < 4:
            continue
        code, name = field[:2], field[3:]
        names = [name]
        # In -z porcelain v1, a rename/copy's old name follows its new name.
        if (code[:1] in b"RC" or code[1:2] in b"RC") and index < len(fields):
            names.append(fields[index])
            index += 1
        for raw_name in names:
            path = raw_name.decode("utf-8", "surrogateescape")
            full = os.path.join(repo, *path.split("/"))
            if code[:1] == b"D" or code[1:2] == b"D" or not os.path.lexists(full):
                result[path] = "deleted"
            elif os.path.islink(full):
                try:
                    result[path] = "link:" + os.readlink(full)
                except OSError:
                    result[path] = "unreadable"
            else:
                try:
                    digest = hashlib.sha256()
                    with open(full, "rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                    result[path] = digest.hexdigest()
                except OSError:
                    result[path] = "unreadable"
    return result


def take(session: str, cwd: str) -> bool:
    if not SESSION.fullmatch(session):
        return False
    repo = repo_root(cwd)
    if not repo:
        return False
    try:
        head = git(repo, "rev-parse", "HEAD").decode().strip()
    except subprocess.CalledProcessError:
        head = None
    payload = {"repo": os.path.realpath(repo), "head": head, "paths": status_paths(repo)}
    directory = os.path.join(state_dir(), "sessions")
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".%s." % session, suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, ensure_ascii=True)
            handle.write("\n")
        os.replace(temporary, os.path.join(directory, session + ".json"))
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="highways snapshot")
    parser.add_argument("--session", required=True)
    parser.add_argument("--cwd", required=True)
    args = parser.parse_args(argv)
    return 0 if take(args.session, args.cwd) else 1


if __name__ == "__main__":
    raise SystemExit(main())
