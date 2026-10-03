#!/usr/bin/env bash
set -u -o pipefail
root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
passed=0; failed=0; last_status=0; out=""
pass() { printf 'PASS %s\n' "$1"; passed=$((passed+1)); }
fail() { printf 'FAIL %s\n' "$1"; failed=$((failed+1)); }
check() { local name=$1; shift; if "$@"; then pass "$name"; else fail "$name"; fi; }
repo="$tmp/repo"; state="$tmp/state"; config="$tmp/config"
git init -q "$repo"
git --no-optional-locks -C "$repo" config user.email hooks@example.test
git --no-optional-locks -C "$repo" config user.name hooks
mkdir -p "$repo/lib"
printf '%s\n' '# root router names `gone.txt`, `lib/old.txt`' > "$repo/AGENTS.md"
printf '%s\n' '# child router' > "$repo/lib/AGENTS.md"
printf old > "$repo/lib/old.txt"; printf gone > "$repo/gone.txt"
git --no-optional-locks -C "$repo" add .
git --no-optional-locks -C "$repo" commit -qm initial
repo_state() { python3 - "$repo" <<'PY'
import hashlib, json, os, sys
root=sys.argv[1]
rows=[]
for base, _, names in os.walk(root):
 for name in sorted(names):
  path=os.path.join(base,name); rel=os.path.relpath(path,root)
  if os.path.islink(path): digest='link:'+os.readlink(path); stamp=os.lstat(path).st_mtime_ns
  else:
   with open(path,'rb') as f: digest=hashlib.sha256(f.read()).hexdigest()
   stamp=os.stat(path).st_mtime_ns
  rows.append([rel,digest,stamp])
print(json.dumps(sorted(rows), ensure_ascii=True, separators=(',',':')))
PY
}
index_state() { sha256sum "$repo/.git/index"; stat -c %y "$repo/.git/index"; }
assert_unchanged() {
  local label=$1 before=$2 before_index=$3 after after_index
  after=$(repo_state); after_index=$(index_state)
  check "$label leaves every fixture file unchanged" test "$before" = "$after"
  check "$label leaves index hash and mtime unchanged" test "$before_index" = "$after_index"
}
run_hook() {
  local label=$1 script=$2 harness=$3 payload=$4 before before_index
  before=$(repo_state); before_index=$(index_state)
  set +e
  env -u WHEELCHAIR_LANE -u HIGHWAYS_LANE HIGHWAYS_STATE="$state" HIGHWAYS_CONFIG="$config" "$root/hooks/$script" "$harness" <<<"$payload" >"$tmp/out" 2>"$tmp/err"
  last_status=$?
  set -e
  out=$(<"$tmp/out")
  assert_unchanged "$label" "$before" "$before_index"
  check "$label exits 0" test "$last_status" -eq 0
}
run_sweep() {
  local label=$1; shift; local before before_index
  before=$(repo_state); before_index=$(index_state)
  set +e
  HIGHWAYS_STATE="$state" "$root/bin/highways" sweep --repo "$repo" "$@" >"$tmp/out" 2>"$tmp/err"
  last_status=$?
  set -e
  out=$(<"$tmp/out")
  assert_unchanged "$label" "$before" "$before_index"
  check "$label exits 0" test "$last_status" -eq 0
}
prompt_json() { printf '{"session_id":"%s","cwd":"%s","prompt":"%s"}' "$1" "$repo" "$2"; }
stop_json() { printf '{"session_id":"%s","cwd":"%s"}' "$1" "$repo"; }

run_hook lane prompt.sh codex "$(prompt_json lane 'four words are enough')"
check 'lane is silent' test -z "$out"
before=$(repo_state); before_index=$(index_state)
set +e; WHEELCHAIR_LANE=1 HIGHWAYS_STATE="$state" "$root/hooks/prompt.sh" codex <<<"$(prompt_json lane2 'four words are enough')" >"$tmp/out" 2>"$tmp/err"; last_status=$?; set -e
out=$(<"$tmp/out"); assert_unchanged 'lane prompt' "$before" "$before_index"; check 'lane prompt exits 0' test "$last_status" -eq 0; check 'lane prompt is silent' test -z "$out"
run_hook agent prompt.sh claude "$(printf '{"session_id":"agent","cwd":"%s","prompt":"four words are enough","agent_id":"a"}' "$repo")"
check 'agent_id is silent' test -z "$out"
run_hook bad-prompt prompt.sh codex '{bad'
check 'garbage prompt is silent' test -z "$out"
run_hook bad-stop stop.sh codex '{bad'
check 'garbage stop is silent' test -z "$out"
run_hook active stop.sh claude "$(printf '{"session_id":"active","cwd":"%s","stop_hook_active":true}' "$repo")"
check 'active stop is silent' test -z "$out"
outside="$tmp/outside"; mkdir "$outside"
run_hook missing-repo-prompt prompt.sh codex "$(printf '{"session_id":"x","cwd":"%s","prompt":"four words are enough"}' "$outside")"
check 'missing repo prompt is silent' test -z "$out"
run_hook missing-repo-stop stop.sh claude "$(printf '{"session_id":"x","cwd":"%s"}' "$outside")"
check 'missing repo stop is silent' test -z "$out"

printf before >> "$repo/lib/old.txt"
run_hook short prompt.sh codex "$(prompt_json short 'one two three')"
check 'sending-off prompt prints nothing' test -z "$out"
check 'sending-off prompt writes snapshot' test -f "$state/sessions/short.json"
run_hook preedit stop.sh claude "$(stop_json short)"
check 'edit before turn is not blamed' test -z "$out"
git --no-optional-locks -C "$repo" checkout -- lib/old.txt

run_hook quiet-snapshot prompt.sh codex "$(prompt_json quiet 'one two three')"
run_hook quiet-stop stop.sh codex "$(stop_json quiet)"
check 'no routed change produces no stop output' test -z "$out"

printf same > "$repo/lib/link-one.txt"; printf same > "$repo/lib/link-two.txt"
ln -s link-one.txt "$repo/lib/tracked-link.txt"
git --no-optional-locks -C "$repo" add lib/link-one.txt lib/link-two.txt lib/tracked-link.txt
git --no-optional-locks -C "$repo" commit -qm tracked-link
run_hook retarget-snapshot prompt.sh codex "$(prompt_json retarget 'one two three')"
rm "$repo/lib/tracked-link.txt"; ln -s link-two.txt "$repo/lib/tracked-link.txt"
run_hook retarget-stop stop.sh codex "$(stop_json retarget)"
check 'retargeted tracked symlink is reported changed' python3 -c 'import json,sys; assert "lib/tracked-link.txt" in json.load(sys.stdin)["reason"]' <<<"$out"
git --no-optional-locks -C "$repo" checkout -- lib/tracked-link.txt

ln -s missing-target "$repo/broken-link.txt"
run_hook broken-link-snapshot prompt.sh codex "$(prompt_json broken-link 'one two three')"
printf changed >> "$repo/lib/old.txt"
run_hook broken-link-stop stop.sh codex "$(stop_json broken-link)"
check 'broken symlink does not suppress routed send-back' python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["decision"]=="block" and "lib/old.txt" in x["reason"]' <<<"$out"
rm "$repo/broken-link.txt"
git --no-optional-locks -C "$repo" checkout -- lib/old.txt

printf fallback > "$repo/lib/fallback.txt"
run_hook missing-snapshot stop.sh claude "$(stop_json absent)"
check 'missing snapshot falls back to status paths' python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["decision"]=="block" and "lib/fallback.txt" in x["reason"]' <<<"$out"
rm "$repo/lib/fallback.txt"

run_hook dirty-snapshot prompt.sh codex "$(prompt_json dirty 'one two three')"
printf changed >> "$repo/lib/old.txt"
run_hook dirty-claude stop.sh claude "$(stop_json dirty)"
claude_out=$out
check 'Claude stop shape is exact' python3 -c 'import json,sys; x=json.load(sys.stdin); assert set(x)=={"decision","reason"} and x["decision"]=="block" and isinstance(x["reason"],str)' <<<"$out"
run_hook dirty-codex stop.sh codex "$(stop_json dirty)"
check 'Codex stop shape is exact' python3 -c 'import json,sys; x=json.load(sys.stdin); assert set(x)=={"decision","reason"} and x["decision"]=="block" and isinstance(x["reason"],str)' <<<"$out"
git --no-optional-locks -C "$repo" add lib/old.txt
git --no-optional-locks -C "$repo" commit -qm during
run_sweep commit-sweep --session dirty --json
check 'commit made during session is found' python3 -c 'import json,sys; assert "lib/old.txt" in str(json.load(sys.stdin))' <<<"$out"

run_hook rename-snapshot prompt.sh codex "$(prompt_json rename 'one two three')"
git --no-optional-locks -C "$repo" mv lib/old.txt lib/new.txt
run_sweep rename-sweep --session rename --json
check 'rename reaches both paths' python3 -c 'import json,sys; x=str(json.load(sys.stdin)); assert "lib/old.txt" in x and "lib/new.txt" in x' <<<"$out"
git --no-optional-locks -C "$repo" reset --quiet
mv "$repo/lib/new.txt" "$repo/lib/old.txt"
git --no-optional-locks -C "$repo" checkout -- lib/old.txt

run_hook tracked-delete-snapshot prompt.sh codex "$(prompt_json tracked-delete 'one two three')"
rm "$repo/gone.txt"
run_hook tracked-delete-stop stop.sh codex "$(stop_json tracked-delete)"
check 'ancestor naming deleted tracked file is reached' python3 -c 'import json,sys; x=json.load(sys.stdin); assert "AGENTS.md: gone.txt" in x["reason"]' <<<"$out"
git --no-optional-locks -C "$repo" checkout -- gone.txt
printf temp > "$repo/ephemeral.txt"
run_hook untracked-delete-snapshot prompt.sh codex "$(prompt_json untracked-delete 'one two three')"
rm "$repo/ephemeral.txt"
run_sweep untracked-delete-sweep --session untracked-delete --json
check 'deleted untracked file is caught' python3 -c 'import json,sys; assert "ephemeral.txt" in str(json.load(sys.stdin))' <<<"$out"

printf '{"default":"on","repos":{}}\n' > "$config"; port="$tmp/port"
python3 -u - "$port" <<'PY' &
import json,sys
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
class H(BaseHTTPRequestHandler):
 def do_POST(self):
  q=json.loads(self.rfile.read(int(self.headers['Content-Length']))); b=json.dumps({'answers':{k:{'noul':1} for k in q['questions']}}).encode(); self.send_response(200); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def log_message(self,*args): pass
s=ThreadingHTTPServer(('127.0.0.1',0),H); open(sys.argv[1],'w').write(str(s.server_port)); s.serve_forever()
PY
server=$!
for _ in {1..30}; do [[ -s $port ]] && break; sleep .02; done
before=$(repo_state); before_index=$(index_state)
set +e; env -u WHEELCHAIR_LANE -u HIGHWAYS_LANE HIGHWAYS_STATE="$state" HIGHWAYS_CONFIG="$config" HIGHWAYS_DECISIONS_URL="http://127.0.0.1:$(cat "$port")" OPENROUTER_API_KEY=x "$root/hooks/prompt.sh" claude <<<"$(prompt_json claude-answer 'please find the relevant implementation')" >"$tmp/out"; last_status=$?; set -e
out=$(<"$tmp/out"); assert_unchanged 'confident Claude prompt' "$before" "$before_index"; check 'confident Claude prompt exits 0' test "$last_status" -eq 0
check 'Claude prompt shape is exact' python3 -c 'import json,sys; x=json.load(sys.stdin); assert set(x)=={"hookSpecificOutput"}; y=x["hookSpecificOutput"]; assert set(y)=={"hookEventName","additionalContext"} and y["hookEventName"]=="UserPromptSubmit"' <<<"$out"
before=$(repo_state); before_index=$(index_state)
set +e; env -u WHEELCHAIR_LANE -u HIGHWAYS_LANE HIGHWAYS_STATE="$state" HIGHWAYS_CONFIG="$config" HIGHWAYS_DECISIONS_URL="http://127.0.0.1:$(cat "$port")" OPENROUTER_API_KEY=x "$root/hooks/prompt.sh" codex <<<"$(prompt_json codex-answer 'please find the relevant implementation')" >"$tmp/out"; last_status=$?; set -e
out=$(<"$tmp/out"); assert_unchanged 'confident Codex prompt' "$before" "$before_index"; check 'confident Codex prompt exits 0' test "$last_status" -eq 0
check 'Codex prompt shape is exact' python3 -c 'import json,sys; x=json.load(sys.stdin); assert set(x)=={"hookSpecificOutput"}; y=x["hookSpecificOutput"]; assert set(y)=={"hookEventName","additionalContext"} and y["hookEventName"]=="UserPromptSubmit"' <<<"$out"
kill "$server" 2>/dev/null || true
printf 'RESULT %d passed, %d failed\n' "$passed" "$failed"
((failed == 0))
