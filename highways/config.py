"""The deliberately outside-the-repository sending switch."""
from __future__ import annotations

import json
import os
import tempfile


def path() -> str:
    return os.environ.get("HIGHWAYS_CONFIG", os.path.expanduser("~/.config/highways/config.json"))


def read() -> dict:
    try:
        with open(path(), encoding="utf-8") as f:
            value = json.load(f)
        if not isinstance(value, dict):
            raise ValueError
        default = value.get("default", "off")
        repos = value.get("repos", {})
        if not isinstance(default, str) or default not in {"on", "off"}:
            raise ValueError
        if not isinstance(repos, dict):
            raise ValueError
        if any(not isinstance(key, str) or not isinstance(setting, str) or setting not in {"on", "off"}
               for key, setting in repos.items()):
            raise ValueError
        return {"default": default, "repos": repos}
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {"default": "off", "repos": {}}


def write(value: dict) -> None:
    target = path()
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".config.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, sort_keys=True)
            f.write("\n")
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def enabled(repo: str) -> bool:
    value = read()
    return value["repos"].get(os.path.realpath(repo), value["default"]) == "on"


def set_repo(repo: str, value: str) -> None:
    current = read()
    current["repos"][os.path.realpath(repo)] = value
    write(current)


def set_default(value: str) -> None:
    current = read()
    current["default"] = value
    write(current)
