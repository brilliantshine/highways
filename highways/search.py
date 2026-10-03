"""Router-only search and its deterministic walk."""
from __future__ import annotations

import json
import os
import re

from . import config, decisions
from .routers import Router, discover


class Unavailable(Exception):
    pass


REACH = "Is what the question asks about anywhere in this directory, its subdirectories included?"
OWN = "Is it in this directory's own files, or in a subdirectory this router names as having no router of its own? A subdirectory with its own router does not count."
FILE = "Is what the question asks about in this file?"


def _question(instructions: str) -> dict:
    criteria = {
        REACH: {"true": "What the question asks about is anywhere in this directory, its subdirectories included.",
                "false": "What the question asks about is not anywhere in this directory or its subdirectories."},
        OWN: {"true": "It is in this directory's own files, or a subdirectory this router names as having no router of its own.",
              "false": "It is not in this directory's own files or a subdirectory this router names as having no router of its own."},
        FILE: {"true": "What the question asks about is in this file.",
               "false": "What the question asks about is not in this file."},
    }[instructions]
    return {"type": "noul", "instructions": instructions,
            "criteria": criteria}


def _router_body(router: Router, question: str) -> dict:
    return {"state": {"directory": router.dir, "router": router.text, "question": question},
            "questions": {"reach": _question(REACH), "own": _question(OWN)}}


def score_routers(repo: str, routers: list[Router], question: str, *, budget: float | None,
                  timeout: float | None, resend_after: float | None = None) -> dict[str, dict[str, float]]:
    results = decisions.batch([(_router_body(router, question), {"reach", "own"}) for router in routers],
                              budget=budget, timeout=timeout, resend_after=resend_after)
    if any(isinstance(item, decisions.Failure) for item in results):
        raise Unavailable("router request failed")
    return {router.dir: result for router, result in zip(routers, results)}  # type: ignore[dict-item]


def walk(routers: list[Router], scores: dict[str, dict[str, float]], bars: dict) -> list[str]:
    """Return eligible router directories, ranked and capped."""
    if bars["mode"] == "flat":
        reached = [router.dir for router in routers if scores[router.dir]["own"] >= bars["answer"]]
    else:
        by_parent: dict[str | None, list[Router]] = {}
        by_dir = {router.dir: router for router in routers}
        for router in routers:
            by_parent.setdefault(router.parent, []).append(router)
        entered: set[str] = set()

        def enter(router: Router, root: bool = False) -> None:
            if not root and scores[router.dir]["reach"] < bars["walk"]:
                return
            entered.add(router.dir)
            for child in by_parent.get(router.dir, []):
                enter(child)

        root = by_dir.get(".")
        if root:
            enter(root, True)
        else:
            for router in by_parent.get(None, []):
                enter(router)
        reached = [directory for directory in entered if scores[directory]["own"] >= bars["answer"]]
    reached.sort(key=lambda directory: (-scores[directory]["own"], directory))
    return reached[:bars["cap"]]


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(root)]) == os.path.realpath(root)
    except ValueError:
        return False


def named_files(repo: str, router: Router) -> list[str]:
    """Extract existing regular files named by a router, preserving first mention."""
    tokens = re.findall(r"`([^`]+)`|\[[^\]]*\]\(([^)]+)\)", router.text)
    result: list[str] = []
    root = os.path.realpath(repo)
    router_dir = os.path.join(root, *([] if router.dir == "." else router.dir.split("/")))
    for tick, link in tokens:
        if tick:
            token = tick.strip()
        else:
            # Markdown targets may include a trailing title and anchor; preserve all
            # other target text, including spaces and literal # characters in ticks.
            token = re.sub(r'\s+"[^"]*"\s*$', "", link.strip())
            token = token.split("#", 1)[0]
        if not token or "://" in token:
            continue
        candidates = [os.path.join(router_dir, token), os.path.join(root, token)]
        for candidate in candidates:
            if os.path.isfile(candidate) and _inside(candidate, root):
                relative = os.path.relpath(os.path.realpath(candidate), root).replace(os.sep, "/")
                if relative not in result:
                    result.append(relative)
                break
    return result


def _file_question(path: str) -> dict:
    return {"type": "noul", "instructions": "%s The file is `%s`." % (FILE, path),
            "criteria": {"true": "What the question asks about is in `%s`." % path,
                         "false": "What the question asks about is not in `%s`." % path}}


def _file_body(router: Router, question: str, files: list[str]) -> dict:
    # Each question names its own file, so the answers can't be confused with one another.
    questions = {"f%d" % index: _file_question(path) for index, path in enumerate(files)}
    return {"state": {"directory": router.dir, "router": router.text, "question": question}, "questions": questions}


def _file_result(router: Router, question: str, files: list[str], result: dict | decisions.Failure) -> list[dict] | None:
    if isinstance(result, decisions.Failure):
        return None
    kept = [{"path": path, "p": result["f%d" % index]} for index, path in enumerate(files) if result["f%d" % index] >= 0.0]
    # Filtering is done by caller's answer bar; this helper only ranks a valid result.
    return kept


def file_step(repo: str, router: Router, question: str, files: list[str], *, budget: float | None, timeout: float | None) -> list[dict] | None:
    if not files:
        return []
    response = decisions.batch([(_file_body(router, question, files), {"f%d" % i for i in range(len(files))})], budget=budget, timeout=timeout)[0]
    values = _file_result(router, question, files, response)
    if values is None:
        return None
    values = [value for value in values if value["p"] >= _bars(repo)["answer"]]
    values.sort(key=lambda item: (-item["p"], item["path"]))
    return values[:5]


def _validate_bars(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"walk", "answer", "file", "cap", "mode"}:
        raise ValueError
    if (not isinstance(value["walk"], (int, float)) or not isinstance(value["answer"], (int, float)) or
            value["file"] is not None and not isinstance(value["file"], (int, float)) or
            not isinstance(value["cap"], int) or value["cap"] < 1 or value["mode"] not in {"walk", "flat"} or
            value["answer"] < .5 or (value["file"] is not None and value["answer"] > value["file"])):
        raise ValueError
    return value


def _bars(repo: str) -> dict:
    filename = os.environ.get("HIGHWAYS_BARS") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "search", "bars.json")
    try:
        with open(filename, encoding="utf-8") as f:
            value = json.load(f)
        # Candidate files carry evaluation metadata.  The production reader owns
        # only the five settings it needs, and deliberately ignores the rest.
        if not isinstance(value, dict):
            raise ValueError
        return _validate_bars({key: value[key] for key in ("walk", "answer", "file", "cap", "mode")})
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise Unavailable("bars file %s is invalid" % filename) from exc


def search(repo: str, question: str, *, bars: dict | None = None, budgets: tuple[float | None, float | None] = (.7, .3), timeout: float | None = None) -> dict:
    routers = discover(repo)
    if not routers:
        return {"status": "no-routers", "answers": [], "note": "no routers found; run /highways create"}
    if not config.enabled(repo):
        return {"status": "not-enabled", "answers": [], "note": "sending is off for this repo; only the person can turn it on, from their own terminal"}
    if not os.environ.get("OPENROUTER_API_KEY"):
        return {"status": "unavailable", "answers": [], "note": "OPENROUTER_API_KEY is not set"}
    try:
        bars = _validate_bars(bars) if bars is not None else _bars(repo)
        scores = score_routers(repo, routers, question, budget=budgets[0],
                               timeout=timeout if timeout is not None else budgets[0],
                               resend_after=.35)
    except Unavailable as exc:
        return {"status": "unavailable", "answers": [], "note": str(exc)}
    dirs = walk(routers, scores, bars)
    if not dirs:
        return {"status": "not-confident", "answers": [], "note": "not confident; grep instead"}
    by_dir = {router.dir: router for router in routers}
    answers = [{"dir": directory, "router": by_dir[directory].paths[0], "own": scores[directory]["own"], "reach": scores[directory]["reach"], "files": []} for directory in dirs]
    if bars["file"] is not None:
        candidates: list[tuple[int, list[str]]] = []
        for index, answer in enumerate(answers):
            if answer["own"] >= bars["file"]:
                files = named_files(repo, by_dir[answer["dir"]])
                if files:
                    candidates.append((index, files))
        batch = decisions.batch([(_file_body(by_dir[answers[index]["dir"]], question, files), {"f%d" % i for i in range(len(files))}) for index, files in candidates], budget=budgets[1], timeout=timeout if timeout is not None else budgets[1])
        for (index, files), response in zip(candidates, batch):
            values = _file_result(by_dir[answers[index]["dir"]], question, files, response)
            if values is not None:
                values = [value for value in values if value["p"] >= bars["answer"]]
                values.sort(key=lambda item: (-item["p"], item["path"]))
                answers[index]["files"] = values[:5]
    return {"status": "answers", "answers": answers, "note": "these are where to start reading, not a guarantee"}
