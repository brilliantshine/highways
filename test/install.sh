#!/usr/bin/env bash
# Offline fixture tests for install.sh. No case touches a live harness home.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
installer=${HIGHWAYS_INSTALLER:-"$repo/install.sh"}
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
passes=0 failures=0
pass() { printf 'PASS %s\n' "$1"; passes=$((passes + 1)); }
fail() { printf 'FAIL %s\n' "$1"; failures=$((failures + 1)); }
assert() { local note=$1; shift; if "$@"; then pass "$note"; else fail "$note"; fi; }
hash() { [[ -e $1 || -L $1 ]] && sha256sum "$1" | awk '{print $1}' || printf absent; }

declare -A claude codex bindir home present output status
new() {
  local n=$1 b=$fixture/$1
  claude[$n]=$b/claude; codex[$n]=$b/codex; bindir[$n]=$b/bin; home[$n]=$b/home
  present[$n]=claude,codex
}
settings() { printf '%s/settings.json' "${claude[$1]}"; }
hooks() { printf '%s/hooks.json' "${codex[$1]}"; }
binlink() { printf '%s/highways' "${bindir[$1]}"; }
run() {
  local n=$1
  set +e
  output[$n]=$(HOME="${home[$n]}" HIGHWAYS_PRESENT="${present[$n]}" HIGHWAYS_CLAUDE_HOME="${claude[$n]}" HIGHWAYS_CODEX_HOME="${codex[$n]}" HIGHWAYS_BIN_DIR="${bindir[$n]}" bash "$installer" 2>&1)
  status[$n]=$?
  set -e
}

new fresh; run fresh
assert 'fresh install succeeds' bash -c '[[ $1 == 0 ]]' _ "${status[fresh]}"
assert 'fresh wrappers render their placeholders' python3 - "$repo" "${claude[fresh]}/skills/highways/SKILL.md" "${codex[fresh]}/prompts/highways.md" <<'PY'
import sys
root, *paths = sys.argv[1:]
for path in paths:
    text = open(path).read()
    assert '{{' not in text and root in text
assert 'name: highways' in open(paths[0]).read()
PY
assert 'fresh install creates the command symlink' bash -c '[[ -L $1 && $(readlink "$1") == "$2/bin/highways" ]]' _ "$(binlink fresh)" "$repo"
assert 'fresh install writes both hook groups for both harnesses' python3 - "$repo" "$(settings fresh)" "$(hooks fresh)" <<'PY'
import json, sys
root = sys.argv[1]
for path, harness in zip(sys.argv[2:], ('claude', 'codex')):
    data = json.load(open(path))
    for event, script, timeout in (('UserPromptSubmit', 'prompt.sh', 2), ('Stop', 'stop.sh', 10)):
        groups = data['hooks'][event]
        assert len(groups) == 1
        assert groups[0]['hooks'][0] == {'type': 'command', 'command': f'{root}/hooks/{script} {harness}', 'timeout': timeout}
PY
assert 'fresh Codex hook requests approval once' bash -c '[[ $1 == *"run /hooks in Codex once to approve the highways hooks"* ]]' _ "${output[fresh]}"
assert 'nothing named spine is installed' bash -c '[[ ! -e $1 && ! -e $2 ]]' _ "${claude[fresh]}/skills/spine" "${codex[fresh]}/prompts/spine.md"
assert 'seams keep HOME harnesses and bin untouched' bash -c '[[ ! -e $1/.claude && ! -e $1/.codex && ! -e $1/.local/bin ]]' _ "${home[fresh]}"

before="$(hash "$(settings fresh)") $(hash "$(hooks fresh)") $(hash "${claude[fresh]}/skills/highways/SKILL.md") $(hash "${codex[fresh]}/prompts/highways.md")"
run fresh
after="$(hash "$(settings fresh)") $(hash "$(hooks fresh)") $(hash "${claude[fresh]}/skills/highways/SKILL.md") $(hash "${codex[fresh]}/prompts/highways.md")"
assert 'rerun is byte-identical and has no Codex reminder' bash -c '[[ $1 == 0 && "$2" == "$3" && $4 != *"run /hooks"* ]]' _ "${status[fresh]}" "$after" "$before" "${output[fresh]}"

new foreign
mkdir -p "${claude[foreign]}" "${codex[foreign]}"
printf '%s\n' '{"keep":{"claude":true},"hooks":{"UserPromptSubmit":[{"matcher":"*","hooks":[{"command":"foreign prompt"}]}],"Stop":[{"matcher":"*","hooks":[{"command":"foreign stop"}]}]}}' > "$(settings foreign)"
printf '%s\n' '{"keep":{"codex":true},"hooks":{"UserPromptSubmit":[{"matcher":"*","hooks":[{"command":"foreign prompt"}]}],"Stop":[{"matcher":"*","hooks":[{"command":"foreign stop"}]}]}}' > "$(hooks foreign)"
run foreign
assert 'unrelated keys and hook groups survive untouched' python3 - "$(settings foreign)" "$(hooks foreign)" <<'PY'
import json, sys
for path, key in zip(sys.argv[1:], ('claude', 'codex')):
    data = json.load(open(path)); assert data['keep'] == {key: True}
    for event, command in (('UserPromptSubmit', 'foreign prompt'), ('Stop', 'foreign stop')):
        assert len(data['hooks'][event]) == 2
        assert data['hooks'][event][0]['hooks'][0]['command'] == command
PY

new old; run old
python3 - "$(settings old)" "$(hooks old)" <<'PY'
import json, sys
for path in sys.argv[1:]:
    data = json.load(open(path))
    for event in ('UserPromptSubmit', 'Stop'):
        handler = data['hooks'][event][0]['hooks'][0]
        handler['command'] += ' old-argument'; handler['timeout'] = 99
    open(path, 'w').write(json.dumps(data))
PY
run old
assert 'old highways groups rewrite in place without duplicates' python3 - "$repo" "$(settings old)" "$(hooks old)" <<'PY'
import json, sys
root = sys.argv[1]
for path, harness in zip(sys.argv[2:], ('claude', 'codex')):
    data = json.load(open(path))
    for event, script, timeout in (('UserPromptSubmit', 'prompt.sh', 2), ('Stop', 'stop.sh', 10)):
        groups = data['hooks'][event]; assert len(groups) == 1
        handler = groups[0]['hooks'][0]
        assert handler['command'] == f'{root}/hooks/{script} {harness}' and handler['timeout'] == timeout
PY

for harness in claude codex; do
  for shape in invalid_json root_array hooks_array event_object group_scalar group_hooks_scalar; do
    n=${harness}_${shape}; new "$n"; target=$(settings "$n"); [[ $harness == codex ]] && target=$(hooks "$n")
    mkdir -p "${target%/*}"
    event=UserPromptSubmit; [[ $harness == codex && $shape =~ event_object\|group_scalar\|group_hooks_scalar ]] && event=Stop
    case $shape in
      invalid_json) printf '{broken' > "$target" ;;
      root_array) printf '[]\n' > "$target" ;;
      hooks_array) printf '{"hooks":[]}\n' > "$target" ;;
      event_object) printf '{"hooks":{"%s":{}}}\n' "$event" > "$target" ;;
      group_scalar) printf '{"hooks":{"%s":[null]}}\n' "$event" > "$target" ;;
      group_hooks_scalar) printf '{"hooks":{"%s":[{"hooks":{}}]}}\n' "$event" > "$target" ;;
    esac
    original=$(hash "$target"); run "$n"
    other=$(hooks "$n"); [[ $harness == codex ]] && other=$(settings "$n")
    assert "$harness $shape is refused unchanged and the other harness continues" bash -c '[[ $1 == 1 && $2 == "$3" && -f $4 ]]' _ "${status[$n]}" "$(hash "$target")" "$original" "$other"
  done
done

new claude_only; present[claude_only]=claude; run claude_only
assert 'claude-only install does not touch Codex' bash -c '[[ $1 == 0 && -f $2 && ! -e $3 ]]' _ "${status[claude_only]}" "$(settings claude_only)" "${codex[claude_only]}"

new protected_bin; mkdir -p "${bindir[protected_bin]}"; printf 'keep\n' > "$(binlink protected_bin)"
old_bin=$(hash "$(binlink protected_bin)"); run protected_bin
assert 'a non-symlink command entry is warned about and retained' bash -c '[[ $1 == "$2" && $3 == *"refusing to replace non-symlink"* ]]' _ "$(hash "$(binlink protected_bin)")" "$old_bin" "${output[protected_bin]}"

printf 'RESULT %d passed, %d failed\n' "$passes" "$failures"
(( failures == 0 ))
