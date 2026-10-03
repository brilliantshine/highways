"""Small, standard-library-only client for OpenRouter Decisions."""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from urllib import request

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"


class Failure(Exception):
    pass


def _one(body: dict, expected: set[str], timeout: float | None) -> dict:
    outgoing = dict(body)
    outgoing["model"] = MODEL
    outgoing["provider"] = {"zdr": True}
    data = json.dumps(outgoing).encode()
    req = request.Request(os.environ.get("HIGHWAYS_DECISIONS_URL", URL), data=data,
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get("OPENROUTER_API_KEY", "")}, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                raise Failure("HTTP %s" % response.status)
            parsed = json.loads(response.read())
    except Exception as exc:
        # HTTPError is also a file-like response.  Close it before turning it
        # into our small failure value so failed requests do not retain sockets.
        closer = getattr(exc, "close", None)
        if closer:
            closer()
        raise Failure(str(exc)) from exc
    answers = parsed.get("answers") if isinstance(parsed, dict) else None
    if not isinstance(answers, dict):
        raise Failure("invalid response")
    result = {}
    for key in expected:
        item = answers.get(key)
        value = item.get("noul") if isinstance(item, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise Failure("missing probability")
        result[key] = float(value)
    return result


def batch(items: list[tuple[dict, set[str]]], *, budget: float | None,
          timeout: float | None, resend_after: float | None = None) -> list[dict | Failure]:
    """Submit all requests concurrently and return values aligned with *items*.

    ``resend_after`` is deliberately opt-in: only the timed router round uses it.
    Request threads are daemons, so a peer that ignores its socket timeout cannot hold
    the caller (or interpreter shutdown) past a round deadline.
    """
    if not items:
        return []
    results: list[dict | Failure] = [Failure("not run") for _ in items]
    started = time.monotonic()
    deadline = None if budget is None else started + budget
    retry_at = None if resend_after is None else started + resend_after
    completed: list[set[int]] = [set() for _ in items]
    attempts = [0 for _ in items]
    responses: queue.Queue[tuple[int, int, dict | Failure]] = queue.Queue()

    def send(index: int) -> None:
        """Start one request, unless the round has already expired."""
        if deadline is not None and time.monotonic() >= deadline:
            return
        attempts[index] += 1
        attempt = attempts[index]
        body, expected = items[index]

        def run() -> None:
            # This runs in the thread rather than at scheduling time: the timeout is
            # the budget actually left when the request is sent.
            request_timeout = timeout
            if deadline is not None:
                request_timeout = deadline - time.monotonic()
                if request_timeout <= 0:
                    responses.put((index, attempt, Failure("deadline exceeded")))
                    return
            try:
                value: dict | Failure = _one(body, expected, request_timeout)
            except Failure as exc:
                value = exc
            except Exception as exc:
                value = Failure(str(exc))
            responses.put((index, attempt, value))

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    for index in range(len(items)):
        send(index)

    while True:
        now = time.monotonic()
        if deadline is not None and now >= deadline:
            break

        # At the halfway point, anything without a valid answer gets precisely one
        # independent attempt, including an already failed first attempt.
        if retry_at is not None and now >= retry_at:
            for index, result in enumerate(results):
                if isinstance(result, Failure) and attempts[index] == 1:
                    send(index)

        if all(not isinstance(result, Failure) for result in results):
            break
        if all(not isinstance(result, Failure) or
               (attempts[index] == 2 and len(completed[index]) == 2)
               for index, result in enumerate(results)):
            break
        if resend_after is None and all(len(completed[index]) == 1 for index in range(len(items))):
            break

        waits = []
        if deadline is not None:
            waits.append(deadline - now)
        if retry_at is not None and now < retry_at:
            waits.append(retry_at - now)
        wait = min(waits) if waits else None
        try:
            index, attempt, value = responses.get(timeout=wait)
        except queue.Empty:
            continue
        completed[index].add(attempt)
        if not isinstance(results[index], Failure):
            continue  # the first valid answer wins; a later attempt never replaces it
        if not isinstance(value, Failure):
            results[index] = value
        else:
            # A failure before the halfway point is retried promptly rather than
            # making the caller wait for the scheduled resend tick.
            if (retry_at is not None and attempts[index] == 1 and
                    time.monotonic() < retry_at):
                send(index)
            results[index] = value

    for index, result in enumerate(results):
        if isinstance(result, Failure):
            results[index] = Failure("deadline exceeded" if deadline is not None else str(result))
    return results
