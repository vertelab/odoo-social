#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
"""Check that the editor chart library stays in parity with the render service copy.

Design D3 (openspec/changes/editor-grid-dynamic-elements): chart elements are
generated from ONE pure data-to-SVG module. render_service/chart_spec.mjs is
the reference implementation; the editor vendors a copy at
social_image_creator/static/src/js/dialog/chart_library.js. If the two drift,
editor preview and server render diverge silently, so this check fails the
build the same way check_fabric_sync.py does.

Both files must export the same functions:

    chartSpecToSvg(spec)    -> SVG string
    substituteChartSpec(spec, bindings) -> new spec

The check runs node once with an inline ESM script that imports both modules
and compares their outputs on a shared fixture set (all six chart types,
tokens, non-numeric cells, markup injection attempts). Any divergence exits 1.

Usage:
    check_chart_sync.py [--repo PATH]

Exit codes:
    0: editor copy absent (SKIP, reported) or both copies in parity
    1: divergence, or the editor copy does not export the expected functions
    2: usage or environment error (node missing, service module broken)
"""

import argparse
import os
import subprocess
import sys

SERVICE_MODULE = 'render_service/chart_spec.mjs'
EDITOR_MODULE = 'social_image_creator/static/src/js/dialog/chart_library.js'

# Inline ESM program: import both copies, run the fixture set, exit non-zero
# on any divergence. Kept dependency-free so it runs on plain node.
NODE_CHECK_PROGRAM = r"""
import * as service from '%(service_url)s'
import * as editor from '%(editor_url)s'

const failures = []

function compare(label, a, b) {
    if (a !== b) {
        failures.push(label)
        console.error('DIVERGENCE in ' + label)
        console.error('  service: ' + JSON.stringify(a))
        console.error('  editor:  ' + JSON.stringify(b))
    }
}

for (const name of ['chartSpecToSvg', 'substituteChartSpec']) {
    if (typeof editor[name] !== 'function') {
        console.error('EDITOR MODULE MISSING EXPORT: ' + name)
        process.exit(1)
    }
    if (typeof service[name] !== 'function') {
        console.error('SERVICE MODULE MISSING EXPORT: ' + name)
        process.exit(1)
    }
}

const FIXTURES = [
    {
        name: 'bar-v two series',
        spec: {
            version: 1, type: 'bar-v', title: 'Forsaljning',
            categories: ['Jan', 'Feb', 'Mar'],
            series: [
                { name: 'Stolar', values: [10, 20, 30] },
                { name: 'Bord', values: ['5', 15, '25'] },
            ],
            options: { width: 480, height: 320 },
        },
    },
    {
        name: 'bar-h with zero and bad cells',
        spec: {
            version: 1, type: 'bar-h', title: '',
            categories: ['A', 'B <script>'],
            series: [{ name: 'S', values: ['abc', 0] }],
            options: { width: 320, height: 240 },
        },
    },
    {
        name: 'line empty series',
        spec: {
            version: 1, type: 'line', title: 'Trender',
            categories: [],
            series: [],
            options: { width: 400, height: 300 },
        },
    },
    {
        name: 'area single point',
        spec: {
            version: 1, type: 'area', title: 'En punkt',
            categories: ['Enda'],
            series: [{ name: 'S', values: [42] }],
            options: { width: 300, height: 200, colors: ['#123456'] },
        },
    },
    {
        name: 'pie',
        spec: {
            version: 1, type: 'pie', title: 'Andel',
            categories: ['Ett & "tv\xe5"', 'Tre'],
            series: [{ name: 'S', values: [1, 3] }],
            options: { width: 400, height: 400 },
        },
    },
    {
        name: 'donut zero total',
        spec: {
            version: 1, type: 'donut', title: 'Tom',
            categories: ['A'],
            series: [{ name: 'S', values: [0] }],
            options: { width: 200, height: 200 },
        },
    },
    {
        name: 'default options',
        spec: {
            version: 1, type: 'bar-v',
            categories: ['A'],
            series: [{ name: 'S', values: [1] }],
        },
    },
]

const BINDINGS = { 'product.weight': '12.5', 'categ.name': 'Kok', 'missing': '' }

for (const fx of FIXTURES) {
    const spec = JSON.parse(JSON.stringify(fx.spec))
    compare(fx.name + ': chartSpecToSvg',
        service.chartSpecToSvg(spec), editor.chartSpecToSvg(spec))
    compare(fx.name + ': substituteChartSpec',
        JSON.stringify(service.substituteChartSpec(spec, BINDINGS)),
        JSON.stringify(editor.substituteChartSpec(spec, BINDINGS)))
}

// Token-bound cells on top of every fixture shape.
const bound = {
    version: 1, type: 'bar-v', title: '{{categ.name}}',
    categories: ['{{categ.name}}', 'Statisk'],
    series: [{ name: 'Vikt', values: ['{{product.weight}}', '{{missing}}'] }],
    options: { width: 320, height: 240 },
}
compare('bound: substituteChartSpec',
    JSON.stringify(service.substituteChartSpec(bound, BINDINGS)),
    JSON.stringify(editor.substituteChartSpec(bound, BINDINGS)))
compare('bound: chartSpecToSvg after substitution',
    service.chartSpecToSvg(service.substituteChartSpec(bound, BINDINGS)),
    editor.chartSpecToSvg(editor.substituteChartSpec(bound, BINDINGS)))

if (failures.length > 0) {
    console.error(failures.length + ' divergence(s) found')
    process.exit(1)
}
console.log('PARITY OK: ' + (FIXTURES.length + 1) + ' fixture(s) identical')
"""


def find_repo_root(start):
    try:
        out = subprocess.run(
            ['git', '-C', start, 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def path_to_file_url(path):
    return 'file://' + os.path.abspath(path)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Check editor chart library parity with the render service copy.')
    parser.add_argument('--repo', default=None,
                        help='repository root (defaults to the repo holding this script)')
    args = parser.parse_args(argv)

    repo = args.repo or find_repo_root(os.path.dirname(os.path.abspath(__file__)))
    if repo is None:
        print('ERROR: not inside a git repository', file=sys.stderr)
        return 2

    service_path = os.path.join(repo, SERVICE_MODULE)
    editor_path = os.path.join(repo, EDITOR_MODULE)

    print('chart library sync check')
    print('=' * 72)

    if not os.path.isfile(service_path):
        print('FAILED: service module missing: %s' % SERVICE_MODULE)
        return 2
    print('  %-28s %s' % ('service:', SERVICE_MODULE))

    if not os.path.isfile(editor_path):
        print('  %-28s %s' % ('editor copy:', 'not present yet'))
        print('')
        print('SKIP: %s does not exist; the editor copy lands in a later wave.'
              % EDITOR_MODULE)
        print('Nothing to compare, treating as passed. Re-run once the file exists.')
        return 0
    print('  %-28s %s' % ('editor copy:', EDITOR_MODULE))

    program = NODE_CHECK_PROGRAM % {
        'service_url': path_to_file_url(service_path),
        'editor_url': path_to_file_url(editor_path),
    }
    try:
        out = subprocess.run(
            ['node', '--input-type=module', '--eval', program],
            capture_output=True, text=True, cwd=repo,
        )
    except FileNotFoundError:
        print('ERROR: node is not available on PATH', file=sys.stderr)
        return 2

    sys.stdout.write(out.stdout)
    if out.returncode != 0:
        sys.stderr.write(out.stderr)
        print('')
        print('FAILED: chart library drift between %s and %s.'
              % (EDITOR_MODULE, SERVICE_MODULE))
        print('Both sides must stay byte-parity identical (design D3); apply the')
        print('change to both copies in the same commit.')
        return 1

    print('')
    print('OK: editor chart library and render service are in parity.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
