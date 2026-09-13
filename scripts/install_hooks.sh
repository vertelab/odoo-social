#!/usr/bin/env bash
# Install the p-file sync guard into .git/hooks for this repository.
#
# The guard lives in scripts/git-hooks/ so it is version-controlled and
# reviewable, but git only executes hooks from .git/hooks. This script copies
# it into place. Run it once per clone:
#
#   scripts/install_hooks.sh
#
# Note: git hooks are not distributed with a clone, so a fresh clone has no
# guard until this script is run. That is why the same check also runs from
# `make check-pfiles` and in the test suite: the hook catches the mistake at
# commit time for people who installed it, and the repository-level check
# catches it for everyone else.

set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
hook_src="$repo_root/scripts/git-hooks/pre-commit"
hook_dst="$repo_root/.git/hooks/pre-commit"

if [ ! -f "$hook_src" ]; then
    echo "ERROR: $hook_src not found" >&2
    exit 1
fi

if [ -f "$hook_dst" ] && ! grep -q "Vertel p-file sync guard" "$hook_dst" 2>/dev/null; then
    backup="$hook_dst.pre-pfile-sync.$(date +%Y%m%d-%H%M%S)"
    cp "$hook_dst" "$backup"
    echo "Existing pre-commit hook backed up to $backup"
fi

install -m 0755 "$hook_src" "$hook_dst"
echo "Installed p-file sync guard: $hook_dst"

# Verify it is executable and runs.
if "$hook_dst" >/dev/null 2>&1; then
    echo "Hook executes cleanly."
else
    # A non-zero exit here just means divergence already exists; that is the
    # hook working, not the install failing.
    echo "Hook executes (reported existing divergence — run scripts/check_pfile_sync.py for details)."
fi
