#!/usr/bin/env bash
# Install highways' harness wrappers, hooks, and command-line entry point.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
claude_home=${HIGHWAYS_CLAUDE_HOME:-"$HOME/.claude"}
codex_home=${HIGHWAYS_CODEX_HOME:-"$HOME/.codex"}
bin_dir=${HIGHWAYS_BIN_DIR:-"$HOME/.local/bin"}

# Testing seam: when set (including to empty), this replaces PATH detection.
if [[ ${HIGHWAYS_PRESENT+x} ]]; then
  case ",$HIGHWAYS_PRESENT," in *,claude,*) claude_present=1 ;; *) claude_present=0 ;; esac
  case ",$HIGHWAYS_PRESENT," in *,codex,*) codex_present=1 ;; *) codex_present=0 ;; esac
else
  command -v claude >/dev/null 2>&1 && claude_present=1 || claude_present=0
  command -v codex >/dev/null 2>&1 && codex_present=1 || codex_present=0
fi

render() {  # render <source> <destination>
  local source=$1 destination=$2 temporary
  mkdir -p "${destination%/*}"
  temporary=$(mktemp "${destination%/*}/.highways-render.XXXXXX")
  python3 - "$source" "$temporary" "$ROOT" <<'PY'
import sys
source, destination, root = sys.argv[1:]
with open(source, encoding="utf-8") as f:
    text = f.read()
with open(destination, "w", encoding="utf-8", newline="") as f:
    f.write(text.replace("{{HIGHWAYS_ROOT}}", root))
PY
  if [[ -e $destination ]] && cmp -s "$temporary" "$destination"; then
    rm "$temporary"
  else
    mv "$temporary" "$destination"
  fi
}

if (( claude_present )); then
  render "$ROOT/skills/highways/SKILL.md" "$claude_home/skills/highways/SKILL.md"
fi

if (( codex_present )); then
  render "$ROOT/codex/prompts/highways.md" "$codex_home/prompts/highways.md"
fi

mkdir -p "$bin_dir"
bin_link="$bin_dir/highways"
if [[ -e $bin_link && ! -L $bin_link ]]; then
  printf 'highways: warning — refusing to replace non-symlink %s\n' "$bin_link" >&2
else
  ln -sfn "$ROOT/bin/highways" "$bin_link"
fi

present=''
(( claude_present )) && present+=claude,
(( codex_present )) && present+=codex,
python3 -I - "$ROOT" "$claude_home" "$codex_home" "$present" <<'PY'
import json
import os
import shlex
import sys
import tempfile

ROOT, CLAUDE_HOME, CODEX_HOME, present_arg = sys.argv[1:]
PRESENT = [name for name in present_arg.rstrip(",").split(",") if name]
problems = []
changed_codex = False


def problem(path, message):
    problems.append(f"highways: {message}: {path}")


def read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def document(path):
    raw = read_bytes(path)
    if raw is None:
        return None, {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        problem(path, "invalid JSON")
        return raw, None
    if not isinstance(value, dict):
        problem(path, "JSON root is not an object")
        return raw, None
    return raw, value


def command_path(event):
    return os.path.join(ROOT, "hooks", "prompt.sh" if event == "UserPromptSubmit" else "stop.sh")


def canonical_group(event, harness):
    timeout = 2 if event == "UserPromptSubmit" else 10
    command = f"{shlex.quote(command_path(event))} {harness}"
    return {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}


def owns_group(group, event):
    for handler in group["hooks"]:
        if not isinstance(handler, dict) or not isinstance(handler.get("command"), str):
            continue
        try:
            tokens = shlex.split(handler["command"])
        except ValueError:
            continue
        if tokens and tokens[0] == command_path(event):
            return True
    return False


def update_event(value, event, harness, path):
    hooks = value.get("hooks")
    if hooks is None:
        hooks = {}
        value["hooks"] = hooks
    elif not isinstance(hooks, dict):
        problem(path, "hooks is not an object")
        return False
    groups = hooks.get(event)
    if groups is None:
        groups = []
        hooks[event] = groups
    elif not isinstance(groups, list):
        problem(path, f"hooks.{event} is not a list")
        return False
    for group in groups:
        if not isinstance(group, dict):
            problem(path, f"{event} group is not an object")
            return False
        if not isinstance(group.get("hooks"), list):
            problem(path, f"{event} group hooks is not a list")
            return False
    canonical = canonical_group(event, harness)
    ours = [index for index, group in enumerate(groups) if owns_group(group, event)]
    if ours:
        groups[ours[0]] = canonical
        for index in reversed(ours[1:]):
            del groups[index]
    else:
        groups.append(canonical)
    return True


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


plans = []
for harness, path in (
    ("claude", os.path.join(CLAUDE_HOME, "settings.json")),
    ("codex", os.path.join(CODEX_HOME, "hooks.json")),
):
    if harness not in PRESENT:
        continue
    old, value = document(path)
    if value is None:
        continue
    before_count = len(problems)
    for event in ("UserPromptSubmit", "Stop"):
        update_event(value, event, harness, path)
        if len(problems) != before_count:
            break
    if len(problems) == before_count:
        plans.append((harness, path, old, encoded(value)))

for harness, path, old, new in plans:
    if old == new:
        continue
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".highways-hooks.", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(new)
        try:
            mode = os.stat(path).st_mode & 0o777
        except FileNotFoundError:
            mode = 0o644
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    if harness == "codex":
        changed_codex = True

if changed_codex:
    print("run /hooks in Codex once to approve the highways hooks")
for message in problems:
    print(message, file=sys.stderr)
sys.exit(1 if problems else 0)
PY
