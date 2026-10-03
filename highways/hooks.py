"""Small, fail-silent implementations behind the two shell hook entrypoints."""
from __future__ import annotations

import json
import os
import subprocess
import sys

if __package__ in {None, ""}:  # invoked by hooks/*.sh as a file
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    from highways.snapshot import SESSION, repo_root
else:
    from .snapshot import SESSION, repo_root

HEADER = "highways: likely places for this request (start here, confirm by reading)"


def _run(root: str, args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([sys.executable, os.path.join(root, "bin", "highways"), *args], stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False)


def _payload() -> dict | None:
    try:
        value = json.loads(sys.stdin.buffer.read())
    except (ValueError, UnicodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _skip(value: dict) -> bool:
    return bool(os.environ.get("WHEELCHAIR_LANE") or os.environ.get("HIGHWAYS_LANE") or "agent_id" in value)


def _answer_text(value: dict) -> str:
    lines: list[str] = []
    for answer in value["answers"]:
        lines.append("%s — %s — %.2f" % (answer["dir"], answer["router"], answer["own"]))
        for item in answer["files"]:
            lines.append("  %s — %.2f" % (item["path"], item["p"]))
    lines.append(value["note"])
    return "\n".join(lines)


def prompt(root: str, value: dict) -> None:
    if _skip(value):
        return
    session, cwd, question = value.get("session_id"), value.get("cwd"), value.get("prompt")
    if not all(isinstance(item, str) for item in (session, cwd, question)) or not SESSION.fullmatch(session):
        return
    repo = repo_root(cwd)
    if not repo:
        return
    snapshot = _run(root, ["snapshot", "--session", session, "--cwd", repo], 1.0)
    if snapshot.returncode != 0 or len(question.split()) < 4:
        return
    result = _run(root, ["search", "--repo", repo, "--json", question], 1.5)
    if result.returncode != 0:
        return
    try:
        search = json.loads(result.stdout)
        if search.get("status") != "answers":
            return
        text = HEADER + "\n" + _answer_text(search)
    except (ValueError, TypeError, KeyError):
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}, ensure_ascii=False, separators=(",", ":")))


def stop(root: str, value: dict) -> None:
    if _skip(value) or value.get("stop_hook_active") is True:
        return
    session, cwd = value.get("session_id"), value.get("cwd")
    if not isinstance(session, str) or not isinstance(cwd, str) or not SESSION.fullmatch(session):
        return
    repo = repo_root(cwd)
    if not repo:
        return
    result = _run(root, ["sweep", "--session", session, "--repo", repo, "--json"], 1.5)
    if result.returncode != 0:
        return
    try:
        rows = json.loads(result.stdout)["routers"]
        if not rows:
            return
        lines = ["highways found routers to check:"]
        for row in rows:
            lines.append(row["router"] + ": " + ", ".join(row["paths"]))
        lines.append("Read each router against your change; fix anything it now says that is false; additions and factual corrections only, never reformat (%s); then finish." % os.path.join(root, "protocol", "sweep.md"))
    except (ValueError, TypeError, KeyError):
        return
    print(json.dumps({"decision": "block", "reason": "\n".join(lines)}, ensure_ascii=False, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 3 or argv[0] not in {"prompt", "stop"} or argv[2] not in {"claude", "codex"}:
        return 0
    value = _payload()
    if value is None:
        return 0
    try:
        (prompt if argv[0] == "prompt" else stop)(argv[1], value)
    except BaseException:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
