#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
"""Check that the Fabric version used by the render service matches the
Fabric bundle shipped for the editor.

Editor and render service must run the same Fabric version: scene JSON is
produced by the editor's Fabric and consumed by the service's
``loadFromJSON``, and a version skew silently changes rendering
(design.md, "Fabric version skew" risk).

Two sources, one expected value each:

* ``render_service/package.json`` pins the service dependency (e.g.
  ``"fabric": "^6.9.1"``). A range prefix (^, ~) is stripped; the pinned
  numeric part must equal the bundle version.
* ``social_image_creator/static/lib/fabric/index.min.js`` carries the
  version as a string literal (``const x = "6.9.1"`` in the 6.9.x
  builds). If a future bundle drops that literal, add a marker comment on
  the first line instead, which this check reads first::

      /* fabric-version: 6.9.1 */

Usage:
    check_fabric_sync.py [--repo PATH]

Exit codes:
    0: versions match
    1: mismatch or version not extractable
    2: usage or environment error
"""

import argparse
import json
import os
import re
import subprocess
import sys

PACKAGE_JSON = 'render_service/package.json'
BUNDLE_JS = 'social_image_creator/static/lib/fabric/index.min.js'
MARKER_RE = re.compile(r'/\*\s*fabric-version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*\*/')
LITERAL_RE = re.compile(r'"([0-9]+\.[0-9]+\.[0-9]+)"')
RANGE_PREFIX_RE = re.compile(r'^[\^~<>=\s]+')


def find_repo_root(start):
    try:
        out = subprocess.run(
            ['git', '-C', start, 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def package_version(repo):
    """Return the Fabric version pinned in the render service package.json."""
    path = os.path.join(repo, PACKAGE_JSON)
    with open(path, 'r', encoding='utf-8') as handle:
        data = json.load(handle)
    spec = data.get('dependencies', {}).get('fabric')
    if not spec:
        raise ValueError('no fabric dependency in %s' % path)
    return RANGE_PREFIX_RE.sub('', spec).strip()


def bundle_version(repo):
    """Return the Fabric version baked into the editor bundle, or None."""
    path = os.path.join(repo, BUNDLE_JS)
    with open(path, 'r', encoding='utf-8', errors='replace') as handle:
        head = handle.readline()
        match = MARKER_RE.search(head)
        if match:
            return match.group(1)
        handle.seek(0)
        body = handle.read()
    # The 6.9.x minified build carries exactly one three-part version
    # literal. Refuse to guess when several appear.
    versions = LITERAL_RE.findall(body)
    unique = sorted(set(versions))
    if len(unique) == 1:
        return unique[0]
    if len(unique) > 1:
        raise ValueError(
            'several version literals %s in %s; add a fabric-version '
            'marker comment on the first line instead' % (unique, path))
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Check editor bundle Fabric version vs render service pin.')
    parser.add_argument('--repo', default=None,
                        help='repository root (defaults to the repo holding this script)')
    args = parser.parse_args(argv)

    repo = args.repo or find_repo_root(os.path.dirname(os.path.abspath(__file__)))
    if repo is None:
        print('ERROR: not inside a git repository', file=sys.stderr)
        return 2

    print('fabric version sync check')
    print('=' * 72)

    try:
        pkg = package_version(repo)
    except (OSError, ValueError) as e:
        print('FAILED: cannot read the service pin: %s' % e)
        return 1
    print('  %-28s %s' % (PACKAGE_JSON, pkg))

    try:
        bundle = bundle_version(repo)
    except (OSError, ValueError) as e:
        print('FAILED: cannot read the bundle version: %s' % e)
        return 1
    if bundle is None:
        print('FAILED: no version literal and no fabric-version marker in %s'
              % BUNDLE_JS)
        return 1
    print('  %-28s %s' % (BUNDLE_JS, bundle))

    if pkg != bundle:
        print('')
        print('FAILED: Fabric version skew: editor bundle is %s, render '
              'service pins %s.' % (bundle, pkg))
        print('Scene JSON is not portable across Fabric versions; bump both '
              'in the same commit.')
        return 1

    print('')
    print('OK: editor bundle and render service both use Fabric %s.' % pkg)
    return 0


if __name__ == '__main__':
    sys.exit(main())
