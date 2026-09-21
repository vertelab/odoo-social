# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
"""Repository-level guard: p-file sources must match their generated files.

This is the belt to the pre-commit hook's braces. Git does not distribute
hooks with a clone, so a fresh clone has no commit-time gate until
`make install-hooks` is run. This test runs wherever the module's tests run
(`checkmodule -t`, CI, a developer's `--test-enable`), so the rule is enforced
for everyone, not only for those who installed the hook.

The check itself lives in scripts/check_pfile_sync.py so it can also be run
standalone: `make check-pfiles`. See README, section "Filhantering: p-filer".
"""

import importlib.util
import os

from odoo.tests.common import BaseCase


def _load_checker(module_root):
    """Load scripts/check_pfile_sync.py by path.

    It is not a package module and must not be imported through Odoo's addon
    loader, so it is loaded directly from its file.
    """
    path = os.path.join(module_root, '..', 'scripts', 'check_pfile_sync.py')
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location('check_pfile_sync', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPfileSync(BaseCase):
    """A p-file and its generated branch file must not drift apart."""

    def setUp(self):
        super().setUp()
        # .../social_marketing/tests/ -> repo root is two levels up from tests
        self.module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.checker = _load_checker(self.module_root)

    def test_checker_is_present(self):
        """The gate script must exist; without it the rule is unenforced."""
        self.assertIsNotNone(
            self.checker,
            "scripts/check_pfile_sync.py is missing — the p-file sync gate "
            "cannot run. Do not remove it; see README.",
        )

    def test_repository_root_is_a_git_repo(self):
        """The checker needs git to enumerate tracked files."""
        root = self.checker.find_repo_root(self.module_root)
        self.assertIsNotNone(
            root,
            "Could not find a git repository above %s. The p-file check "
            "cannot enumerate tracked files." % self.module_root,
        )
        self.root = root

    def test_no_divergence(self):
        """Fail when a version-neutral p-file differs from its branch file.

        A p-file with preprocessor directives is expected to differ (each
        branch holds that version's evaluated result) and is not a failure.
        A p-file without directives preprocesses to itself, so any difference
        means one side was edited alone and the next regeneration will revert
        it.
        """
        root = self.checker.find_repo_root(self.module_root)
        if root is None:
            self.skipTest('not a git repository')

        pairs, divergences, orphans, version_specific = self.checker.check_repo(
            root, quiet=True)

        if divergences or orphans:
            lines = []
            for pfile, branch, _diff in divergences:
                lines.append(
                    '  %s has diverged from %s\n'
                    '    apply the change to BOTH files in the same commit'
                    % (pfile, branch))
            for pfile, branch in orphans:
                lines.append(
                    '  %s has no tracked generated file %s\n'
                    '    the generated file must be committed alongside it'
                    % (pfile, branch))
            self.fail(
                'p-file sync: %d divergence(s), %d orphan(s) in %s\n%s\n'
                'Run: make check-pfiles'
                % (len(divergences), len(orphans), root, '\n'.join(lines)))

        # Recorded for the log. Not an assertion: a repo may legitimately have
        # no version-specific p-files, as odoo-social does today.
        self.assertGreaterEqual(len(pairs), 0)
        self.assertGreaterEqual(version_specific, 0)
