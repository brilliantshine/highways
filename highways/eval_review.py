"""A local review page for drafted test-set question files (`highways eval review`)."""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

STRIP = ("review", "edited", "proposed", "suggest", "why")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _write_atomic(path: str, text: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    descriptor, temporary = tempfile.mkstemp(prefix=".review.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary, os.stat(path).st_mode & 0o7777)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _dump(value: dict) -> str:
    return json.dumps(value, sort_keys=True)


class QuestionFile:
    """One question file held as raw lines, so a save changes only the line it names."""

    def __init__(self, path: str) -> None:
        self.path = os.path.abspath(path)
        self.lock = threading.Lock()
        with open(self.path, encoding="utf-8") as handle:
            raw = [line.rstrip("\n") for line in handle if line.strip()]
        if not raw:
            raise ValueError("invalid questions file %s" % path)
        try:
            self.header = json.loads(raw[0])
            self.questions = [json.loads(line) for line in raw[1:]]
        except json.JSONDecodeError as exc:
            raise ValueError("invalid questions file %s" % path) from exc
        if not isinstance(self.header, dict) or not all(isinstance(item, dict) for item in self.questions):
            raise ValueError("invalid questions file %s" % path)
        if self.header.get("reviewed") is True:
            raise ValueError("questions file %s is already reviewed" % path)
        self.lines = raw
        self.finished = False

    def _flush(self) -> None:
        _write_atomic(self.path, "\n".join(self.lines) + "\n")

    def find(self, qid: str) -> int | None:
        for index, item in enumerate(self.questions):
            if item.get("id") == qid:
                return index
        return None

    def decide(self, qid: str, body: dict) -> dict | None:
        with self.lock:
            if self.finished:
                raise PermissionError("file is finished")
            index = self.find(qid)
            if index is None:
                return None
            item = self.questions[index]
            if "review" in body:
                if body["review"] in ("keep", "drop"):
                    item["review"] = body["review"]
                else:
                    item.pop("review", None)
            if "edited" in body:
                if isinstance(body["edited"], str):
                    item["edited"] = body["edited"]
                else:
                    item.pop("edited", None)
            self.lines[index + 1] = _dump(item)
            self._flush()
            return item

    def edit(self, qid: str, text: str) -> dict | None:
        """Save an edited question text only; the decision stays exactly as it was."""
        with self.lock:
            if self.finished:
                raise PermissionError("file is finished")
            index = self.find(qid)
            if index is None:
                return None
            item = self.questions[index]
            item["edited"] = text
            self.lines[index + 1] = _dump(item)
            self._flush()
            return item

    def final_text(self, item: dict) -> str:
        # A written question keeps its own wording unless the reviewer chose the suggestion.
        keys = ("edited", "question") if item.get("subject") == "written" else ("edited", "proposed", "question")
        for key in keys:
            if isinstance(item.get(key), str) and item[key].strip():
                return item[key]
        return ""

    def finish(self) -> tuple[int, int]:
        with self.lock:
            if self.finished:
                raise PermissionError("file is finished")
            if any(item.get("review") not in ("keep", "drop") for item in self.questions):
                raise ValueError("undecided questions remain")
            backup = self.path + ".pre-review.bak"
            if not os.path.exists(backup):
                with open(self.path, "rb") as source:
                    original = source.read()
                with open(backup, "xb") as handle:
                    handle.write(original)
            kept = []
            for item in self.questions:
                if item["review"] != "keep":
                    continue
                final = {key: value for key, value in item.items() if key not in STRIP}
                final["question"] = self.final_text(item)
                kept.append(final)
            header = dict(self.header, reviewed=True)
            self.lines = [_dump(header)] + [_dump(item) for item in kept]
            self._flush()
            self.finished = True
            self.header = header
            dropped = len(self.questions) - len(kept)
            self.questions = kept
            return len(kept), dropped

    def view(self) -> dict:
        with self.lock:
            return {"path": self.path, "finished": self.finished, "source": self.header.get("source"), "questions": self.questions}


def _git(source: str, *args: str) -> str:
    return subprocess.run(["git", "--no-optional-locks", "-C", source, *args], capture_output=True, text=True, timeout=30, check=True).stdout


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, files: list[QuestionFile], port: int = 0, prefix: str = "/highways-review") -> None:
        self.files = files
        self.prefix = "/" + prefix.strip("/")
        self.token = secrets.token_urlsafe(24)
        super().__init__(("127.0.0.1", port), Handler)

    @property
    def url(self) -> str:
        return "http://127.0.0.1:%d%s/?t=%s" % (self.server_address[1], self.prefix, self.token)


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    def _send(self, status: int, body: bytes, kind: str = "application/json", headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: object) -> None:
        self._send(status, json.dumps(value).encode())

    def _route(self) -> tuple[str, dict] | None:
        parts = urlsplit(self.path)
        query = {key: values[-1] for key, values in parse_qs(parts.query).items()}
        prefix = self.server.prefix
        if parts.path == prefix:
            route = ""
        elif parts.path.startswith(prefix + "/"):
            route = parts.path[len(prefix) + 1:]
        else:
            self._json(404, {"error": "not found"})
            return None
        token = query.get("t") or self.headers.get("X-Token") or ""
        if not secrets.compare_digest(token.encode(), self.server.token.encode()):
            self._json(403, {"error": "forbidden"})
            return None
        if parts.path == prefix:
            self._send(302, b"", headers={"Location": "%s/?t=%s" % (prefix.rsplit("/", 1)[-1], self.server.token)})
            return None
        return route, query

    def _file(self, value: object) -> QuestionFile | None:
        try:
            return self.server.files[int(value)]  # type: ignore[call-overload]
        except (TypeError, ValueError, IndexError):
            self._json(404, {"error": "no such file"})
            return None

    def do_GET(self) -> None:  # noqa: N802
        routed = self._route()
        if routed is None:
            return
        route, query = routed
        if route == "":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif route == "api/files":
            self._json(200, {"files": [{"index": index, "path": item.path, "finished": item.finished} for index, item in enumerate(self.server.files)]})
        elif route == "api/state":
            target = self._file(query.get("file"))
            if target is not None:
                self._json(200, target.view())
        elif route == "api/commit":
            self._commit(query)
        else:
            self._json(404, {"error": "not found"})

    def _commit(self, query: dict) -> None:
        target = self._file(query.get("file"))
        if target is None:
            return
        commit = query.get("id", "")
        item = next((entry for entry in target.questions if entry.get("commit") == commit), None)
        if not COMMIT.match(commit) or item is None:
            self._json(404, {"error": "unknown commit"})
            return
        source = str(target.header.get("source", ""))
        parent = str(item.get("parent", ""))
        try:
            message = _git(source, "show", "--no-patch", "--format=%B", commit)
            changed = _git(source, "diff-tree", "--no-commit-id", "-r", "--name-status", parent, commit) if COMMIT.match(parent) else ""
        except (OSError, subprocess.SubprocessError):
            self._json(502, {"error": "git failed"})
            return
        self._json(200, {"message": message.strip(), "changed": [line.split("\t") for line in changed.splitlines() if line]})

    def do_POST(self) -> None:  # noqa: N802
        routed = self._route()
        if routed is None:
            return
        route, query = routed
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "bad request"})
            return
        target = self._file(body.get("file"))
        if target is None:
            return
        try:
            if route == "api/decide":
                item = target.decide(str(body.get("id")), body)
                if item is None:
                    self._json(404, {"error": "unknown question"})
                else:
                    self._json(200, {"question": item})
            elif route == "api/edit":
                if not isinstance(body.get("edited"), str):
                    self._json(400, {"error": "bad request"})
                    return
                item = target.edit(str(body.get("id")), body["edited"])
                if item is None:
                    self._json(404, {"error": "unknown question"})
                else:
                    self._json(200, {"question": item})
            elif route == "api/finish":
                kept, dropped = target.finish()
                print("highways: finished %s (kept %d, dropped %d)" % (target.path, kept, dropped), flush=True)
                self._json(200, {"kept": kept, "dropped": dropped})
            else:
                self._json(404, {"error": "not found"})
        except PermissionError as exc:
            self._json(409, {"error": str(exc)})
        except ValueError as exc:
            self._json(409, {"error": str(exc)})
        except OSError as exc:
            self._json(500, {"error": str(exc)})


def make_server(paths: list[str], port: int = 0, prefix: str = "/highways-review") -> Server:
    return Server([QuestionFile(path) for path in paths], port, prefix)


def run(paths: list[str], port: int = 0, prefix: str = "/highways-review") -> int:
    try:
        server = make_server(paths, port, prefix)
    except (OSError, ValueError) as exc:
        print("highways: %s" % exc, file=sys.stderr)
        return 1
    print("highways: review page at %s" % server.url, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review questions</title>
<style>
:root{--bg:#fafafa;--panel:#fff;--fg:#1d2024;--mut:#6a7079;--line:#dcdfe4;--acc:#2458d6;--keep:#1c7c3b;--drop:#b3261e;--warn:#9a6700;--chip:#eef1f6}
@media (prefers-color-scheme:dark){:root{--bg:#15171a;--panel:#1d2024;--fg:#e6e8eb;--mut:#9aa1ab;--line:#33373d;--acc:#7aa2ff;--keep:#5fd07f;--drop:#ff8a80;--warn:#e3b341;--chip:#2a2e35}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif;height:100vh;display:flex;flex-direction:column}
header{padding:8px 14px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;flex-wrap:wrap;background:var(--panel)}
header .grow{flex:1}button,select{font:inherit;color:var(--fg);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer}
button:hover:not(:disabled){border-color:var(--acc)}button:disabled{opacity:.45;cursor:default}button.on{background:var(--acc);color:#fff;border-color:var(--acc)}
main{flex:1;display:flex;min-height:0}#list{width:380px;overflow:auto;border-right:1px solid var(--line);background:var(--panel)}
#detail{flex:1;overflow:auto;padding:18px 24px}.row{padding:7px 12px;border-bottom:1px solid var(--line);cursor:pointer;display:flex;gap:8px;align-items:baseline}
.row.sel{background:var(--chip);box-shadow:inset 3px 0 var(--acc)}.row .n{color:var(--mut);min-width:2.2em;text-align:right}.row .t{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.badge{font-size:12px;padding:1px 7px;border-radius:9px;border:1px solid var(--line);color:var(--mut)}.badge.keep{color:var(--keep);border-color:var(--keep)}.badge.drop{color:var(--drop);border-color:var(--drop)}
.sd{font-size:11px;color:var(--warn);border:1px solid var(--warn);border-radius:9px;padding:0 6px}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);margin:18px 0 4px}p{margin:0}
textarea{width:100%;min-height:90px;font:inherit;color:var(--fg);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px}
.chip{display:inline-block;background:var(--chip);border-radius:5px;padding:1px 8px;margin:2px 4px 2px 0;font:13px ui-monospace,monospace}
pre{background:var(--chip);padding:10px;border-radius:6px;overflow:auto;white-space:pre-wrap;margin:0;font:13px ui-monospace,monospace}
.bar{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}.keep-b{border-color:var(--keep);color:var(--keep)}.drop-b{border-color:var(--drop);color:var(--drop)}
#help{position:fixed;inset:0;background:#0008;display:none;align-items:center;justify-content:center}#help div{background:var(--panel);padding:20px 28px;border-radius:10px}
.fin{color:var(--keep);font-weight:600}
@media (max-width:760px){main{flex-direction:column}#list{width:auto;height:35%;border-right:0;border-bottom:1px solid var(--line)}}
</style></head><body>
<header><strong>Review</strong><select id="files"></select><span id="filters"></span><span class="grow"></span><span id="progress"></span><button id="finish">Finish this file</button><button id="helpb">?</button></header>
<main><div id="list"></div><div id="detail"></div></main>
<div id="help"><div><b>Shortcuts</b><p>j / k: next / previous</p><p>a: keep (saves the text box; moving on also saves an edit)</p><p>d: drop</p><p>e: edit the text box; Esc leaves it</p><p>?: this help (any key closes)</p></div></div>
<script>
const token = new URLSearchParams(location.search).get('t') || '';
const $ = id => document.getElementById(id);
let fileIdx = 0, data = null, cur = 0, filter = 'all', files = [], commits = {};
const FILTERS = ['all', 'undecided', 'keep', 'drop', 'suggested-drop'];
async function api(path, body) {
  const sep = path.includes('?') ? '&' : '?';
  const r = await fetch(path + sep + 't=' + encodeURIComponent(token), body ? {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Token': token}, body: JSON.stringify(body)} : {});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.status);
  return j;
}
const state = q => q.review === 'keep' || q.review === 'drop' ? q.review : 'undecided';
const text = q => q.edited != null ? q.edited : (q.proposed != null && q.subject !== 'written' ? q.proposed : q.question);
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
function visible() {
  return data.questions.map((q, i) => i).filter(i => {
    const q = data.questions[i];
    return filter === 'all' || (filter === 'suggested-drop' ? q.suggest === 'drop' : state(q) === filter);
  });
}
function renderHeader() {
  const decided = data.questions.filter(q => state(q) !== 'undecided').length;
  $('progress').textContent = data.finished ? 'finished' : decided + ' of ' + data.questions.length + ' decided';
  $('finish').disabled = data.finished || decided !== data.questions.length || !data.questions.length;
  $('filters').replaceChildren(...FILTERS.map(f => { const b = el('button', f === filter ? 'on' : '', f.replace('-', ' ')); b.onclick = () => { flushEdit(); filter = f; renderList(); }; return b; }));
}
function renderList() {
  renderHeader();
  const list = $('list'); list.replaceChildren();
  for (const i of visible()) {
    const q = data.questions[i], row = el('div', 'row' + (i === cur ? ' sel' : ''));
    // Every question opens the same way; show the part that differs.
    row.append(el('span', 'n', i + 1), el('span', 't', text(q).replace(/^where is (the )?(code|text|test)( that| for)?\s*/i, '')));
    if (q.suggest === 'drop') row.append(el('span', 'sd', 'suggested drop'));
    row.append(el('span', 'badge ' + state(q), state(q)));
    row.onclick = () => select(i);
    row.dataset.i = i; list.append(row);
  }
  const s = list.querySelector('.sel'); if (s) s.scrollIntoView({block: 'nearest'});
}
// Save an edited text box without touching the decision; called whenever the reviewer leaves a question.
function flushEdit() {
  const box = $('box');
  if (!data || data.finished || !box || box.disabled) return;
  const q = data.questions[cur];
  if (!q || box.value === text(q)) return;
  const f = fileIdx, value = box.value;
  q.edited = value;
  api('api/edit', {file: f, id: q.id, edited: value}).catch(e => alert('save failed: ' + e.message));
}
function select(i) { flushEdit(); cur = i; renderList(); renderDetail(); }
function renderDetail() {
  const d = $('detail'); d.replaceChildren();
  const q = data.questions[cur];
  if (!q) { d.append(el('p', '', data.finished ? 'This file is finished and read-only.' : 'No questions.')); return; }
  if (data.finished) d.append(el('p', 'fin', 'Finished: this file is read-only.'));
  d.append(el('h2', '', 'Commit subject'), el('p', '', q.subject || ''));
  if (q.proposed != null || q.why) {
    d.append(el('h2', '', 'Suggested rewrite' + (q.suggest ? ' (suggest ' + q.suggest + ')' : '')));
    if (q.proposed != null) d.append(el('p', '', q.proposed));
    if (q.why) { const w = el('p', '', 'Why: ' + q.why); w.style.color = 'var(--mut)'; d.append(w); }
  } else if (q.suggest) d.append(el('h2', '', 'Suggestion'), el('p', '', 'suggest ' + q.suggest));
  d.append(el('h2', '', 'Question'));
  const box = el('textarea'); box.id = 'box'; box.value = text(q); box.disabled = data.finished; d.append(box);
  const bar = el('div', 'bar');
  const mk = (label, cls, fn) => { const b = el('button', cls, label); b.disabled = data.finished; b.onclick = fn; bar.append(b); return b; };
  mk('use suggestion', '', () => { if (q.proposed != null) box.value = q.proposed; });
  mk('use original', '', () => { box.value = q.question; });
  mk('keep (a)', 'keep-b', () => decide('keep'));
  mk('drop (d)', 'drop-b', () => decide('drop'));
  mk('clear decision', '', () => decide(null));
  d.append(bar);
  d.append(el('h2', '', 'Right answers'));
  const chips = el('div');
  for (const a of q.answers || []) chips.append(el('span', 'chip', a + '/'));
  for (const f of q.files || []) chips.append(el('span', 'chip', f));
  d.append(chips, el('h2', '', 'Commit'));
  const info = el('pre', '', 'loading...'); d.append(info);
  loadCommit(q, info);
}
async function loadCommit(q, info) {
  try {
    let c = commits[q.commit];
    if (!c) c = commits[q.commit] = await api('api/commit?file=' + fileIdx + '&id=' + q.commit);
    info.textContent = c.message + '\n\n' + c.changed.map(r => r.join('\t')).join('\n');
  } catch (e) { info.textContent = 'commit details unavailable: ' + e.message; }
}
async function decide(review) {
  if (data.finished) return;
  const q = data.questions[cur], box = $('box');
  const body = {file: fileIdx, id: q.id, review};
  if (review === 'keep' || (box && box.value !== text(q))) body.edited = box.value;
  try {
    const r = await api('api/decide', body);
    data.questions[cur] = r.question;
  } catch (e) { alert('save failed: ' + e.message); return; }
  if (review) {
    const n = data.questions.length;
    for (let k = 1; k <= n; k++) { const j = (cur + k) % n; if (state(data.questions[j]) === 'undecided') { cur = j; break; } }
  }
  renderList(); renderDetail();
}
function step(dir) {
  const v = visible(); if (!v.length) return;
  let pos = v.indexOf(cur);
  if (pos < 0) pos = dir > 0 ? v.findIndex(i => i > cur) - 1 : v.length;
  if (pos < -1) pos = v.length - 1;
  select(v[Math.min(v.length - 1, Math.max(0, pos + dir))]);
}
async function load(i) {
  fileIdx = i; data = await api('api/state?file=' + i); commits = {};
  const first = data.questions.findIndex(q => state(q) === 'undecided');
  cur = first < 0 ? 0 : first; renderList(); renderDetail();
}
$('finish').onclick = async () => {
  if (!confirm('Finish this file? It keeps only the questions marked keep, marks it reviewed, and cannot be edited afterwards.')) return;
  try { await api('api/finish', {file: fileIdx}); await load(fileIdx); } catch (e) { alert(e.message); }
};
window.addEventListener('beforeunload', () => {
  const box = $('box');
  if (!data || data.finished || !box || box.disabled) return;
  const q = data.questions[cur];
  if (q && box.value !== text(q)) navigator.sendBeacon('api/edit?t=' + encodeURIComponent(token), JSON.stringify({file: fileIdx, id: q.id, edited: box.value}));
});
$('helpb').onclick = () => { $('help').style.display = 'flex'; };
$('help').onclick = () => { $('help').style.display = 'none'; };
document.addEventListener('keydown', e => {
  if ($('help').style.display === 'flex') { $('help').style.display = 'none'; return; }
  if (e.target.tagName === 'TEXTAREA') { if (e.key === 'Escape') e.target.blur(); return; }
  if (e.ctrlKey || e.metaKey || e.altKey || !data) return;
  if (e.key === 'j') step(1); else if (e.key === 'k') step(-1);
  else if (e.key === 'a') decide('keep'); else if (e.key === 'd') decide('drop');
  else if (e.key === 'e') { const b = $('box'); if (b && !b.disabled) { e.preventDefault(); b.focus(); } }
  else if (e.key === '?') $('help').style.display = 'flex';
});
(async () => {
  try {
    files = (await api('api/files')).files;
    const sel = $('files');
    files.forEach(f => sel.append(new Option(f.path.split('/').slice(-1)[0] + (f.finished ? ' (finished)' : ''), f.index)));
    sel.style.display = files.length > 1 ? '' : 'none';
    sel.onchange = () => { flushEdit(); load(+sel.value); };
    await load(0);
  } catch (e) { $('detail').textContent = 'error: ' + e.message; }
})();
</script></body></html>
"""
