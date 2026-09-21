#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
"""Check that p-file sources stay consistent with their generated branch files.

Under the parallel-development p-file methodology a `*.p.<ext>` file is the
source of truth for a branch file (`*.<ext>`), and `odoobranchpfile` /
`preprocess` regenerate the branch file FROM the p-file. If a change is made
to only the generated file, the next regeneration silently reverts it. That
has happened three times in odoo-social (0d4f797, 886962f, and again in the
worktree that became 18cdd73), so the rule needs a check rather than a habit.

Rule enforced, and it is deliberately narrow:

* A p-file that contains NO preprocessor directive is version-neutral: every
  branch preprocesses it to itself. It must therefore be byte-identical to its
  generated branch file. If they differ, someone edited one side only and the
  next regeneration will silently revert that edit. This is the defect class
  that hit odoo-social three times.

* A p-file that DOES contain directives (# #if / # #elif / # #else / # #endif)
  legitimately differs from every single branch file, because each branch is
  the evaluated result for that version. Divergence there is expected, not a
  defect, and is reported as version-specific rather than as a failure.

Usage:
    check_pfile_sync.py [--repo PATH]... [--pairs] [--quiet]

Exit codes:
    0 — no divergence
    1 — divergence found (details on stdout)
    2 — usage or environment error
"""

import argparse
import os
import re
import subprocess
import sys

# Extensions we treat as p-file sources. Add here if new ones appear.
P_EXTENSIONS = ('py', 'xml', 'js', 'css', 'scss', 'csv')

# The preprocessor directive syntax used by the Vertel p-file methodology.
# Matches "# #if VERSION >= '18.0'", "# #elif", "# #else", "# #endif" and
# the comment-flavoured forms used inside XML/JS.
DIRECTIVE_RE = re.compile(
    r'^\s*(?:#|<!--|//)\s*#\s*(?:if|elif|else|endif)\b',
)


def find_repo_root(start):
    """Return the git top-level for start, or None."""
    try:
        out = subprocess.run(
            ['git', '-C', start, 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def tracked_files(repo):
    """Return tracked files at the index, relative to repo root."""
    out = subprocess.run(
        ['git', '-C', repo, 'ls-files'],
        capture_output=True, text=True, check=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def pfile_pairs(files):
    """Yield (pfile, branchfile) for every tracked p-file whose partner exists.

    A p-file whose generated partner is absent is reported separately by
    orphaned_pfiles(): the partner is the build artefact and is expected to be
    committed, so its absence is its own defect.
    """
    index = set(files)
    for path in sorted(files):
        for ext in P_EXTENSIONS:
            suffix = '.p.' + ext
            if path.endswith(suffix):
                branch = path[: -len(suffix)] + '.' + ext
                if branch in index:
                    yield path, branch
                break


def orphaned_pfiles(files):
    """Return p-files whose generated branch file is not tracked."""
    index = set(files)
    orphans = []
    for path in sorted(files):
        for ext in P_EXTENSIONS:
            suffix = '.p.' + ext
            if path.endswith(suffix):
                branch = path[: -len(suffix)] + '.' + ext
                if branch not in index:
                    orphans.append((path, branch))
                break
    return orphans


def read_text(path):
    with open(path, 'rb') as handle:
        return handle.read()


def has_directives(path):
    """True if the p-file contains preprocessor directives.

    A p-file with directives is expected to differ from its branch file (each
    branch holds that version's evaluated result), so it is checked for
    presence only. A p-file without directives must equal its branch file.
    """
    with open(path, 'r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            if DIRECTIVE_RE.match(line):
                return True
    return False


def diverging_lines(pfile_bytes, branch_bytes, limit=12):
    """Return a short unified diff, bounded so output stays readable."""
    import difflib

    p_lines = pfile_bytes.decode('utf-8', 'replace').splitlines(keepends=True)
    b_lines = branch_bytes.decode('utf-8', 'replace').splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        p_lines, b_lines,
        fromfile='p-file (source of truth)',
        tofile='generated branch file',
        n=2,
    ))
    if len(diff) > limit + 4:
        diff = diff[:limit + 4] + ['  ... (truncated)\n']
    return ''.join(diff)


def check_repo(repo, quiet=False):
    """Check one repository.

    Returns (n_pairs, divergences, orphans, version_specific) where
    version_specific counts p-files that carry directives and therefore are
    expected to differ from their branch file.
    """
    try:
        files = tracked_files(repo)
    except subprocess.CalledProcessError as exc:
        print('ERROR: cannot list files in %s: %s' % (repo, exc), file=sys.stderr)
        raise SystemExit(2)

    pairs = list(pfile_pairs(files))
    divergences = []
    version_specific = 0

    for pfile, branch in pairs:
        p_path = os.path.join(repo, pfile)
        p_bytes = read_text(p_path)
        b_bytes = read_text(os.path.join(repo, branch))
        if p_bytes == b_bytes:
            continue
        if has_directives(p_path):
            # Expected: the branch file is this version's evaluated result.
            version_specific += 1
            continue
        divergences.append((pfile, branch, diverging_lines(p_bytes, b_bytes)))

    orphans = orphaned_pfiles(files)

    if not quiet:
        name = os.path.basename(repo)
        if not pairs and not orphans:
            print('  %-24s no p-files' % name)
        else:
            status = 'OK' if not divergences and not orphans else 'DIVERGENCE'
            notes = []
            if version_specific:
                notes.append('%d version-specific' % version_specific)
            if orphans:
                notes.append('%d orphan(s)' % len(orphans))
            print('  %-24s %-11s %d pair(s)%s' % (
                name, status, len(pairs),
                ', ' + ', '.join(notes) if notes else '',
            ))

    for pfile, branch, diff in divergences:
        print('')
        print('DIVERGENCE in %s' % repo)
        print('  p-file (source of truth): %s' % pfile)
        print('  generated branch file:    %s' % branch)
        print('  The next regeneration of %s would overwrite it with the' % branch)
        print('  contents of %s, losing these lines.' % pfile)
        print('')
        for line in diff.rstrip('\n').split('\n'):
            print('      ' + line)

    for pfile, branch in orphans:
        print('')
        print('ORPHAN p-file in %s' % repo)
        print('  p-file:                 %s' % pfile)
        print('  generated branch file:  %s (not tracked)' % branch)
        print('  The generated file is a build artefact that must be committed')
        print('  alongside its p-file, otherwise the pair regenerates to nothing.')

    return len(pairs), divergences, orphans, version_specific


def default_repos():
    """Repo to check when none is given: the one containing this script.

    Defaulting to the enclosing repository keeps `make check-pfiles` and the
    pre-commit hook self-contained: a commit in one repository never fails
    because of unrelated drift in another. Pass --repo (repeatable) to check
    more than one, e.g. to survey odoo-base from here.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = find_repo_root(here)
    if root is not None:
        return [root]

    # Fall back to the historical survey targets if we are not in a repo.
    candidates = ['/usr/share/odoo-social', '/usr/share/odoo-base']
    return [path for path in candidates if os.path.isdir(path)]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Check p-file sources against their generated branch files.',
    )
    parser.add_argument('--repo', action='append', default=None,
                        help='repository to check (repeatable); '
                             'defaults to odoo-social and odoo-base')
    parser.add_argument('--pairs', action='store_true',
                        help='list every pair checked, not just problems')
    parser.add_argument('--quiet', action='store_true',
                        help='only report problems')
    args = parser.parse_args(argv)

    repos = args.repo or default_repos()
    if not repos:
        print('ERROR: no repositories given and no default found', file=sys.stderr)
        return 2

    print('p-file sync check')
    print('=' * 72)

    total_pairs = 0
    total_divergences = []
    total_orphans = []
    total_version_specific = 0

    if args.pairs:
        for repo in repos:
            root = find_repo_root(repo) or repo
            for pfile, branch in pfile_pairs(tracked_files(root)):
                print('  pair  %s:%s -> %s' % (os.path.basename(root), pfile, branch))
        print('')

    for repo in repos:
        root = find_repo_root(repo)
        if root is None:
            print('ERROR: %s is not a git repository' % repo, file=sys.stderr)
            return 2
        pairs, divergences, orphans, version_specific = check_repo(
            root, quiet=args.quiet)
        total_pairs += pairs
        total_divergences.extend(divergences)
        total_orphans.extend(orphans)
        total_version_specific += version_specific

    print('')
    if not total_divergences and not total_orphans:
        extra = (', %d version-specific pair(s) skipped (p-file has directives)'
                 % total_version_specific) if total_version_specific else ''
        print('OK — %d p-file pair(s) in sync across %d repo(s)%s.'
              % (total_pairs, len(repos), extra))
        return 0

    print('FAILED — %d divergence(s), %d orphan(s) across %d pair(s).'
          % (len(total_divergences), len(total_orphans), total_pairs))
    print('')
    print('Fix: apply the change to the p-file AND its generated branch file in')
    print('the same commit, then re-run this check. Do not delete p-files —')
    print('they are the per-branch source of truth.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
