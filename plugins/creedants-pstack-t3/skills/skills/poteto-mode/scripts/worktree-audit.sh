#!/usr/bin/env bash
# Read-only worktree prune audit for Linux and macOS. Classifies every git
# worktree by size, last commit age, last checkout activity, merge state,
# uncommitted work, upstream state, PR state, and whether T3 created it.
# Emits a table sorted by size with a suggested bucket. Never deletes anything;
# deletion stays a human-gated step in the playbook, and the playbook checks
# T3 thread bindings with T3's tools, which this script cannot see.
#
# Usage: worktree-audit.sh [repo-path] [--t3-worktrees DIR]
# Env:   TRUNK=<branch>     override the trunk branch (default: origin/HEAD, else main)
#        T3CODE_HOME=<dir>  T3 data dir, the variable T3's server reads (else ~/.t3)
#        T3_HOME=<dir>      data dir when T3CODE_HOME is unset
#        T3_WORKTREES=<dir> configured worktree directory for this run
#        RECENT_DAYS=<n>    activity window for verify-recent (default: 4)
# T3=yes when the worktree sits under <data dir>/worktrees, or under
# worktreesDirectory or previousWorktreesDirectories in
# <data dir>/userdata/settings.json. dev/settings.json is read only when
# T3CODE_HOME is unset and userdata/settings.json is absent. --t3-worktrees
# and T3_WORKTREES replace those settings roots, and the flag wins.
# An empty, relative, or filesystem-root value is ignored. The default
# directory still counts, matching T3's managed set.
# previousWorktreesDirectories counts only when it is an array of strings.
# T3CODE_HOME and each settings path are trimmed before ~ expansion.
# An existing directory is compared by its physical path. A filesystem root
# is ignored after that resolution, so a symlink to / matches nothing.
set -u

invoke_pwd=$(pwd)
repo=""
flag_root=""
while [ $# -gt 0 ]; do
	case "$1" in
		--t3-worktrees)
			shift
			if [ $# -eq 0 ] || [ -z "${1:-}" ]; then
				echo "worktree-audit: --t3-worktrees needs a directory" >&2
				exit 1
			fi
			flag_root="$1"
			;;
		--t3-worktrees=*)
			flag_root="${1#--t3-worktrees=}"
			if [ -z "$flag_root" ]; then
				echo "worktree-audit: --t3-worktrees needs a directory" >&2
				exit 1
			fi
			;;
		-*)
			echo "worktree-audit: unknown option $1" >&2
			exit 1
			;;
		*)
			if [ -n "$repo" ]; then
				echo "worktree-audit: unexpected argument $1" >&2
				exit 1
			fi
			repo="$1"
			;;
	esac
	shift
done

repo="${repo:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$repo" ] && { echo "not in a git repo; pass a repo path" >&2; exit 1; }
cd "$repo" || exit 1

expand_home() {
	case "$1" in
		"~") printf '%s\n' "$HOME" ;;
		"~/"*) printf '%s\n' "$HOME/${1#"~/"}" ;;
		*) printf '%s\n' "$1" ;;
	esac
}

# T3 trims the data dir and settings paths before it expands ~.
# JavaScript String.prototype.trim, as UTF-8 bytes. [:space:] follows the
# locale and keeps U+00A0 and U+FEFF. Python str.strip() keeps U+FEFF.
trim() {
	local s="$1" prev="" w
	while [ "$s" != "$prev" ]; do
		prev="$s"
		for w in \
			$'\t' $'\n' $'\v' $'\f' $'\r' ' ' \
			$'\xc2\xa0' \
			$'\xe1\x9a\x80' \
			$'\xe2\x80\x80' $'\xe2\x80\x81' $'\xe2\x80\x82' $'\xe2\x80\x83' \
			$'\xe2\x80\x84' $'\xe2\x80\x85' $'\xe2\x80\x86' $'\xe2\x80\x87' \
			$'\xe2\x80\x88' $'\xe2\x80\x89' $'\xe2\x80\x8a' \
			$'\xe2\x80\xa8' $'\xe2\x80\xa9' $'\xe2\x80\xaf' \
			$'\xe2\x81\x9f' \
			$'\xe3\x80\x80' \
			$'\xef\xbb\xbf'
		do
			s="${s#"$w"}"
			s="${s%"$w"}"
		done
	done
	printf '%s\n' "$s"
}

# Git records the physical path. cd -P and pwd -P are POSIX. realpath flags
# differ between GNU and BSD, so this does not call realpath. A missing leaf
# keeps the physical path of the ancestor that does exist.
physical_abs() {
	local path="$1" tail="" base
	[ -z "$path" ] && return 0
	if [ -d "$path" ] && base=$(cd -P -- "$path" && pwd -P); then
		printf '%s\n' "$base"
		return 0
	fi
	while [ "$path" != "/" ] && [ ! -d "$path" ]; do
		tail="/${path##*/}$tail"
		path="${path%/*}"
		[ -n "$path" ] || path="/"
	done
	if [ "$path" = "/" ]; then
		printf '/%s\n' "${tail#/}"
		return 0
	fi
	if base=$(cd -P -- "$path" && pwd -P); then
		printf '%s%s\n' "$base" "$tail"
		return 0
	fi
	printf '%s\n' "$1"
}

# Drop . and .. without resolving symlinks. A non-absolute input prints nothing.
normalize_abs() {
	local rest="$1" part acc=""
	case "$rest" in
		/*) ;;
		*) printf '\n'; return ;;
	esac
	rest="${rest#/}"
	while [ -n "$rest" ]; do
		part="${rest%%/*}"
		case "$rest" in
			*/*) rest="${rest#*/}" ;;
			*) rest="" ;;
		esac
		case "$part" in
			""|.) ;;
			..)
				case "$acc" in
					"") ;;
					*/*) acc="${acc%/*}" ;;
					*) acc="" ;;
				esac
				;;
			*)
				if [ -z "$acc" ]; then acc="$part"; else acc="$acc/$part"; fi
				;;
		esac
	done
	if [ -z "$acc" ]; then printf '/\n'; else printf '/%s\n' "$acc"; fi
}

# Empty, relative, or a filesystem root prints nothing. A root would mark
# every path on that drive as a T3 worktree.
resolve_worktrees_dir() {
	local raw expanded abs
	raw=$(trim "$1")
	[ -z "$raw" ] && return 0
	expanded=$(expand_home "$raw")
	case "$expanded" in
		/*) ;;
		*) return 0 ;;
	esac
	abs=$(normalize_abs "$expanded")
	[ -z "$abs" ] && return 0
	abs=$(physical_abs "$abs")
	[ -z "$abs" ] || [ "$abs" = "/" ] && return 0
	printf '%s\n' "$abs"
}

resolve_t3_home() {
	local raw expanded abs
	raw=$(trim "$1")
	[ -z "$raw" ] && return 0
	expanded=$(expand_home "$raw")
	case "$expanded" in
		/*) ;;
		*) expanded="$invoke_pwd/$expanded" ;;
	esac
	abs=$(normalize_abs "$expanded")
	[ -z "$abs" ] || [ "$abs" = "/" ] && return 0
	printf '%s\n' "$abs"
}

read_configured_dirs() {
	local file="$1" out
	if command -v jq >/dev/null 2>&1; then
		if out=$(jq -r '
			if type != "object" then error("settings are not an object") else
				(if (.worktreesDirectory | type) == "string" then .worktreesDirectory else empty end),
				(if (.previousWorktreesDirectories | type) == "array"
				 then .previousWorktreesDirectories[] | select(type == "string")
				 else empty end)
			end
		' "$file" 2>/dev/null); then
			printf '%s\n' "$out"
			return 0
		fi
		echo "warn: could not read $file; T3 worktree location unread" >&2
		return 0
	fi
	if command -v python3 >/dev/null 2>&1; then
		if out=$(python3 -c '
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
if not isinstance(data, dict):
    sys.exit(1)
current = data.get("worktreesDirectory") or ""
if isinstance(current, str):
    print(current)
previous = data.get("previousWorktreesDirectories") or []
if isinstance(previous, list):
    for item in previous:
        if isinstance(item, str):
            print(item)
' "$file" 2>/dev/null); then
			printf '%s\n' "$out"
			return 0
		fi
		echo "warn: could not read $file; T3 worktree location unread" >&2
		return 0
	fi
	echo "warn: jq and python3 missing; T3 worktree location unread" >&2
}

# A blank T3CODE_HOME is unset. T3's resolveBaseDir trims first, and an empty
# result uses the default data dir rather than a padded path.
t3_home=""
if [ -n "$(trim "${T3CODE_HOME:-}")" ]; then
	t3_home=$(resolve_t3_home "$T3CODE_HOME")
elif [ -n "$(trim "${T3_HOME:-}")" ]; then
	t3_home=$(resolve_t3_home "$T3_HOME")
else
	t3_home=$(resolve_t3_home "$HOME/.t3")
fi
if [ -z "$t3_home" ]; then
	echo "worktree-audit: T3 data dir is not a usable path" >&2
	exit 1
fi

t3_roots=""
add_root() {
	local dir
	dir=$(resolve_worktrees_dir "$1")
	[ -z "$dir" ] && return 0
	case "
$t3_roots
" in
		*"
$dir
"*) return 0 ;;
	esac
	if [ -z "$t3_roots" ]; then t3_roots="$dir"; else t3_roots="$t3_roots
$dir"; fi
}

add_root "$t3_home/worktrees"
if [ -n "$flag_root" ] || [ -n "${T3_WORKTREES:-}" ]; then
	add_root "${flag_root:-$T3_WORKTREES}"
else
	settings=""
	if [ -f "$t3_home/userdata/settings.json" ]; then
		settings="$t3_home/userdata/settings.json"
	elif [ -z "${T3CODE_HOME:-}" ] && [ -f "$t3_home/dev/settings.json" ]; then
		settings="$t3_home/dev/settings.json"
	fi
	if [ -n "$settings" ]; then
		configured=$(read_configured_dirs "$settings") || true
		if [ -n "$configured" ]; then
			while IFS= read -r line; do
				add_root "$line"
			done <<EOF
$configured
EOF
		fi
	fi
fi

recent_days="${RECENT_DAYS:-4}"
now=$(date +%s)

# Epoch seconds to YYYY-MM-DD. GNU date takes -d @N, BSD date takes -r N.
fmt_day() {
	date -d "@$1" '+%Y-%m-%d' 2>/dev/null || date -r "$1" '+%Y-%m-%d' 2>/dev/null || echo "?"
}

# Kilobytes to a short human size. du -sk is the same on GNU and BSD.
human() {
	awk -v k="$1" 'BEGIN {
		split("K M G T", u, " "); i = 1
		while (k >= 1024 && i < 4) { k /= 1024; i++ }
		printf (k < 10 && i > 1) ? "%.1f%s" : "%d%s", k, u[i]
	}'
}

# Main worktree is the first entry; everything else is a candidate.
main_wt=$(git worktree list --porcelain | sed -n 's/^worktree //p' | head -1)

trunk="${TRUNK:-$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')}"
trunk="${trunk:-main}"

# origin/<trunk> drives the merge check. Best-effort; stale is fine for a first pass.
git fetch origin "$trunk" --quiet 2>/dev/null \
	|| echo "warn: could not fetch origin/$trunk; MERGED may be stale" >&2
git rev-parse --verify --quiet "origin/$trunk" >/dev/null \
	|| echo "warn: origin/$trunk does not exist; MERGED shows ?" >&2

# PR state by branch, fetched once. Empty if gh or jq is unavailable.
prs=$(mktemp)
trap 'rm -f "$prs"' EXIT
if command -v gh >/dev/null && command -v jq >/dev/null; then
	gh pr list --author "@me" --state all --limit 1000 \
		--json number,state,headRefName 2>/dev/null > "$prs" || echo "[]" > "$prs"
else
	echo "warn: gh or jq missing; PR shows -" >&2
	echo "[]" > "$prs"
fi

printf "SIZE\tAGE\tACTIVE\tMERGED\tDIRTY\tREMOTE\tPR\tT3\tBUCKET\tWORKTREE\n"

# Paths are read whole, so a worktree path with spaces survives.
git worktree list --porcelain | sed -n 's/^worktree //p' | while IFS= read -r wt; do
	[ "$wt" = "$main_wt" ] && continue

	t3=no
	wt_abs=$(normalize_abs "$wt")
	[ -n "$wt_abs" ] || wt_abs="$wt"
	phys=$(physical_abs "$wt_abs")
	[ -n "$phys" ] && wt_abs="$phys"
	while IFS= read -r root; do
		[ -z "$root" ] && continue
		case "$wt_abs" in
			"$root"|"$root"/*) t3=yes; break ;;
		esac
	done <<EOF
$t3_roots
EOF

	# A registered worktree whose directory is gone is metadata only.
	if [ ! -d "$wt" ]; then
		printf "0\t-\t-\t-\t-\t-\t-\t%s\tprunable-missing\t%s\n" "$t3" "$wt"
		continue
	fi

	size_kb=$(du -sk "$wt" 2>/dev/null | awk '{print $1}')
	size_kb="${size_kb:-0}"
	head=$(git -C "$wt" rev-parse HEAD 2>/dev/null)
	head_ts=$(git -C "$wt" log -1 --format='%ct' HEAD 2>/dev/null)
	age=$([ -n "$head_ts" ] && echo "$(( (now - head_ts) / 86400 ))d" || echo "?")

	# Newest HEAD reflog entry: the last commit, checkout, reset, or rebase in
	# this worktree. Catches a worktree in use whose commits are old.
	active_ts=$(git -C "$wt" reflog -1 --format='%ct' HEAD 2>/dev/null)
	active_ts="${active_ts:-${head_ts:-0}}"
	active=$([ "$active_ts" -gt 0 ] && fmt_day "$active_ts" || echo "?")
	recent=no
	[ "$active_ts" -gt 0 ] && [ $(( (now - active_ts) / 86400 )) -le "$recent_days" ] && recent=yes

	# Squash-merged branches are not ancestors of trunk, so PR state is the
	# real signal; merge-base only catches fast-forward/rebase merges.
	if ! git rev-parse --verify --quiet "origin/$trunk" >/dev/null; then merged="?"
	elif git merge-base --is-ancestor "$head" "origin/$trunk" 2>/dev/null; then merged=YES
	else merged=no; fi

	# Distinguish real WIP (tracked edits) from disposable untracked scratch.
	porcelain=$(git -C "$wt" status --porcelain 2>/dev/null)
	if [ -z "$porcelain" ]; then dirty=clean
	elif printf '%s\n' "$porcelain" | grep -qv '^??'; then
		dirty="wip:$(printf '%s\n' "$porcelain" | grep -cv '^??')"
	else dirty="scratch:$(printf '%s\n' "$porcelain" | grep -c '^??')"; fi

	# Compare against the configured upstream, else origin/<branch>.
	branch=$(git -C "$wt" symbolic-ref --quiet --short HEAD 2>/dev/null || echo "")
	if [ -z "$branch" ]; then remote=detached
	else
		upstream=$(git -C "$wt" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null)
		if [ -z "$upstream" ] && git -C "$wt" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
			upstream="origin/$branch"
		fi
		if [ -z "$upstream" ]; then remote=no-remote
		elif [ "$(git -C "$wt" rev-parse "$upstream" 2>/dev/null)" = "$head" ]; then remote=pushed
		else remote="ahead$(git -C "$wt" rev-list --count "$upstream..HEAD" 2>/dev/null)"; fi
	fi

	pr=""
	[ -n "$branch" ] && pr=$(jq -r --arg b "$branch" \
		'.[] | select(.headRefName==$b) | "#\(.number)/\(.state)"' "$prs" 2>/dev/null | head -1)
	[ -z "$pr" ] && pr="-"

	case "$dirty" in wip:*) bucket=hold-wip ;; *)
		case "$pr" in *OPEN*) bucket=hold-open-pr ;; *)
			if [ "$recent" = yes ]; then bucket=verify-recent
			elif [ "$merged" = YES ] || [ "$pr" != "-" ]; then bucket=safe
			else bucket=review; fi ;;
		esac ;;
	esac

	printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
		"$size_kb" "$age" "$active" "$merged" "$dirty" "$remote" "$pr" "$t3" "$bucket" "$wt"
done | sort -t "$(printf '\t')" -k1,1nr | while IFS="$(printf '\t')" read -r kb rest; do
	printf "%s\t%s\n" "$(human "$kb")" "$rest"
done
