"""Build and evaluate the hand-reviewed router-search test set."""
from __future__ import annotations

import argparse
import datetime as _datetime
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import random
import re
import statistics
import subprocess
import sys
import tempfile
import time

from . import decisions, search
from .routers import Router, discover


ROUTER_NAMES = {"AGENTS.md", "CLAUDE.md"}
BAR_KEYS = ("walk", "answer", "file", "cap", "mode")
ANSWERABLE_FLOOR = 40
UNANSWERABLE_FLOOR = 5


def _state() -> Path:
    return Path(os.environ.get("HIGHWAYS_STATE", os.path.expanduser("~/.cache/highways"))).expanduser() / "eval"


def _git(repo: str | Path, *args: str, text: bool = True) -> str:
    return subprocess.check_output(["git", "--no-optional-locks", "-C", os.fspath(repo), *args], text=text, stderr=subprocess.DEVNULL).strip()  # type: ignore[return-value]


def _clone(source: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory(prefix="highways-eval-")
    repo = Path(temporary.name) / "repo"
    subprocess.run(["git", "--no-optional-locks", "clone", "--quiet", "--no-hardlinks", source, str(repo)], check=True)
    _inherit_promisor(source, repo)
    return temporary, repo


def _inherit_promisor(source: str, repo: Path) -> None:
    """A clone of a partial clone lacks the blobs the source never fetched; let it fetch them
    from the source's own remote, as the source would. Only the temp clone's config changes."""
    try:
        if _git(source, "config", "--get", "remote.origin.promisor") != "true":
            return
        url = _git(source, "config", "--get", "remote.origin.url")
        fltr = _git(source, "config", "--get", "remote.origin.partialclonefilter")
    except subprocess.CalledProcessError:
        return
    for key, value in (("remote.origin.url", url), ("remote.origin.promisor", "true"), ("remote.origin.partialclonefilter", fltr)):
        _git(repo, "config", key, value)


def _router_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return bool(parts) and parts[-1] in ROUTER_NAMES and not any(part.startswith(".") for part in parts)


def _tree_paths(repo: str | Path, rev: str) -> dict[str, tuple[str, str]]:
    raw = _git(repo, "ls-tree", "-r", "--full-tree", "-z", rev, text=False)
    result: dict[str, tuple[str, str]] = {}
    for item in raw.split(b"\0"):
        if not item:
            continue
        meta, path = item.split(b"\t", 1)
        mode, _kind, obj = meta.decode("ascii").split()
        result[path.decode("utf-8", "surrogateescape")] = (mode, obj)
    return result


def _blob(repo: str | Path, rev: str, path: str) -> str:
    return subprocess.check_output(["git", "--no-optional-locks", "-C", os.fspath(repo), "show", "%s:%s" % (rev, path)]).decode("utf-8", "surrogateescape")


def _normal_relative(base: str, token: str) -> str | None:
    if not token or token.startswith("/"):
        return None
    candidate = PurePosixPath(base) / token if base != "." else PurePosixPath(token)
    normal = os.path.normpath(str(candidate)).replace(os.sep, "/")
    if normal == ".." or normal.startswith("../"):
        return None
    return normal


def _historic_routers(repo: str | Path, rev: str) -> tuple[list[Router], set[str]]:
    """Discover router documents in a tree, including a sibling symlink pair."""
    tree = _tree_paths(repo, rev)
    grouped: dict[str, list[tuple[str, str, str]]] = {}
    for path, (mode, obj) in tree.items():
        if not _router_path(path):
            continue
        directory = str(PurePosixPath(path).parent) or "."
        target = path
        if mode == "120000":
            link = _blob(repo, rev, path)
            candidate = _normal_relative(directory, link)
            if candidate not in tree or PurePosixPath(candidate).parent.as_posix() != ("." if directory == "." else directory):
                continue
            target = candidate
            target_mode, target_obj = tree[target]
            if target_mode == "120000" or PurePosixPath(target).name not in ROUTER_NAMES:
                continue
            obj = target_obj
        grouped.setdefault(directory, []).append((path, target, obj))
    directories = sorted(grouped, key=lambda item: (item.count("/"), item))
    routers: list[Router] = []
    for directory in directories:
        entries = sorted(grouped[directory], key=lambda item: (PurePosixPath(item[0]).name != "AGENTS.md", item[0]))
        paths = tuple(item[0] for item in entries)
        unique: list[str] = []
        seen: set[str] = set()
        for _path, target, obj in entries:
            # Git trees do not preserve hard-link identity.  Only a symlink's
            # target is an alias here; two real files with equal text remain
            # two labelled router documents.
            if target not in seen:
                unique.append(target)
                seen.add(target)
        text = _blob(repo, rev, unique[0]) if len(unique) == 1 else "\n".join("== %s ==\n%s" % (PurePosixPath(path).name, _blob(repo, rev, path)) for path in unique)
        parent = None
        if directory != ".":
            bits = directory.split("/")
            for end in range(len(bits) - 1, -1, -1):
                candidate = "/".join(bits[:end]) or "."
                if candidate in grouped:
                    parent = candidate
                    break
        routers.append(Router(directory, paths, text, parent))
    return routers, set(tree)


def _covering(routers: list[Router], path: str) -> Router | None:
    directory = str(PurePosixPath(path).parent) or "."
    by_dir = {router.dir: router for router in routers}
    while True:
        if directory in by_dir:
            return by_dir[directory]
        if directory == ".":
            return None
        directory = str(PurePosixPath(directory).parent) or "."


def _named_at_tree(router: Router, paths: set[str]) -> list[str]:
    result: list[str] = []
    tokens = re.findall(r"`([^`]+)`|\[[^\]]*\]\(([^)]+)\)", router.text)
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
        for base in (router.dir, "."):
            candidate = _normal_relative(base, token)
            if candidate in paths and candidate not in result:
                result.append(candidate)
                break
    return result


def _question(subject: str) -> str:
    import re
    value = subject.strip()
    while True:
        stripped = re.sub(r"^(?:[A-Za-z][A-Za-z0-9_-]*)(?:\([^)]*\))?:\s*", "", value)
        stripped = re.sub(r"^[A-Z][A-Z0-9]+-\d+:\s*", "", stripped)
        if stripped == value:
            return value.strip()
        value = stripped.strip()


def _read_questions(filename: str) -> tuple[dict, list[dict]]:
    try:
        with open(filename, encoding="utf-8") as handle:
            lines = [line for line in handle if line.strip()]
        header = json.loads(lines[0])
        questions = [json.loads(line) for line in lines[1:]]
    except (OSError, IndexError, json.JSONDecodeError) as exc:
        raise ValueError("invalid questions file %s" % filename) from exc
    if not isinstance(header, dict):
        raise ValueError("invalid questions file %s" % filename)
    return header, questions


def _leaks(repo: str | Path, parent: str, question: str, answers: list[str]) -> bool:
    """Whether a question exposes a location the evaluator is meant to test."""
    if "/" in question:
        return True
    tree = _tree_paths(repo, parent)
    for path in tree:
        name = PurePosixPath(path).name
        if re.search(r"(?<!\w)%s(?!\w)" % re.escape(name), question, re.IGNORECASE):
            return True
    for directory in answers:
        if directory == ".":
            continue
        if re.search(r"(?<![\w/])%s(?![\w/])" % re.escape(directory), question, re.IGNORECASE):
            return True
    return False


def written(source: str, rev: str, filename: str) -> int:
    """Map a router-free worker's file list into reviewable written questions."""
    source = os.path.realpath(source)
    try:
        resolved = _git(source, "rev-parse", "--verify", rev + "^{commit}")
        rows = []
        with open(filename, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if line.strip():
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError("line %d is not an object" % number)
                    rows.append(value)
    except (OSError, subprocess.CalledProcessError):
        print("highways: --source is not a git repository or --rev is invalid", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print("highways: invalid written questions file: %s" % exc, file=sys.stderr)
        return 1

    tree = _tree_paths(source, resolved)
    routers, paths = _historic_routers(source, resolved)
    mapped: list[dict] = []
    try:
        for number, value in enumerate(rows, 1):
            question, listed = value.get("question"), value.get("files")
            if not isinstance(question, str) or not isinstance(listed, list) or not all(isinstance(path, str) for path in listed):
                raise ValueError("line %d must contain a string question and a files list" % number)
            if len(listed) > 3:
                raise ValueError("line %d names more than 3 files" % number)
            answers: list[str] = []
            named: list[str] = []
            for path in listed:
                if path not in tree:
                    raise ValueError("line %d names untracked file %s" % (number, path))
                router = _covering(routers, path)
                if router is None:
                    raise ValueError("line %d has no covering router for %s" % (number, path))
                if router.dir not in answers:
                    answers.append(router.dir)
                if path in _named_at_tree(router, paths) and path not in named:
                    named.append(path)
            if _leaks(source, resolved, question, answers):
                raise ValueError("line %d question leaks a path, file name, or answer directory" % number)
            mapped.append({"question": question, "answers": answers, "files": named})
    except ValueError as exc:
        print("highways: %s" % exc, file=sys.stderr)
        return 1

    stem = os.path.basename(source.rstrip(os.sep))
    batch = 1
    while (_state() / ("%s-written-%d-questions.jsonl" % (stem, batch))).exists():
        batch += 1
    output = _state() / ("%s-written-%d-questions.jsonl" % (stem, batch))
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "x", encoding="utf-8") as handle:
        handle.write(json.dumps({"reviewed": False, "source": source, "head": resolved}) + "\n")
        for number, item in enumerate(mapped, 1):
            handle.write(json.dumps({"id": "w-%s-%d-%d" % (stem, batch, number), "commit": resolved,
                                     "parent": resolved, "subject": "written", **item}, sort_keys=True) + "\n")
    answerable = sum(bool(item["answers"]) for item in mapped)
    print("highways: written %d answerable, %d unanswerable (%s)" % (answerable, len(mapped) - answerable, output))
    return 0


def _reviewed(files: list[str]) -> list[tuple[str, dict, list[dict]]]:
    result = []
    for filename in files:
        header, questions = _read_questions(filename)
        if header.get("reviewed") is not True:
            raise ValueError("questions file %s has not been reviewed" % filename)
        if not isinstance(header.get("source"), str):
            raise ValueError("questions file %s has no source" % filename)
        result.append((filename, header, questions))
    return result


def draft(source: str) -> int:
    source = os.path.realpath(source)
    try:
        head = _git(source, "rev-parse", "HEAD")
    except (OSError, subprocess.CalledProcessError):
        print("highways: --source is not a git repository", file=sys.stderr)
        return 1
    output = _state() / (os.path.basename(source.rstrip(os.sep)) + "-questions.jsonl")
    if output.exists():
        try:
            header, _ = _read_questions(str(output))
        except ValueError:
            header = {}
        if header.get("reviewed") is True:
            print("highways: refusing to overwrite reviewed questions %s" % output, file=sys.stderr)
            return 1
    temporary, clone = _clone(source)
    try:
        commits = _git(clone, "log", "--no-merges", "--format=%H").splitlines()
        random.Random(0).shuffle(commits)
        kept: list[dict] = []
        skipped = 0
        for commit in commits:
            parents = _git(clone, "rev-list", "--parents", "-n", "1", commit).split()
            if len(parents) != 2:
                skipped += 1
                continue
            parent = parents[1]
            changed = _git(clone, "diff-tree", "--no-commit-id", "--no-renames", "-r", "--name-only", parent, commit).splitlines()
            if (not any(not name.endswith(".md") for name in changed) or all(name == "docs" or name.startswith("docs/") for name in changed) or any(_router_path(name) for name in changed)):
                skipped += 1
                continue
            routers, tree = _historic_routers(clone, parent)
            covering = [_covering(routers, name) for name in changed]
            if any(item is None for item in covering) or not 1 <= len({item.dir for item in covering if item}) <= 5:
                skipped += 1
                continue
            subject = _git(clone, "show", "-s", "--format=%s", commit)
            answers: list[str] = []
            files: list[str] = []
            for name, router in zip(changed, covering):
                assert router is not None
                if router.dir not in answers:
                    answers.append(router.dir)
                if name in _named_at_tree(router, tree) and name not in files:
                    files.append(name)
            kept.append({"id": commit, "commit": commit, "parent": parent, "subject": subject, "question": _question(subject), "answers": answers, "files": files})
            if len(kept) == 100:
                break
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"reviewed": False, "source": source, "head": head}) + "\n")
            for item in kept:
                handle.write(json.dumps(item, sort_keys=True) + "\n")
    finally:
        temporary.cleanup()
    print("highways: draft kept %d, skipped %d (%s)" % (len(kept), skipped, output))
    return 0


def _tracked(repo: Path) -> list[str]:
    return _git(repo, "ls-files").splitlines()


def _own_files(routers: list[Router], tracked: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for router in routers:
        prefix = "" if router.dir == "." else router.dir + "/"
        children = [other.dir + "/" for other in routers if other.dir != router.dir and other.dir.startswith(prefix)]
        result[router.dir] = [path for path in tracked if path.startswith(prefix) and not any(path.startswith(child) for child in children)]
    return result


def _score_question(repo: Path, item: dict) -> tuple[dict | None, int]:
    _git(repo, "checkout", "--quiet", "--detach", item["parent"])
    routers = discover(str(repo))
    try:
        scores = search.score_routers(str(repo), routers, item["question"], budget=None, timeout=10)
    except search.Unavailable:
        return None, 0
    named = {router.dir: search.named_files(str(repo), router) for router in routers}
    selected = [router for router in routers if scores[router.dir]["own"] >= .5 and named[router.dir]]
    responses = decisions.batch([(search._file_body(router, item["question"], named[router.dir]), {"f%d" % index for index in range(len(named[router.dir]))}) for router in selected], budget=None, timeout=10)
    file_scores: dict[str, list[dict]] = {}
    failures = 0
    for router, response in zip(selected, responses):
        values = search._file_result(router, item["question"], named[router.dir], response)
        if values is None:
            failures += 1
        else:
            file_scores[router.dir] = values
    tracked = _tracked(repo)
    own = _own_files(routers, tracked)
    return ({"parent": item["parent"], "question": item["question"], "answers": item.get("answers", []), "files": item.get("files", []), "tracked": tracked, "routers": [{"dir": router.dir, "parent": router.parent, "reach": scores[router.dir]["reach"], "own": scores[router.dir]["own"], "named": named[router.dir], "own_files": own[router.dir]} for router in routers], "file_scores": file_scores}, failures)


def _cache_path(parent: str, question: str, source: str) -> Path:
    key = hashlib.sha256((os.path.realpath(source) + "\n" + parent + "\n" + question).encode()).hexdigest()
    return _state() / "scores" / os.path.basename(source.rstrip(os.sep)) / (key + ".json")


def _with_question(record: dict, item: dict, source: str) -> dict:
    """Cache records deliberately omit review-file identity; restore it at use time."""
    result = dict(record)
    result.update(answers=item.get("answers", []), files=item.get("files", []),
                  repo=os.path.realpath(source),
                  origin="written" if str(item.get("id", "")).startswith("w-") else "drafted")
    return result


def _floor_and_leaks(groups: list[tuple[str, dict, list[dict]]]) -> list[str]:
    """All checks that must complete before score sends its first request."""
    errors: list[str] = []
    by_repo: dict[str, int] = {}
    unanswerable = 0
    for _filename, header, questions in groups:
        source = os.path.realpath(header["source"])
        answerable = sum(bool(item.get("answers", [])) for item in questions if isinstance(item, dict))
        by_repo[source] = by_repo.get(source, 0) + answerable
        unanswerable += sum(not item.get("answers", []) for item in questions if isinstance(item, dict))
        for item in questions:
            try:
                if (not isinstance(item, dict) or not isinstance(item.get("question"), str) or
                        not isinstance(item.get("parent"), str) or not isinstance(item.get("answers", []), list)):
                    raise ValueError
                leaked = _leaks(source, item["parent"], item["question"], item.get("answers", []))
            except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError):
                errors.append("cannot check question %s" % item.get("id", "<unknown>"))
                continue
            if leaked:
                errors.append("question %s leaks a path, file name, or answer directory" % item.get("id", "<unknown>"))
    for source, count in by_repo.items():
        if count < ANSWERABLE_FLOOR:
            errors.append("%s has %d reviewed answerable questions; need %d" % (source, count, ANSWERABLE_FLOOR))
    if unanswerable < UNANSWERABLE_FLOOR:
        errors.append("pool has %d reviewed unanswerable questions; need %d" % (unanswerable, UNANSWERABLE_FLOOR))
    return errors


def _router_objects(record: dict) -> tuple[list[Router], dict[str, dict[str, float]]]:
    routers = [Router(item["dir"], (), "", item.get("parent")) for item in record["routers"]]
    scores = {item["dir"]: {"reach": item["reach"], "own": item["own"]} for item in record["routers"]}
    return routers, scores


def _answer_rows(record: dict, bars: dict) -> list[dict]:
    if "live_answers" in record:
        return record["live_answers"]
    routers, scores = _router_objects(record)
    by_dir = {item["dir"]: item for item in record["routers"]}
    result = []
    for directory in search.walk(routers, scores, bars):
        item = by_dir[directory]
        files: list[dict] = []
        if bars["file"] is not None and item["own"] >= bars["file"]:
            files = [value for value in record.get("file_scores", {}).get(directory, []) if value["p"] >= bars["answer"]]
            files.sort(key=lambda value: (-value["p"], value["path"]))
            files = files[:5]
        result.append({"dir": directory, "own": item["own"], "files": files, "own_files": item["own_files"]})
    return result


def _median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _metrics(records: list[dict], bars: dict) -> dict:
    answered = right_questions = top_wrong = right_answers = total_answers = 0
    false_answers = unanswerable = 0
    narrowings: list[float] = []
    right_files = total_files = expected_files = 0
    for record in records:
        rows = _answer_rows(record, bars)
        expected_dirs = set(record.get("answers", []))
        if not expected_dirs:
            unanswerable += 1
            false_answers += bool(rows)
            continue
        expected = set(record.get("files", []))
        expected_files += len(expected)
        if rows:
            answered += 1
            if rows[0]["dir"] not in expected_dirs:
                top_wrong += 1
            if any(row["dir"] in expected_dirs for row in rows):
                right_questions += 1
            pointed: set[str] = set()
            for row in rows:
                returned = {value["path"] for value in row.get("files", [])}
                pointed.update(returned or set(row.get("own_files", [])))
                total_files += len(returned)
                right_files += len(returned & expected)
            tracked = len(record.get("tracked", []))
            narrowings.append(len(pointed) / tracked if tracked else 0.0)
        total_answers += len(rows)
        right_answers += sum(row["dir"] in expected_dirs for row in rows)
    count = len(records) - unanswerable
    return {"questions": len(records), "answerable_questions": count,
            "unanswerable_questions": unanswerable, "answered": answered,
            "answered_rate": answered / count if count else 0.0,
            "top_wrong_rate": top_wrong / answered if answered else 0.0,
            "answer_precision": right_answers / total_answers if total_answers else 0.0,
            "recall": right_questions / count if count else 0.0,
            "file_precision": right_files / total_files if total_files else 0.0,
            "file_recall": right_files / expected_files if expected_files else 0.0,
            "files_returned": total_files, "median_narrowing": _median(narrowings),
            "false_answers": false_answers,
            "false_answer_rate": false_answers / unanswerable if unanswerable else 0.0}


def _metric_groups(records: list[dict], bars: dict) -> dict:
    """The same measurements by pool, source repository, and question origin."""
    repos = sorted({record.get("repo", "") for record in records})
    return {"pool": _metrics(records, bars),
            "repos": {repo: _metrics([record for record in records if record.get("repo", "") == repo], bars) for repo in repos},
            "drafted": _metrics([record for record in records if record.get("origin") == "drafted"], bars),
            "written": _metrics([record for record in records if record.get("origin") == "written"], bars)}


def _passes_selection(metrics: dict) -> bool:
    pool = metrics["pool"] if "pool" in metrics else metrics
    drafted = metrics.get("drafted", {"top_wrong_rate": 0.0})
    return (pool["top_wrong_rate"] <= .05 and drafted["top_wrong_rate"] <= .05 and
            pool["answer_precision"] >= .80 and pool["median_narrowing"] is not None and
            pool["median_narrowing"] <= .10 and pool["false_answer_rate"] <= .05 and
            pool["answered_rate"] >= .45)


MARGIN = .02


def _shifted(records: list[dict], delta: float) -> list[dict]:
    """Copies of the cached records with every router score and file score moved by delta, clamped to [0, 1]."""
    def move(value: float) -> float:
        return min(1.0, max(0.0, value + delta))
    result = []
    for record in records:
        copy = dict(record)
        copy["routers"] = [dict(item, reach=move(item["reach"]), own=move(item["own"])) for item in record["routers"]]
        if "file_scores" in record:
            copy["file_scores"] = {directory: [dict(value, p=move(value["p"])) for value in values]
                                   for directory, values in record["file_scores"].items()}
        result.append(copy)
    return result


def _selection_key(rates: tuple[float, float, float], bars: dict) -> tuple:
    """Highest worst-case answered rate, then cached rate, then the higher answer bar, then walk bar."""
    return (min(rates), rates[1], bars["answer"], bars["walk"])


def _grid(start: float, end: float) -> list[float]:
    return [round(start + .05 * index, 2) for index in range(round((end - start) / .05) + 1)]


def _best_for_mode(records: list[dict], mode: str) -> tuple[dict, dict] | None:
    versions = [_shifted(records, -MARGIN), records, _shifted(records, MARGIN)]
    candidates: list[tuple[dict, dict]] = []
    walks = _grid(.10, .95) if mode == "walk" else [.5]
    for answer in _grid(.50, .95):
        for walk in walks:
            bars = {"walk": walk, "answer": answer, "file": None, "cap": 5, "mode": mode}
            grouped = [_metric_groups(version, bars) for version in versions]
            if all(_passes_selection(metrics) for metrics in grouped):
                rates = tuple(metrics["pool"]["answered_rate"] for metrics in grouped)
                candidates.append((bars, dict(grouped[1], margin={"low": rates[0], "cached": rates[1], "high": rates[2]})))
    return max(candidates, key=lambda value: _selection_key((value[1]["margin"]["low"], value[1]["margin"]["cached"], value[1]["margin"]["high"]), value[0])) if candidates else None


def _margin_rates(selected: dict) -> tuple[float, float, float]:
    margin = selected["margin"]
    return (margin["low"], margin["cached"], margin["high"])


def _choose_file(records: list[dict], bars: dict) -> float | None:
    for value in _grid(bars["answer"], .95):
        metrics = _metrics(records, dict(bars, file=value))
        if metrics["files_returned"] and metrics["file_precision"] >= .80:
            return value
    return None


def _gates(metrics: dict, bars: dict, *, latency: float | None = None, require_files: bool = False) -> dict[str, bool]:
    pool = metrics["pool"] if "pool" in metrics else metrics
    drafted = metrics.get("drafted", {"top_wrong_rate": 0.0})
    gates = {"answered_rate": pool["answered_rate"] >= .45,
             "top_wrong_rate": pool["top_wrong_rate"] <= .05,
             "drafted_top_wrong_rate": drafted["top_wrong_rate"] <= .05,
             "false_answer_rate": pool["false_answer_rate"] <= .05,
             "answer_precision": pool["answer_precision"] >= .80,
             "median_narrowing": pool["median_narrowing"] is not None and pool["median_narrowing"] <= .10}
    if bars["file"] is not None:
        gates["file_precision"] = pool["file_precision"] >= .80
        if require_files:
            gates["files_returned"] = bool(pool["files_returned"])
    if latency is not None:
        gates["latency_p95"] = latency <= 1.0
    return gates


def _report(prefix: str, metrics: dict, gates: dict, *, latency: dict | None = None) -> None:
    def line(name: str, value: dict, extra: str = "") -> None:
        fields = "answered %.1f%%, top-wrong %.1f%%, false-answer %.1f%%, precision %.1f%%, recall %.1f%%, file-precision %.1f%%, file-recall %.1f%%, narrowing %s" % (100 * value["answered_rate"], 100 * value["top_wrong_rate"], 100 * value["false_answer_rate"], 100 * value["answer_precision"], 100 * value["recall"], 100 * value["file_precision"], 100 * value["file_recall"], "n/a" if value["median_narrowing"] is None else "%.1f%%" % (100 * value["median_narrowing"]))
        print("highways: %s %s: %s%s" % (prefix, name, fields, extra))
    if "pool" not in metrics:
        metrics = {"pool": metrics, "repos": {}, "drafted": _metrics([], {}), "written": _metrics([], {})}
    extra = ", latency median %.3fs p95 %.3fs" % (latency["median"], latency["p95"]) if latency else ""
    line("pool", metrics["pool"], extra)
    for repo, value in metrics["repos"].items():
        line("repo %s" % repo, value)
    line("drafted", metrics["drafted"], "; no drafted question answered" if not metrics["drafted"]["answered"] else "")
    line("written", metrics["written"])
    print("highways: gates " + ", ".join("%s=%s" % (key, "pass" if value else "FAIL") for key, value in gates.items()))


def score(question_files: list[str]) -> int:
    try:
        groups = _reviewed(question_files)
    except ValueError as exc:
        print("highways: %s" % exc, file=sys.stderr)
        return 1
    errors = _floor_and_leaks(groups)
    if errors:
        for error in errors:
            print("highways: %s" % error, file=sys.stderr)
        return 1
    records: list[dict] = []
    sources: list[dict] = []
    failures = 0
    for _filename, header, questions in groups:
        temporary, clone = _clone(header["source"])
        dropped = 0
        try:
            for item in questions:
                cache = _cache_path(item["parent"], item["question"], header["source"])
                if cache.exists():
                    try:
                        record = json.loads(cache.read_text(encoding="utf-8"))
                        # The cache holds Jev's scores; the right answers always come from the reviewed file.
                        records.append(_with_question(record, item, header["source"]))
                        continue
                    except json.JSONDecodeError:
                        pass
                value, failed = _score_question(clone, item)
                failures += failed
                if value is None:
                    dropped += 1
                    continue
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
                records.append(_with_question(value, item, header["source"]))
        finally:
            temporary.cleanup()
        sources.append({"source": header["source"], "head": header.get("head"), "questions": len(questions), "dropped": dropped})
    walk = _best_for_mode(records, "walk")
    flat = _best_for_mode(records, "flat")
    if walk is not None and (flat is None or _selection_key(_margin_rates(walk[1]), walk[0])[:2] > _selection_key(_margin_rates(flat[1]), flat[0])[:2]):
        bars, selected = walk
    elif flat is not None:
        bars, selected = flat
    else:
        bars, selected = ({"walk": .5, "answer": .95, "file": None, "cap": 5, "mode": "flat"}, None)
    bars["file"] = _choose_file(records, bars) if selected is not None else None
    metrics = _metric_groups(records, bars)
    gates = _gates(metrics, bars)
    margin = selected["margin"] if selected is not None else None
    candidate = {**bars, "margin": margin, "date": _datetime.date.today().isoformat(), "sources": sources, "metrics": metrics, "gates": gates,
                 "passed": selected is not None and all(gates.values())}
    target = _state() / "bars.candidate.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(candidate, sort_keys=True) + "\n", encoding="utf-8")
    _report("score (%d file-request failures)" % failures, metrics, gates)
    return 0 if candidate["passed"] else 1


def _candidate() -> dict:
    filename = _state() / "bars.candidate.json"
    try:
        value = json.loads(filename.read_text(encoding="utf-8"))
        search._validate_bars({key: value[key] for key in BAR_KEYS})
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("missing or invalid bars candidate") from exc
    if value.get("passed") is not True:
        raise ValueError("bars candidate did not pass cached gates")
    return value


def _p95(values: list[float]) -> float:
    return sorted(values)[max(0, math.ceil(.95 * len(values)) - 1)]


def latency(question_files: list[str]) -> int:
    try:
        groups = _reviewed(question_files)
        candidate = _candidate()
    except ValueError as exc:
        print("highways: %s" % exc, file=sys.stderr)
        return 1
    bars = {key: candidate[key] for key in BAR_KEYS}
    root = Path(__file__).resolve().parents[1]
    records: list[dict] = []
    timings: list[float] = []
    for _filename, header, questions in groups:
        temporary, clone = _clone(header["source"])
        config_dir = tempfile.TemporaryDirectory(prefix="highways-eval-config-")
        config = Path(config_dir.name) / "config.json"
        config.write_text(json.dumps({"default": "off", "repos": {os.path.realpath(clone): "on"}}), encoding="utf-8")
        try:
            for item in questions:
                _git(clone, "checkout", "--quiet", "--detach", item["parent"])
                env = os.environ.copy()
                env["HIGHWAYS_CONFIG"] = str(config)
                env["HIGHWAYS_BARS"] = str(_state() / "bars.candidate.json")
                started = time.monotonic()
                process = subprocess.run([str(root / "bin" / "highways"), "search", item["question"], "--json"], cwd=clone, env=env, text=True, capture_output=True)
                timings.append(time.monotonic() - started)
                try:
                    output = json.loads(process.stdout)
                except json.JSONDecodeError:
                    output = {"status": "unavailable", "answers": []}
                routers = discover(str(clone))
                own = _own_files(routers, _tracked(clone))
                rows = []
                if output.get("status") == "answers":
                    for answer in output.get("answers", []):
                        directory = answer.get("dir")
                        if directory in own:
                            rows.append({"dir": directory, "own": answer.get("own", 0), "files": answer.get("files", []), "own_files": own[directory]})
                records.append({"answers": item.get("answers", []), "files": item.get("files", []),
                                "tracked": _tracked(clone), "live_answers": rows,
                                "repo": os.path.realpath(header["source"]),
                                "origin": "written" if str(item.get("id", "")).startswith("w-") else "drafted"})
        finally:
            config_dir.cleanup()
            temporary.cleanup()
    metrics = _metric_groups(records, bars)
    values = {"median": _median(timings) or 0.0, "p95": _p95(timings) if timings else float("inf")}
    gates = _gates(metrics, bars, latency=values["p95"], require_files=True)
    _report("latency", metrics, gates, latency=values)
    if bars["file"] is not None and not metrics["pool"]["files_returned"]:
        print("highways: file step returned no files; switch the file step off")
    if not all(gates.values()):
        return 1
    target = Path(os.environ.get("HIGHWAYS_BARS_TARGET", root / "search" / "bars.json"))
    descriptor, temporary_name = tempfile.mkstemp(prefix="bars.", suffix=".json", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(bars, handle, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="highways eval")
    commands = parser.add_subparsers(dest="command", required=True)
    draft_parser = commands.add_parser("draft")
    draft_parser.add_argument("--source", required=True)
    written_parser = commands.add_parser("written")
    written_parser.add_argument("--source", required=True)
    written_parser.add_argument("--rev", required=True)
    written_parser.add_argument("--from", dest="filename", required=True)
    for name in ("score", "latency"):
        command = commands.add_parser(name)
        command.add_argument("--questions", action="append", required=True)
    review_parser = commands.add_parser("review")
    review_parser.add_argument("--questions", action="append", required=True)
    review_parser.add_argument("--port", type=int, default=0)
    review_parser.add_argument("--prefix", default="/highways-review")
    args = parser.parse_args(argv)
    if args.command == "review":
        from . import eval_review
        return eval_review.run(args.questions, args.port, args.prefix)
    if args.command == "draft":
        return draft(args.source)
    if args.command == "written":
        return written(args.source, args.rev, args.filename)
    if args.command == "score":
        return score(args.questions)
    return latency(args.questions)
