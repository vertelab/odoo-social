#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

"""Standalone checks for social_image_creator binding resolution.

The binding helpers in social_image_creator/models/social_image_binding.py
are deliberately free of Odoo imports, so this script exercises them with
plain ``python3`` and a fake record object (no ORM, no database):

    python3 scripts/check_social_image_binding.py

Exit code 0 when every check passes, 1 otherwise.
"""

import importlib.util
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(
    REPO_ROOT, 'social_image_creator', 'models', 'social_image_binding.py')

spec = importlib.util.spec_from_file_location('social_image_binding', MODULE_PATH)
binding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(binding)

FAILURES = 0


def check(name, actual, expected):
    global FAILURES
    if actual != expected:
        FAILURES += 1
        print('FAIL %s: got %r, want %r' % (name, actual, expected))
    else:
        print('ok %s' % name)


class FakeField:
    def __init__(self, ftype, compute=False):
        self.type = ftype
        self.compute = compute


class FakeRecord:
    """Minimal stand-in for an Odoo recordset."""

    def __init__(self, name, data, fields):
        self._name = name
        self._data = data
        self._fields = fields

    def __getitem__(self, key):
        if isinstance(key, slice):
            # Mirror a single-record Odoo recordset: [:1] stays addressable.
            start = key.start or 0
            return FakeRecordList([self] if start == 0 else [], self._fields)
        return self._data[key]

    def __bool__(self):
        return True

    @property
    def display_name(self):
        return self._data.get('display_name') or self._data.get('name', '')


class FakeRecordList(list):
    """Stand-in for an x2many recordset: slices stay a FakeRecordList and
    keep the model's fields, mirroring real Odoo recordsets."""

    def __init__(self, items=(), fields=None):
        super().__init__(items)
        if fields is None and items:
            fields = getattr(items[0], '_fields', None)
        self._fields = fields or {}
        self._name = getattr(items[0], '_name', '?') if items else '?'

    def __getitem__(self, item):
        if isinstance(item, str):
            return self[0][item]
        result = super().__getitem__(item)
        if isinstance(item, slice):
            return FakeRecordList(result, self._fields)
        return result

    @property
    def display_name(self):
        return self[0].display_name if self else ''


PNG_1PX = (b'\x89PNG\r\n\x1a\n' + b'\x00' * 32)
JPEG_1PX = (b'\xff\xd8\xff\xe0' + b'\x00' * 32)

PRODUCT_FIELDS = {
    'name': FakeField('char'),
    'description': FakeField('text'),
    'list_price': FakeField('float'),
    'is_new': FakeField('boolean'),
    'sale_ok': FakeField('boolean'),
    'sequence': FakeField('integer'),
    'image_1920': FakeField('binary'),
    'raw_blob': FakeField('binary'),
    'categ_id': FakeField('many2one'),
    'tag_ids': FakeField('many2many'),
    'line_ids': FakeField('one2many'),
    'computed_rel': FakeField('many2one', compute=True),
}
CATEG_FIELDS = {
    'name': FakeField('char'),
    'display_name': FakeField('char'),
}

CHAIR_CATEGORY = FakeRecord('product.category', {'name': 'Chairs'}, CATEG_FIELDS)
TAG_A = FakeRecord('product.tag', {'name': 'Sale'}, {'name': FakeField('char')})

PRODUCT = FakeRecord('product.product', {
    'name': 'Stol\nmed nackstöd',
    'description': 'En fin stol',
    'list_price': 1295.5,
    'is_new': True,
    'sale_ok': False,
    'sequence': 7,
    'image_1920': PNG_1PX,
    'raw_blob': b'\x01\x02\x03\x04',
    'categ_id': CHAIR_CATEGORY,
    'tag_ids': FakeRecordList([TAG_A]),
    'computed_rel': CHAIR_CATEGORY,
}, PRODUCT_FIELDS)

SCENE = {
    'version': '6.9.1',
    'objects': [
        {'type': 'textbox', 'text': '{{name|upper}}'},
        {'type': 'textbox', 'text': '{{categ_id.name}}'},
        {'type': 'textbox', 'text': '{{list_price}} kr'},
        {'type': 'image', 'src': '/web/image/1', '_dataBinding': {'field': 'image_1920'}},
        {'type': 'rect', '_hideIfEmpty': {'field': 'sale_ok'}},
        {'type': 'textbox', 'text': '{{tag_ids.name}}'},
    ],
}

# --- iter_tokens -----------------------------------------------------------
check('token plain', list(binding.iter_tokens('Hej {{name}}!')),
      [('name', [])])
check('token pipes', list(binding.iter_tokens('{{name|upper|trim}}')),
      [('name', ['upper', 'trim'])])
check('token dotted + pipe', list(binding.iter_tokens('{{categ_id.name|title}}')),
      [('categ_id.name', ['title'])])
check('token whitespace tolerated',
      list(binding.iter_tokens('{{  name  | upper }}')), [('name', ['upper'])])

# --- collect_scene_fields --------------------------------------------------
check('collect scene fields', binding.collect_scene_fields(SCENE),
      ['name', 'categ_id.name', 'list_price', 'image_1920', 'sale_ok',
       'tag_ids.name'])

# --- resolve_field_path ----------------------------------------------------
check('resolve char', binding.resolve_field_path(PRODUCT, 'name'),
      'Stol\nmed nackstöd')
check('resolve float', binding.resolve_field_path(PRODUCT, 'list_price'), 1295.5)
check('resolve relation leaf',
      binding.resolve_field_path(PRODUCT, 'categ_id.name'), 'Chairs')
check('resolve x2many hop',
      binding.resolve_field_path(PRODUCT, 'tag_ids.name'), 'Sale')

try:
    binding.resolve_field_path(PRODUCT, 'does_not_exist')
    check('unknown field raises', 'no error', 'BindingError')
except binding.BindingError as e:
    check('unknown field raises', 'ok', 'ok')
    check('unknown field names token', "'does_not_exist'" in str(e), True)

try:
    binding.resolve_field_path(PRODUCT, 'name.foo')
    check('non-relation hop raises', 'no error', 'BindingError')
except binding.BindingError as e:
    check('non-relation hop raises', 'ok', 'ok')
    check('non-relation hop names token', "'name.foo'" in str(e), True)

try:
    binding.resolve_field_path(PRODUCT, 'computed_rel.name')
    check('computed relation raises', 'no error', 'BindingError')
except binding.BindingError:
    check('computed relation raises', 'ok', 'ok')

# --- format_binding_value --------------------------------------------------
check('format None', binding.format_binding_value(None), '')
check('format False', binding.format_binding_value(False), '')
check('format bool true', binding.format_binding_value(True), 'True')
check('format int', binding.format_binding_value(7), '7')
import datetime
check('format date', binding.format_binding_value(datetime.date(2026, 9, 14)),
      '2026-09-14')
check('format png data url',
      binding.format_binding_value(PNG_1PX).startswith('data:image/png;base64,'),
      True)
check('format jpeg sniffed',
      binding.format_binding_value(JPEG_1PX).startswith('data:image/jpeg;base64,'),
      True)
check('format unknown binary',
      binding.format_binding_value(b'\x01\x02').startswith(
          'data:application/octet-stream;base64,'),
      True)
check('format m2o leaf display_name',
      binding.format_binding_value(CHAIR_CATEGORY), 'Chairs')
check('format x2many leaf first display_name',
      binding.format_binding_value(FakeRecordList([TAG_A])), 'Sale')
check('format multiline kept',
      binding.format_binding_value('Stol\nmed nackstöd'), 'Stol\nmed nackstöd')

# --- build_bindings --------------------------------------------------------
expected_bindings = {
    'name': 'Stol\nmed nackstöd',
    'categ_id.name': 'Chairs',
    'list_price': '1295.5',
    'image_1920': binding.format_binding_value(PNG_1PX),
    'sale_ok': '',
    'tag_ids.name': 'Sale',
}
check('build_bindings', binding.build_bindings(PRODUCT, SCENE),
      expected_bindings)

# --- check_required_layers -------------------------------------------------
REQUIRED_SCENE = {
    'objects': [
        {'type': 'image', '_layerName': 'Hero image',
         '_dataBinding': {'field': 'image_1920'},
         '_required': {'field': 'image_1920'}},
        {'type': 'textbox', '_required': {'field': 'name'}},
    ]
}
try:
    binding.check_required_layers(
        REQUIRED_SCENE,
        {'image_1920': '', 'name': 'Stol\nmed nackstöd'})
    check('required empty raises', 'no error', 'BindingError')
except binding.BindingError as e:
    check('required empty raises', 'ok', 'ok')
    check('required names layer', 'Hero image' in str(e), True)
    check('required names field', "'image_1920'" in str(e), True)

check('required satisfied passes',
      binding.check_required_layers(
          REQUIRED_SCENE,
          {'image_1920': 'data:image/png;base64,AAA', 'name': 'x'}),
      None)

if FAILURES:
    print('\n%d check(s) FAILED' % FAILURES)
    sys.exit(1)
print('\nALL binding CHECKS PASSED')
