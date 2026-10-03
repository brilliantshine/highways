#!/usr/bin/env bash
# Fixture output stays in shell variables.  python3 is required because the
# assertions exercise JSON values, not merely its outer punctuation.
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  printf 'create/test/run.sh: python3 is required for JSON assertions\n' >&2
  exit 1
fi

scan=${SPINE_SCAN:-"$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scan.sh"}
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fixture=$(mktemp -d)
sandbox_home=$(mktemp -d)
sandbox_tmp=$(mktemp -d)
trap 'rm -rf "$fixture" "$sandbox_home" "$sandbox_tmp"' EXIT

passes=0
failures=0
declare -A report stderr status before_hash after_hash

pass() { printf 'PASS %s\n' "$1"; passes=$((passes + 1)); }
fail() { printf 'FAIL %s\n' "$1"; failures=$((failures + 1)); }
assert() {
  local description=$1
  shift
  if "$@"; then pass "$description"; else fail "$description"; fi
}

tree_hash() {
  local root=$1 item rel
  while IFS= read -r -d '' item; do
    rel=${item#"$root"}
    if [[ -L $item ]]; then
      printf 'L\0%s\0%s\0' "$rel" "$(readlink "$item")"
    elif [[ -f $item ]]; then
      printf 'F\0%s\0' "$rel"
      sha256sum "$item" | awk '{print $1}'
    elif [[ -d $item ]]; then
      printf 'D\0%s\0' "$rel"
    else
      printf 'O\0%s\0' "$rel"
    fi
  done < <(find "$root" -print0 | sort -z) | sha256sum | awk '{print $1}'
}

make_repo() {
  local name=$1 root
  root=$fixture/$name
  mkdir -p "$root"
  git -C "$root" init -q
  printf '__pycache__/\nnode_modules/\ndata/\n' > "$root/.gitignore"
  printf '%s' "$root"
}

run_case() {
  local name=$1 root=$2 output code stderr_path
  before_hash[$name]=$(tree_hash "$root")
  stderr_path=$sandbox_tmp/$name.stderr
  set +e
  output=$(HOME="$sandbox_home" TMPDIR="$sandbox_tmp" "$scan" "$root" 2>"$stderr_path")
  code=$?
  set -e
  stderr[$name]=$(<"$stderr_path")
  rm -f "$stderr_path"
  after_hash[$name]=$(tree_hash "$root")
  report[$name]=$output
  status[$name]=$code
  if [[ ${before_hash[$name]} == "${after_hash[$name]}" ]]; then
    pass "$name fixture tree unchanged by scan"
  else
    fail "$name fixture tree unchanged by scan"
  fi
}

json_assert() {
  local description=$1 name=$2 program=$3
  if printf '%s' "${report[$name]}" | python3 -c "$program"; then
    pass "$description"
  else
    fail "$description"
  fi
}

valid_json() {
  local name=$1
  if printf '%s' "${report[$name]}" | python3 -m json.tool >/dev/null; then
    pass "$name stdout is valid JSON"
  else
    fail "$name stdout is valid JSON"
  fi
}

# 1. A deliberately non-git workspace.  The enclosing mktemp directory is not
# initialized, so rev-parse cannot accidentally find a parent repository.
workspace=$fixture/workspace
mkdir -p "$workspace"
for child in beacon atlas-state; do
  mkdir -p "$workspace/$child"
  git -C "$workspace/$child" init -q
done
for hub in atlas-engine atlas-data; do
  mkdir -p "$workspace/$hub/.repo.git" "$workspace/$hub/development" "$workspace/$hub/main"
done

# 2. Differing real files: their first three non-blank lines are identical.
differing=$(make_repo differing)
printf '# Shared title\n## Shared section\nA shared line\n\n### AGENTS "detail"\nagent body\n' > "$differing/AGENTS.md"
printf '# Shared title\n## Shared section\nA shared line\n\n### CLAUDE detail\nclaude body\n' > "$differing/CLAUDE.md"

# 3. Two byte-identical real files.
identical=$(make_repo identical)
printf '# Same\n## Layout\nbody\n' > "$identical/AGENTS.md"
cp "$identical/AGENTS.md" "$identical/CLAUDE.md"

# 4. The scanner reports the short real pointer without attempting to classify it.
pointer=$(make_repo pointer)
printf '# Router\n## Details\nreal router\n' > "$pointer/AGENTS.md"
printf '# CLAUDE\n\nSee AGENTS.md\n' > "$pointer/CLAUDE.md"

# 5. Reachable unmanaged surfaces, including a directory name with a space.
unmanaged=$(make_repo unmanaged)
mkdir -p "$unmanaged/space dir"
printf '# Router\n' > "$unmanaged/space dir/AGENTS.md"
printf 'unmanaged\n' > "$unmanaged/space dir/GEMINI.md"
printf 'unmanaged\n' > "$unmanaged/.cursorrules"

# 6. A nested checkout must be reported once and not walked.
nested=$(make_repo nested)
mkdir -p "$nested/vendor/upstream"
git -C "$nested/vendor/upstream" init -q
printf '# Inner\n' > "$nested/vendor/upstream/AGENTS.md"

# 7 and 8. Both live symlink directions.
claude_link=$(make_repo claude-link)
printf '# Agents\n## Layout\n' > "$claude_link/AGENTS.md"
ln -s AGENTS.md "$claude_link/CLAUDE.md"
claude_link_before=$(realpath "$claude_link/CLAUDE.md")
agents_link=$(make_repo agents-link)
printf '# Claude\n## Layout\n' > "$agents_link/CLAUDE.md"
ln -s CLAUDE.md "$agents_link/AGENTS.md"
agents_link_before=$(realpath "$agents_link/AGENTS.md")

# 9. Broken candidate link.
broken=$(make_repo broken)
mkdir -p "$broken/docs"
ln -s missing-router.md "$broken/docs/CLAUDE.md"

# 10. A grouping directory contributes a normal empty directory report.
grouping=$(make_repo grouping)
mkdir -p "$grouping/group only"
printf 'ordinary file\n' > "$grouping/group only/item.txt"

# 11 and 12. All are ignored by the fixture .gitignore.
ignored=$(make_repo ignored)
mkdir -p "$ignored/__pycache__" "$ignored/node_modules" "$ignored/data"
printf '# Hidden\n' > "$ignored/__pycache__/AGENTS.md"
printf '# Hidden\n' > "$ignored/node_modules/CLAUDE.md"
printf '# Hidden\n' > "$ignored/data/AGENTS.md"

# 13. Headings carrying every character JSON has to escape.  A trailing
# backslash is the sharp case: emitted raw it escapes the closing quote and the
# whole document stops parsing while the scanner still exits 0.
escaping=$(make_repo escaping)
printf '# trailing backslash \\\n## quote "q" and back\\slash\n### tab\there\n' > "$escaping/AGENTS.md"

# 14. A directory symlink is an excluded alias, whether it points outside the
# target or back to an ancestor; neither target may be walked.
directory_link=$(make_repo directory-link)
outside_directory=$fixture/outside-directory
mkdir -p "$outside_directory/subdir" "$directory_link/d1"
printf '# Outside\n' > "$outside_directory/subdir/AGENTS.md"
ln -s "$outside_directory" "$directory_link/vendor-link"
ln -s .. "$directory_link/d1/up"

# 15. A candidate link that resolves to a real file outside its target root.
outside_candidate=$(make_repo outside-candidate)
outside_router=$fixture/outside-router.md
printf '# External router\n' > "$outside_router"
# NUL in the external target: the report must never disclose that it is there,
# because the file is outside the target and the no-read rule covers every check.
printf '\000\n' >> "$outside_router"
mkdir -p "$outside_candidate/docs"
ln -s "$outside_router" "$outside_candidate/docs/CLAUDE.md"

# 16. Invalid UTF-8 is excluded rather than emitted as invalid JSON.  A target
# with the same defect refuses before it can produce a document.
invalid_utf8=$(make_repo invalid-utf8)
mkdir -p "$invalid_utf8"/$'bad\xff dir'
invalid_target=$fixture/$'invalid-target-\xff'
mkdir -p "$invalid_target"

# 17. A pathname ending in a newline is a normal git target and must round-trip.
newline_target=$fixture/$'newline target\n'
mkdir -p "$newline_target"
git -C "$newline_target" init -q
printf '__pycache__/\nnode_modules/\ndata/\n' > "$newline_target/.gitignore"

# 18. These controls must be JSON escapes, with no scanner warning on stderr.
controls=$(make_repo controls)
printf '# bell \a\n## vertical \v\n### delete \177\n' > "$controls/AGENTS.md"

# 19. A malformed heading byte must be made visible by the common JSON-string
# serializer rather than breaking stdout after a successful scan.
invalid_heading=$(make_repo invalid-heading)
printf '# bad \xff heading\n' > "$invalid_heading/AGENTS.md"
# The collision cases: a raw malformed byte, the four characters that spell one
# out, a *different* malformed byte, and a file carrying NUL — which bash drops
# before any string reaches the serializer.
mkdir -p "$invalid_heading/rawbyte" "$invalid_heading/literal" "$invalid_heading/otherbyte" "$invalid_heading/nul"
printf '# m \xff x\n' > "$invalid_heading/rawbyte/AGENTS.md"
printf '# m \\xff x\n' > "$invalid_heading/literal/AGENTS.md"
printf '# m \xfe x\n' > "$invalid_heading/otherbyte/AGENTS.md"
# Literal U+FFFD: valid UTF-8, so it renders exactly as a malformed byte does.
# The collision is accepted; what must hold is that only the malformed file is
# flagged, so a reader is told which heading list not to trust.
# Above U+10FFFF. glibc's iconv accepts these, so any flag built on an
# independent validity predicate misses them while the serializer still replaces
# the bytes -- the exact drift that made flag and rendering disagree.
mkdir -p "$invalid_heading/aboverange"
printf '# high \xf4\x90\x80\x80\n' > "$invalid_heading/aboverange/AGENTS.md"
# Ordinary Markdown that merely mentions the escape. JSON-escaping its backslash
# produces the same characters the replacement marker does, so any flag inferred
# from the rendered text false-fires here.
mkdir -p "$invalid_heading/mentions"
printf '# literal \\ufffd text\n' > "$invalid_heading/mentions/AGENTS.md"
# A malformed byte in the body, not in a heading. Deliberately NOT flagged: the
# report carries headings, sizes and a diff count, and none of them is affected.
mkdir -p "$invalid_heading/bodyonly"
printf '# clean heading\nbody has \xff here\n' > "$invalid_heading/bodyonly/AGENTS.md"
mkdir -p "$invalid_heading/literalfffd"
printf '# m \xef\xbf\xbdff x\n' > "$invalid_heading/literalfffd/AGENTS.md"
printf '# a' > "$invalid_heading/nul/AGENTS.md"
printf '\000b\n' >> "$invalid_heading/nul/AGENTS.md"

umbrella_before=$(tree_hash "$fixture")
# Guarded: the suite must stay runnable from a copy outside any git repo, which is
# how a mutated scanner gets tested. An unguarded `git` here aborts the whole run with
# a bare `fatal: not a git repository` under `set -e`.
repo_is_git=0
if git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then repo_is_git=1; fi
repo_status_before=""
(( repo_is_git )) && repo_status_before=$(git -C "$repo" status --porcelain --ignored)

run_case workspace "$workspace"
run_case differing "$differing"
run_case identical "$identical"
run_case pointer "$pointer"
run_case unmanaged "$unmanaged"
run_case nested "$nested"
run_case claude-link "$claude_link"
run_case agents-link "$agents_link"
run_case broken "$broken"
run_case grouping "$grouping"
run_case ignored "$ignored"
run_case escaping "$escaping"
run_case directory-link "$directory_link"
run_case outside-candidate "$outside_candidate"
run_case invalid-utf8 "$invalid_utf8"
run_case invalid-target "$invalid_target"
run_case newline-target "$newline_target"
run_case controls "$controls"
run_case invalid-heading "$invalid_heading"

case_names=(workspace differing identical pointer unmanaged nested claude-link agents-link broken grouping ignored escaping directory-link outside-candidate invalid-utf8 invalid-target newline-target controls invalid-heading)
json_case_names=(workspace differing identical pointer unmanaged nested claude-link agents-link broken grouping ignored escaping directory-link outside-candidate invalid-utf8 newline-target controls invalid-heading)

assert 'workspace refusal exits non-zero' bash -c '(( $1 != 0 ))' _ "${status[workspace]}"
json_assert 'workspace names child repositories, hubs, and hub lanes' workspace '
import json, sys
d=json.load(sys.stdin); assert not d["ok"] and d["gitToplevel"] is None
assert set(d["refusal"]["repositories"]) == {"beacon", "atlas-state"}
h={x["path"]: x["lanes"] for x in d["refusal"]["hubs"]}
assert h == {"atlas-engine": ["development", "main"], "atlas-data": ["development", "main"]}
'

assert 'differing routers scan exits zero' bash -c '(( $1 == 0 ))' _ "${status[differing]}"
json_assert 'differing routers both have size, heading lists, and a positive diff count' differing '
import json, sys
d=json.load(sys.stdin); root=d["directories"][0]; c={x["name"]:x for x in root["candidates"]}
assert set(c)=={"AGENTS.md","CLAUDE.md"} and root["realCount"]==2 and root["diffLines"]>0
assert all(isinstance(x["size"],int) and x["headings"] for x in c.values())
assert c["AGENTS.md"]["headings"] != c["CLAUDE.md"]["headings"]
'
json_assert 'differing routers are not reduced to indistinguishable opening lines' differing '
import json, sys
c={x["name"]:x for x in json.load(sys.stdin)["directories"][0]["candidates"]}
assert any("AGENTS " + chr(34) + "detail" + chr(34) in h for h in c["AGENTS.md"]["headings"])
assert any("CLAUDE detail" in h for h in c["CLAUDE.md"]["headings"])
'
json_assert 'pointer case reports both real files without aborting' pointer '
import json, sys
d=json.load(sys.stdin); assert d["ok"] and len(d["directories"][0]["candidates"])==2
'
link_target_cases=()
for name in "${json_case_names[@]}"; do
  if printf '%s' "${report[$name]}" | python3 -c '
import json, sys
assert any(c["isSymlink"] for directory in json.load(sys.stdin)["directories"] for c in directory["candidates"])
' 2>/dev/null; then
    link_target_cases+=("$name")
  fi
done
if (( ${#link_target_cases[@]} == 0 )); then
  fail 'write-target link check has no routing-file symlink reports'
else
  pass "write-target link check runs against ${#link_target_cases[@]} routing-file symlink reports"
fi
for name in "${link_target_cases[@]}"; do
  json_assert "$name write targets refer to real files, never symlink paths" "$name" '
import json, os, sys
d=json.load(sys.stdin)
for directory in d["directories"]:
    wt=directory["writeTarget"]
    if wt is not None: assert not os.path.islink(os.path.join(d["target"], wt))
'
done
json_assert 'nested repository is excluded and has no candidate report' nested '
import json, sys
d=json.load(sys.stdin); assert {x["path"] for x in d["excluded"] if x["reason"]=="nested repository"}=={"vendor/upstream"}
assert all(x["path"] != "vendor/upstream" for x in d["directories"])
assert all("Inner" not in str(x) for x in d["directories"])
'
json_assert 'every non-broken candidate has size and headings; broken has null and empty list' broken '
import json, sys
for directory in json.load(sys.stdin)["directories"]:
  for c in directory["candidates"]:
    if c["broken"]: assert c["size"] is None and c["headings"]==[]
    else: assert isinstance(c["size"],int) and isinstance(c["headings"],list)
'
json_assert 'CLAUDE link resolves to real AGENTS write target' claude-link '
import json, sys
d=json.load(sys.stdin); r=d["directories"][0]; assert r["writeTarget"]=="AGENTS.md" and r["candidates"][1]["isSymlink"]
'
assert 'CLAUDE symlink remains a link and resolves unchanged' bash -c 'test -L "$1" && [[ $(realpath "$1") == "$2" ]]' _ "$claude_link/CLAUDE.md" "$claude_link_before"
json_assert 'AGENTS link resolves to real CLAUDE write target' agents-link '
import json, sys
d=json.load(sys.stdin); r=d["directories"][0]; assert r["writeTarget"]=="CLAUDE.md" and r["candidates"][0]["isSymlink"]
'
assert 'AGENTS symlink remains a link and resolves unchanged' bash -c 'test -L "$1" && [[ $(realpath "$1") == "$2" ]]' _ "$agents_link/AGENTS.md" "$agents_link_before"
json_assert 'unmanaged surfaces are reported and never write targets' unmanaged '
import json, sys
d=json.load(sys.stdin); by={x["path"]:x for x in d["directories"]}
assert ".cursorrules" in by["."]["unmanagedSurfaces"] and "GEMINI.md" in by["space dir"]["unmanagedSurfaces"]
assert all(x["writeTarget"] not in {"GEMINI.md", ".cursorrules"} for x in d["directories"])
'
json_assert 'byte-identical pair has no write target and carries consolidation note' identical '
import json, sys
r=json.load(sys.stdin)["directories"][0]
assert r["realCount"]==2 and r["identical"] and r["diffLines"]==0 and r["writeTarget"] is None
assert "two byte-identical routing files — duplicate, consolidate" in r["notes"]
'
json_assert 'ignored cache, modules, and data directories are excluded once as git-ignored' ignored '
import json, sys
d=json.load(sys.stdin); got={(x["path"],x["reason"]) for x in d["excluded"]}
assert {("__pycache__","git-ignored"),("node_modules","git-ignored"),("data","git-ignored")} <= got
'
json_assert 'broken link is reported and its directory is skipped' broken '
import json, sys
d=json.load(sys.stdin); r=next(x for x in d["directories"] if x["path"]=="docs"); c=r["candidates"][0]
assert c["name"]=="CLAUDE.md" and c["broken"] and r["skipped"] and r["writeTarget"] is None
'
json_assert 'group-only directory is reported with no candidates and no inferred rule' grouping '
import json, sys
r=next(x for x in json.load(sys.stdin)["directories"] if x["path"]=="group only")
assert r["candidates"]==[] and r["realCount"]==0 and r["writeTarget"] is None
'
json_assert 'directory symlinks outside and to an ancestor are excluded without a descent' directory-link '
import json, sys
d=json.load(sys.stdin)
got={(x["path"], x["reason"]) for x in d["excluded"]}
assert {("vendor-link", "directory symlink"), ("d1/up", "directory symlink")} <= got
paths={x["path"] for x in d["directories"]}
assert not any(path.startswith("vendor-link/") or path.startswith("d1/up/") for path in paths)
'
json_assert 'outside-target candidate is reported, skipped, and names no write target' outside-candidate '
import json, sys
r=next(x for x in json.load(sys.stdin)["directories"] if x["path"]=="docs")
c=r["candidates"][0]
assert c["name"]=="CLAUDE.md" and c["resolvesOutsideTarget"] and r["skipped"]
assert r["writeTarget"] is None and c["size"] is None and c["headings"]==[]
'
json_assert 'invalid UTF-8 directory is excluded with a safe diagnostic path' invalid-utf8 '
import json, sys
d=json.load(sys.stdin)
assert any(x["path"]=="bad\ufffdff dir" and x["reason"]=="path is not valid UTF-8" for x in d["excluded"])
assert all(x["path"] != "badÿ dir" for x in d["directories"])
'
assert 'invalid UTF-8 target refuses with exit 2 and a clear stderr message' \
  bash -c '[[ $1 == 2 && $2 == *"target path is not valid UTF-8"* ]]' _ "${status[invalid-target]}" "${stderr[invalid-target]}"
assert 'newline target scan exits zero' bash -c '(( $1 == 0 ))' _ "${status[newline-target]}"
json_assert 'newline target name is preserved exactly in JSON' newline-target '
import json, sys
assert json.load(sys.stdin)["target"].endswith("\n")
'
assert 'control-character headings produce no scanner stderr' bash -c '[[ -z $1 ]]' _ "${stderr[controls]}"
json_assert 'control-character headings round-trip through JSON escapes' controls '
import json, sys
h=json.load(sys.stdin)["directories"][0]["candidates"][0]["headings"]
assert h == ["# bell " + chr(7), "## vertical " + chr(11), "### delete " + chr(127)]
'
json_assert 'invalid UTF-8 heading is visibly marked and stdout stays usable' invalid-heading '
import json, sys
h=json.load(sys.stdin)["directories"][0]["candidates"][0]["headings"]
# U+FFFD then the hex. A raw 0xff must NOT render the same as the literal text \xff.
assert h == ["# bad \ufffdff heading"], h
'

json_assert 'Markdown mentioning the escape is not flagged, and a body-only bad byte is not either' invalid-heading '
import json, sys
d=json.load(sys.stdin)
m={r["path"]: r for r in d["directories"]}
def flagged(p): return any("could not be represented" in n for n in m[p]["notes"])
assert not flagged("mentions"), ("literal text false-fired", m["mentions"]["notes"])
assert m["mentions"]["candidates"][0]["headings"] == [r"# literal \ufffd text"], m["mentions"]["candidates"][0]["headings"]
assert not flagged("bodyonly"), ("body byte flagged though the report is unaffected", m["bodyonly"]["notes"])
assert m["bodyonly"]["candidates"][0]["headings"] == ["# clean heading"]
'
json_assert 'the flag follows the rendering, including bytes iconv accepts' invalid-heading '
import json, sys
d=json.load(sys.stdin)
m={r["path"]: r for r in d["directories"]}
# Every candidate whose rendered headings carry a replacement must be flagged, and
# no other may be. Derived from the report itself, so it cannot drift from the code.
for path, r in m.items():
    if not r["candidates"]: continue
    replaced = any("\ufffd" in h for h in r["candidates"][0]["headings"])
    literal_only = path == "literalfffd"
    flagged = any("could not be represented" in n for n in r["notes"])
    if literal_only:
        assert not flagged, (path, "valid U+FFFD must not be flagged", r["notes"])
    else:
        assert flagged == replaced, (path, replaced, flagged, r["notes"])
assert any("could not be represented" in n for n in m["aboverange"]["notes"]), m["aboverange"]["notes"]
'
json_assert 'a file with malformed bytes is flagged, and a valid lookalike is not' invalid-heading '
import json, sys
d=json.load(sys.stdin)
m={r["path"]: r for r in d["directories"]}
raw, look = m["rawbyte"], m["literalfffd"]
# The two render identically -- that is accepted, not a defect.
assert raw["candidates"][0]["headings"] == look["candidates"][0]["headings"]
# What must hold: the malformed one is flagged and the valid one is not, so the
# reader is told which heading list cannot be relied on.
assert any("could not be represented" in n for n in raw["notes"]), raw["notes"]
assert not any("could not be represented" in n for n in look["notes"]), look["notes"]
'
json_assert 'a mangled byte stays distinct from text spelling \\xff, and from another mangled byte' invalid-heading '
import json, sys
d=json.load(sys.stdin)
h={r["path"]: r["candidates"][0]["headings"][0] for r in d["directories"] if r["candidates"]}
raw, lit, other = h["rawbyte"], h["literal"], h["otherbyte"]
assert raw != lit, ("collision: raw byte and literal text render alike", raw, lit)
assert raw != other, ("two different bad bytes collapsed together", raw, other)
assert lit == r"# m \xff x", lit
'
json_assert 'an outside-resolving candidate is never opened, not even to check for NUL' outside-candidate '
import json, sys
d=json.load(sys.stdin)
r=[x for x in d["directories"] if x["path"]=="docs"][0]
assert r["skipped"], r
assert not any("NUL" in n for n in r["notes"]), ("read through an external link", r["notes"])
'
json_assert 'a candidate carrying NUL is reported rather than silently shortened' invalid-heading '
import json, sys
d=json.load(sys.stdin)
n=[r for r in d["directories"] if r["path"]=="nul"][0]
assert any("NUL" in x for x in n["notes"]), n["notes"]
'

for name in "${json_case_names[@]}"; do
  valid_json "$name"
done

json_assert 'a backslash, a quote and a tab in a heading survive as valid JSON' escaping '
import json, sys
h=json.load(sys.stdin)["directories"][0]["candidates"][0]["headings"]
assert h == ["# trailing backslash \\", "## quote \"q\" and back\\slash", "### tab\there"], h
'

no_raw_size_newlines() {
  local name
  for name in "$@"; do
    [[ ${report[$name]} != *$'\n,'* ]] || return 1
  done
}
assert 'sizes do not leave stat newlines inside JSON' no_raw_size_newlines "${case_names[@]}"

# Per-case and umbrella hashes cover the fixture tree.  The repository snapshot
# covers tracked and ignored paths under the repository root; empty HOME/TMPDIR
# sandboxes add likely outside targets. Together these are not a proof that no
# write can occur anywhere in general.
umbrella_after=$(tree_hash "$fixture")
assert 'nothing anywhere in the fixture tree changed across every scan' \
  bash -c '[[ $1 == "$2" ]]' _ "$umbrella_before" "$umbrella_after"
assert 'sandbox HOME stayed empty across every scan' \
  bash -c '[[ -z $(find "$1" -mindepth 1 -print -quit) ]]' _ "$sandbox_home"
assert 'sandbox TMPDIR stayed empty across every scan' \
  bash -c '[[ -z $(find "$1" -mindepth 1 -print -quit) ]]' _ "$sandbox_tmp"
if (( repo_is_git )); then
  repo_status_after=$(git -C "$repo" status --porcelain --ignored)
  assert 'repository git status is byte-identical across the whole suite' \
    bash -c '[[ $1 == "$2" ]]' _ "$repo_status_before" "$repo_status_after"
else
  printf 'SKIP repository git status check — %s is not a git repository\n' "$repo"
fi

printf 'RESULT %d passed, %d failed\n' "$passes" "$failures"
(( failures == 0 ))
