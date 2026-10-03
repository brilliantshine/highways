"""Discover the tracked, unignored router files in a repository."""
from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess


@dataclass(frozen=True)
class Router:
    dir: str
    paths: tuple[str, ...]
    text: str
    parent: str | None


def _git(repo: str, *args: str) -> bytes:
    return subprocess.check_output(["git", "--no-optional-locks", "-C", repo, *args])


def _inside(path: str, repo: str) -> bool:
    root = os.path.realpath(repo)
    return os.path.commonpath([os.path.realpath(path), root]) == root


def _in_nested_repo(repo: str, bits: list[str]) -> bool:
    """Whether a router path descends through another repository's metadata."""
    directory = repo
    for bit in bits[:-1]:
        directory = os.path.join(directory, bit)
        if os.path.lexists(os.path.join(directory, ".git")):
            return True
    return False


def discover(repo: str) -> list[Router]:
    """Return routers ordered by their repository-relative directory."""
    raw = _git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    grouped: dict[str, list[str]] = {}
    for item in raw.decode("utf-8", "surrogateescape").split("\0"):
        if not item:
            continue
        bits = item.split("/")
        if any(bit.startswith(".") for bit in bits):
            continue
        if bits[-1] not in {"AGENTS.md", "CLAUDE.md"}:
            continue
        if _in_nested_repo(repo, bits):
            continue
        full = os.path.join(repo, *bits)
        # A broken link or one resolving outside the repo is skipped, as create/scan.sh does:
        # its text is never read, so it can never be sent.
        if os.path.isfile(full) and _inside(full, repo):
            directory = "/".join(bits[:-1]) or "."
            grouped.setdefault(directory, []).append(item)

    result: list[Router] = []
    dirs = sorted(grouped, key=lambda d: (d.count("/"), d))
    for directory in dirs:
        paths = sorted(grouped[directory], key=lambda p: (os.path.basename(p) != "AGENTS.md", p))
        # A symlink pair (and hard links) is one router document.
        unique: list[str] = []
        seen: set[str] = set()
        for path in paths:
            real = os.path.realpath(os.path.join(repo, path))
            if real not in seen:
                unique.append(path)
                seen.add(real)
        if len(unique) == 1:
            with open(os.path.join(repo, unique[0]), encoding="utf-8", errors="surrogateescape") as f:
                text = f.read()
        else:
            sections = []
            for path in unique:
                with open(os.path.join(repo, path), encoding="utf-8", errors="surrogateescape") as f:
                    sections.append("== %s ==\n%s" % (os.path.basename(path), f.read()))
            text = "\n".join(sections)
        parent = None
        if directory != ".":
            parts = directory.split("/")
            for end in range(len(parts) - 1, -1, -1):
                candidate = "/".join(parts[:end]) or "."
                if candidate in grouped:
                    parent = candidate
                    break
        # Keep every source name for callers reporting the router, even when the text
        # was deduplicated through a symlink.
        result.append(Router(directory, tuple(paths), text, parent))
    return result
