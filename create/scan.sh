#!/usr/bin/env bash
# Read-only router-document scanner.  It intentionally has no write operations.
set -euo pipefail

if (( $# != 1 )); then
  printf 'usage: %s <directory>\n' "${0##*/}" >&2
  exit 2
fi

if [[ ! -e $1 || ! -d $1 ]]; then
  printf '%s: not an existing directory: %s\n' "${0##*/}" "$1" >&2
  exit 2
fi

# `realpath -z` plus `read -d ''` is deliberate: command substitution strips
# every trailing newline, including a newline that is part of a legal pathname.
realpath_into() {
  local -n destination=$1
  IFS= read -r -d '' destination < <(realpath -z -- "$2")
}

# git writes a newline terminator, so retain every pathname byte and remove only
# that terminator before resolving it through the NUL-delimited helper above.
git_toplevel_into() {
  local -n destination=$1
  local reported
  IFS= read -r -d '' reported < <(git --no-optional-locks -C "$2" rev-parse --show-toplevel 2>/dev/null && printf '\0') || return 1
  reported=${reported%$'\n'}
  realpath_into "$1" "$reported"
}

valid_utf8() {
  printf '%s' "$1" | iconv -f UTF-8 -t UTF-8 >/dev/null 2>&1
}

if ! realpath_into target "$1"; then
  printf '%s: could not resolve directory: %s\n' "${0##*/}" "$1" >&2
  exit 2
fi
if ! valid_utf8 "$target"; then
  printf '%s: target path is not valid UTF-8\n' "${0##*/}" >&2
  exit 2
fi

# Print a shell string as a JSON string.  Work byte-wise so every JSON control
# character is escaped.  A malformed UTF-8 byte becomes a visible U+FFFD marker
# followed by its hex, which keeps JSON parseable and keeps one bad byte distinct
# from another.  It is deliberately **not** injective against all input: U+FFFD is
# ordinary valid UTF-8, so a file containing it literally renders the same way.
# That is why a candidate whose *headings* carry such bytes is flagged in its
# directory's notes rather than the rendering being trusted to tell two apart.
#
# One byte never reaches here: bash cannot hold NUL in a variable, so it is gone
# before any string is passed in.  A candidate file containing NUL is detected
# separately, against the file, and reported in that directory's notes.
# A heading list is a human-readable summary, not a byte-faithful channel. Two
# files whose headings carry bytes that cannot be represented can render alike, so
# the report says so rather than implying the headings distinguish them.
#
# NUL is the exception to the heading-only scope, and it is checked against the
# whole file: bash drops it from any variable, so it never reaches a rendering that
# could report it. Malformed UTF-8 is reported by the serializer itself, per
# heading, in emit_headings.
file_has_nul() {
  [[ -f $1 ]] || return 1
  ! cmp -s "$1" <(tr -d '\000' < "$1")
}

# The flag comes from the serializer itself, reported alongside the rendering, not
# inferred from it.  An independent validity predicate drifts -- glibc's iconv
# accepts sequences above U+10FFFF that the serializer correctly replaces -- and
# sniffing the rendered text is worse, because JSON escaping of a literal backslash
# produces the same characters and ordinary Markdown mentioning \ufffd false-fires.
#
# The claim is scoped to the **heading list**, which is what the report carries. A
# malformed byte elsewhere in the file changes nothing the report says: sizes are
# byte counts, the diff line count is computed by diff itself, and neither is
# affected. Flagging it would be reporting something the reader cannot act on.

# Set by json_string when it replaces a byte.  The caller resets it and reads it
# afterwards; sniffing the rendered text for the marker does not work, because JSON
# escaping of a literal backslash produces the same characters.
json_string_replaced=0

json_string() {
  local value=$1 char code escaped='' i length next second third
  local valid_sequence
  local LC_ALL=C

  # The serializer is the choke point for every string emitted in the report.
  # Preserve valid multi-byte UTF-8 sequences, but render each malformed byte
  # as a diagnostic \xHH placeholder rather than putting it in JSON verbatim.
  length=${#value}
  for ((i = 0; i < ${#value}; i++)); do
    char=${value:i:1}
    printf -v code '%d' "'$char"

    valid_sequence=0
    if (( code >= 194 && code <= 223 && i + 1 < length )); then
      printf -v next '%d' "'${value:i + 1:1}"
      (( next >= 128 && next <= 191 )) && valid_sequence=2
    elif (( code == 224 && i + 2 < length )); then
      printf -v next '%d' "'${value:i + 1:1}"
      printf -v second '%d' "'${value:i + 2:1}"
      (( next >= 160 && next <= 191 && second >= 128 && second <= 191 )) && valid_sequence=3
    elif (( (code >= 225 && code <= 236 || code >= 238 && code <= 239) && i + 2 < length )); then
      printf -v next '%d' "'${value:i + 1:1}"
      printf -v second '%d' "'${value:i + 2:1}"
      (( next >= 128 && next <= 191 && second >= 128 && second <= 191 )) && valid_sequence=3
    elif (( code == 237 && i + 2 < length )); then
      printf -v next '%d' "'${value:i + 1:1}"
      printf -v second '%d' "'${value:i + 2:1}"
      (( next >= 128 && next <= 159 && second >= 128 && second <= 191 )) && valid_sequence=3
    elif (( code == 240 && i + 3 < length )); then
      printf -v next '%d' "'${value:i + 1:1}"
      printf -v second '%d' "'${value:i + 2:1}"
      printf -v third '%d' "'${value:i + 3:1}"
      (( next >= 144 && next <= 191 && second >= 128 && second <= 191 && third >= 128 && third <= 191 )) && valid_sequence=4
    elif (( (code >= 241 && code <= 243) && i + 3 < length )); then
      printf -v next '%d' "'${value:i + 1:1}"
      printf -v second '%d' "'${value:i + 2:1}"
      printf -v third '%d' "'${value:i + 3:1}"
      (( next >= 128 && next <= 191 && second >= 128 && second <= 191 && third >= 128 && third <= 191 )) && valid_sequence=4
    elif (( code == 244 && i + 3 < length )); then
      printf -v next '%d' "'${value:i + 1:1}"
      printf -v second '%d' "'${value:i + 2:1}"
      printf -v third '%d' "'${value:i + 3:1}"
      (( next >= 128 && next <= 143 && second >= 128 && second <= 191 && third >= 128 && third <= 191 )) && valid_sequence=4
    fi

    if (( code >= 128 && ! valid_sequence )); then
      # U+FFFD, then the byte in hex.  This keeps one bad byte distinct from
      # another and avoids the earlier collision with text spelling out \xff.  It
      # is **not** injective against all input -- U+FFFD is ordinary valid UTF-8,
      # so a file containing it renders the same way.  That is accepted under
      # decision 53; the directory's notes carry the flag that tells them apart.
      json_string_replaced=1
      escaped+='\ufffd'
      printf -v char '%02x' "$code"
      escaped+=$char
      continue
    fi

    case $char in
      '"') escaped+='\"' ;;
      \\) escaped+='\\' ;;
      $'\b') escaped+='\b' ;;
      $'\t') escaped+='\t' ;;
      $'\n') escaped+='\n' ;;
      $'\f') escaped+='\f' ;;
      $'\r') escaped+='\r' ;;
      *)
        if (( code < 32 )); then
          printf -v hex '%04x' "$code"
          escaped+="\\u$hex"
        else
          escaped+=$char
        fi
        ;;
    esac

    if (( valid_sequence )); then
      for ((next = 1; next < valid_sequence; next++)); do
        escaped+=${value:i + next:1}
      done
      i=$((i + valid_sequence - 1))
    fi
  done
  printf '"%s"' "$escaped"
}

json_array_strings() {
  local first=1 value
  printf '['
  for value in "$@"; do
    (( first )) || printf ','
    json_string "$value"
    first=0
  done
  printf ']'
}

relative_to_target() {
  local path=$1
  if [[ $path == "$target" ]]; then
    printf '.'
  elif [[ $path == "$target"/* ]]; then
    printf '%s' "${path#"$target"/}"
  else
    printf '%s' "$path"
  fi
}

inside_target() {
  [[ $1 == "$target" || $1 == "$target"/* ]]
}

git_toplevel=''
if git_toplevel_into git_toplevel "$target"; then
  :
else
  # A refusal is still useful JSON.  Only immediate child directories can be
  # repositories or worktree hubs for this report.
  repositories=()
  hubs_json=()
  shopt -s nullglob dotglob
  for child in "$target"/*; do
    [[ -d $child ]] || continue
    base=${child##*/}
    [[ $base == . || $base == .. ]] && continue
    realpath_into child_real "$child"
    child_top=''
    if git_toplevel_into child_top "$child" && [[ $child_top == "$child_real" ]]; then
      repositories+=("$base")
    fi
    if [[ -e $child/.repo.git || -L $child/.repo.git ]]; then
      lanes=()
      for lane in "$child"/*; do
        [[ -d $lane ]] || continue
        lane_base=${lane##*/}
        [[ $lane_base == . || $lane_base == .. || $lane_base == .repo.git || $lane_base == .* ]] && continue
        lanes+=("$lane_base")
      done
      hub_entry=$(printf '{"path":'; json_string "$base"; printf ',"lanes":'; json_array_strings "${lanes[@]}"; printf '}')
      hubs_json+=("$hub_entry")
    fi
  done
  shopt -u nullglob dotglob

  printf '{"target":'
  json_string "$target"
  printf ',"gitToplevel":null,"ok":false,"refusal":{"reason":"target is not inside a git repository","repositories":'
  json_array_strings "${repositories[@]}"
  printf ',"hubs":['
  for ((i = 0; i < ${#hubs_json[@]}; i++)); do
    (( i == 0 )) || printf ','
    printf '%s' "${hubs_json[i]}"
  done
  printf ']},"directories":[],"excluded":[]}\n'
  exit 1
fi

directories_json=''
excluded_json=''

# Prints "<0|1> <json-array>": whether any heading needed a byte replaced, then
# the array itself.  The flag is reported rather than inferred from the text.
emit_headings() {
  local file=$1 line first=1 body
  json_string_replaced=0
  body=$(
    printf '['
    while IFS= read -r line || [[ -n $line ]]; do
      if [[ $line =~ ^#{1,6}\  ]]; then
        (( first )) || printf ','
        json_string "$line"
        first=0
      fi
    done < "$file"
    printf ']'
    printf '\034%s' "$json_string_replaced"
  )
  printf '%s %s' "${body##*$'\034'}" "${body%$'\034'*}"
}

emit_directory() {
  local dir=$1 rel candidate name resolved='' broken outside=0 skip='' first=1 n rendered
  local -a names=() resolves=() broken_flags=() outside_flags=() headings_json=()
  local -A seen=()
  local real_count=0 identical=false diff_lines=null write_target=null
  local -a unmanaged=() notes=()

  rel=$(relative_to_target "$dir")
  for name in AGENTS.md CLAUDE.md; do
    candidate=$dir/$name
    [[ -e $candidate || -L $candidate ]] || continue
    names+=("$name")
    resolved=''
    broken=false
    outside=false
    if [[ -L $candidate && ! -f $candidate ]]; then
      broken=true
      skip=${skip:-"$name is a broken symlink"}
    elif realpath_into resolved "$candidate" 2>/dev/null && [[ -f $resolved ]]; then
      if ! inside_target "$resolved"; then
        outside=true
        skip=${skip:-"$name resolves outside target"}
      fi
      if [[ -z ${seen[$resolved]+yes} ]]; then
        seen[$resolved]=1
        resolves+=("$resolved")
      fi
    else
      broken=true
      [[ -L $candidate ]] && skip=${skip:-"$name is a broken symlink"}
    fi
    broken_flags+=("$broken")
    outside_flags+=("$outside")
  done
  real_count=${#resolves[@]}

  for name in GEMINI.md .cursorrules; do
    [[ -e $dir/$name || -L $dir/$name ]] && unmanaged+=("$name")
  done

  # Do not read an external link target.  Resolution is enough to identify the
  # unsafe condition, and the directory is skipped before any possible write.
  if [[ -z $skip && $real_count -eq 1 ]]; then
    write_target=$(relative_to_target "${resolves[0]}")
  elif [[ -z $skip && $real_count -eq 2 ]]; then
    if cmp -s "${resolves[0]}" "${resolves[1]}"; then
      identical=true
      notes+=("two byte-identical routing files — duplicate, consolidate")
      diff_lines=0
    else
      identical=false
      diff_lines=0
      while IFS= read -r line || [[ -n $line ]]; do
        [[ $line == +++* || $line == ---* ]] && continue
        [[ $line == +* || $line == -* ]] && diff_lines=$((diff_lines + 1))
      done < <(diff -u "${resolves[0]}" "${resolves[1]}" || true)
      notes+=("two real routing files differ — the prompt must propose which is the router")
    fi
  fi
  # Only for a candidate that resolves inside the target and is not broken.  The
  # no-read rule above governs this too: an external link target is never opened,
  # so its contents are never disclosed in the report.
  for ((n = 0; n < ${#names[@]}; n++)); do
    headings_json[n]=''
    [[ ${broken_flags[n]} == true || ${outside_flags[n]} == true ]] && continue
    realpath_into resolved "$dir/${names[n]}"
    rendered=$(emit_headings "$resolved")
    headings_json[n]=${rendered#* }
    if file_has_nul "$dir/${names[n]}"; then
      notes+=("${names[n]} contains NUL bytes; its heading list is incomplete")
    fi
    if [[ ${rendered%% *} == 1 ]]; then
      notes+=("${names[n]} has headings carrying bytes that could not be represented; its heading list is unreliable and may not distinguish it from another such file")
    fi
  done
  [[ -n $skip ]] && notes+=("$skip")

  printf '{"path":'
  json_string "$rel"
  printf ',"candidates":['
  for ((i = 0; i < ${#names[@]}; i++)); do
    (( i == 0 )) || printf ','
    name=${names[i]}
    candidate=$dir/$name
    printf '{"name":'
    json_string "$name"
    printf ',"isSymlink":%s,"resolves":' "$([[ -L $candidate ]] && printf true || printf false)"
    if [[ ${broken_flags[i]} == true ]]; then
      printf 'null'
    else
      realpath_into resolved "$candidate"
      json_string "$(relative_to_target "$resolved")"
    fi
    printf ',"broken":%s,"resolvesOutsideTarget":%s,"size":' "${broken_flags[i]}" "${outside_flags[i]}"
    if [[ ${broken_flags[i]} == true || ${outside_flags[i]} == true ]]; then
      printf 'null'
    else
      realpath_into resolved "$candidate"
      size=$(stat -c %s "$resolved")
      printf '%s' "$size"
    fi
    printf ',"headings":'
    if [[ ${broken_flags[i]} == true || ${outside_flags[i]} == true ]]; then
      printf '[]'
    else
      printf '%s' "${headings_json[i]}"
    fi
    printf '}'
  done
  printf '],"realCount":%d,"writeTarget":' "$real_count"
  if [[ $write_target == null ]]; then printf 'null'; else json_string "$write_target"; fi
  printf ',"identical":%s,"diffLines":' "$identical"
  [[ $diff_lines == null ]] && printf null || printf '%s' "$diff_lines"
  printf ',"skipped":'
  [[ -n $skip ]] && json_string "$skip" || printf null
  printf ',"unmanagedSurfaces":'
  json_array_strings "${unmanaged[@]}"
  printf ',"notes":'
  json_array_strings "${notes[@]}"
  printf '}'
}

emit_excluded() {
  local dir=$1 reason=$2
  printf '{"path":'
  json_string "$(relative_to_target "$dir")"
  printf ',"reason":'
  json_string "$reason"
  printf '}'
}

walk() {
  local dir=$1 child base child_top entry
  entry=$(emit_directory "$dir")
  if [[ -n $directories_json ]]; then directories_json+=','; fi
  directories_json+=$entry
  shopt -s nullglob dotglob
  for child in "$dir"/*; do
    [[ -L $child || -d $child ]] || continue
    base=${child##*/}
    [[ $base == . || $base == .. ]] && continue
    if git --no-optional-locks -C "$target" check-ignore -q -- "$child" 2>/dev/null; then
      entry=$(emit_excluded "$child" git-ignored)
      if [[ -n $excluded_json ]]; then excluded_json+=','; fi
      excluded_json+=$entry
    elif [[ $base == .* ]]; then
      entry=$(emit_excluded "$child" dotted)
      if [[ -n $excluded_json ]]; then excluded_json+=','; fi
      excluded_json+=$entry
    elif ! valid_utf8 "$child"; then
      entry=$(emit_excluded "$child" 'path is not valid UTF-8')
      if [[ -n $excluded_json ]]; then excluded_json+=','; fi
      excluded_json+=$entry
    elif [[ -L $child && -d $child ]]; then
      entry=$(emit_excluded "$child" 'directory symlink')
      if [[ -n $excluded_json ]]; then excluded_json+=','; fi
      excluded_json+=$entry
    elif git_toplevel_into child_top "$child" && [[ $child_top != "$git_toplevel" ]]; then
      entry=$(emit_excluded "$child" 'nested repository')
      if [[ -n $excluded_json ]]; then excluded_json+=','; fi
      excluded_json+=$entry
    else
      walk "$child"
    fi
  done
  shopt -u nullglob dotglob
}

printf '{"target":'
json_string "$target"
printf ',"gitToplevel":'
json_string "$git_toplevel"
printf ',"ok":true,"refusal":null,"directories":['
walk "$target"
printf '%s],"excluded":[%s]}' "$directories_json" "$excluded_json"
printf '\n'
